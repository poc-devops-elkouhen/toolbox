# poc-devops-toolbox

Scripts partagés pour piloter les projets `poc-devops`.

Les scripts de bootstrap restent utilisables depuis `poc-devops-platform`. Cette toolbox contient une copie réutilisable des utilitaires Python, avec une racine plateforme configurable.

## Installation

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Ajouter un projet sans checkout plateforme

Pour ajouter un projet standard comme `helloworld`, le développeur n'a pas
besoin de cloner `poc-devops-platform`. Depuis le dossier qui contient les
dépôts `helloworld` et `helloworld-iac`:

```sh
PLATFORM_REPO_URL=http://gitlab.192.168.33.100.nip.io/root/poc-devops-platform.git \
GITLAB_TOKEN=<token> \
python3 /chemin/poc-devops-toolbox/scripts/init-project.py helloworld
```

Le script clone temporairement le dépôt plateforme, ajoute ou met à jour
`argocd/apps/helloworld.yaml`, régénère `argocd/managed/apps-appset.yaml`, pousse
une branche `toolbox/add-helloworld`, puis ouvre une merge request.

Si les dépôts applicatifs sont dans un autre dossier:

```sh
PLATFORM_REPO_URL=http://gitlab.192.168.33.100.nip.io/root/poc-devops-platform.git \
GITLAB_TOKEN=<token> \
PROJECTS_DIR=/chemin/projets \
python3 /chemin/poc-devops-toolbox/scripts/init-project.py helloworld
```

Les URLs Git restent possibles lorsque le développeur n'a pas non plus les
dépôts applicatifs en local:

```sh
PLATFORM_REPO_URL=http://gitlab.192.168.33.100.nip.io/root/poc-devops-platform.git \
GITLAB_TOKEN=<token> \
python3 /chemin/poc-devops-toolbox/scripts/init-project.py \
  https://git.example.com/team/helloworld.git \
  https://git.example.com/team/helloworld-iac.git
```

## Supprimer un projet sans checkout plateforme

Pour retirer `helloworld` de la plateforme sans cloner `poc-devops-platform`:

```sh
PLATFORM_REPO_URL=http://gitlab.192.168.33.100.nip.io/root/poc-devops-platform.git \
GITLAB_TOKEN=<token> \
python3 /chemin/poc-devops-toolbox/scripts/delete-project.py helloworld
```

Le script supprime l'entrée `argocd/apps/helloworld.yaml` du dépôt plateforme,
régénère `argocd/managed/apps-appset.yaml`, pousse une branche
`toolbox/delete-helloworld`, puis ouvre une merge request. Il ne supprime pas les
dépôts GitLab applicatifs.

## Utilisation avec checkout plateforme

Depuis le dépôt plateforme, pour les opérations d'administration:

```sh
PLATFORM_REPO_ROOT="$PWD" python3 ../poc-devops-toolbox/scripts/render-argocd-apps.py > argocd/managed/apps-appset.yaml
PLATFORM_REPO_ROOT="$PWD" python3 ../poc-devops-toolbox/scripts/init-project.py helloworld
PLATFORM_REPO_ROOT="$PWD" python3 ../poc-devops-toolbox/scripts/init-project.py ../helloworld ../helloworld-iac
PLATFORM_REPO_ROOT="$PWD" python3 ../poc-devops-toolbox/scripts/delete-project.py helloworld
PLATFORM_REPO_ROOT="$PWD" python3 ../poc-devops-toolbox/scripts/gitlab-seed.py
PLATFORM_REPO_ROOT="$PWD" python3 ../poc-devops-toolbox/scripts/argocd-repo-creds.py
python3 ../poc-devops-toolbox/scripts/gitlab-runner-token.py
```

Depuis n'importe quel autre répertoire, renseigner `PLATFORM_REPO_ROOT` avec le chemin absolu du dépôt `poc-devops-platform`.

## Scripts

- `filter-argocd-install.py`: filtre le manifeste d'installation ArgoCD.
- `render-argocd-apps.py`: génère les `AppProject` et l'`ApplicationSet` depuis l'inventaire apps.
- `init-project.py` et `init_projects/`: ajoute ou met à jour une app dans `argocd/apps/*.yaml`.
- `delete-project.py`: supprime une app de `argocd/apps/*.yaml` et ouvre une merge request en mode `PLATFORM_REPO_URL`.
- `gitlab-seed.py`: crée et alimente les projets GitLab déclarés dans l'inventaire.
- `gitlab-runner-token.py`: crée le token runner GitLab et le Secret Kubernetes associé.
- `argocd-repo-creds.py`: crée les credentials ArgoCD pour les dépôts manifests privés.

## Variables utiles

- `PLATFORM_REPO_ROOT`: racine du dépôt plateforme. Par défaut: répertoire courant.
- `PLATFORM_REPO_URL`: URL Git du dépôt plateforme. Si renseignée, les scripts projet ouvrent une merge request au lieu d'écrire dans un checkout local.
- `GITLAB_TOKEN`: token utilisé pour cloner/pousser le dépôt plateforme et créer la merge request.
- `PROJECTS_DIR`: dossier contenant les dépôts applicatifs lorsque `init-project.py` est appelé avec un nom de projet. Par défaut: répertoire courant en mode `PLATFORM_REPO_URL`, sinon dossier parent du dépôt plateforme.
- `APPS_FILE`: chemin explicite vers l'inventaire apps.
- `APPS_DIR`: dossier contenant les fichiers app YAML.
- `GITLAB_NAMESPACE`, `GITLAB_URL`, `ARGOCD_NAMESPACE`: paramètres Kubernetes/GitLab utilisés par les scripts de bootstrap.
