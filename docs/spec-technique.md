# Spec technique

## Structure

- `Makefile` enveloppe les commandes principales.
- `scripts/init-project.py` délègue à `scripts/init_projects/`.
- `scripts/delete-project.py` supprime une app de l'inventaire.
- `scripts/render-argocd-apps.py` génère les objets ArgoCD.
- `scripts/gitlab-seed.py` synchronise GitLab avec l'inventaire.
- `scripts/argocd-repo-creds.py` crée les credentials ArgoCD.
- `scripts/platform_git.py` gère les opérations Git/MR en mode distant.
- `scripts/platform_inventory.py` lit l'inventaire GitOps.

## Configuration

Les variables principales sont :

- `PLATFORM_REPO_ROOT` ;
- `PLATFORM_REPO_URL` ;
- `GITLAB_TOKEN` ;
- `PROJECTS_DIR` ;
- `APPS_FILE` ;
- `APPS_DIR` ;
- `GITLAB_NAMESPACE` ;
- `GITLAB_URL` ;
- `ARGOCD_NAMESPACE`.

## Onboarding

Le module `init_projects` charge la configuration CLI, découvre les services,
construit le modèle d'app, puis écrit `argocd/apps/<app>.yaml`. La sortie
affiche l'action réalisée, les services découverts, le dépôt de code et le
dépôt manifests.

## Maintenance

Le bootstrap technique reste dans `platform-cicd`. La toolbox opère sur
`platform-gitops` par défaut via `PLATFORM_REPO_ROOT`, afin que les opérations
d'onboarding et de génération ciblent le dépôt suivi par ArgoCD.
