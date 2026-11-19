#!/bin/sh
set -e

WORKSPACE_DIR="${WORKSPACE_DIR:-/home/voz/workspace}"
mkdir -p "$WORKSPACE_DIR" "$HOME/.claude"

# git autenticado pelo gh (clonar, criar branches, push) quando houver token
if [ -n "${GH_TOKEN:-}" ]; then
  gh auth setup-git || echo "aviso: gh auth setup-git falhou" >&2
  git config --global user.name  >/dev/null 2>&1 || git config --global user.name  "${GIT_USER_NAME:-Assistente de voz}"
  git config --global user.email >/dev/null 2>&1 || git config --global user.email "${GIT_USER_EMAIL:-voz@localhost}"
fi

# Permite "docker run voz <comando>" para inspeção (ex.: claude --version)
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

exec uvicorn voz.app:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
