#!/usr/bin/env python3
# Seed GitLab depuis l'inventaire argocd/apps.yaml + argocd/apps/*.yaml :
# - root/ci-templates, tagué en version immuable pour les includes CI ;
# - root/<app>-iac et root/<app>, dépôts manifests/code par app.
#   Source : sourceURL (clone HTTP) si présent dans l'inventaire, sinon chemin
#   local APPS_BASE_DIR/<localPath>. Le code reçoit en plus un .gitlab-ci.yml
#   généré depuis le template.
from __future__ import annotations

import atexit
import base64
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import yaml

from platform_inventory import load_inventory, platform_repo_root

GITLAB_NAMESPACE = os.environ.get("GITLAB_NAMESPACE", "gitlab")
GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.192.168.33.100.nip.io")
GITLAB_INSECURE_TLS = os.environ.get("GITLAB_INSECURE_TLS", "true").lower() not in ("0", "false", "no")
GITLAB_ROOT_NAMESPACE = os.environ.get("GITLAB_ROOT_NAMESPACE", "root")
GITLAB_REMOTE_NAME = os.environ.get("GITLAB_REMOTE_NAME", "gitlab")
REPO_ROOT = platform_repo_root()
APPS_FILE = Path(os.environ.get("APPS_FILE", REPO_ROOT / "argocd/apps.yaml"))
# Local app repos are siblings of the caller's directory, not of the (possibly
# cloned) platform repo. Default to REPO_ROOT for backward-compat with local mode.
APPS_BASE_DIR = Path(os.environ.get("APPS_BASE_DIR", str(REPO_ROOT))).resolve()
SIBLING_PROJECTS_DIR = Path(os.environ.get("SIBLING_PROJECTS_DIR", str(APPS_BASE_DIR.parent))).resolve()
SEED_SIBLING_PROJECTS = os.environ.get("SEED_SIBLING_PROJECTS", "false").lower() not in ("0", "false", "no")
SIBLING_PROJECTS_PUSH_ACCESS_LEVEL = int(os.environ.get("SIBLING_PROJECTS_PUSH_ACCESS_LEVEL", "40"))
inventory = load_inventory(APPS_FILE)
HTTPS_CONTEXT = None
GIT_SSL_CONFIG: list[str] = []


def yaml_value(dotted_key):
    obj = inventory
    for key in dotted_key.split("."):
        obj = obj[key]
    return obj


def _nested_value(data, dotted_key, default=None):
    obj = data
    for key in dotted_key.split("."):
        if not isinstance(obj, dict) or key not in obj:
            return default
        obj = obj[key]
    return obj


def _load_platform_config() -> tuple[dict, Path | None]:
    config_path = os.environ.get("PLATFORM_CONFIG")
    if not config_path:
        return {}, None

    path = Path(config_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        print(f"Config plateforme introuvable: {path}", file=sys.stderr)
        sys.exit(1)

    with path.open() as f:
        return yaml.safe_load(f) or {}, path


def config_value(dotted_key, default=None):
    return _nested_value(platform_config, dotted_key, default)


def inventory_value(dotted_key, default=None):
    return _nested_value(inventory, dotted_key, default)


platform_config, platform_config_path = _load_platform_config()

CI_TEMPLATE_PROJECT_PATH = (
    os.environ.get("CI_TEMPLATE_PROJECT_PATH")
    or config_value("platform.ciTemplate.projectPath")
    or inventory_value("ciTemplate.projectPath")
    or "root/ci-templates"
)
CI_TEMPLATE_PROJECT_NAME = (
    os.environ.get("CI_TEMPLATE_PROJECT_NAME")
    or config_value("platform.ciTemplate.projectName")
    or inventory_value("ciTemplate.projectName")
    or "ci-templates"
)
ci_template_source_dir = os.environ.get("CI_TEMPLATE_SOURCE_DIR")
ci_template_source_base = APPS_BASE_DIR
if not ci_template_source_dir:
    ci_template_source_dir = config_value("platform.ciTemplate.sourceDir")
    if ci_template_source_dir and platform_config_path:
        ci_template_source_base = platform_config_path.parent
if not ci_template_source_dir:
    ci_template_source_dir = inventory_value("ciTemplate.sourceDir") or "../ci-templates"
CI_TEMPLATE_SOURCE_DIR = Path(
    ci_template_source_dir
    if Path(ci_template_source_dir).is_absolute()
    else ci_template_source_base / ci_template_source_dir
)
CI_TEMPLATE_REF = (
    os.environ.get("CI_TEMPLATE_REF")
    or config_value("platform.ciTemplate.ref")
    or inventory_value("ciTemplate.ref")
    or "v0.11.1"
)
CI_TEMPLATE_FILE = (
    os.environ.get("CI_TEMPLATE_FILE")
    or config_value("platform.ciTemplate.file")
    or inventory_value("ciTemplate.file")
    or "/gitlab-ci.yml"
)
REGISTRY_HOST = os.environ.get("REGISTRY_HOST", "registry.registry.svc.cluster.local:5000")
INTERNAL_GITLAB_HOST = os.environ.get("INTERNAL_GITLAB_HOST") or yaml_value("gitlab.internalHost")


def _resolve_repo_dir(source_url: str | None, local_path: Path, label: str) -> Path:
    """Return a local Path to the repo for seeding.

    Uses source_url (full clone) when provided, otherwise expects the repo
    at local_path. Cloned tmpdirs are auto-deleted at process exit.
    """
    if source_url:
        tmpdir = Path(tempfile.mkdtemp(prefix="seed-repo-"))
        atexit.register(shutil.rmtree, tmpdir, ignore_errors=True)
        print(f"Clone de {label} depuis {source_url}...")
        result = subprocess.run(
            ["git", "clone", source_url, str(tmpdir)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            local_repo = _resolved_existing_git_dir(local_path)
            if local_repo:
                print(
                    f"Clone de {label} impossible depuis {source_url}, "
                    f"utilisation du dépôt local {local_repo}.",
                    file=sys.stderr,
                )
                return local_repo
            print(f"Échec du clone de {label}: {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
        return tmpdir

    local_repo = _resolved_existing_git_dir(local_path)
    if not local_repo:
        print(f"Dépôt git {label} introuvable: {local_path}", file=sys.stderr)
        sys.exit(1)
    return local_repo


def _resolved_existing_git_dir(path: Path) -> Path | None:
    resolved = path.resolve()
    if (resolved / ".git").is_dir():
        return resolved
    return None


def _canonical_repo_url(value: str) -> tuple[str, str, str] | None:
    parsed = urllib.parse.urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return None
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return parsed.scheme, parsed.netloc.lower(), path


def _is_target_gitlab_url(source_url: str | None, project_path: str) -> bool:
    if not source_url:
        return False
    source = _canonical_repo_url(source_url)
    target = _canonical_repo_url(f"{GITLAB_URL}/{project_path}.git")
    return source is not None and source == target


def handled_local_repo_dirs() -> set[Path]:
    """Return local repos already seeded by the inventory-specific flows."""
    handled = set()

    ci_template_dir = _resolved_existing_git_dir(CI_TEMPLATE_SOURCE_DIR)
    if ci_template_dir:
        handled.add(ci_template_dir)

    for app in inventory["apps"]:
        manifests = app["manifests"]
        if not manifests.get("sourceURL"):
            repo_dir = _resolved_existing_git_dir(APPS_BASE_DIR / manifests["localPath"])
            if repo_dir:
                handled.add(repo_dir)

        code = app["code"]
        if not code.get("sourceURL"):
            repo_dir = _resolved_existing_git_dir(APPS_BASE_DIR / code["localPath"])
            if repo_dir:
                handled.add(repo_dir)

    return handled


def handled_project_paths() -> set[str]:
    handled = {CI_TEMPLATE_PROJECT_PATH}
    for app in inventory["apps"]:
        handled.add(app["manifests"]["projectPath"])
        handled.add(app["code"]["projectPath"])
    return handled


def discover_sibling_repos(base_dir: Path) -> list[Path]:
    if not SEED_SIBLING_PROJECTS:
        print("Seed des projets frères désactivé (SEED_SIBLING_PROJECTS=false).")
        return []
    if not base_dir.is_dir():
        print(f"Dossier des projets frères introuvable: {base_dir}", file=sys.stderr)
        return []

    repos = []
    for child in sorted(base_dir.iterdir(), key=lambda p: p.name):
        if child.is_dir() and (child / ".git").is_dir():
            repos.append(child.resolve())
    return repos


def kube_secret_field(namespace, name, jsonpath):
    raw = subprocess.run(
        ["kubectl", "-n", namespace, "get", "secret", name, "-o", f"jsonpath={jsonpath}"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return base64.b64decode(raw).decode() if raw else ""


def configure_gitlab_ca():
    """Trust the GitLab chart CA for local HTTPS API and git operations."""
    global HTTPS_CONTEXT, GIT_SSL_CONFIG

    if GITLAB_INSECURE_TLS:
        print("TLS GitLab auto-signé: vérification désactivée (GITLAB_INSECURE_TLS=true).")
        HTTPS_CONTEXT = ssl._create_unverified_context()
        GIT_SSL_CONFIG = ["-c", "http.sslVerify=false"]
        return

    certs = []
    try:
        certs.append(kube_secret_field(
            GITLAB_NAMESPACE, "gitlab-wildcard-tls-ca", "{.data.cfssl_ca}"
        ))
    except subprocess.CalledProcessError:
        pass

    try:
        parsed = urllib.parse.urlparse(GITLAB_URL)
        host = parsed.hostname
        port = parsed.port or 443
        if parsed.scheme == "https" and host:
            certs.append(ssl.get_server_certificate((host, port)))
    except OSError:
        pass

    certs = [cert for cert in certs if cert]
    if not certs:
        return

    ca_file = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix="gitlab-ca-", suffix=".crt", delete=False
    )
    ca_file.write("\n".join(certs))
    ca_file.close()
    atexit.register(lambda: Path(ca_file.name).unlink(missing_ok=True))

    HTTPS_CONTEXT = ssl.create_default_context(cafile=ca_file.name)
    GIT_SSL_CONFIG = ["-c", f"http.sslCAInfo={ca_file.name}"]


def http(url, method="GET", data=None, token=None):
    headers = {}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=HTTPS_CONTEXT) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, {}


def encode_path(value):
    return urllib.parse.quote(value, safe="")


def ensure_project(project_path, project_name):
    """Crée le projet s'il n'existe pas. Retourne (empty_repo, project_id)."""
    status, project = http(
        f"{GITLAB_URL}/api/v4/projects/{encode_path(project_path)}",
        token=bearer_token,
    )
    if status == 200 and project.get("id"):
        if project.get("path_with_namespace") != project_path:
            if project.get("marked_for_deletion_at"):
                purge_deleted_project(project["id"], project_path, project["path_with_namespace"])
            else:
                print(
                    f"Projet inattendu pour '{project_path}': "
                    f"{project.get('path_with_namespace')}",
                    file=sys.stderr,
                )
                sys.exit(1)
        else:
            return project.get("empty_repo") is True, project["id"]

    status, project = http(
        f"{GITLAB_URL}/api/v4/projects/{encode_path(project_path)}",
        token=bearer_token,
    )
    if status == 200 and project.get("id"):
        return project.get("empty_repo") is True, project["id"]

    print(f"Projet '{project_path}' absent, création...", file=sys.stderr)
    status, project = http(
        f"{GITLAB_URL}/api/v4/projects",
        method="POST",
        token=bearer_token,
        data={
            "name": project_name,
            "path": project_path.rsplit("/", 1)[-1],
            "visibility": "private",
            "initialize_with_readme": "false",
        },
    )
    if not (200 <= status < 300) or not project.get("id"):
        print(f"Création du projet '{project_path}' impossible (HTTP {status}).", file=sys.stderr)
        sys.exit(1)
    return True, project["id"]


def purge_deleted_project(project_id, project_path, deletion_path):
    print(f"Projet '{project_path}' marqué pour suppression, purge définitive...", file=sys.stderr)
    http(
        f"{GITLAB_URL}/api/v4/projects/{project_id}",
        method="DELETE",
        token=bearer_token,
        data={
            "permanently_remove": "true",
            "full_path": deletion_path,
        },
    )
    for _ in range(30):
        status, _ = http(
            f"{GITLAB_URL}/api/v4/projects/{encode_path(project_path)}",
            token=bearer_token,
        )
        if status == 404:
            return
        time.sleep(1)
    print(f"Le projet '{project_path}' reste visible après purge.", file=sys.stderr)
    sys.exit(1)


def seed_project_from_dir(project_path, source_dir):
    """Pousse un snapshot (sans historique) d'un répertoire local vers GitLab."""
    print(f"Poussée du contenu initial de '{source_dir}' vers '{project_path}'...")
    gitlab_scheme, gitlab_host = GITLAB_URL.split("://", 1)
    encoded_password = urllib.parse.quote(root_password, safe="")
    remote_url = f"{gitlab_scheme}://root:{encoded_password}@{gitlab_host}/{project_path}.git"

    with tempfile.TemporaryDirectory() as workdir:
        shutil.copytree(source_dir, workdir, dirs_exist_ok=True)
        shutil.rmtree(os.path.join(workdir, ".venv"), ignore_errors=True)
        shutil.rmtree(os.path.join(workdir, ".git"), ignore_errors=True)
        subprocess.run(["git", "-C", workdir, "init", "-q", "-b", "main"], check=True)
        subprocess.run(["git", "-C", workdir, "config", "user.email", "bootstrap@gitlab.local"], check=True)
        subprocess.run(["git", "-C", workdir, "config", "user.name", "GitLab Bootstrap"], check=True)
        subprocess.run(["git", "-C", workdir, "add", "-A"], check=True)
        subprocess.run(["git", "-C", workdir, "commit", "-q", "-m", f"chore: seed initial du projet {project_path}"], check=True)
        subprocess.run(["git", "-C", workdir, "remote", "add", "origin", remote_url], check=True)
        subprocess.run(["git", "-C", workdir, *GIT_SSL_CONFIG, "push", "-q", "origin", "main"], check=True)

    print(f"Contenu initial poussé sur 'main' de '{project_path}'.")


def seed_project_from_repo(project_path, repo_dir, branches_to_push=None):
    """Pousse l'historique git réel d'un dépôt local vers GitLab via un remote nommé dédié.

    Préserve l'historique de développement. Le token passe par un header HTTP
    à la volée (-c http.extraheader) pour ne jamais persister le mot de passe
    root dans le remote du dépôt réel.
    """
    remote_url = f"{GITLAB_URL}/{project_path}.git"
    print(f"Poussée de l'historique de '{repo_dir}' vers '{project_path}' (remote '{GITLAB_REMOTE_NAME}')...")

    existing = subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "get-url", GITLAB_REMOTE_NAME],
        capture_output=True,
    )
    if existing.returncode == 0:
        subprocess.run(["git", "-C", str(repo_dir), "remote", "set-url", GITLAB_REMOTE_NAME, remote_url], check=True)
    else:
        subprocess.run(["git", "-C", str(repo_dir), "remote", "add", GITLAB_REMOTE_NAME, remote_url], check=True)

    branches = subprocess.run(
        ["git", "-C", str(repo_dir), "for-each-ref", "--format=%(refname:short)", "refs/heads/"],
        capture_output=True, text=True, check=True,
    ).stdout.strip().splitlines()
    if branches_to_push is not None:
        branches = [branch for branch in branches if branch in branches_to_push]

    for branch in branches:
        subprocess.run(
            ["git", "-C", str(repo_dir), *GIT_SSL_CONFIG, "-c", f"http.extraheader={git_auth_header}",
             "push", "-q", GITLAB_REMOTE_NAME, f"refs/heads/{branch}:refs/heads/{branch}"],
            check=True,
        )
    print(f"Historique de '{repo_dir}' poussé vers '{project_path}'.")


def seed_repo_branches_from_ref(project_path, repo_dir, source_ref, branches):
    """Pousse des branches d'environnement depuis une ref source."""
    print(f"Poussée des branches '{branches}' de '{repo_dir}' vers '{project_path}' depuis '{source_ref}'...")
    for branch in branches.split():
        subprocess.run(
            ["git", "-C", str(repo_dir), *GIT_SSL_CONFIG, "-c", f"http.extraheader={git_auth_header}",
             "push", "-q", GITLAB_REMOTE_NAME, f"+refs/heads/{source_ref}:refs/heads/{branch}"],
            check=True,
        )
    print(f"Branches '{branches}' disponibles dans '{project_path}'.")


def unprotect_main_branch(project_id):
    http(
        f"{GITLAB_URL}/api/v4/projects/{project_id}/protected_branches/main",
        method="DELETE",
        token=bearer_token,
    )


def configure_main_gate(project_id, push_access_level=0):
    print(f"Configuration du gate sur la branche 'main' (push_access_level={push_access_level}, merge réservé aux Maintainers)...")
    unprotect_main_branch(project_id)
    http(
        f"{GITLAB_URL}/api/v4/projects/{project_id}/protected_branches",
        method="POST",
        token=bearer_token,
        data={
            "name": "main",
            "push_access_level": push_access_level,
            "merge_access_level": 40,
            "allow_force_push": "false",
        },
    )
    http(
        f"{GITLAB_URL}/api/v4/projects/{project_id}",
        method="PUT",
        token=bearer_token,
        data={"only_allow_merge_if_all_discussions_are_resolved": "true"},
    )
    print("Gate configuré sur 'main'.")


def configure_protected_environment(project_id, environment_name, access_level=40):
    print(f"Configuration du protected environment '{environment_name}' (deploy réservé aux Maintainers)...")
    http(
        f"{GITLAB_URL}/api/v4/projects/{project_id}/protected_environments/{environment_name}",
        method="DELETE",
        token=bearer_token,
    )
    status, _ = http(
        f"{GITLAB_URL}/api/v4/projects/{project_id}/protected_environments",
        method="POST",
        token=bearer_token,
        data={
            "name": environment_name,
            "deploy_access_levels[][access_level]": access_level,
        },
    )
    if not (200 <= status < 300):
        print(f"Protected environment '{environment_name}' non configuré (HTTP {status})", file=sys.stderr)
        return
    print(f"Protected environment '{environment_name}' configuré.")


def ensure_repository_file(project_id, file_path, local_file, commit_message):
    encoded = encode_path(file_path)
    local_content = Path(local_file).read_bytes()
    raw_url = f"{GITLAB_URL}/api/v4/projects/{project_id}/repository/files/{encoded}/raw?ref=main"
    files_url = f"{GITLAB_URL}/api/v4/projects/{project_id}/repository/files/{encoded}"

    try:
        req = urllib.request.Request(raw_url, headers={"Authorization": f"Bearer {bearer_token}"})
        with urllib.request.urlopen(req, context=HTTPS_CONTEXT) as resp:
            current_content = resp.read()
        if current_content == local_content:
            print(f"Fichier '{file_path}' déjà à jour dans le projet {project_id}.")
            return
        print(f"Mise à jour de '{file_path}' dans le projet {project_id}...")
        http(files_url, method="PUT", token=bearer_token, data={
            "branch": "main",
            "commit_message": commit_message,
            "content": local_content.decode(),
        })
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        print(f"Création de '{file_path}' dans le projet {project_id}...")
        http(files_url, method="POST", token=bearer_token, data={
            "branch": "main",
            "commit_message": commit_message,
            "content": local_content.decode(),
        })


def ensure_repository_file_on_main_with_gate(project_id, file_path, local_file, commit_message, push_access_level):
    unprotect_main_branch(project_id)
    try:
        ensure_repository_file(project_id, file_path, local_file, commit_message)
    finally:
        configure_main_gate(project_id, push_access_level)


def ensure_project_tag(project_id, tag_name, ref):
    status, _ = http(
        f"{GITLAB_URL}/api/v4/projects/{project_id}/repository/tags/{tag_name}",
        token=bearer_token,
    )
    if status == 200:
        print(f"Tag '{tag_name}' déjà présent.")
        return
    print(f"Création du tag '{tag_name}' sur '{ref}'...")
    http(
        f"{GITLAB_URL}/api/v4/projects/{project_id}/repository/tags",
        method="POST",
        token=bearer_token,
        data={"tag_name": tag_name, "ref": ref},
    )


def ensure_push_token_variable(project_id, label):
    status, _ = http(
        f"{GITLAB_URL}/api/v4/projects/{project_id}/variables/GITLAB_PUSH_TOKEN",
        token=bearer_token,
    )
    if status == 200:
        print("Variable CI/CD 'GITLAB_PUSH_TOKEN' déjà présente.")
        return

    print(f"Variable CI/CD 'GITLAB_PUSH_TOKEN' absente pour '{label}', génération d'un token root et création...")
    _, user = http(f"{GITLAB_URL}/api/v4/user", token=bearer_token)
    root_user_id = user["id"]

    today = date.today()
    try:
        expires_at = today.replace(year=today.year + 1).strftime("%Y-%m-%d")
    except ValueError:
        expires_at = today.replace(year=today.year + 1, day=28).strftime("%Y-%m-%d")

    _, token_data = http(
        f"{GITLAB_URL}/api/v4/users/{root_user_id}/personal_access_tokens",
        method="POST",
        token=bearer_token,
        data={
            "name": f"ci-push-{label}",
            "scopes[]": "api",
            "expires_at": expires_at,
        },
    )
    http(
        f"{GITLAB_URL}/api/v4/projects/{project_id}/variables",
        method="POST",
        token=bearer_token,
        data={
            "key": "GITLAB_PUSH_TOKEN",
            "value": token_data.get("token", ""),
            "masked": "true",
            "protected": "false",
        },
    )
    print("Variable CI/CD 'GITLAB_PUSH_TOKEN' créée.")


def render_app_ci(app_name, services, showcase_service, internal_gitlab_host,
                  manifests_project_path, manifests_path, has_preprod, out_path):
    Path(out_path).write_text(
        f"include:\n"
        f"  - project: {CI_TEMPLATE_PROJECT_PATH}\n"
        f"    ref: {CI_TEMPLATE_REF}\n"
        f"    file: {CI_TEMPLATE_FILE}\n"
        f"\n"
        f"variables:\n"
        f"  APP_NAME: {app_name}\n"
        f"  # Monorepo multi-services (cf. AGENTS.md) : liste \"<service>=<image>\"\n"
        f"  # espacée, un sous-dossier + un Dockerfile par service. SERVICE_NAME reste\n"
        f"  # le service vitrine pour l'URL des environnements GitLab CI.\n"
        f'  SERVICES: "{services}"\n'
        f"  SERVICE_NAME: {showcase_service}\n"
        f"  INTERNAL_GITLAB_HOST: {internal_gitlab_host}\n"
        f"  MANIFESTS_PROJECT_PATH: {manifests_project_path}\n"
        f"  MANIFESTS_PATH: {manifests_path}\n"
        f'  HAS_PREPROD: "{has_preprod}"\n'
    )


# ── Authentification ────────────────────────────────────────────────────────

root_password = kube_secret_field(
    GITLAB_NAMESPACE, "gitlab-gitlab-initial-root-password", "{.data.password}"
)
configure_gitlab_ca()

_, auth = http(f"{GITLAB_URL}/oauth/token", method="POST", data={
    "grant_type": "password",
    "username": "root",
    "password": root_password,
})
bearer_token = auth.get("access_token", "")
if not bearer_token or bearer_token == "null":
    print("Échec d'authentification à l'API GitLab", file=sys.stderr)
    sys.exit(1)

git_credentials = base64.b64encode(f"root:{root_password}".encode()).decode()
git_auth_header = f"Authorization: Basic {git_credentials}"

# ── Template CI ─────────────────────────────────────────────────────────────

ci_template_empty_repo, ci_template_project_id = ensure_project(CI_TEMPLATE_PROJECT_PATH, CI_TEMPLATE_PROJECT_NAME)
if ci_template_empty_repo:
    seed_project_from_dir(CI_TEMPLATE_PROJECT_PATH, CI_TEMPLATE_SOURCE_DIR)
else:
    ensure_repository_file(
        ci_template_project_id,
        "gitlab-ci.yml",
        CI_TEMPLATE_SOURCE_DIR / "gitlab-ci.yml",
        "chore: update CI template",
    )
ensure_project_tag(ci_template_project_id, CI_TEMPLATE_REF, "main")

# ── Dépôts manifests ────────────────────────────────────────────────────────

for app in inventory["apps"]:
    manifests = app["manifests"]
    app_name = app["name"]
    manifests_source_url = manifests.get("sourceURL")
    if _is_target_gitlab_url(manifests_source_url, manifests["projectPath"]):
        manifests_source_url = None
    manifests_source_dir = _resolve_repo_dir(
        manifests_source_url,
        APPS_BASE_DIR / manifests["localPath"],
        f"manifests '{app_name}'",
    )

    unique_branches = list(dict.fromkeys(env["branch"] for env in app["environments"]))

    _, manifests_project_id = ensure_project(manifests["projectPath"], manifests["projectName"])
    unprotect_main_branch(manifests_project_id)
    seed_project_from_repo(manifests["projectPath"], manifests_source_dir, ["main"])
    seed_repo_branches_from_ref(manifests["projectPath"], manifests_source_dir, "main", " ".join(unique_branches))
    configure_main_gate(manifests_project_id, manifests["mainPushAccessLevel"])

# ── Dépôts code applicatif ──────────────────────────────────────────────────

for app in inventory["apps"]:
    code = app["code"]
    manifests = app["manifests"]
    app_name = app["name"]
    code_source_url = code.get("sourceURL")
    if _is_target_gitlab_url(code_source_url, code["projectPath"]):
        code_source_url = None
    code_source_dir = _resolve_repo_dir(
        code_source_url,
        APPS_BASE_DIR / code["localPath"],
        f"code '{app_name}'",
    )

    services_str = " ".join(f"{s['name']}={s['image']}" for s in app["services"])
    has_preprod_str = str(app["hasPreprod"]).lower()

    _, code_project_id = ensure_project(code["projectPath"], code["projectName"])
    ensure_push_token_variable(code_project_id, app_name)
    unprotect_main_branch(code_project_id)

    ci_file = code_source_dir / ".gitlab-ci.yml"
    render_app_ci(
        app_name, services_str, app["showcaseService"], INTERNAL_GITLAB_HOST,
        manifests["projectPath"], manifests["path"], has_preprod_str, ci_file,
    )

    git_status = subprocess.run(
        ["git", "-C", str(code_source_dir), "status", "--porcelain", "--", ".gitlab-ci.yml"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    if git_status:
        print(f"Commit du fichier CI GitLab dans le dépôt réel '{code_source_dir}'...")
        subprocess.run(["git", "-C", str(code_source_dir), "add", ".gitlab-ci.yml"], check=True)
        subprocess.run(["git", "-C", str(code_source_dir), "commit", "-q", "-m", "chore: configure CI GitLab"], check=True)

    seed_project_from_repo(code["projectPath"], code_source_dir)
    configure_main_gate(code_project_id, 0)
    configure_protected_environment(code_project_id, "prod", 40)

# ── Autres dépôts locaux du workspace ───────────────────────────────────────

already_seeded_dirs = handled_local_repo_dirs()
already_seeded_project_paths = handled_project_paths()
for repo_dir in discover_sibling_repos(SIBLING_PROJECTS_DIR):
    project_name = repo_dir.name
    project_path = f"{GITLAB_ROOT_NAMESPACE}/{project_name}"

    if repo_dir in already_seeded_dirs:
        print(f"Dépôt frère déjà couvert par l'inventaire, ignoré: {repo_dir}")
        continue
    if project_path in already_seeded_project_paths:
        print(f"Projet frère déjà couvert par l'inventaire, ignoré: {project_path}")
        continue

    _, project_id = ensure_project(project_path, project_name)
    unprotect_main_branch(project_id)
    seed_project_from_repo(project_path, repo_dir)
    configure_main_gate(project_id, SIBLING_PROJECTS_PUSH_ACCESS_LEVEL)
