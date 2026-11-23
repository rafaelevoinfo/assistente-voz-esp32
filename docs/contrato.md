# Contrato de comunicação — v1

Fonte única de verdade para a comunicação entre **placa (ESP32-S3)**, **servidor (Python)** e **notebook (player)**.
Qualquer mudança aqui exige ajuste nos dois lados. Spec: `docs/specs/2026-11-17-assistente-voz-design.md`.

---

## 1. WebSocket placa ⇄ servidor

### 1.1 Conexão

| Item | Valor |
|---|---|
| Caminho | `/ws` |
| Autenticação | query string `?token=<TOKEN_PLACA>` |
| Produção | `wss://<dominio>/ws?token=...` (porta 443, TLS terminado no Traefik) |
| Desenvolvimento local | `ws://<ip-do-notebook>:8000/ws?token=...` |
| Health check (HTTP) | `GET /health` → `200 {"status":"ok"}` |

**Códigos de fechamento enviados pelo servidor:**

| Código | Quando | O que a placa faz |
|---|---|---|
| `4401` | Token ausente ou inválido | Loga o erro e tenta de novo a cada 30 s (não fica martelando) |
| `4000` | Outra conexão válida assumiu o lugar desta | Reconecta normalmente (intervalo padrão) |
| outros / queda | Rede, deploy etc. | Reconecta a cada 3 s |

**Keepalive:** a placa envia ping WebSocket a cada 15 s. Se não houver pong em 3 s, por 2 vezes seguidas, considera a conexão caída e reconecta. O servidor responde pings automaticamente.

### 1.2 Tipos de frame

- **Binário** = áudio PCM **16 bits little-endian, mono**, sem cabeçalho.
  - placa → servidor: **16000 Hz**, frames de **640 bytes** (20 ms). Só enquanto a placa estiver no estado "enviando mic" (entre `listen` e `stop_listen`/`session_end`).
  - servidor → placa: **24000 Hz**, frames de até **4800 bytes** (100 ms). Só entre `audio_start` e `audio_end`. Sempre um número par de bytes.
- **Texto** = um objeto JSON UTF-8 com o campo obrigatório `"type"`.
  - Campos extras desconhecidos devem ser **ignorados**.
  - Um `type` desconhecido ou JSON inválido: o receptor **loga e ignora**, sem fechar a conexão.

### 1.3 Mensagens placa → servidor

| `type` | Campos | Quando |
|---|---|---|
| `hello` | `fw` (string, ex. `"1.0"`) | Logo após **toda** conexão ou reconexão. É a primeira mensagem. |
| `wake` | — | A wake word "Hi ESP" foi detectada (só no estado "esperando wake word"). |
| `playback_done` | — | O áudio recebido até o último `audio_end` terminou de tocar (ver §1.6). |

Exemplos:
```json
{"type":"hello","fw":"1.0"}
{"type":"wake"}
{"type":"playback_done"}
```

### 1.4 Mensagens servidor → placa

| `type` | Campos | Efeito na placa |
|---|---|---|
| `listen` | — | Começar a enviar o mic (frames binários de 16 kHz). LED RX aceso. |
| `stop_listen` | — | Parar de enviar o mic (o servidor vai falar). LED RX apagado. |
| `audio_start` | `rate` (int, sempre `24000` na v1) | Vão chegar frames binários para tocar. Repassar `BEGIN` ao notebook. |
| `audio_end` | — | Fim do áudio. Repassar `END` ao notebook e aguardar o fim da reprodução. |
| `session_end` | — | Encerrar a sessão: parar o mic (se estiver enviando) e voltar a esperar "Hi ESP". |

Exemplos:
```json
{"type":"listen"}
{"type":"stop_listen"}
{"type":"audio_start","rate":24000}
{"type":"audio_end"}
{"type":"session_end"}
```

### 1.5 Estados da placa (referência para os dois lados)

```
           conectou + hello
                 │
                 ▼
   ┌───► ESPERANDO_WAKE ──"Hi ESP"──► envia wake, aguarda
   │            ▲                          │ listen
   │            │ session_end              ▼
   │            └────────────────── ENVIANDO_MIC ──stop_listen──► SILENCIO
   │                                    ▲   (frames 16k)             │
   │                                    │ listen                     │ audio_start / binário / audio_end
   │                                    └─────────────────── (tocando; envia playback_done no fim)
   └─ desconectou: aborta tudo, para o mic e volta a ESPERANDO_WAKE ao reconectar
```

Regras:
- Áudio do servidor (`audio_start` … `audio_end`) pode chegar **em qualquer estado**, inclusive em `ESPERANDO_WAKE`: é o resultado do Claude Code empurrado sem conversa. A placa sempre repassa ao notebook.
- `listen` pode chegar sem um `wake` antes: é a janela de continuação depois de um áudio empurrado. A placa obedece. Enquanto envia o mic, a wake word fica desligada.
- `session_end` pode chegar em qualquer estado. Ele sempre leva de volta a `ESPERANDO_WAKE`.
- Enquanto toca áudio (entre `audio_start` e o `playback_done`), a placa **nunca** envia mic (meio-duplex). O servidor garante isso enviando `stop_listen` antes de `audio_start` quando o mic estava aberto.

### 1.6 `playback_done` e timeouts de segurança

- A placa envia `playback_done` quando o último pedaço do áudio terminou de sair no alto-falante (MAX98357A, desde o fw 2.0; antes era o `DONE` do notebook).
- **Timeout na placa:** se o som não terminar em `duração_do_áudio + 3 s`, a placa envia `playback_done` assim mesmo. A duração vem de `bytes_recebidos / 48000` segundos, e o relógio começa no `audio_end`.
- **Timeout no servidor:** se o `playback_done` não chegar em `duração_do_áudio + 6 s` após o `audio_end`, o servidor age como se tivesse chegado.

### 1.7 Sequências de referência

**A. Pergunta geral**
```
placa → wake
serv  → listen
placa → [binário 16k …]          (usuário fala)
serv  → stop_listen
serv  → audio_start{24000}, [binário 24k …], audio_end
placa → playback_done
serv  → listen                    (janela de continuação, 8 s)
          … ninguém fala …
serv  → session_end
```

**B. Pedido de código + resultado empurrado minutos depois**
```
placa → wake
serv  → listen
placa → [binário …]               ("ajuste a página de pedidos…")
serv  → stop_listen, audio_start, [binário …], audio_end   ("ok, passei para o Claude Code")
placa → playback_done
serv  → listen                    (janela)
serv  → session_end               (ninguém falou)
          … minutos depois, Claude Code termina …
serv  → audio_start, [binário …], audio_end                (resultado)
placa → playback_done
serv  → listen                    (janela de continuação com contexto)
serv  → session_end               (ou conversa continua)
```

**C. Reconexão com resultado pendente**
```
(conexão cai; Claude Code termina; servidor guarda o resultado)
placa → (reconecta) hello
serv  → audio_start, [binário …], audio_end
placa → playback_done
serv  → listen … session_end
```

---

## 2. Serial placa → notebook (USB, só logs)

| Item | Valor |
|---|---|
| Porta | USB nativa do ESP32-S3 (USB CDC). Hoje é a COM4 no notebook. |
| Baud | 921600 (no USB CDC o valor é nominal) |

A placa só envia linhas `LOG <texto>
`, para exibir. Desde o fw 2.0 o áudio das respostas e o sinal de "estou ouvindo" (3 notas, só ao detectar "Hi ESP") saem no alto-falante da própria placa. As linhas `BEGIN`/`AUD`/`END`/`BEEP` e o `DONE` do notebook, usados enquanto não havia alto-falante, foram removidos.

---

## 3. Versionamento

- Esta é a **v1**. A placa informa a versão do firmware em `hello.fw`.
- Mudanças compatíveis (campos novos, tipos novos ignoráveis) não mudam a versão do contrato. Mudanças incompatíveis viram v2 e precisam de atualização coordenada.
