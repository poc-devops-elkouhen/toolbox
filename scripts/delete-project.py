#!/usr/bin/env python3
"""Remove an app from the GitOps inventory.

No local GitOps checkout:
  PLATFORM_REPO_URL=https://github.com/poc-devops-elkouhen/platform-gitops.git scripts/delete-project.py helloworld

Local GitOps checkout:
  PLATFORM_REPO_ROOT="$PWD" scripts/delete-project.py helloworld

When PLATFORM_REPO_URL is set, clones the source GitOps repo,
applies the change, renders the ApplicationSet, and opens a merge request instead
of writing directly to the local filesystem.
"""

import os
import sys

if os.environ.get("PLATFORM_REPO_URL"):
    from platform_git import create_mr_for_delete
    create_mr_for_delete(sys.argv)
else:
    from delete_projects import main
    main()
