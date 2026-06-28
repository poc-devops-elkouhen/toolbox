# Spec fonctionnelle

## Ajouter une application

L'utilisateur peut appeler `init-project.py` avec un nom de projet, deux chemins
locaux ou deux URLs Git. Le script découvre les sources, construit le modèle
d'application et écrit le fichier d'inventaire plateforme.

En mode `PLATFORM_REPO_URL`, la toolbox clone temporairement le dépôt GitOps
source sur GitHub, pousse une branche dédiée et ouvre une merge request.

## Supprimer une application

`delete-project.py` retire le fichier d'application de l'inventaire GitOps,
régénère les manifests ArgoCD et ouvre une merge request en mode distant. La
suppression ne détruit ni les dépôts GitLab ni les ressources déjà déployées.

## Seeder et administrer

La toolbox expose aussi :

- `gitlab-seed.py` pour créer ou mettre à jour les projets GitLab ;
- `argocd-repo-creds.py` pour enregistrer les credentials manifests ;
- `render-argocd-apps.py` pour générer les `AppProject` et `ApplicationSet` ;
- `get-gitlab-token.py` pour récupérer un token d'administration local.

## Modes d'utilisation

Deux modes sont supportés :

- checkout local avec `PLATFORM_REPO_ROOT` ;
- dépôt distant avec `PLATFORM_REPO_URL` et `GITLAB_TOKEN`.

Le mode distant est celui attendu pour un utilisateur qui ne veut pas cloner
manuellement `platform-gitops`.
