// Alto-falante: MAX98357A no segundo I2S (o primeiro é do microfone).
// O áudio que chega da rede entra num buffer circular na PSRAM; uma task
// própria toca o buffer no I2S, então o loop() nunca espera o som acabar.
#pragma once
#include <Arduino.h>

#define AF_BCLK  7
#define AF_LRC   6
#define AF_DIN   9

bool altoFalanteIniciar();

// Volume em % (0-100) do curso do potenciômetro (curva quadrática).
void altoFalanteVolume(int pct);

// Uma resposta do servidor: começar -> audio (n vezes) -> fim.
void altoFalanteComecar(int taxa);
void altoFalanteAudio(const uint8_t *dados, size_t n);  // PCM16LE mono
void altoFalanteFim();

// true (uma vez) quando o áudio de uma resposta terminou de sair no alto-falante.
bool altoFalanteTerminou();

// Resumo do último segmento tocado (para o log).
void altoFalanteResumo(char *saida, size_t tam);

// Corta o que estiver tocando (queda de conexão etc.).
void altoFalanteAbortar();

// Sinal de "estou ouvindo" (3 notas, ~310 ms), gerado aqui mesmo.
// Não conta como resposta: não dispara altoFalanteTerminou().
void altoFalanteBeep();
