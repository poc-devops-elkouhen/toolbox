# AGENTS.md — toolbox

## Rôle du dépôt

`toolbox` regroupe les scripts d'opération plateforme utilisables indépendamment
de `platform-cicd`. Il permet d'onboarder des applications et de gérer les
credentials ArgoCD sans checkout actif de `platform-cicd`.

## Fichiers clés

| Fichier | Rôle |
|---------|------|
| `scripts/platform_inventory.py` | Modèle de données partagé (chargement et normalisation de l'inventaire) |
| `scripts/init-project.py` | Onboarding d'une app (met à jour `argocd/apps/<app>/`) |
| `scripts/argocd-repo-creds.py` | Crée les secrets ArgoCD pour les dépôts manifests privés |
| `scripts/get-gitlab-token.py` | Récupère un token GitLab pour les opérations locales |
| `scripts/delete-project.py` / `delete_projects.py` | Suppression d'apps de l'inventaire |

## Modes de fonctionnement

**Mode local** — dépôt `platform-gitops` cloné localement :
```bash
PLATFORM_REPO_ROOT=../platform-gitops make argocd-repo-creds
```

**Mode MR** — clone temporaire depuis GitHub :
```bash
PLATFORM_REPO_URL=https://github.com/poc-devops-elkouhen/platform-gitops \
GITHUB_TOKEN=<token> make init-project
```

Les projets GitLab ne sont plus seedés depuis `toolbox`. Ils sont déclarés dans
`gitlab-projects-iac` et appliqués par le `Terraform/gitlab-iac`.

## Variables d'environnement importantes

| Variable | Rôle |
|----------|------|
| `PLATFORM_REPO_ROOT` | Chemin local vers `platform-gitops` |
| `PLATFORM_REPO_URL` | URL GitHub pour clone temporaire (mode MR) |
| `GITLAB_URL` | URL externe GitLab (défaut : `https://gitlab.192.168.33.100.nip.io`) |
| `GITLAB_NAMESPACE` | Namespace K8s GitLab (défaut : `gitlab`) |
| `CI_TEMPLATE_SOURCE_DIR` | Chemin local vers `ci-templates` |
| `APPS_BASE_DIR` | Répertoire de base pour résoudre les chemins relatifs des apps |

## Ce qu'il ne faut pas faire

- Ne pas modifier `platform_inventory.py` sans répercuter le changement dans
  `platform-cicd/scripts/platform_inventory.py` — les deux fichiers doivent
  rester synchronisés.
- Ne pas supprimer physiquement les dépôts GitLab applicatifs depuis les scripts
  de suppression — ils retirent uniquement l'entrée de l'inventaire.
- Ne pas committer de tokens ou mots de passe dans ce dépôt.
