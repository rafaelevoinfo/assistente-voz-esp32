// =============================================================
//  Assistente de voz "Hi ESP" - firmware da placa (contrato v1)
//  ESP32-S3 N16R8 + INMP441. Contrato: docs/contrato.md
//
//  DECISAO (Task 9, Step 2) - ESP_SR.pause() x end()/begin():
//    Usamos ESP_SR.pause()/resume(). Lendo o esp32-hal-sr.c do core 3.3.12:
//    - pause() so liga os bits PAUSE_FEED|PAUSE_DETECT; a "SR Feed Task"
//      termina a leitura em andamento (1 bloco = 32 ms), volta ao topo do
//      laco e fica bloqueada em xEventGroupWaitBits ate o resume(). A partir
//      dai ninguem mais chama i2s.readBytes(), entao o firmware le o I2S
//      direto, no MESMO formato (32->16 bits), sem reconfigurar nada. O canal
//      I2S nao e desligado (o DMA continua rodando).
//    - Por isso, apos pause() esperamos ~80 ms antes da primeira leitura.
//    - pause()/resume() precisam ser SEMPRE em pares: um resume() sem pause()
//      deixa o bit RESUME_FEED ligado e o proximo pause() nao pausaria nada.
//      audio.cpp controla isso com a flag srPausado.
//    - O _fill do ESP_SR muda o timeout do I2S para portMAX_DELAY; antes de
//      ler direto voltamos o timeout para 100 ms.
//    - Ao detectar a wake word, o ESP-SR (evento CHANNEL_VERIFIED) chama
//      sr_set_mode(SR_MODE_OFF) e desliga a WakeNet. Ao voltar para
//      ESPERANDO_WAKE fazemos setMode(OFF) -> setMode(WAKEWORD) antes do
//      resume(), e o loop reativa a WakeNet se o evento chegar atrasado.
//    - end()/begin() NAO foi usado: recarregaria os modelos a cada sessao
//      (lento e fragmenta a memoria) e o end() bloqueia esperando a feed task.
//
//  Estados (contrato §1.5):
//    ESPERANDO_WAKE   ESP-SR ativo. "Hi ESP" -> pause, envia wake ->
//    AGUARDANDO_LISTEN ESP-SR pausado; espera listen (15 s, senao volta)
//    ENVIANDO_MIC     le o I2S em frames de 20 ms (640 bytes) e envia
//    SILENCIO         depois de stop_listen; espera audio/listen/session_end
//    + "reproducao" (ortogonal): entre audio_start e o playback_done a placa
//      nunca envia mic; um listen que chegue nesse meio e adiado.
//    session_end (qualquer estado) e queda da conexao -> ESPERANDO_WAKE.
//
//  LED RGB (WS2812 no GPIO48; exige o jumper "RGB" da placa fechado):
//    vermelho = sem conexao (Wi-Fi ou servidor)
//    verde    = conectado, esperando "Hi ESP"
//    azul     = ouvindo (AGUARDANDO_LISTEN ou ENVIANDO_MIC)
//  Os LEDs TX/RX (GPIO43/44) nao sao mais usados.
//
//  SOM (fw 2.0): o audio das respostas sai no alto-falante da propria placa
//    (MAX98357A no segundo I2S, ver alto_falante.h). O playback_done e enviado
//    quando o ultimo pedaco do audio sai no alto-falante. A Serial ficou so
//    para os LOGs.
//
//  SINAL "ESTOU OUVINDO": ao detectar "Hi ESP" a placa toca um bipe curto
//    (3 notas) no alto-falante. A janela de continuacao apos uma resposta so
//    acende o LED, sem som. Por BEEP_MUDO_MS o mic e descartado para o proprio
//    bipe nao chegar ao servidor como se fosse fala.
//
//  TAMANHO: ESP-SR + Wi-Fi + TLS da ~3,2 MB e NAO cabe no app de 3 MB da
//    "ESP SR 16M". O partitions.csv desta pasta (prioridade sobre o esquema
//    do menu) usa um app de 6 MB e mantem "model" em 0xC10000.
//  Compilar/gravar pelo arduino-cli (grava tambem os modelos de voz):
//    arduino-cli compile --fqbn "esp32:esp32:esp32s3:CDCOnBoot=cdc,FlashSize=16M,PSRAM=opi,PartitionScheme=esp_sr_16"
//        --build-property "upload.maximum_size=6291456" firmware/AssistenteVoz
//    arduino-cli upload -p COM4 --fqbn "<mesmo FQBN>" firmware/AssistenteVoz
//  Pela Arduino IDE: ESP32S3 Dev Module | USB CDC On Boot: Enabled |
//    Flash 16MB | PSRAM: OPI PSRAM | Partition Scheme: "Custom" (usa o
//    partitions.csv, limite 16 MB). Nesse modo a IDE nao grava os modelos,
//    mas eles ja estao em 0xC10000 desde o WakeWordESP (mesmo endereco).
//    (Com "ESP SR 16M" a IDE recusa: "Sketch too big".)
//  Biblioteca: WebSockets (Markus Sattler / links2004)
//  Configuracao: copie config.example.h para config.h.
// =============================================================

#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>

#if __has_include("config.h")
#include "config.h"
#else
#error "Copie config.example.h para config.h e preencha."
#endif

#include "alto_falante.h"
#include "audio.h"
#include "notebook.h"

#define FW_VERSAO "2.0"

// Potenciometro de volume (10 kΩ): pontas no 3V3 e no GND, pino do meio no
// GPIO10 (ADC1, que funciona junto com o Wi-Fi). -1 no config.h = sem potenciometro.
#ifndef POT_VOLUME_PINO
#define POT_VOLUME_PINO 10
#endif
#define POT_INTERVALO_MS  50
#define POT_HISTERESE     4    // % minima de mudanca (evita o volume "tremer")

#define LED_RGB_PINO  48
#define LED_BRILHO    25   // 0-255 (o WS2812 e muito forte; 25 ja e bem visivel)

#define RECONEXAO_MS            3000
#define RECONEXAO_AUTH_MS       30000   // depois de 4401
#define CONEXAO_CURTA_MS        5000    // ver aoDesconectar()
#define PING_INTERVALO_MS       15000
#define PONG_TIMEOUT_MS         3000
#define PONG_FALHAS             2
#define PLAYBACK_FOLGA_MS       3000
#define AGUARDA_LISTEN_MAX_MS   15000

enum Estado { ESPERANDO_WAKE, AGUARDANDO_LISTEN, ENVIANDO_MIC, SILENCIO };
static const char *NOMES_ESTADO[] = {"ESPERANDO_WAKE", "AGUARDANDO_LISTEN", "ENVIANDO_MIC", "SILENCIO"};

WebSocketsClient ws;

static Estado estado = ESPERANDO_WAKE;
static bool conectado = false;
static uint32_t conectouEm = 0;
static bool recebeuDoServidor = false;   // alguma mensagem nesta conexao
static uint32_t estadoDesde = 0;

// Reproducao (contrato §1.6)
static bool recebendoAudio = false;      // entre audio_start e audio_end
static int taxaAudio = 24000;
static bool tocandoFim = false;          // audio_end recebido; esperando o som acabar
static uint32_t bytesPendentes = 0;      // audio da resposta atual
static uint32_t prazoPlayback = 0;       // millis() limite de seguranca para o playback_done
static bool listenAdiado = false;

static int16_t frameMic[MIC_AMOSTRAS_FRAME];

// Bipe ~310 ms + DMA do I2S (60 ms) + folga
#define BEEP_MUDO_MS 450
static uint32_t micMudoAte = 0;

static bool ouvindo(Estado e) { return e == AGUARDANDO_LISTEN || e == ENVIANDO_MIC; }

// Fila do mic (PSRAM). Desde o "Hi ESP" a placa ja grava o mic na fila, para nao
// perder o comeco da fala enquanto o servidor conecta ao provedor (~1-2 s ate o
// listen). Em ENVIANDO_MIC cada frame novo entra na fila e saem ate
// FILA_MIC_SAIDA_POR_LOOP frames: o atraso acumulado e recuperado sem perder audio.
#define FILA_MIC_FRAMES         200   // 4 s (200 x 20 ms) = 128 KB
#define FILA_MIC_SAIDA_POR_LOOP 5
static int16_t (*filaMic)[MIC_AMOSTRAS_FRAME] = nullptr;
static int filaInicio = 0, filaQtd = 0;

static void filaLimpar() { filaInicio = 0; filaQtd = 0; }

static void filaInserir(const int16_t *frame) {
  if (!filaMic) return;
  if (filaQtd == FILA_MIC_FRAMES) {  // cheia: descarta o mais antigo
    filaInicio = (filaInicio + 1) % FILA_MIC_FRAMES;
    filaQtd--;
  }
  memcpy(filaMic[(filaInicio + filaQtd) % FILA_MIC_FRAMES], frame, sizeof(frameMic));
  filaQtd++;
}

static const int16_t *filaRetirar() {
  if (!filaMic || filaQtd == 0) return nullptr;
  const int16_t *f = filaMic[filaInicio];
  filaInicio = (filaInicio + 1) % FILA_MIC_FRAMES;
  filaQtd--;
  return f;
}

// ------------------------------------------------------------------ util

static void ledCor(uint8_t r, uint8_t g, uint8_t b) {
  static uint32_t atual = 0xFFFFFFFF;
  uint32_t nova = ((uint32_t)r << 16) | ((uint32_t)g << 8) | b;
  if (nova == atual) return;  // so reescreve o LED quando a cor muda
  atual = nova;
  rgbLedWrite(LED_RGB_PINO, r, g, b);
}

// Cor do LED a partir do estado atual (vermelho/verde/azul).
static void atualizarLed() {
  if (!conectado) ledCor(LED_BRILHO, 0, 0);
  else if (ouvindo(estado)) ledCor(0, 0, LED_BRILHO);
  else ledCor(0, LED_BRILHO, 0);
}

static void checarHeap(const char *ponto);

static void mudarEstado(Estado novo) {
  if (novo == estado) return;
  checarHeap("antes de mudarEstado");
  logMsg("estado: %s -> %s", NOMES_ESTADO[estado], NOMES_ESTADO[novo]);
  Estado anterior = estado;
  estado = novo;
  estadoDesde = millis();
  atualizarLed();
  // Sinal sonoro so depois do "Hi ESP" (a janela de continuacao apos uma
  // resposta acende o LED, mas sem som: o usuario achou irritante).
  if (novo == AGUARDANDO_LISTEN && !ouvindo(anterior)) {
    altoFalanteBeep();
    micMudoAte = millis() + BEEP_MUDO_MS;
  }
  // A fila so sobrevive a passagem AGUARDANDO_LISTEN -> ENVIANDO_MIC.
  if (!(anterior == AGUARDANDO_LISTEN && novo == ENVIANDO_MIC)) filaLimpar();
  if (estado == ESPERANDO_WAKE) {
    audioRetomarWake();
  } else {
    audioPausarWake();
  }
  checarHeap("depois de mudarEstado");
}

static bool tocando() { return recebendoAudio || tocandoFim; }

static void enviarTipo(const char *tipo) {
  char msg[48];
  snprintf(msg, sizeof(msg), "{\"type\":\"%s\"}", tipo);
  ws.sendTXT(msg);
  logMsg("-> %s", tipo);
}

// Extrai o valor de "campo" (string) de um JSON simples e plano.
static bool jsonCampo(const char *json, const char *campo, char *saida, size_t tam) {
  char chave[24];
  snprintf(chave, sizeof(chave), "\"%s\"", campo);
  const char *p = strstr(json, chave);
  if (!p) return false;
  p += strlen(chave);
  while (*p == ' ' || *p == '\t') p++;
  if (*p != ':') return false;
  p++;
  while (*p == ' ' || *p == '\t') p++;
  size_t n = 0;
  if (*p == '"') {
    p++;
    while (*p && *p != '"' && n < tam - 1) saida[n++] = *p++;
    if (*p != '"') return false;
  } else {
    while (*p && *p != ',' && *p != '}' && *p != ' ' && n < tam - 1) saida[n++] = *p++;
  }
  saida[n] = '\0';
  return n > 0;
}

// ------------------------------------------------- diagnostico de memoria
// Procura quem corrompe o heap interno: confere a integridade em varios pontos
// do loop e registra o primeiro ponto em que a corrupcao aparece.
#include <esp_heap_caps.h>
static const char *ultimoPontoOk = "inicio";
static bool heapOk = true;

static void checarHeap(const char *ponto) {
  if (!heapOk) return;
  if (heap_caps_check_integrity(MALLOC_CAP_INTERNAL, false)) {
    ultimoPontoOk = ponto;
    return;
  }
  heapOk = false;
  logMsg("HEAP CORROMPIDO: detectado em '%s' (ultimo ponto ok: '%s')", ponto, ultimoPontoOk);
}

// ---------------------------------------------------------- potenciometro

static void lerPotenciometro() {
#if POT_VOLUME_PINO >= 0
  static uint32_t ultimaLeitura = 0, ultimoLog = 0;
  static float media = -1;
  static int pctAplicado = -100, pctLogado = -100;
  if (millis() - ultimaLeitura < POT_INTERVALO_MS) return;
  ultimaLeitura = millis();

  int bruto = analogRead(POT_VOLUME_PINO);  // 0..4095
  media = media < 0 ? bruto : media * 0.85f + bruto * 0.15f;  // suaviza o ruido do ADC
  int pct = (int)(media * 100.0f / 4095.0f + 0.5f);
  if (pct > 98) pct = 100;  // as pontas do curso nem sempre chegam a 0/4095
  if (pct < 2) pct = 0;
  if (abs(pct - pctAplicado) < POT_HISTERESE && pct != 0 && pct != 100) return;
  if (pct == pctAplicado) return;
  pctAplicado = pct;
  altoFalanteVolume(pct);
  if (pct != pctLogado && millis() - ultimoLog > 300) {
    logMsg("volume: %d%%", pct);
    pctLogado = pct;
    ultimoLog = millis();
  }
#endif
}

// Motivo do ultimo reinicio (diagnostico de quedas de energia x travamentos).
static const char *motivoReset() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON:   return "ligou a energia (ou o USB reconectou)";
    case ESP_RST_EXT:       return "pino de reset externo";
    case ESP_RST_SW:        return "reinicio por software (ex.: apos gravar)";
    case ESP_RST_PANIC:     return "TRAVAMENTO (panic/Guru Meditation)";
    case ESP_RST_INT_WDT:   return "TRAVAMENTO (watchdog de interrupcao)";
    case ESP_RST_TASK_WDT:  return "TRAVAMENTO (watchdog de task)";
    case ESP_RST_WDT:       return "TRAVAMENTO (watchdog)";
    case ESP_RST_BROWNOUT:  return "QUEDA DE TENSAO (brownout: a fonte nao aguentou)";
    case ESP_RST_DEEPSLEEP: return "saiu do deep sleep";
    case ESP_RST_USB:       return "reset pelo USB (ex.: RTS do upload)";
    default:                return "desconhecido";
  }
}

// ------------------------------------------------------------ reproducao

static void enviarPlaybackDone(const char *motivo) {
  logMsg("reproducao concluida (%s)", motivo);
  tocandoFim = false;
  bytesPendentes = 0;
  enviarTipo("playback_done");
  if (listenAdiado) {
    listenAdiado = false;
    logMsg("executando listen adiado");
    mudarEstado(ENVIANDO_MIC);
  }
}

static void abortarReproducao() {
  altoFalanteAbortar();
  recebendoAudio = false;
  tocandoFim = false;
  bytesPendentes = 0;
  listenAdiado = false;
}

// ------------------------------------------------------------- mensagens

static void aoTexto(const char *json) {
  char tipo[24];
  if (!jsonCampo(json, "type", tipo, sizeof(tipo))) {
    logMsg("JSON invalido ignorado: %.80s", json);
    return;
  }
  logMsg("<- %s", tipo);

  if (strcmp(tipo, "listen") == 0) {
    if (tocando()) {
      logMsg("listen durante reproducao: adiado ate o playback_done");
      listenAdiado = true;
    } else {
      mudarEstado(ENVIANDO_MIC);
    }
  } else if (strcmp(tipo, "stop_listen") == 0) {
    listenAdiado = false;
    if (estado == ENVIANDO_MIC || estado == AGUARDANDO_LISTEN) mudarEstado(SILENCIO);
  } else if (strcmp(tipo, "session_end") == 0) {
    listenAdiado = false;
    mudarEstado(ESPERANDO_WAKE);
  } else if (strcmp(tipo, "audio_start") == 0) {
    char rate[12];
    taxaAudio = jsonCampo(json, "rate", rate, sizeof(rate)) ? atoi(rate) : 24000;
    if (taxaAudio <= 0) taxaAudio = 24000;
    if (estado == ENVIANDO_MIC) {
      logMsg("audio_start com o mic aberto: parando o mic (meio-duplex)");
      mudarEstado(SILENCIO);
    }
    recebendoAudio = true;
    bytesPendentes = 0;
    altoFalanteComecar(taxaAudio);
    logMsg("memoria: heap interno livre %u (min %u), pilha do loop livre %u",
           (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
           (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL),
           (unsigned)uxTaskGetStackHighWaterMark(NULL));
  } else if (strcmp(tipo, "audio_end") == 0) {
    if (!recebendoAudio) {
      logMsg("audio_end sem audio_start: ignorado");
      return;
    }
    recebendoAudio = false;
    altoFalanteFim();
    tocandoFim = true;
    // Prazo de seguranca: o audio inteiro ja pode estar no buffer, entao nunca
    // demora mais que a sua duracao (+ folga) para terminar de tocar.
    uint32_t duracaoMs = (uint32_t)((uint64_t)bytesPendentes * 1000 / (taxaAudio * 2));
    prazoPlayback = millis() + duracaoMs + PLAYBACK_FOLGA_MS;
    logMsg("audio de %u ms recebido; tocando", (unsigned)duracaoMs);
  } else {
    logMsg("tipo desconhecido ignorado: %s", tipo);
  }
}

static void aoBinario(const uint8_t *dados, size_t n) {
  if (!recebendoAudio) {
    logMsg("audio fora de audio_start/audio_end ignorado (%u bytes)", (unsigned)n);
    return;
  }
  checarHeap("antes de altoFalanteAudio");
  altoFalanteAudio(dados, n);
  checarHeap("depois de altoFalanteAudio");
  bytesPendentes += n;
}

static void aoConectar() {
  conectado = true;
  conectouEm = millis();
  recebeuDoServidor = false;
  atualizarLed();
  logMsg("conectado ao servidor");
  char hello[48];
  snprintf(hello, sizeof(hello), "{\"type\":\"hello\",\"fw\":\"%s\"}", FW_VERSAO);
  ws.sendTXT(hello);
  logMsg("-> hello");
}

static void aoDesconectar(const char *motivo) {
  bool estavaConectado = conectado;
  conectado = false;
  atualizarLed();
  abortarReproducao();
  mudarEstado(ESPERANDO_WAKE);

  // A biblioteca WebSockets nao repassa o codigo de fechamento (4401/4000).
  // Tratamos como token recusado (4401) -> nova tentativa em 30 s:
  //  - handshake recusado com HTTP 401/403 (servidor que fecha antes do accept);
  //  - conexao que cai em menos de 5 s sem receber nenhuma mensagem.
  // Conexoes validas ficam abertas indefinidamente; um 4000 (substituida)
  // so acontece em conexao longa -> reconexao normal em 3 s.
  bool recusaHttp = motivo && (strstr(motivo, "HTTP 401") || strstr(motivo, "HTTP 403"));
  bool provavel4401 = recusaHttp || (estavaConectado && !recebeuDoServidor &&
                                     (millis() - conectouEm) < CONEXAO_CURTA_MS);
  if (motivo && *motivo) logMsg("WebSocket: %s", motivo);
  if (provavel4401) {
    logMsg("ERRO: servidor fechou a conexao logo apos abrir (token invalido? 4401). Nova tentativa em 30 s");
    ws.setReconnectInterval(RECONEXAO_AUTH_MS);
  } else {
    if (estavaConectado) logMsg("desconectado do servidor; reconectando em 3 s");
    ws.setReconnectInterval(RECONEXAO_MS);
  }
}

static void aoEventoWs(WStype_t tipo, uint8_t *payload, size_t tamanho) {
  switch (tipo) {
    case WStype_CONNECTED:
      aoConectar();
      break;
    case WStype_DISCONNECTED: {
      char motivo[64] = "";
      if (payload && tamanho > 0) {
        size_t n = tamanho < sizeof(motivo) - 1 ? tamanho : sizeof(motivo) - 1;
        memcpy(motivo, payload, n);
        motivo[n] = 0;
      }
      aoDesconectar(motivo);
      break;
    }
    case WStype_TEXT: {
      recebeuDoServidor = true;
      char buf[256];
      size_t n = tamanho < sizeof(buf) - 1 ? tamanho : sizeof(buf) - 1;
      memcpy(buf, payload, n);
      buf[n] = '\0';
      aoTexto(buf);
      break;
    }
    case WStype_BIN:
      recebeuDoServidor = true;
      aoBinario(payload, tamanho);
      break;
    case WStype_ERROR:
      logMsg("erro no WebSocket");
      break;
    case WStype_FRAGMENT_TEXT_START:
    case WStype_FRAGMENT_BIN_START:
    case WStype_FRAGMENT:
    case WStype_FRAGMENT_FIN:
      recebeuDoServidor = true;
      logMsg("frame fragmentado ignorado");
      break;
    default:
      break;
  }
}

// ------------------------------------------------------------- setup/loop

static void iniciarWifi() {
  // Registra o motivo de cada falha (ex.: 15/204 = senha errada, 201 = rede nao encontrada).
  WiFi.onEvent([](WiFiEvent_t, WiFiEventInfo_t info) {
    logMsg("Wi-Fi falhou, motivo %d", info.wifi_sta_disconnected.reason);
  }, ARDUINO_EVENT_WIFI_STA_DISCONNECTED);
  logMsg("senha do Wi-Fi tem %d caracteres", (int)strlen(WIFI_SENHA));
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // menor latencia no streaming
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_SENHA);
  logMsg("conectando ao Wi-Fi '%s'...", WIFI_SSID);
}

static void iniciarWebSocket() {
  static const char *caminho = "/ws?token=" TOKEN_PLACA;
#if SERVIDOR_TLS
  ws.beginSSL(SERVIDOR_HOST, SERVIDOR_PORTA, caminho);
  logMsg("servidor: wss://%s:%d/ws", SERVIDOR_HOST, SERVIDOR_PORTA);
#else
  ws.begin(SERVIDOR_HOST, SERVIDOR_PORTA, caminho);
  logMsg("servidor: ws://%s:%d/ws", SERVIDOR_HOST, SERVIDOR_PORTA);
#endif
  ws.onEvent(aoEventoWs);
  ws.setReconnectInterval(RECONEXAO_MS);
  ws.enableHeartbeat(PING_INTERVALO_MS, PONG_TIMEOUT_MS, PONG_FALHAS);
}

// O TLS (mbedTLS) roda dentro do ws.loop(): a pilha padrao de 8 KB do loop()
// estoura e corrompe o heap (crash "Cache error" no malloc do Wi-Fi).
// (fica aqui, e nao no topo, porque a macro define uma funcao e o
// pre-processador do Arduino poria os prototipos antes do enum Estado)
SET_LOOP_TASK_STACK_SIZE(16 * 1024);

void setup() {
  ledCor(LED_BRILHO, 0, 0);  // vermelho: ainda sem conexao

  notebookIniciar();
  delay(1500);
  logMsg("Assistente de voz fw %s iniciando", FW_VERSAO);
  logMsg("motivo do ultimo reinicio: %s (codigo %d)", motivoReset(), (int)esp_reset_reason());

  filaMic = (int16_t (*)[MIC_AMOSTRAS_FRAME])ps_malloc(FILA_MIC_FRAMES * sizeof(frameMic));
  if (!filaMic) logMsg("AVISO: sem PSRAM para a fila do mic; o comeco da fala pode ser cortado");

  if (altoFalanteIniciar()) {
    altoFalanteBeep();  // teste: o bipe ao ligar confirma que o alto-falante funciona
  } else {
    logMsg("AVISO: sem alto-falante; as respostas nao vao tocar");
  }

  if (!audioIniciar()) {
    while (true) {
      logMsg("ERRO fatal no audio; reinicie a placa");
      delay(5000);
    }
  }
  estadoDesde = millis();
  iniciarWifi();
  iniciarWebSocket();
  logMsg("pronto: diga \"Hi ESP\"");
}

void loop() {
  static bool wifiOk = false;
  bool wifiAgora = WiFi.status() == WL_CONNECTED;
  if (wifiAgora != wifiOk) {
    wifiOk = wifiAgora;
    if (wifiOk) {
      logMsg("Wi-Fi conectado, IP %s", WiFi.localIP().toString().c_str());
    } else {
      logMsg("Wi-Fi desconectado");
    }
  }

  checarHeap("topo do loop");
  ws.loop();
  checarHeap("depois do ws.loop");
  audioManutencao();
  lerPotenciometro();
  checarHeap("depois do potenciometro");

  // Wake word
  if (audioPegarWake()) {
    if (estado != ESPERANDO_WAKE) {
      // evento atrasado; ignorado
    } else if (!conectado) {
      logMsg("\"Hi ESP\" detectado, mas sem conexao com o servidor");
    } else if (tocando()) {
      logMsg("\"Hi ESP\" ignorado: tocando audio");
    } else {
      logMsg("\"Hi ESP\" detectado");
      mudarEstado(AGUARDANDO_LISTEN);
      enviarTipo("wake");
    }
  }

  if (estado == AGUARDANDO_LISTEN && millis() - estadoDesde > AGUARDA_LISTEN_MAX_MS) {
    logMsg("servidor nao respondeu ao wake; voltando a esperar \"Hi ESP\"");
    mudarEstado(ESPERANDO_WAKE);
  }

  // Fim do som da resposta -> playback_done
  if (altoFalanteTerminou() && tocandoFim && !recebendoAudio) {
    char resumo[160];
    altoFalanteResumo(resumo, sizeof(resumo));
    logMsg("alto-falante: %s", resumo);
    if (conectado) enviarPlaybackDone("alto-falante");
  }
  if (tocandoFim && !recebendoAudio && (int32_t)(millis() - prazoPlayback) >= 0) {
    logMsg("o alto-falante nao terminou a tempo; seguindo assim mesmo");
    altoFalanteAbortar();
    if (conectado) enviarPlaybackDone("timeout");
    else abortarReproducao();
  }

  // Mic -> fila -> servidor (bloqueia ~20 ms por frame: ritmo natural do loop)
  bool micMudo = (int32_t)(millis() - micMudoAte) < 0;  // descarta o proprio bipe
  if (estado == AGUARDANDO_LISTEN) {
    if (audioLerFrame(frameMic) && !micMudo) filaInserir(frameMic);
    checarHeap("leitura do mic (aguardando)");
  } else if (estado == ENVIANDO_MIC && conectado) {
    if (audioLerFrame(frameMic) && !micMudo) filaInserir(frameMic);
    checarHeap("leitura do mic (enviando)");
    for (int i = 0; i < FILA_MIC_SAIDA_POR_LOOP; i++) {
      const int16_t *f = filaRetirar();
      if (!f) break;
      ws.sendBIN((uint8_t *)f, sizeof(frameMic));
    }
    checarHeap("envio do mic");
  } else {
    delay(2);
  }
}
