#include "alto_falante.h"
#include "config.h"
#include "notebook.h"  // logMsg
#include <ESP_I2S.h>
#include <math.h>

// Volume inicial em % (0-100), aplicado em software. Pode ser definido no config.h.
// Com o potenciômetro ligado, ele passa a mandar no volume (altoFalanteVolume).
#ifndef VOLUME_ALTO_FALANTE
#define VOLUME_ALTO_FALANTE 40
#endif

#define TAXA_PADRAO     24000
// Buffer circular na PSRAM: 512 K amostras = 1 MB = ~21 s a 24 kHz. Respostas
// maiores funcionam: quando enche, altoFalanteAudio() espera a task abrir espaço
// (o TCP segura o resto do áudio no servidor).
#define BUF_AMOSTRAS    (512 * 1024)
#define PREBUFFER_MS    200     // espera juntar isso antes de começar (rede irregular)
#define BLOCO_AMOSTRAS  480     // 20 ms a 24 kHz por escrita no I2S
#define ESPERA_CHEIO_MS 5000    // tempo máximo esperando espaço no buffer

static I2SClass spk;
static int16_t *buf = nullptr;

// Contadores crescentes (o índice no buffer é contador % BUF_AMOSTRAS).
// escrita: só o loop() muda; leitura: só a task muda.
static volatile uint32_t escrita = 0;
static volatile uint32_t leitura = 0;

// Estado do segmento atual (resposta ou bipe). Protegido por mux.
static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
static volatile uint32_t geracao = 0;        // muda a cada começar/abortar
static volatile uint32_t inicioSegmento = 0; // valor de "escrita" no começo do segmento
static volatile bool ativo = false;          // há segmento tocando ou para tocar
static volatile bool fimRecebido = false;    // não chega mais áudio neste segmento
static volatile bool ehBeep = false;
static volatile int taxaPedida = TAXA_PADRAO;
static volatile bool terminou = false;       // resposta terminou de tocar (lida pelo loop)

// Ganho em 1/256, lido pela task a cada bloco (muda pelo potenciômetro).
static volatile int32_t ganho256 = VOLUME_ALTO_FALANTE * 256 / 100;

static int16_t bloco[BLOCO_AMOSTRAS];
static int16_t silencio[BLOCO_AMOSTRAS];

// Estatísticas do segmento atual (só a task escreve; o loop lê depois do fim).
static volatile uint32_t estAmostras = 0, estFaltas = 0, estRecusados = 0, estPico = 0;
static TaskHandle_t taskHandle = nullptr;

static void escrever(const int16_t *dados, size_t bytes) {
  size_t ok = spk.write(dados, bytes);
  if (ok < bytes) estRecusados += bytes - ok;
}

static void novoSegmento(int taxa, bool beep) {
  portENTER_CRITICAL(&mux);
  geracao++;
  inicioSegmento = escrita;
  taxaPedida = taxa;
  ehBeep = beep;
  fimRecebido = false;
  terminou = false;
  ativo = true;
  portEXIT_CRITICAL(&mux);
}

static void taskAltoFalante(void *) {
  uint32_t geracaoVista = 0;
  int taxaAtual = TAXA_PADRAO;
  bool enchendo = true;

  for (;;) {
    // Começou um segmento novo (ou houve abortar): pula para o início dele.
    portENTER_CRITICAL(&mux);
    uint32_t g = geracao;
    bool novo = g != geracaoVista;
    if (novo) {
      geracaoVista = g;
      leitura = inicioSegmento;
    }
    bool estaAtivo = ativo;
    bool fim = fimRecebido;
    int taxa = taxaPedida;
    portEXIT_CRITICAL(&mux);

    if (novo) {
      enchendo = true;
      estAmostras = estFaltas = estRecusados = estPico = 0;
      if (taxa != taxaAtual && spk.configureTX(taxa, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO, I2S_STD_SLOT_BOTH)) {
        taxaAtual = taxa;
      }
    }
    if (!estaAtivo) {
      vTaskDelay(pdMS_TO_TICKS(10));
      continue;
    }

    uint32_t disponivel = escrita - leitura;
    if (enchendo) {
      if (disponivel < (uint32_t)(taxaAtual * PREBUFFER_MS / 1000) && !fim) {
        vTaskDelay(pdMS_TO_TICKS(5));
        continue;
      }
      enchendo = false;
    }

    if (disponivel == 0) {
      if (fim) {
        // Empurra o fim do áudio para fora do DMA (6 x 240 quadros = 60 ms) com silêncio.
        for (int i = 0; i < 5; i++) escrever(silencio, sizeof(silencio));
        portENTER_CRITICAL(&mux);
        if (geracao == geracaoVista) {  // ninguém começou outro segmento nesse meio tempo
          ativo = false;
          if (!ehBeep) terminou = true;
        }
        portEXIT_CRITICAL(&mux);
      } else {
        // Faltou áudio (rede atrasou): toca silêncio, que é melhor que repetir o DMA.
        estFaltas++;
        escrever(silencio, sizeof(silencio));
      }
      continue;
    }

    // Copia um bloco (sem atravessar o fim do buffer) aplicando o volume.
    uint32_t pos = leitura % BUF_AMOSTRAS;
    uint32_t n = disponivel;
    if (n > BLOCO_AMOSTRAS) n = BLOCO_AMOSTRAS;
    if (n > BUF_AMOSTRAS - pos) n = BUF_AMOSTRAS - pos;
    const int32_t volume = ganho256;
    for (uint32_t i = 0; i < n; i++) {
      int32_t v = (int32_t)buf[pos + i] * volume / 256;
      bloco[i] = (int16_t)v;
      uint32_t a = v < 0 ? -v : v;
      if (a > estPico) estPico = a;
    }
    leitura += n;
    estAmostras += n;
    escrever(bloco, n * sizeof(int16_t));  // bloqueia no ritmo do áudio
  }
}

bool altoFalanteIniciar() {
  buf = (int16_t *)ps_malloc(BUF_AMOSTRAS * sizeof(int16_t));
  if (!buf) {
    logMsg("ERRO: sem PSRAM para o buffer do alto-falante");
    return false;
  }
  memset(silencio, 0, sizeof(silencio));
  spk.setPins(AF_BCLK, AF_LRC, AF_DIN);
  // Mono nos DOIS canais (I2S_STD_SLOT_BOTH): com o SD solto o MAX98357A toca (L+R)/2;
  // com o padrão (só o esquerdo) o direito ia em silêncio e o volume caía pela metade (-6 dB).
  if (!spk.begin(I2S_MODE_STD, TAXA_PADRAO, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO, I2S_STD_SLOT_BOTH)) {
    logMsg("ERRO: falha ao iniciar o I2S do alto-falante");
    return false;
  }
  // Core 0, junto do Wi-Fi; o loop() (core 1) fica livre para o mic e a rede.
  if (xTaskCreatePinnedToCore(taskAltoFalante, "AltoFalante", 8192, nullptr, 5, &taskHandle, 0) != pdPASS) {
    logMsg("ERRO: falha ao criar a task do alto-falante");
    return false;
  }
  logMsg("alto-falante pronto (I2S: BCLK %d, LRC %d, DIN %d; volume %d%%)", AF_BCLK, AF_LRC, AF_DIN,
         VOLUME_ALTO_FALANTE);
  return true;
}

void altoFalanteVolume(int pct) {
  if (pct < 0) pct = 0;
  if (pct > 100) pct = 100;
  // Curva quadrática: o ouvido percebe volume de forma logarítmica, então um
  // potenciômetro linear com ganho linear "acontece" todo no começo do curso.
  ganho256 = pct * pct * 256 / 10000;
}

void altoFalanteComecar(int taxa) {
  novoSegmento(taxa > 0 ? taxa : TAXA_PADRAO, false);
}

static void empilhar(const int16_t *amostras, uint32_t n) {
  if (!buf) return;
  uint32_t inicio = millis();
  while (n > 0) {
    uint32_t livre = BUF_AMOSTRAS - (escrita - leitura);
    if (livre == 0) {
      if (millis() - inicio > ESPERA_CHEIO_MS) {
        logMsg("alto-falante: buffer cheio, %u amostras descartadas", (unsigned)n);
        return;
      }
      delay(5);
      continue;
    }
    uint32_t pos = escrita % BUF_AMOSTRAS;
    uint32_t k = n;
    if (k > livre) k = livre;
    if (k > BUF_AMOSTRAS - pos) k = BUF_AMOSTRAS - pos;
    memcpy(buf + pos, amostras, k * sizeof(int16_t));
    escrita += k;  // publica só depois de copiar
    amostras += k;
    n -= k;
  }
}

void altoFalanteAudio(const uint8_t *dados, size_t n) {
  // O WebSocket entrega os bytes num buffer alocado com malloc (alinhado).
  empilhar((const int16_t *)dados, n / 2);
}

void altoFalanteFim() {
  portENTER_CRITICAL(&mux);
  fimRecebido = true;
  portEXIT_CRITICAL(&mux);
}

void altoFalanteResumo(char *saida, size_t tam) {
  snprintf(saida, tam, "%u amostras (%u ms), pico %u, faltas de audio %u, bytes recusados pelo I2S %u, "
           "pilha livre da task %u",
           (unsigned)estAmostras, (unsigned)(estAmostras * 1000ULL / TAXA_PADRAO), (unsigned)estPico,
           (unsigned)estFaltas, (unsigned)estRecusados,
           taskHandle ? (unsigned)uxTaskGetStackHighWaterMark(taskHandle) : 0u);
}

bool altoFalanteTerminou() {
  portENTER_CRITICAL(&mux);
  bool t = terminou;
  terminou = false;
  portEXIT_CRITICAL(&mux);
  return t;
}

void altoFalanteAbortar() {
  portENTER_CRITICAL(&mux);
  geracao++;
  inicioSegmento = escrita;
  ativo = false;
  fimRecebido = true;
  terminou = false;
  portEXIT_CRITICAL(&mux);
}

// ------------------------------------------------------------------ bipe
// Mesmo som que o player do notebook tocava (variação "C", escolhida pelo usuário):
// sol -> dó -> mi (392 / 523,25 / 659,25 Hz; 80 / 80 / 170 ms), cada nota como uma
// "gota" (ataque de 8 ms, queda exponencial), sobrepostas 10 ms, pico 6500.
void altoFalanteBeep() {
  static int16_t *beep = nullptr;
  static uint32_t tam = 0;
  if (!beep) {
    const int taxa = TAXA_PADRAO;
    const float freqs[3] = {392.0f, 523.25f, 659.25f};
    const int ms[3] = {80, 80, 170};
    const int sobre = taxa * 10 / 1000;
    int total = 0;
    for (int i = 0; i < 3; i++) total += taxa * ms[i] / 1000;
    total -= sobre * 2;
    float *onda = (float *)ps_calloc(total, sizeof(float));
    beep = (int16_t *)ps_malloc(total * sizeof(int16_t));
    if (!onda || !beep) {
      free(onda);
      free(beep);
      beep = nullptr;
      return;
    }
    int pos = 0;
    for (int i = 0; i < 3; i++) {
      int n = taxa * ms[i] / 1000;
      float dur = ms[i] / 1000.0f;
      for (int k = 0; k < n && pos + k < total; k++) {
        float t = (float)k / taxa;
        float ataque = fminf(1.0f, (float)k / (taxa * 8 / 1000));
        float queda = expf(-5.0f * t / dur);
        float fim = fminf(1.0f, (n - k) / (taxa * 0.005f));
        onda[pos + k] += sinf(2.0f * (float)M_PI * freqs[i] * t) * ataque * queda * fim;
      }
      pos += n - sobre;
    }
    float pico = 1e-9f;
    for (int k = 0; k < total; k++) pico = fmaxf(pico, fabsf(onda[k]));
    for (int k = 0; k < total; k++) beep[k] = (int16_t)(onda[k] / pico * 6500.0f);
    free(onda);
    tam = total;
  }
  novoSegmento(TAXA_PADRAO, true);
  empilhar(beep, tam);
  altoFalanteFim();
}
