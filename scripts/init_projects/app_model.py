from __future__ import annotations

from .config import InitProjectConfig, _is_git_url


def build_app(config: InitProjectConfig) -> dict:
    app: dict = {
        "name": config.app_name,
        "hasPreprod": config.has_preprod,
        "services": config.services,
        "manifests": {
            "path": config.kustomize_path,
        },
    }
    # sourceURL = URL externe d'origine, distincte de repoURL (URL GitLab de la plateforme,
    # dérivée par convention dans _normalize_app).
    if _is_git_url(config.code_ref):
        app["code"] = {"sourceURL": config.code_ref}
    if _is_git_url(config.iac_ref):
        app["manifests"]["sourceURL"] = config.iac_ref
    return app
