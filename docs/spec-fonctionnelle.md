# Spec fonctionnelle

## Ajouter une application

L'utilisateur peut appeler `init-project.py` avec un nom de projet, deux chemins
locaux ou deux URLs Git. Le script découvre les sources, construit le modèle
d'application et écrit le dossier applicatif GitOps.

En mode `PLATFORM_REPO_URL`, la toolbox clone temporairement le dépôt GitOps
source sur GitHub, pousse une branche dédiée et ouvre une pull request.

## Supprimer une application

`delete-project.py` retire le dossier d'application de l'inventaire GitOps et
ouvre une pull/merge request en mode distant. La suppression ne détruit ni les
dépôts GitLab ni les ressources déjà déployées.

## Seeder et administrer

La toolbox expose aussi :

- `argocd-repo-creds.py` pour enregistrer les credentials manifests ;
- `get-gitlab-token.py` pour récupérer un token d'administration local.

La création ou mise à jour des projets GitLab est portée par
`gitlab-projects-iac`, appliqué par le `Terraform/gitlab-iac`.

## Modes d'utilisation

Deux modes sont supportés :

- checkout local avec `PLATFORM_REPO_ROOT` ;
- dépôt distant avec `PLATFORM_REPO_URL` et `GITHUB_TOKEN` pour GitHub.

Le mode distant est celui attendu pour un utilisateur qui ne veut pas cloner
manuellement `platform-gitops`.
