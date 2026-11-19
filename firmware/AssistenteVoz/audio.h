// Microfone (INMP441 via I2S) e wake word "Hi ESP" (ESP-SR / WakeNet9).
#pragma once
#include <Arduino.h>

#define MIC_TAXA            16000
#define MIC_AMOSTRAS_FRAME  320   // 20 ms a 16 kHz = 640 bytes (contrato)

// Inicia o I2S e o ESP-SR já ouvindo a wake word. false = erro fatal.
bool audioIniciar();

// true (uma vez) se "Hi ESP" foi detectado desde a última chamada.
bool audioPegarWake();

// Pausa o ESP-SR e libera o I2S para leitura direta (idempotente).
void audioPausarWake();

// Volta a ouvir a wake word (idempotente).
void audioRetomarWake();

// Chamar no loop: reativa a WakeNet se o ESP-SR a desligou sozinho
// (evento de canal verificado) enquanto a wake word deveria estar ativa.
void audioManutencao();

// Lê um frame de MIC_AMOSTRAS_FRAME amostras (16 bits) com o ganho aplicado.
// Só pode ser chamada com o ESP-SR pausado. false = leitura incompleta.
bool audioLerFrame(int16_t *amostras);
