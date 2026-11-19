#include "notebook.h"
#include <stdarg.h>

static char linhaRx[32];
static size_t tamLinhaRx = 0;
static bool linhaRxEstourou = false;

void notebookIniciar() {
  Serial.setRxBufferSize(512);
  Serial.begin(NOTEBOOK_BAUD);
}

void logMsg(const char *fmt, ...) {
  char buf[260] = "LOG ";
  va_list args;
  va_start(args, fmt);
  vsnprintf(buf + 4, sizeof(buf) - 5, fmt, args);
  va_end(args);
  // Uma linha só: troca quebras de linha por espaço.
  size_t n = 4;
  for (; buf[n]; n++) {
    if (buf[n] == '\n' || buf[n] == '\r') buf[n] = ' ';
  }
  buf[n++] = '\n';
  Serial.write((const uint8_t *)buf, n);
}

void notebookBegin(int taxa) {
  Serial.printf("BEGIN %d\n", taxa);
}

void notebookAudio(const uint8_t *dados, size_t n) {
  n &= ~(size_t)1;  // sempre um número par de bytes
  while (n > 0) {
    size_t bloco = n > NOTEBOOK_AUD_MAX ? NOTEBOOK_AUD_MAX : n;
    Serial.printf("AUD %u\n", (unsigned)bloco);
    Serial.write(dados, bloco);
    dados += bloco;
    n -= bloco;
  }
}

void notebookEnd() {
  Serial.print("END\n");
}

void notebookBeep() {
  Serial.print("BEEP\n");
}

int notebookLerDones() {
  int dones = 0;
  while (Serial.available() > 0) {
    int c = Serial.read();
    if (c < 0) break;
    if (c == '\n') {
      while (tamLinhaRx > 0 && linhaRx[tamLinhaRx - 1] == '\r') tamLinhaRx--;
      linhaRx[tamLinhaRx] = '\0';
      if (!linhaRxEstourou && strcmp(linhaRx, "DONE") == 0) dones++;
      tamLinhaRx = 0;
      linhaRxEstourou = false;
    } else if (tamLinhaRx < sizeof(linhaRx) - 1) {
      linhaRx[tamLinhaRx++] = (char)c;
    } else {
      linhaRxEstourou = true;  // linha longa demais: não é DONE
    }
  }
  return dones;
}
