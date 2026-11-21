# Assistente de voz "Hi ESP"

Assistente de voz caseiro: você diz **"Hi ESP"** perto de uma placa ESP32-S3, conversa por voz com o **Gemini Live** e, quando o pedido é de programação, ele é **delegado ao Claude Code**. A resposta do Claude Code é falada sozinha quando a tarefa termina, mesmo minutos depois.

```
Mesa                                    VPS (Docker / Dokploy)
┌───────────────────────────┐           ┌────────────────────────────────────────────┐
│ INMP441 ─I2S─► ESP32-S3    │  Wi-Fi    │ servidor (Python + Pipecat)                 │
│   • wake word "Hi ESP"     │◄════════► │   • conversa ◄══► Gemini Live               │
│   • WebSocket              │  WSS      │   • pedidos de código ──► claude -p (fila)  │
│        │ USB serial        │           │   • resultado ──► TTS Gemini ──► placa      │
│        ▼                   │           └────────────────────────────────────────────┘
│ notebook: player.py 🔊     │  (temporário, até ligar um MAX98357A na placa)
└───────────────────────────┘
```

## Projetos

| Pasta | O que é | README |
|---|---|---|
| [`servidor/`](servidor/) | Servidor de voz em Python: ponte com o Gemini Live, fila do Claude Code, TTS. Roda em Docker. | [servidor/README.md](servidor/README.md) |
| [`firmware/AssistenteVoz/`](firmware/AssistenteVoz/) | Firmware da placa ESP32-S3 (Arduino): wake word, WebSocket, envio do mic. | [firmware/AssistenteVoz/README.md](firmware/AssistenteVoz/README.md) |
| [`notebook/`](notebook/) | Player que toca no notebook o áudio que a placa recebe (via USB). | [notebook/README.md](notebook/README.md) |

## Documentação

- [`docs/specs/2026-11-17-assistente-voz-design.md`](docs/specs/2026-11-17-assistente-voz-design.md): o design (o que e por quê).
- [`docs/contrato.md`](docs/contrato.md): **o contrato** de comunicação placa ⇄ servidor ⇄ notebook. Qualquer mudança no protocolo começa aqui.
- [`docs/notas-pipecat.md`](docs/notas-pipecat.md): APIs do Pipecat e do Gemini confirmadas na prática (inclui a pegadinha da API `v1beta`).

## Rodando tudo localmente (desenvolvimento)

O jeito mais fácil: **dê dois cliques em `iniciar.bat`**. Ele sobe o servidor e o player em duas janelas (veja os ajustes no topo do arquivo). Com o servidor rodando na VPS, use `iniciar.bat player` para abrir só o player.

Ou, manualmente, nesta ordem:

1. **Servidor** no notebook: veja [servidor/README.md › Rodar localmente](servidor/README.md#rodar-localmente).
2. **Firmware** com `SERVIDOR_HOST` = IP do notebook, `SERVIDOR_PORTA 8000`, `SERVIDOR_TLS 0`: veja [firmware/AssistenteVoz/README.md](firmware/AssistenteVoz/README.md).
3. **Player** na porta USB da placa: veja [notebook/README.md](notebook/README.md).
4. Diga **"Hi ESP"** e faça uma pergunta.

O `TOKEN_PLACA` do `servidor/.env` e o do `firmware/AssistenteVoz/config.h` precisam ser iguais.
