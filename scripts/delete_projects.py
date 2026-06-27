from __future__ import annotations

import os
import sys
from pathlib import Path

from init_projects.common import slug
from init_projects.config import _resolve_apps_dir
from init_projects.errors import fail
from init_projects.inventory import delete_app_file, delete_app_from_apps_file
from platform_inventory import platform_repo_root

USAGE = "Usage: {script} <project-name>"


def main() -> None:
    delete_project(sys.argv)


def delete_project(argv: list[str]) -> None:
    if len(argv) != 2:
        fail(USAGE.format(script=argv[0]))

    repo_root = platform_repo_root()
    apps_file = Path(os.environ.get("APPS_FILE", repo_root / "argocd/apps.yaml")).resolve()
    app_name = slug(argv[1])
    apps_dir = _resolve_apps_dir(apps_file)

    removed_file = delete_app_file(apps_dir, app_name)
    if removed_file:
        print(f"Application '{app_name}' supprimee de {removed_file}")
        return

    if apps_file.is_file() and delete_app_from_apps_file(apps_file, app_name):
        print(f"Application '{app_name}' supprimee de {apps_file}")
        return

    fail(f"Application '{app_name}' introuvable dans {apps_dir} ou {apps_file}")
