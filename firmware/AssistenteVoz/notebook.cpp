#include "notebook.h"
#include <stdarg.h>

void notebookIniciar() {
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
