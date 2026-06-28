GITLAB_DOMAIN     ?= 192.168.33.100.nip.io
PLATFORM_REPO_ROOT ?= $(abspath ../platform-gitops)
PLATFORM_REPO_URL ?=
GITLAB_TOKEN      ?=
APPS_BASE_DIR     ?= $(CURDIR)
SIBLING_PROJECTS_DIR ?= $(abspath $(APPS_BASE_DIR)/..)
CI_TEMPLATE_SOURCE_DIR ?= $(abspath ../ci-templates)
ARGOCD_NAMESPACE  ?= argocd
GITLAB_NAMESPACE  ?= gitlab

.PHONY: help init-project gitlab-seed argocd-repo-creds get-gitlab-token

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

init-project: ## Onboard une app via MR: make init-project CODE_REPO=<url-http> IAC_REPO=<url-http>
	@test -n "$(CODE_REPO)"    || (echo "CODE_REPO est requis"    >&2; exit 1)
	@test -n "$(IAC_REPO)"    || (echo "IAC_REPO est requis"     >&2; exit 1)
	@test -n "$(GITLAB_TOKEN)" || (echo "GITLAB_TOKEN est requis (clone + création MR)" >&2; exit 1)
	PLATFORM_REPO_ROOT=$(PLATFORM_REPO_ROOT) PLATFORM_REPO_URL=$(PLATFORM_REPO_URL) GITLAB_URL=http://gitlab.$(GITLAB_DOMAIN) \
	    GITLAB_TOKEN=$(GITLAB_TOKEN) python3 scripts/init-project.py "$(CODE_REPO)" "$(IAC_REPO)"

gitlab-seed: ## Seed les projets GitLab depuis l'inventaire plateforme
	PLATFORM_REPO_ROOT=$(PLATFORM_REPO_ROOT) PLATFORM_REPO_URL=$(PLATFORM_REPO_URL) GITLAB_URL=http://gitlab.$(GITLAB_DOMAIN) \
	    GITLAB_NAMESPACE=$(GITLAB_NAMESPACE) APPS_BASE_DIR=$(APPS_BASE_DIR) SIBLING_PROJECTS_DIR=$(SIBLING_PROJECTS_DIR) \
	    CI_TEMPLATE_SOURCE_DIR=$(CI_TEMPLATE_SOURCE_DIR) \
	    GITLAB_TOKEN=$(GITLAB_TOKEN) python3 scripts/gitlab-seed.py

get-gitlab-token: ## Affiche le GITLAB_TOKEN (usage : eval $(make get-gitlab-token))
	GITLAB_URL=http://gitlab.$(GITLAB_DOMAIN) \
	    GITLAB_NAMESPACE=$(GITLAB_NAMESPACE) python3 scripts/get-gitlab-token.py

argocd-repo-creds: ## Cree les credentials ArgoCD pour les repos manifests prives
	PLATFORM_REPO_ROOT=$(PLATFORM_REPO_ROOT) PLATFORM_REPO_URL=$(PLATFORM_REPO_URL) GITLAB_URL=http://gitlab.$(GITLAB_DOMAIN) \
	    GITLAB_NAMESPACE=$(GITLAB_NAMESPACE) ARGOCD_NAMESPACE=$(ARGOCD_NAMESPACE) \
	    GITLAB_TOKEN=$(GITLAB_TOKEN) python3 scripts/argocd-repo-creds.py
