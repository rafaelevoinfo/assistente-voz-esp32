// Protocolo serial placa -> notebook (docs/contrato.md §2).
// Todas as escritas na Serial acontecem na task do loop(), para que um
// LOG nunca caia no meio de um bloco AUD.
#pragma once
#include <Arduino.h>

#define NOTEBOOK_BAUD     921600
#define NOTEBOOK_AUD_MAX  4800   // bytes por bloco AUD (contrato)

void notebookIniciar();

// "LOG <texto>\n" (formato printf). Todo log da placa passa por aqui.
void logMsg(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

void notebookBegin(int taxa);                         // "BEGIN <rate>\n"
void notebookAudio(const uint8_t *dados, size_t n);   // "AUD <n>\n" + bytes (divide em blocos <= 4800)
void notebookEnd();                                   // "END\n"
void notebookBeep();                                  // "BEEP\n": sinal de "estou ouvindo"

// Lê o que chegou do notebook. Devolve quantos "DONE" chegaram (outras linhas são ignoradas).
int notebookLerDones();
