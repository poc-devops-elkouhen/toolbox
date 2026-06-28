#!/usr/bin/env python3
"""Clone the GitOps repo, apply changes, push a branch, open a GitLab MR."""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def _gitlab_api(
    gitlab_url: str,
    path: str,
    method: str = "GET",
    data: dict | None = None,
    token: str = "",
) -> tuple[int, dict]:
    url = f"{gitlab_url}/api/v4/{path}"
    headers: dict[str, str] = {}
    body = None
    if token:
        headers["PRIVATE-TOKEN"] = token
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _auth_url(repo_url: str, token: str) -> str:
    """Embed oauth2 token into an HTTP(S) git URL."""
    if not token or not repo_url.startswith(("http://", "https://")):
        return repo_url
    parsed = urllib.parse.urlparse(repo_url)
    netloc = f"oauth2:{token}@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urllib.parse.urlunparse(parsed._replace(netloc=netloc))


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo)] + list(args), check=True, capture_output=True)


def _render_appset(repo_root: Path) -> str:
    """Render AppProjects + ApplicationSet YAML from inventory in repo_root."""
    import yaml
    from platform_inventory import load_inventory

    apps_file = repo_root / "argocd/apps.yaml"
    inventory = load_inventory(apps_file)
    apps = inventory["apps"]

    projects = [
        {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "AppProject",
            "metadata": {"name": app["argocd"]["project"], "namespace": "argocd"},
            "spec": {
                "sourceRepos": app["argocd"]["sourceRepos"],
                "destinations": app["argocd"]["destinations"],
                "clusterResourceWhitelist": [{"group": "", "kind": "Namespace"}],
            },
        }
        for app in apps
    ]

    elements = [
        {
            "app": app["name"],
            "project": app["argocd"]["project"],
            "env": env["name"],
            "branch": env["branch"],
            "namespace": env["namespace"],
            "repoURL": app["manifests"]["argocdRepoURL"],
            "path": app["manifests"]["path"],
        }
        for app in apps
        for env in app["environments"]
    ]

    applicationset = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "ApplicationSet",
        "metadata": {"name": "apps", "namespace": "argocd"},
        "spec": {
            "goTemplate": True,
            "goTemplateOptions": ["missingkey=error"],
            "generators": [{"list": {"elements": elements}}],
            "template": {
                "metadata": {
                    "name": "{{ .app }}-{{ .env }}",
                    "namespace": "argocd",
                    "finalizers": ["resources-finalizer.argocd.argoproj.io"],
                },
                "spec": {
                    "project": "{{ .project }}",
                    "source": {
                        "repoURL": "{{ .repoURL }}",
                        "targetRevision": "{{ .branch }}",
                        "path": "{{ .path }}",
                    },
                    "destination": {
                        "server": "https://kubernetes.default.svc",
                        "namespace": "{{ .namespace }}",
                    },
                    "syncPolicy": {
                        "automated": {"prune": True, "selfHeal": True},
                        "syncOptions": ["CreateNamespace=true"],
                    },
                },
            },
        },
    }

    header = "# Généré par scripts/render-argocd-apps.py depuis argocd/apps.yaml + argocd/apps/*.yaml -- ne pas éditer à la main."
    parts = [header]
    for i, doc in enumerate(projects + [applicationset]):
        if i > 0:
            parts.append("---")
        rendered = yaml.dump(doc, allow_unicode=True, sort_keys=False, default_flow_style=False)
        parts.append(rendered.lstrip("---\n").lstrip().rstrip())
    return "\n".join(parts) + "\n"


def _push_branch_and_create_mr(repo_root: Path, branch: str, commit_msg: str, mr_title: str) -> str:
    platform_url = os.environ["PLATFORM_REPO_URL"]
    gitlab_url = os.environ.get("GITLAB_URL", "http://gitlab.192.168.33.100.nip.io")
    token = os.environ.get("GITLAB_TOKEN", "")
    base_branch = os.environ.get("PLATFORM_BRANCH", "main")

    _git(repo_root, "config", "user.email", "toolbox@local")
    _git(repo_root, "config", "user.name", "DevOps Toolbox")
    _git(repo_root, "checkout", "-b", branch)
    _git(repo_root, "add", "-A")
    _git(repo_root, "commit", "-m", commit_msg)

    push_url = _auth_url(platform_url, token)
    subprocess.run(
        ["git", "-C", str(repo_root), "push", push_url, f"HEAD:{branch}"],
        check=True,
        capture_output=True,
    )

    parsed = urllib.parse.urlparse(platform_url)
    project_path = parsed.path.lstrip("/").removesuffix(".git")
    project_path_encoded = urllib.parse.quote(project_path, safe="")

    status, mr = _gitlab_api(
        gitlab_url,
        f"projects/{project_path_encoded}/merge_requests",
        method="POST",
        token=token,
        data={
            "source_branch": branch,
            "target_branch": base_branch,
            "title": mr_title,
            "remove_source_branch": True,
        },
    )
    if 200 <= status < 300:
        return mr.get("web_url", f"{gitlab_url}/{project_path}/-/merge_requests")
    raise RuntimeError(f"Échec de création de la MR (HTTP {status}): {mr}")


def create_mr_for_init(argv: list[str]) -> None:
    """Clone GitOps repo, run init logic, render appset, open a GitLab MR."""
    from init_projects.config import load_config
    from init_projects.app_model import build_app
    from init_projects.inventory import write_app_file
    from platform_inventory import platform_repo_root

    config = load_config(argv)  # triggers clone via platform_repo_root()
    app = build_app(config)
    action = write_app_file(config.apps_dir, config.app_name, app)
    print(f"Application '{config.app_name}' {action} dans {config.apps_dir / (config.app_name + '.yaml')}")
    print(f"Services: {', '.join(config.services)}")
    print(f"Code:      {config.code_ref}")
    print(f"Manifests: {config.iac_ref}:{config.kustomize_path}")

    repo_root = platform_repo_root()  # returns the cached tmpdir
    appset_path = repo_root / "argocd/managed/apps-appset.yaml"
    appset_path.parent.mkdir(parents=True, exist_ok=True)
    appset_path.write_text(_render_appset(repo_root))

    branch = f"toolbox/add-{config.app_name}"
    mr_url = _push_branch_and_create_mr(
        repo_root,
        branch=branch,
        commit_msg=f"feat(platform): onboard {config.app_name}",
        mr_title=f"[toolbox] Onboard {config.app_name}",
    )
    print(f"\nMR créée : {mr_url}")


def create_mr_for_delete(argv: list[str]) -> None:
    """Clone GitOps repo, remove app inventory, render appset, open a GitLab MR."""
    from delete_projects import delete_project
    from init_projects.common import slug
    from platform_inventory import platform_repo_root

    app_name = _delete_app_name_from_argv(argv)
    delete_project(argv)

    repo_root = platform_repo_root()  # returns the cached tmpdir
    appset_path = repo_root / "argocd/managed/apps-appset.yaml"
    appset_path.parent.mkdir(parents=True, exist_ok=True)
    appset_path.write_text(_render_appset(repo_root))

    branch = f"toolbox/delete-{slug(app_name)}"
    mr_url = _push_branch_and_create_mr(
        repo_root,
        branch=branch,
        commit_msg=f"feat(platform): remove {slug(app_name)}",
        mr_title=f"[toolbox] Remove {slug(app_name)}",
    )
    print(f"\nMR créée : {mr_url}")


def _delete_app_name_from_argv(argv: list[str]) -> str:
    if len(argv) != 2:
        return ""
    return argv[1]
