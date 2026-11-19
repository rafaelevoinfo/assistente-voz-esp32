#include "audio.h"
#include "config.h"
#include "notebook.h"
#include <ESP_I2S.h>
#include <ESP_SR.h>

#define I2S_WS   4
#define I2S_SCK  5
#define I2S_SD   8

// Tempo para a "SR Feed Task" terminar a leitura em andamento (um bloco de
// 512 amostras = 32 ms) e parar no PAUSE_FEED antes de lermos o I2S direto.
#define ESPERA_PAUSA_MS  80

static I2SClass i2s;

static volatile bool wakeDetectado = false;
static volatile bool wakeDesligadaPeloSR = false;
static bool srPausado = false;

// O ESP-SR sempre carrega a MultiNet; nunca entramos no modo de comandos,
// mas passamos uma frase para ela iniciar como no WakeWordESP (testado).
// ATENCAO: com uma unica frase a MultiNet7 trava em build_fsts (StoreProhibited no
// ESP_SR.begin). As mesmas 4 frases do WakeWordESP funcionam.
static const sr_cmd_t comandos[] = {
  {0, "Turn on the light"},
  {0, "Lights on"},
  {1, "Turn off the light"},
  {1, "Lights off"},
};

// Roda na "SR Handler Task": só marca flags, nunca escreve na Serial.
static void aoEventoSR(sr_event_t evento, int comando, int frase) {
  (void)comando;
  (void)frase;
  if (evento == SR_EVENT_WAKEWORD) {
    wakeDetectado = true;
  } else if (evento == SR_EVENT_WAKEWORD_CHANNEL) {
    // O esp32-hal-sr.c chama sr_set_mode(SR_MODE_OFF) nesse evento,
    // desligando a WakeNet. Reativamos no loop se for o caso.
    wakeDesligadaPeloSR = true;
  }
}

bool audioIniciar() {
  // O INMP441 envia 32 bits; o ESP-SR (e o servidor) usam 16 bits.
  i2s.setTimeout(1000);
  i2s.setPins(I2S_SCK, I2S_WS, -1, I2S_SD);
  if (!i2s.begin(I2S_MODE_STD, MIC_TAXA, I2S_DATA_BIT_WIDTH_32BIT,
                 I2S_SLOT_MODE_MONO, I2S_STD_SLOT_LEFT)) {
    logMsg("ERRO: falha ao iniciar o I2S");
    return false;
  }
  i2s.configureRX(MIC_TAXA, I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO,
                  I2S_RX_TRANSFORM_32_TO_16);

  ESP_SR.onEvent(aoEventoSR);
  bool ok = ESP_SR.begin(i2s, comandos, sizeof(comandos) / sizeof(sr_cmd_t),
                         SR_CHANNELS_MONO, SR_MODE_WAKEWORD, "M");
  if (!ok) {
    logMsg("ERRO: ESP_SR nao iniciou. Confira PSRAM e a particao 'ESP SR 16M'.");
    return false;
  }
  srPausado = false;
  return true;
}

bool audioPegarWake() {
  if (!wakeDetectado) return false;
  wakeDetectado = false;
  return true;
}

void audioPausarWake() {
  if (srPausado) return;
  ESP_SR.pause();
  srPausado = true;
  delay(ESPERA_PAUSA_MS);
  // O _fill do ESP_SR deixa o timeout do I2S em portMAX_DELAY; para a
  // leitura direta usamos um timeout curto.
  i2s.setTimeout(100);
  wakeDetectado = false;
}

void audioRetomarWake() {
  if (!srPausado) return;
  // OFF -> WAKEWORD força enable_wakenet(), mesmo que o ESP-SR tenha
  // desligado a WakeNet depois da última detecção.
  ESP_SR.setMode(SR_MODE_OFF);
  ESP_SR.setMode(SR_MODE_WAKEWORD);
  wakeDesligadaPeloSR = false;
  wakeDetectado = false;
  ESP_SR.resume();  // pause() e resume() sempre em pares (ver topo do .ino)
  srPausado = false;
}

void audioManutencao() {
  if (wakeDesligadaPeloSR && !srPausado) {
    wakeDesligadaPeloSR = false;
    ESP_SR.setMode(SR_MODE_WAKEWORD);
  }
}

bool audioLerFrame(int16_t *amostras) {
  const size_t bytes = MIC_AMOSTRAS_FRAME * sizeof(int16_t);
  size_t lidos = i2s.readBytes((char *)amostras, bytes);
  if (lidos != bytes) return false;
  for (size_t i = 0; i < MIC_AMOSTRAS_FRAME; i++) {
    int32_t v = (int32_t)amostras[i] * GANHO_MIC;
    if (v > 32767) v = 32767;
    if (v < -32768) v = -32768;
    amostras[i] = (int16_t)v;
  }
  return true;
}
