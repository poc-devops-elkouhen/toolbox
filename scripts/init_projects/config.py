from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .common import env_bool, slug
from .discover import find_kustomize_path, services_from_code, services_from_kustomization
from .errors import fail
from platform_inventory import platform_repo_root

USAGE = """Usage:
  {script} <project-name>
  {script} <code-repo-url-ou-chemin> <iac-repo-url-ou-chemin>

Avec un nom de projet, les depots sont resolus depuis PROJECTS_DIR
(par defaut: repertoire courant en mode PLATFORM_REPO_URL,
sinon dossier parent du depot plateforme):
  PROJECTS_DIR/helloworld
  PROJECTS_DIR/helloworld-iac
"""


@dataclass(frozen=True)
class InitProjectConfig:
    repo_root: Path
    apps_file: Path
    code_ref: str
    iac_ref: str
    app_name: str
    kustomize_path: str
    services: list[str]
    has_preprod: bool
    apps_dir: Path


def load_config(argv: list[str]) -> InitProjectConfig:
    if len(argv) not in (2, 3):
        fail(USAGE.format(script=argv[0]))

    repo_root = platform_repo_root()
    apps_file = Path(os.environ.get("APPS_FILE", repo_root / "argocd/apps.yaml")).resolve()

    if len(argv) == 2:
        code_ref, iac_ref = _refs_from_project_arg(argv[1], repo_root)
    else:
        code_ref = argv[1]
        iac_ref = argv[2]
    code_dir = _resolve_repo(code_ref, "Depot code")
    iac_dir = _resolve_repo(iac_ref, "Depot IaC")

    app_name = slug(os.environ.get("APP_NAME") or _name_from_ref(code_ref))
    kustomize_path = os.environ.get("MANIFESTS_PATH") or find_kustomize_path(iac_dir)
    services = _discover_services(code_dir, iac_dir, kustomize_path)

    return InitProjectConfig(
        repo_root=repo_root,
        apps_file=apps_file,
        code_ref=code_ref,
        iac_ref=iac_ref,
        app_name=app_name,
        kustomize_path=kustomize_path,
        services=services,
        has_preprod=env_bool("HAS_PREPROD", True),
        apps_dir=_resolve_apps_dir(apps_file),
    )


def _is_git_url(s: str) -> bool:
    return s.startswith(("https://", "http://", "git@", "git://", "ssh://", "file://"))


def _refs_from_project_arg(project_ref: str, repo_root: Path) -> tuple[str, str]:
    """Resolve the shorthand project argument to code and IaC repo paths."""
    if _is_git_url(project_ref):
        fail(
            "Le mode <project-name> attend un nom de projet ou un chemin local. "
            "Pour des URLs Git, passe les deux depots explicitement."
        )

    project_path = Path(project_ref)
    if project_path.exists() or project_ref.startswith(".") or "/" in project_ref:
        code_path = project_path.resolve()
        project_name = _name_from_ref(str(code_path))
        return str(code_path), str(code_path.parent / f"{project_name}-iac")

    project_name = slug(project_ref)
    projects_dir = Path(os.environ.get("PROJECTS_DIR", _default_projects_dir(repo_root))).resolve()
    return str(projects_dir / project_name), str(projects_dir / f"{project_name}-iac")


def _default_projects_dir(repo_root: Path) -> Path:
    if os.environ.get("PLATFORM_REPO_URL"):
        return Path.cwd()
    return repo_root.parent


def _resolve_repo(ref: str, label: str) -> Path:
    """Return a local Path for the repo, cloning to a tmpdir if ref is a URL."""
    if _is_git_url(ref):
        tmpdir = Path(tempfile.mkdtemp(prefix="init-project-"))
        atexit.register(shutil.rmtree, tmpdir, ignore_errors=True)
        result = subprocess.run(
            ["git", "clone", "--depth=1", ref, str(tmpdir)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            fail(f"Echec du clone de {label} ({ref}):\n{result.stderr.strip()}")
        return tmpdir

    path = Path(ref).resolve()
    if not path.is_dir():
        fail(f"{label} introuvable: {path}")
    if not (path / ".git").is_dir():
        fail(f"{label} n'est pas un depot git: {path}")
    return path


def _name_from_ref(ref: str) -> str:
    """Derive an app name from a git URL or local path."""
    base = ref.rstrip("/").split("/")[-1]
    if base.endswith(".git"):
        base = base[:-4]
    return base


def _discover_services(code_dir: Path, iac_dir: Path, kustomize_path: str) -> list[str]:
    services = os.environ.get("SERVICES", "").split()
    if not services:
        services = services_from_kustomization(iac_dir, kustomize_path)
    if not services:
        services = services_from_code(code_dir)
    if not services:
        fail('Aucun service detecte: ajoute un Dockerfile par sous-dossier du depot code, ou passe SERVICES="svc-a svc-b"')
    return services


def _resolve_apps_dir(apps_file: Path) -> Path:
    apps_dir = os.environ.get("APPS_DIR") or _read_apps_dir(apps_file)
    path = Path(apps_dir or "apps")
    if not path.is_absolute():
        path = apps_file.parent / path
    return path.resolve()


def _read_apps_dir(apps_file: Path) -> str | None:
    if not apps_file.is_file():
        return None
    for line in apps_file.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("appsDir:"):
            return stripped.split(":", 1)[1].strip().strip("'\"")
    return None
