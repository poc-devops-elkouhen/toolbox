from __future__ import annotations

import atexit
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

import yaml

_PLATFORM_DEFAULTS = {
    "domain": "192.168.33.100.nip.io",
    "repoURL": "https://github.com/poc-devops-elkouhen/platform-gitops.git",
    "targetRevision": "main",
    "registry": {"host": "registry.registry.svc.cluster.local:5000"},
}

_GITLAB_ROOT_NAMESPACE = "root"

_cached_root: Path | None = None


def platform_repo_root() -> Path:
    """Return the platform repo root.

    Clones PLATFORM_REPO_URL to a tmpdir on first call (MR mode).
    Falls back to PLATFORM_REPO_ROOT or CWD for local mode.
    Result is cached for the lifetime of the process.
    """
    global _cached_root
    if _cached_root is not None:
        return _cached_root
    url = os.environ.get("PLATFORM_REPO_URL")
    if url:
        _cached_root = _clone_to_tmp(url)
    else:
        _cached_root = Path(os.environ.get("PLATFORM_REPO_ROOT", Path.cwd())).resolve()
    return _cached_root


def _clone_to_tmp(url: str) -> Path:
    branch = os.environ.get("PLATFORM_BRANCH", "main")
    token = _repo_token(url)
    tmpdir = Path(tempfile.mkdtemp(prefix="platform-"))
    atexit.register(shutil.rmtree, tmpdir, ignore_errors=True)

    if token and url.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(url)
        username = "x-access-token" if parsed.hostname == "github.com" else "oauth2"
        netloc = f"{username}:{token}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        auth_url = urllib.parse.urlunparse(parsed._replace(netloc=netloc))
    else:
        auth_url = url

    subprocess.run(
        ["git", "clone", "--depth=1", "--branch", branch, auth_url, str(tmpdir)],
        check=True,
        capture_output=True,
    )
    return tmpdir


def _repo_token(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname == "github.com":
        return os.environ.get("GITHUB_TOKEN", "")
    return os.environ.get("GITLAB_TOKEN", "")


def default_apps_file() -> Path:
    return platform_repo_root() / "argocd/apps.yaml"


def platform_constants(inventory: dict) -> dict:
    return {**_PLATFORM_DEFAULTS, **inventory.get("platform", {})}


def load_inventory(apps_file: Path | None = None) -> dict:
    inventory_path = (apps_file or Path(os.environ.get("APPS_FILE", default_apps_file()))).resolve()
    with open(inventory_path) as f:
        inventory = yaml.safe_load(f) or {}

    inline_apps = inventory.get("apps")
    if inline_apps is not None:
        return inventory

    apps_dir_value = os.environ.get("APPS_DIR") or inventory.get("appsDir", "apps")
    apps_dir = Path(apps_dir_value)
    if not apps_dir.is_absolute():
        apps_dir = inventory_path.parent / apps_dir

    pconst = platform_constants(inventory)
    apps = []
    for app_file in sorted(apps_dir.glob("*.yaml")):
        with open(app_file) as f:
            app = yaml.safe_load(f) or {}
        if app:
            apps.append(_normalize_app(app, inventory, pconst))

    inventory["apps"] = apps
    return inventory


def _normalize_app(app: dict, inventory: dict, pconst: dict) -> dict:
    """Expand minimum-format app to full format by convention."""
    app = dict(app)
    name = app["name"]
    gitlab_host = inventory.get("gitlab", {}).get("internalHost", "")
    domain = pconst["domain"]
    registry_host = pconst["registry"]["host"]

    # services: list of strings → list of {name, image}
    raw_services = app.get("services", [])
    if raw_services and isinstance(raw_services[0], str):
        app["services"] = [
            {"name": s, "image": f"{registry_host}/{s}"}
            for s in raw_services
        ]

    # manifests: projectPath and projectName derived from name
    manifests = dict(app.get("manifests", {}))
    if "projectPath" not in manifests:
        manifests["projectPath"] = f"{_GITLAB_ROOT_NAMESPACE}/{name}-iac"
    if "projectName" not in manifests:
        manifests["projectName"] = f"{name}-iac"
    # repoURL (user-facing, external GitLab or source repo) derived if absent
    if "repoURL" not in manifests:
        manifests["repoURL"] = f"https://gitlab.{domain}/{manifests['projectPath']}.git"
    # argocdRepoURL: always the in-cluster GitLab URL, never stored in inventory
    manifests["argocdRepoURL"] = f"http://{gitlab_host}/{manifests['projectPath']}.git"
    if "localPath" not in manifests:
        manifests["localPath"] = f"../{name}-iac"
    if "mainPushAccessLevel" not in manifests:
        manifests["mainPushAccessLevel"] = 40
    if "argocdSecretName" not in manifests:
        manifests["argocdSecretName"] = f"gitlab-{name}-iac-repo"
    if "path" not in manifests:
        manifests["path"] = "k8s"
    app["manifests"] = manifests

    # code: repoURL (user-facing, external GitLab) and localPath derived if absent
    code = dict(app.get("code", {}))
    if "projectPath" not in code:
        code["projectPath"] = f"{_GITLAB_ROOT_NAMESPACE}/{name}"
    if "projectName" not in code:
        code["projectName"] = name
    if "repoURL" not in code:
        code["repoURL"] = f"https://gitlab.{domain}/{_GITLAB_ROOT_NAMESPACE}/{name}.git"
    if "localPath" not in code:
        code["localPath"] = f"../{name}"
    if "mainPushAccessLevel" not in code:
        code["mainPushAccessLevel"] = 0
    app["code"] = code

    # environments: derive if absent
    if "environments" not in app:
        env_specs = [("dev", "dev"), ("rec", "rec")]
        if app.get("hasPreprod"):
            env_specs.append(("preprod", "preprod"))
        env_specs.append(("prod", "main"))

        environments = []
        for env_name, branch in env_specs:
            suffix = "" if env_name == "prod" else f"-{env_name}"
            env_services = []
            for svc in app["services"]:
                svc_name = svc["name"] if isinstance(svc, dict) else svc
                host = (f"{svc_name}.{domain}" if env_name == "prod"
                        else f"{svc_name}-{env_name}.{domain}")
                env_services.append({
                    "name": svc_name,
                    "url": f"http://{host}",
                    "ingressHost": host,
                })
            environments.append({
                "name": env_name,
                "branch": branch,
                "namespace": f"{name}{suffix}",
                "services": env_services,
            })
        app["environments"] = environments

    # showcaseService: derive if absent
    if "showcaseService" not in app:
        svc_names = [s["name"] if isinstance(s, dict) else s for s in app["services"]]
        app["showcaseService"] = next(
            (s for s in svc_names if re.search(r"(gui|ui|web|front|frontend)$", s)),
            svc_names[0] if svc_names else "",
        )

    # argocd: derive if absent — uses argocdRepoURL for in-cluster access
    if "argocd" not in app:
        app["argocd"] = {
            "project": name,
            "sourceRepos": [manifests["argocdRepoURL"]],
            "destinations": [
                {
                    "server": "https://kubernetes.default.svc",
                    "namespace": f"{name}{'' if e['name'] == 'prod' else '-' + e['name']}",
                }
                for e in app["environments"]
            ],
        }

    return app
