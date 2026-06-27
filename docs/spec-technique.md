# Spec technique

## Structure

- `Makefile` enveloppe les commandes principales.
- `scripts/init-project.py` délègue à `scripts/init_projects/`.
- `scripts/delete-project.py` supprime une app de l'inventaire.
- `scripts/render-argocd-apps.py` génère les objets ArgoCD.
- `scripts/gitlab-seed.py` synchronise GitLab avec l'inventaire.
- `scripts/argocd-repo-creds.py` crée les credentials ArgoCD.
- `scripts/platform_git.py` gère les opérations Git/MR en mode distant.
- `scripts/platform_inventory.py` lit l'inventaire plateforme.

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

Certains scripts existent aussi dans `poc-devops-platform/scripts/` pour garder
le bootstrap plateforme autonome. Toute correction fonctionnelle d'un script
partagé doit être répercutée dans les deux emplacements ou remplacée par un
wrapper explicite documenté.
