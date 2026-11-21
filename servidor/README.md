# Servidor de voz

Servidor Python que liga a placa ao **Gemini Live** e ao **Claude Code**:

- mantém uma conexão **WebSocket permanente** com a placa (`/ws?token=...`), autenticada por `TOKEN_PLACA`;
- durante uma conversa (do "Hi ESP" até a janela de continuação fechar), faz a ponte de áudio com o Gemini Live via **Pipecat**;
- quando o modelo chama a ferramenta `tarefa_de_codigo`, coloca o pedido numa **fila** (uma tarefa por vez) e roda `claude -p` em segundo plano;
- quando o Claude Code termina, converte a resposta em áudio com o **TTS do Gemini** e envia à placa, mesmo fora de uma conversa (se a placa estiver offline, entrega ao reconectar).

O protocolo com a placa está em [`../docs/contrato.md`](../docs/contrato.md).

## Estrutura

| Arquivo | Responsabilidade |
|---|---|
| `voz/app.py` | FastAPI: `/ws` (placa) e `/health`; mascara o token nos logs |
| `voz/conexao.py` | Máquina de estados da conexão (OCIOSO, OUVINDO, RESPONDENDO, TOCANDO), janela de continuação e caixa de saída |
| `voz/sessao_pipecat.py` | Sessão de voz com Pipecat (Gemini Live; OpenAI Realtime só configurado) |
| `voz/tts_gemini.py` | TTS do Gemini para falar os resultados |
| `voz/tarefas.py` | Execução do Claude Code (`claude -p`) e fila de tarefas |
| `voz/detector_fala.py` | Detecção local de início e fim de fala (com passa-altas de 80 Hz contra o ronco do mic) |
| `voz/memoria.py` | Memória: `historico.jsonl` (rotação de 10 MB, até 7 arquivos) |
| `voz/config.py` | Configuração por variáveis de ambiente |
| `scripts/teste_real.py` | Simula a placa a partir de um `.wav` (teste sem hardware) |
| `spike/` | Experimentos descartáveis da integração com o Gemini |

## Configuração

Copie `.env.example` para `.env` e preencha. **Nunca commite o `.env`.**

| Variável | Para que serve |
|---|---|
| `TOKEN_PLACA` | Segredo que a placa envia ao conectar. Igual ao do `config.h` do firmware. Use só letras, números, `-` e `_`. |
| `GOOGLE_API_KEY` | Chave do Google AI Studio. |
| `PROVEDOR_VOZ` | `gemini` (padrão) ou `openai`. |
| `MODELO_VOZ`, `VOZ` | Modelo do Gemini Live e voz da conversa. |
| `MODELO_TTS`, `VOZ_TTS` | Modelo e voz do TTS dos resultados. |
| `PROACTIVE_AUDIO` | `1` (padrão): o modelo pode ficar em silêncio com conversas que não são com ele. |
| `JANELA_CONTINUACAO_S` | Segundos de escuta após cada resposta, sem precisar de "Hi ESP" (padrão 8). |
| `ESPERA_RESPOSTA_S` | Fecha a sessão se o modelo não responder depois que você parar de falar (padrão 6). |
| `ESCUTA_MAX_S` | Trava de custo: tempo máximo ouvindo sem resposta do modelo (padrão 60). |
| `WORKSPACE_DIR` | Pasta onde o Claude Code trabalha nos projetos. |
| `MEMORIA_DIR` | Pasta da memória (`historico.jsonl`). Vazio = sem memória. |
| `INSTRUCOES_ARQUIVO` | Arquivo de instruções do assistente. Padrão: `servidor/INSTRUCTIONS.md` (no Docker, `/opt/voz/INSTRUCTIONS.md`). |
| `CLAUDE_TIMEOUT_S` | Tempo máximo de uma tarefa do Claude Code (padrão 1800). |
| `CLAUDE_CODE_OAUTH_TOKEN` | Login do Claude Code pela assinatura (gere com `claude setup-token`). |
| `CLAUDE_CMD` | Comando do Claude Code (padrão `claude`). Em testes, aponte para um script falso. |
| `GH_TOKEN` | Token do GitHub para o Claude Code clonar, criar branches e PRs. |

## Instruções e memória

A instrução de sistema de toda conversa é montada assim (spec §7.2); não há prompt fixo no código:

- **[`INSTRUCTIONS.md`](INSTRUCTIONS.md)**: **todas as instruções do assistente** (personalidade, idioma, prática de inglês, quando usar a ferramenta `tarefa_de_codigo` e a busca, seus projetos). Fica versionado no repositório e vai dentro da imagem Docker (`INSTRUCOES_ARQUIVO=/opt/voz/INSTRUCTIONS.md`), então **cada deploy carrega a versão nova**: edite, faça commit e push (o Dokploy faz o deploy sozinho). Localmente é lido direto de `servidor/INSTRUCTIONS.md`, a cada conversa.
- **As últimas 5 trocas** (pergunta → resposta, incluindo os resultados do Claude Code), tiradas das transcrições do Gemini e guardadas em `historico.jsonl`.

Quando o arquivo chegaria a 10 MB, ele vira `historico.1.jsonl` (o anterior vira `.2`, e assim por diante), e um novo começa vazio. Ficam no máximo 7 arquivos.

## Rodar localmente

Requer Python 3.12+.

```bash
cd servidor
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # Linux/macOS: .venv/bin/pip
```

### Versões das dependências

As versões são travadas em dois lugares:

- `pyproject.toml`: as dependências diretas, com `==`.
- `requirements.txt`: **todas** as dependências, incluindo as indiretas, resolvidas para o Linux do Docker. O Dockerfile instala por ele.

Para atualizar: mude as versões no `pyproject.toml`, reinstale (`pip install -e ".[dev]"`), rode os testes e regenere o lock:

```bash
.venv/Scripts/pip freeze --exclude-editable > /tmp/c.txt
.venv/Scripts/uv pip compile pyproject.toml --python-version 3.12 \
  --python-platform x86_64-unknown-linux-gnu -c /tmp/c.txt \
  --no-header --no-annotate -o requirements.txt
```

Suba o servidor escutando na rede (para a placa alcançar o notebook):

```bash
# carregue as variáveis do .env no ambiente antes (ex. no Git Bash):
set -a && . <(grep -E '^[A-Z_]+=' .env | sed 's/\r$//') && set +a
.venv/Scripts/python -m uvicorn voz.app:app --host 0.0.0.0 --port 8000
```

- Teste: `curl http://localhost:8000/health` → `{"status":"ok"}`.
- No Windows, permita o Python no firewall em **redes privadas**; senão a placa não conecta.
- Para testar **sem mexer em nenhum repositório**, defina `CLAUDE_CMD` apontando para um script que imprime `{"result": "...", "is_error": false}` (veja `tests/fake_claude.py`).

### Testar sem a placa

```bash
.venv/Scripts/python scripts/teste_real.py --wav pergunta.wav --token SEU_TOKEN
```

Faz streaming do `.wav` (16 kHz, mono, 16 bits) como se fosse o mic e salva a resposta em `saida.wav`. `spike/gerar_wavs.py` gera `.wav` de teste com o TTS do Gemini.

## Testes

```bash
.venv/Scripts/python -m pytest -q
```

Os testes não usam rede: o Gemini, o TTS e o Claude Code são substituídos por fakes (`tests/fakes.py`, `tests/fake_claude.py`).

## Docker

```bash
docker build -t voz .
docker run --rm --env-file .env -p 8000:8000 voz
```

A imagem traz Python, Node, **Claude Code** e **gh**, e roda como o usuário **não-root** `voz`. O Claude Code se recusa a rodar com permissões liberadas como root. O volume `voz_home` (`/home/voz`) guarda a memória e o login do Claude Code (`.claude/`) e os projetos (`workspace/`).

### Deploy (Dokploy)

`docker-compose.yml` é o projeto **Compose** do Dokploy:
- variáveis de ambiente cadastradas na UI do Dokploy;
- domínio apontando para o serviço `voz`, porta **8000**, com HTTPS. O Traefik faz o TLS, e a placa usa `wss://<domínio>/ws`.

## Cuidados

- O Gemini exige a API **`v1beta`** para Live e TTS. Na `v1`, o padrão do `google-genai`, os modelos de voz não aparecem (404 / `Unknown name "speechConfig"`).
- Os nomes de modelo do Gemini mudam com frequência; ficam só nas variáveis de ambiente.
- Pedidos de código podem ir até **produção** (o Claude Code decide). Qualquer pessoa que diga "Hi ESP" perto da placa pode disparar uma tarefa.
