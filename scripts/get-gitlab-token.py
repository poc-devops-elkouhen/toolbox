#!/usr/bin/env python3
"""Récupère un token GitLab depuis le secret K8s et l'affiche pour export.

Usage :
    eval $(python3 scripts/get-gitlab-token.py)
    # ou via make :
    eval $(make get-gitlab-token)
"""
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

GITLAB_NAMESPACE = os.environ.get("GITLAB_NAMESPACE", "gitlab")
GITLAB_URL = os.environ.get("GITLAB_URL", "http://gitlab.192.168.33.100.nip.io")


def kube_secret_field(namespace, name, jsonpath):
    try:
        raw = subprocess.run(
            ["kubectl", "-n", namespace, "get", "secret", name, "-o", f"jsonpath={jsonpath}"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        print(f"Erreur kubectl : {exc.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return base64.b64decode(raw).decode() if raw else ""


def http_post(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


root_password = kube_secret_field(
    GITLAB_NAMESPACE, "gitlab-gitlab-initial-root-password", "{.data.password}"
)
if not root_password:
    print("Mot de passe root GitLab introuvable dans le secret K8s.", file=sys.stderr)
    sys.exit(1)

auth = http_post(f"{GITLAB_URL}/oauth/token", {
    "grant_type": "password",
    "username": "root",
    "password": root_password,
})
token = auth.get("access_token", "")
if not token or token == "null":
    print("Échec d'authentification à l'API GitLab.", file=sys.stderr)
    sys.exit(1)

print(f"export GITLAB_TOKEN={token}")
