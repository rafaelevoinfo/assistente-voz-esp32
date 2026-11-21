# Servidor do assistente de voz + Claude Code CLI + gh, rodando como usuário não-root "voz".
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# git, curl, Node.js LTS (NodeSource) e gh (repositório oficial do GitHub CLI)
RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
 && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends gh \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code && npm cache clean --force

RUN useradd -m -s /bin/bash voz

# Dependências com versões travadas (requirements.txt) e depois o pacote do servidor,
# sem deixar o pip resolver de novo (--no-deps). Camadas separadas aproveitam o cache.
WORKDIR /opt/voz
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY pyproject.toml ./
COPY voz ./voz
RUN pip install --no-deps .

COPY --chmod=755 entrypoint.sh /entrypoint.sh
# Instruções do assistente: ficam na imagem, então cada deploy traz a versão do repositório
COPY INSTRUCTIONS.md /opt/voz/INSTRUCTIONS.md
ENV INSTRUCOES_ARQUIVO=/opt/voz/INSTRUCTIONS.md

USER voz
ENV HOME=/home/voz \
    WORKSPACE_DIR=/home/voz/workspace \
    MEMORIA_DIR=/home/voz/memoria
WORKDIR /home/voz
RUN mkdir -p /home/voz/workspace /home/voz/.claude

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
