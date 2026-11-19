# Assistente de voz "Hi ESP": ESP32-S3 → VPS → Gemini Live → Claude Code

**Data:** 2026-11-17
**Status:** design em revisão; código ainda não iniciado

---

## 1. Intenção

Delegar tarefas de programação **falando**, sem abrir o editor.

Exemplo real: *"Ajuste a página de pedidos do projeto ProximoTurno e adicione uma tag para informar se houve uso de cupom ou não."*

O pedido é feito em linguagem natural, no nível de produto. O **Claude Code** decide tudo sobre código: qual projeto, o que alterar, se abre PR e se publica em produção. Quando termina, a placa **fala sozinha** a resposta dele, mesmo que a conversa já tenha acabado há minutos.

O assistente de voz também responde **perguntas gerais**. Essas o próprio modelo de voz responde, sem envolver o Claude Code.

## 2. Objetivos

- Wake word local ("Hi ESP") na placa, sem enviar áudio antes dela.
- Conversa por voz em **português**, com baixa latência, usando o **Gemini Live API** (Google).
- Encaminhar **todo pedido de programação** ao Claude Code, com o texto do pedido fiel ao que foi dito.
- Execução **assíncrona**: a conversa termina logo e o resultado é anunciado quando ficar pronto.
- Falar a resposta do Claude Code **exatamente como veio**, sem reinterpretar.
- **Provedor de voz trocável** (Gemini ↔ OpenAI Realtime) por configuração.
- Servidor rodando em **container Docker na VPS**, implantado pelo Dokploy como os demais projetos.

## 3. Fora do escopo (agora)

- **Hermes / memória de conversa:** não participa. Pode ser integrado no futuro.
- **Controle de dispositivos da casa** (luzes etc.) e Home Assistant propriamente dito.
- **Alto-falante na placa** (MAX98357A): ainda não existe. Por enquanto o áudio toca no **notebook** (ver §5.4).
- **Interromper a resposta falando por cima** (*barge-in*): fica para depois.
- **Wake word personalizada** ("Hey Pegasus"): adiada. Usa-se a "Hi ESP" pronta do ESP-SR.

## 4. Anti-objetivos (seria fracasso mesmo funcionando)

- O modelo de voz **"inventar" ou resumir** a resposta do Claude Code em vez de falá-la como veio.
- O modelo de voz **tentar resolver pedidos de programação sozinho** em vez de delegar.
- A conversa ficar **travada esperando** o Claude Code terminar.
- Alguém além da placa conseguir conectar no servidor e disparar tarefas.
- O assistente **responder a conversas da casa** que não eram com ele durante a janela de continuação.
- Trocar de provedor de voz exigir mexer na placa, no Claude Code ou na lógica de tarefas.

## 5. Arquitetura

```
┌────────────── Mesa ──────────────┐            ┌──────────────────────── VPS ─────────────────────┐
│                                  │            │  Container "voz" (Dokploy + Traefik, WSS)         │
│ INMP441 ─I2S─► ESP32-S3          │  Wi-Fi     │                                                   │
│               • ESP-SR "Hi ESP"  │◄══════════►│  Servidor de voz (Python + Pipecat)               │
│               • WebSocket (WSS)  │  WSS +     │   • pipeline de voz ◄══ WebSocket ══► Gemini Live │
│                     │ USB serial │  token     │   • executa a ferramenta ──► claude -p (async)    │
│                     ▼            │            │   • resultado ──► TTS (Gemini) ──► áudio p/ placa │
│               Notebook (Python)  │            │                                                   │
│               toca o áudio 🔊    │            │  Volume persistente: ~/.claude + workspace/       │
└──────────────────────────────────┘            └───────────────────────────────────────────────────┘
```

### 5.1 Fluxo de uma conversa

1. A placa detecta "Hi ESP" localmente (ESP-SR / WakeNet9).
2. A placa avisa o servidor que uma sessão começou e passa a **enviar o áudio do microfone** pela conexão WebSocket que já estava aberta.
3. O servidor abre uma sessão no **Gemini Live** e repassa o áudio. A detecção de fim de fala (VAD) é feita pelo provedor.
4. **Pergunta geral:** o modelo responde em áudio → servidor → placa → notebook toca.
5. **Pedido de programação:** o modelo chama a ferramenta `tarefa_de_codigo(pedido)`. O servidor:
   - coloca a tarefa na fila do Claude Code **em segundo plano**;
   - devolve imediatamente ao modelo algo como "tarefa recebida". O modelo então confirma em voz, por exemplo "Ok, passei para o Claude Code".
6. A conversa continua enquanto houver interação: depois de **toda** resposta tocada, abre-se a **janela de continuação** (§5.2.1). Se ninguém falar com o assistente dentro dela, a sessão no provedor é encerrada e a placa volta a esperar a wake word.

### 5.2 Fluxo do resultado (assíncrono)

1. O Claude Code termina e devolve um texto de resposta. Ele mesmo diz o que fez, se abriu PR, se foi para produção etc.
2. O servidor converte esse texto em áudio com um **serviço de TTS** (padrão: TTS do Gemini). Não é preciso abrir uma sessão de conversa só para ler um texto pronto.
3. O servidor envia o áudio à placa pela conexão que **fica sempre aberta**, e ela toca na hora.
4. Depois de tocar, abre-se a **janela de continuação** (§5.2.1). Assim, o usuário pode responder ("então abre o PR") **sem dizer "Hi ESP"**. Para isso, o servidor abre uma sessão nova no provedor já com **o texto do resultado como contexto**.

### 5.2.1 Janela de continuação (decisão do usuário)

**Regra:** sempre que a placa termina de tocar um áudio (resposta de conversa ou resultado do Claude Code), ela fica **pronta para ouvir uma resposta nos próximos segundos**, sem precisar da wake word.

Proteções contra conversas da casa (ex.: alguém conversando na sala):

1. **Janela curta:** o mic fica aberto por **8 s** (configurável) depois do fim do áudio. Se ninguém começar a falar, a janela fecha e a placa volta a esperar "Hi ESP".
2. **Proactive Audio do Gemini ativado:** o modelo pode **ficar em silêncio** quando a fala não é dirigida a ele ou não tem relação com o assunto. Junto com isso, uma instrução no prompt: "na continuação, só responda se falarem com você ou sobre o assunto em andamento; caso contrário, fique em silêncio".
3. **Contexto do assunto:** a sessão recebe o texto do último áudio tocado, para o modelo distinguir continuação ("então abre o PR") de conversa alheia ("o jantar tá pronto?").
4. **Tarefas de código na continuação vão direto ao Claude Code, sem confirmação** (decisão do usuário). Isso amplia o risco descrito em §8.

Se o modelo ficar em silêncio (fala não relacionada), a janela fecha normalmente.

### 5.3 Papel de cada parte

| Parte | Responsabilidade |
|---|---|
| **ESP32-S3** | Wake word local; streaming do mic durante a sessão; manter a conexão WSS sempre aberta, com reconexão automática; repassar o áudio recebido ao notebook pela USB. |
| **Servidor de voz (Pipecat)** | Autenticar a placa; montar o pipeline de voz com o provedor configurado; **executar** a ferramenta quando o modelo pedir (o provedor só *pede*, quem roda é o servidor); fila do Claude Code; gerar o TTS do resultado e enviar à placa. |
| **Gemini Live** | A "recepcionista": conversa, responde perguntas gerais e **decide** quando delegar ao Claude Code. |
| **Claude Code** | Tudo que é código: escolher o projeto, alterar, PR, merge, produção. Gera a resposta final para ser falada. |
| **Notebook** | Temporário: recebe o áudio da placa pela USB e toca. |

### 5.4 Áudio no notebook (temporário)

Até chegar o alto-falante, a placa repassa pela **USB serial** o áudio que recebe da VPS, e um script Python no notebook toca nos alto-falantes. Quando o MAX98357A chegar, só esse último trecho muda: a placa passa a tocar direto via I2S.

## 6. Claude Code no container

- **Instalação nova, dentro do container de voz.** A instalação existente no container do Hermes foi só para testes e **não é usada**.
- **Login pela assinatura** do Claude (não chave de API).
- **Volume persistente próprio** para `~/.claude` (memória, configuração, login) e para a pasta de projetos (`workspace/`). Um dia o Hermes pode montar esse mesmo volume para compartilhar os projetos.
- **Acesso ao GitHub:** os projetos do usuário estão no GitHub. O container tem `git` e `gh` com um token do GitHub, para clonar, criar branches e PRs e fazer merge.
- **Produção:** o Dokploy faz o deploy a partir da branch `main`. Um merge feito pelo Claude Code **vai para produção**. A decisão é do Claude Code, que informa isso na resposta.
- **Memória inicial:** escolha minha (*decisão do builder*): começar copiando o `CLAUDE.md` da instalação de testes do Hermes, que já documenta os projetos e os recursos que eles usam.

## 7. Infraestrutura (VPS)

Levantamento feito em 2026-11-17, só leitura:

- VPS Linux acessada por SSH, com recursos de sobra para mais um container.
- **Dokploy** gerencia os containers, e o **Traefik** faz o roteamento por domínio com HTTPS.
- O host **não tem Node nem Claude Code** instalados. Tudo fica no container.
- O novo serviço será **mais um projeto compose no Dokploy**, com domínio próprio no Traefik e WSS para a placa.
- Se o Claude Code precisar consultar o banco de dados de um projeto (como na instalação de testes), o container precisa entrar na **mesma rede Docker** do banco.

## 7.1 Stack do servidor e provedor de voz trocável

**Decisão do usuário:** servidor em **Python** com o framework **Pipecat**, e **Gemini Live API** como provedor de voz.

- O Pipecat monta o pipeline de voz (transporte → provedor → transporte) e já tem serviços prontos para **Gemini Live** e **OpenAI Realtime**. A troca de provedor fica na **configuração**, não no código da aplicação.
- Provedor, modelo, voz e serviço de TTS são escolhidos por **variáveis de ambiente** (ex.: `PROVEDOR_VOZ=gemini|openai`, `MODELO_VOZ=...`, `VOZ=...`). Nomes de modelo **nunca** ficam fixos no código, porque os modelos do Gemini Live mudam e são aposentados com frequência.
- A lógica própria do projeto (autenticação da placa, fila do Claude Code, entrega de resultados) **não depende** do provedor escolhido.
- Formato interno de áudio: **PCM 16 bits mono 16 kHz** na entrada (o que a placa envia e o que o Gemini aceita nativamente). O Gemini responde em PCM 24 kHz.
- Na primeira versão, o provedor **Gemini** é implementado e testado. A OpenAI fica como alternativa configurável. Ela deve funcionar trocando a configuração, mas não precisa ser validada agora.

## 7.2 Memória: `CONTEXTO.md` e histórico (decisão do usuário, 2026-11-18)

Para não precisar explicar tudo sempre, toda sessão de voz começa com uma "memória" anexada à instrução de sistema:

1. **`CONTEXTO.md`:** arquivo de texto livre escrito pelo usuário (nome, preferências, projetos, como quer as respostas). Ele é lido **a cada sessão**, então editar o arquivo vale na próxima conversa, sem reiniciar.
2. **As últimas 5 trocas** (5 pares pergunta → resposta), marcadas como **só referência**. O modelo não deve retomar esses assuntos se o usuário não pedir.

**O que entra no histórico:**
- Cada par **pergunta → resposta** de conversa. Os textos vêm das **transcrições** que o Gemini Live já envia (o Pipecat liga a transcrição de entrada e de saída por padrão; o custo é de texto, desprezível perto do áudio).
- Cada **resultado do Claude Code**: o pedido e a resposta falada.

**Arquivo `historico.jsonl`** (uma troca por linha: `ts`, `origem` = `conversa` | `claude_code`, `pergunta`, `resposta`):
- **Rotação:** quando o arquivo atual atingiria **10 MB**, ele é renomeado e um arquivo novo e vazio começa. Os antigos ficam como `historico.1.jsonl` (o imediatamente anterior), `historico.2.jsonl` e assim por diante.
- **No máximo 7 arquivos** no total (o atual + 6 antigos). O mais antigo é apagado.
- **Leitura das últimas 5:** se o arquivo atual tiver menos de 5 trocas, completa com as mais recentes do **imediatamente anterior** (`historico.1.jsonl`).
- Linhas corrompidas são ignoradas, sem derrubar o servidor.

**Onde ficam os arquivos:** na pasta `MEMORIA_DIR` (padrão `/home/voz/assistente`, dentro do volume persistente). Localmente, `memoria/` na raiz do projeto, fora do git.

## 8. Segurança

- A conexão placa ↔ servidor exige um **token secreto**. Sem o token, a conexão é recusada.
- Chaves (Google/Gemini, GitHub, token do Claude) ficam só em **variáveis de ambiente** do Dokploy, nunca no código nem no firmware. A exceção é o token da placa, que vai no firmware.
- **Risco conhecido e aceito por enquanto:** qualquer voz que diga "Hi ESP" perto da placa (uma visita ou um vídeo) pode disparar uma tarefa que chega até produção. A única proteção atual é a placa estar fisicamente na mesa do usuário.
- **Risco ampliado e aceito pelo usuário:** na janela de continuação (§5.2.1) não há wake word, e as tarefas de código vão direto ao Claude Code. Uma conversa da casa mal interpretada pelo modelo pode disparar uma tarefa. As mitigações são a janela curta, o Proactive Audio e o contexto do assunto.

## 9. Decisões do builder (escolhas minhas, revisáveis)

| Tema | Escolha | Por quê |
|---|---|---|
| Transporte placa ↔ servidor | **WebSocket (WSS)** com mensagens binárias (áudio) e JSON (controle), via transporte WebSocket do Pipecat | Simples na Arduino IDE e passa pelo Traefik. |
| Formato de áudio placa → servidor | PCM 16 bits, 16 kHz, mono | É o que o mic já produz e o que o Gemini aceita. |
| Formato de áudio servidor → placa | PCM 16 bits mono, na taxa de saída do provedor (24 kHz no Gemini) | O notebook toca qualquer taxa. Revisar quando houver MAX98357A. |
| TTS do resultado | TTS do Gemini, configurável | Mesmo provedor e mesma chave. Mais barato que abrir sessão de conversa. |
| Sessão no provedor | Aberta **só durante a conversa** (do "Hi ESP" ou do início de uma janela de continuação até a janela fechar), não durante toda a conexão da placa | Evita custo com sessão ociosa e respeita os limites de duração das sessões Live. |
| Duração da janela de continuação | **8 s**, configurável por variável de ambiente | Tempo suficiente para começar a responder, curto o bastante para não captar a casa à toa. |
| Duplex | **Meio-duplex**: a placa não envia áudio do mic enquanto toca resposta | Evita o mic ouvir o alto-falante (sem cancelamento de eco por enquanto). |
| Várias tarefas ao mesmo tempo | **Fila**: uma tarefa do Claude Code por vez; as outras esperam e a voz avisa "tarefa na fila" | Evita duas tarefas mexendo no mesmo repositório. |
| Resultado chega enquanto há conversa em andamento | Espera a conversa terminar e então fala | Não atropelar a conversa. |
| Placa offline quando o resultado fica pronto | Guarda o resultado e entrega ao reconectar | Nada se perde. |
| Instrução ao modelo de voz | Prompt de sistema: "pedidos de programação → sempre `tarefa_de_codigo` com o pedido literal; nunca responda programação por conta própria" | Atende aos anti-objetivos. |
| Wake word na placa durante a sessão | O ESP-SR é pausado enquanto a sessão está aberta, e o firmware lê o I2S diretamente | O ESP-SR consome o I2S. |

## 10. Notas para quem for construir

- **Claude Code sem interação:** `claude -p "<pedido>" --output-format json`. Para rodar sem pedir permissão, use o modo de permissões apropriado. O Claude Code **recusa rodar com permissões liberadas como root**, então o container deve usar um **usuário não-root**.
- **Login por assinatura sem navegador:** gerar um token de longa duração com `claude setup-token` (feito uma vez pelo usuário) e passá-lo ao container pela variável `CLAUDE_CODE_OAUTH_TOKEN`.
- **Ferramenta do modelo de voz:** o provedor **não executa** a ferramenta. Ele envia um evento de chamada de função pela sessão, e o servidor responde com o resultado. Como a tarefa é longa, o servidor responde na hora com "tarefa recebida" e trata o resultado real depois (§5.2). O Gemini Live suporta chamadas de função assíncronas, o que combina com esse fluxo.
- **Pipecat + placa:** a placa envia PCM cru, não o formato de nenhum cliente Pipecat pronto. Provavelmente será preciso um **serializador próprio** (frames binários = áudio, frames de texto = JSON de controle) no transporte WebSocket do Pipecat.
- **Conexão permanente vs. pipeline:** a conexão da placa fica sempre aberta, mas a sessão no provedor só existe durante a conversa (§9). O servidor precisa gerenciar esses dois ciclos de vida separadamente, inclusive para empurrar o áudio do resultado fora de uma conversa.
- **Proactive Audio:** documentado no Vertex AI (`proactivity.proactive_audio = true` na configuração da sessão, só em modelos de áudio nativo). **Confirmar** se o modelo usado pela API do AI Studio suporta e como o Pipecat expõe a opção. Se não houver suporte, a janela curta e a instrução no prompt passam a ser as únicas proteções, e o usuário deve ser avisado.
- **Janela de continuação na placa:** quando o áudio recebido termina de tocar, a placa envia o mic por até N segundos sem passar pelo ESP-SR. O servidor avisa a placa quando a janela fecha.
- **ESP-SR + I2S:** o firmware atual (`WakeWordESP`) usa `I2S_RX_TRANSFORM_32_TO_16`. Durante a sessão, pausar o ESP-SR e ler o I2S diretamente com o mesmo formato.
- **Reconexão:** a placa precisa reconectar o WebSocket sozinha (Wi-Fi caiu, deploy do container etc.).

## 11. Pendências (o usuário precisa fornecer)

1. **Chave da API do Google Gemini** (Google AI Studio), com faturamento ativo se necessário para os limites de uso.
2. **Token do GitHub** com acesso aos repositórios (e permissão de merge, se for o caso).
3. **Token do Claude** gerado com `claude setup-token` na assinatura.
4. **Domínio** para o serviço de voz (ex.: `voz.seudominio.com.br`) apontando para a VPS.
5. **Wi-Fi** (SSID e senha) para o firmware da placa.
6. *(Opcional, futuro)* Chave da OpenAI, só se for testar o provedor alternativo.

## 12. Estado atual do hardware e firmware (referência)

- Placa: YD-ESP32-S3 N16R8. Mic INMP441 em WS=GPIO4, SCK=GPIO5, SD=GPIO8, L/R=GND.
- LEDs utilizáveis: TX (GPIO43) e RX (GPIO44), acendem com LOW. RGB no GPIO48 inativo (jumper aberto).
- Firmware de referência funcionando: `D:\Repositorios\Arduino\WakeWordESP` ("Hi ESP" + comandos), partição **ESP SR 16M**.
- Porta atual da placa no notebook: **COM4**.
