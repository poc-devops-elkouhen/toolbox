GITLAB_DOMAIN           ?= 192.168.33.100.nip.io
INTERNAL_GITLAB_HOST    ?= gitlab-webservice-default.gitlab.svc.cluster.local:8181
PLATFORM_REPO_ROOT ?= $(abspath ../platform-gitops)
PLATFORM_REPO_URL ?=
GITHUB_TOKEN      ?=
GITLAB_TOKEN      ?=
APPS_BASE_DIR     ?= $(CURDIR)
SIBLING_PROJECTS_DIR ?= $(abspath $(APPS_BASE_DIR)/..)
SEED_SIBLING_PROJECTS ?= false
CI_TEMPLATE_SOURCE_DIR ?= $(abspath ../ci-templates)
ARGOCD_NAMESPACE  ?= argocd
GITLAB_NAMESPACE  ?= gitlab

.PHONY: help init-project argocd-repo-creds get-gitlab-token gitlab-git-creds

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

init-project: ## Onboard une app via MR: make init-project CODE_REPO=<url-http> IAC_REPO=<url-http>
	@test -n "$(CODE_REPO)"    || (echo "CODE_REPO est requis"    >&2; exit 1)
	@test -n "$(IAC_REPO)"    || (echo "IAC_REPO est requis"     >&2; exit 1)
	@test -n "$(GITHUB_TOKEN)" || (echo "GITHUB_TOKEN est requis (clone + création PR GitHub)" >&2; exit 1)
	PLATFORM_REPO_ROOT=$(PLATFORM_REPO_ROOT) PLATFORM_REPO_URL=$(PLATFORM_REPO_URL) GITLAB_URL=https://gitlab.$(GITLAB_DOMAIN) \
	    GITHUB_TOKEN=$(GITHUB_TOKEN) GITLAB_TOKEN=$(GITLAB_TOKEN) python3 scripts/init-project.py "$(CODE_REPO)" "$(IAC_REPO)"

get-gitlab-token: ## Affiche le GITLAB_TOKEN (usage : eval $(make get-gitlab-token))
	GITLAB_URL=https://gitlab.$(GITLAB_DOMAIN) \
	    GITLAB_NAMESPACE=$(GITLAB_NAMESPACE) python3 scripts/get-gitlab-token.py

gitlab-git-creds: ## Cree un PAT GitLab root et l'injecte dans git-credential pour l'URL interne cluster
	GITLAB_URL=https://gitlab.$(GITLAB_DOMAIN) \
	    GITLAB_NAMESPACE=$(GITLAB_NAMESPACE) \
	    INTERNAL_GITLAB_HOST=$(INTERNAL_GITLAB_HOST) \
	    python3 scripts/gitlab-git-creds.py

argocd-repo-creds: ## Cree les credentials ArgoCD pour les repos manifests prives
	PLATFORM_REPO_ROOT=$(PLATFORM_REPO_ROOT) PLATFORM_REPO_URL=$(PLATFORM_REPO_URL) GITLAB_URL=https://gitlab.$(GITLAB_DOMAIN) \
	    GITLAB_NAMESPACE=$(GITLAB_NAMESPACE) ARGOCD_NAMESPACE=$(ARGOCD_NAMESPACE) \
	    GITLAB_TOKEN=$(GITLAB_TOKEN) python3 scripts/argocd-repo-creds.py
