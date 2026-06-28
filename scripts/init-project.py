#!/usr/bin/env python3
"""Initialise/update an app inventory file from local code and IaC Git repos.

Local platform checkout:
  scripts/init-project.py ../my-app ../my-app-iac

No local GitOps checkout:
  PLATFORM_REPO_URL=https://github.com/poc-devops-elkouhen/platform-gitops.git scripts/init-project.py helloworld

When PLATFORM_REPO_URL is set, clones the source GitOps repo,
applies the change, renders the ApplicationSet, and opens a merge request instead
of writing directly to the local filesystem.
"""

import os
import sys

if os.environ.get("PLATFORM_REPO_URL"):
    from platform_git import create_mr_for_init
    create_mr_for_init(sys.argv)
else:
    from init_projects.cli import main
    main()
