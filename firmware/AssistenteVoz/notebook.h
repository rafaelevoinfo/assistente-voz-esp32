// Serial USB para o notebook: só os logs ("LOG <texto>\n", docs/contrato.md §2).
// Desde o fw 2.0 o áudio sai no alto-falante da placa (alto_falante.h).
#pragma once
#include <Arduino.h>

#define NOTEBOOK_BAUD 921600

void notebookIniciar();

// "LOG <texto>\n" (formato printf). Todo log da placa passa por aqui.
void logMsg(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
