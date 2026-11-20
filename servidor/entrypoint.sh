#!/bin/sh
set -e

WORKSPACE_DIR="${WORKSPACE_DIR:-/home/voz/workspace}"
mkdir -p "$WORKSPACE_DIR" "$HOME/.claude"

# Memória (CONTEXTO.md + historico.jsonl): na 1ª inicialização copia o modelo do
# CONTEXTO.md. Nunca sobrescreve um CONTEXTO.md já existente (o do usuário).
if [ -n "${MEMORIA_DIR:-}" ]; then
  mkdir -p "$MEMORIA_DIR"
  if [ ! -f "$MEMORIA_DIR/CONTEXTO.md" ] && [ -f /opt/voz/CONTEXTO.example.md ]; then
    cp /opt/voz/CONTEXTO.example.md "$MEMORIA_DIR/CONTEXTO.md"
    echo "memória: CONTEXTO.md criado a partir do modelo em $MEMORIA_DIR" >&2
  fi
fi

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
