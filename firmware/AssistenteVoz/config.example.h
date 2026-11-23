// Copie este arquivo para config.h (que fica fora do git) e preencha.
#pragma once

// Wi-Fi
#define WIFI_SSID      "minha-rede"
#define WIFI_SENHA     "minha-senha"

// Servidor de voz
//  Produção:       SERVIDOR_HOST "voz.seudominio.com.br", SERVIDOR_PORTA 443,  SERVIDOR_TLS 1
//  Desenvolvimento: SERVIDOR_HOST "192.168.0.10" (IP do notebook), SERVIDOR_PORTA 8000, SERVIDOR_TLS 0
#define SERVIDOR_HOST  "voz.seudominio.com.br"
#define SERVIDOR_PORTA 443
#define SERVIDOR_TLS   1   // 1 = wss:// (sem verificar o certificado), 0 = ws://

// Mesmo valor de TOKEN_PLACA no servidor. Vai na query string: use só
// letras, números, '-' e '_' (sem caracteres que precisem de URL-encoding).
#define TOKEN_PLACA    "troque-este-token"

// Ganho em software aplicado ao mic antes de enviar (com saturação em int16).
#define GANHO_MIC      4

// Volume do alto-falante em % (0-100), aplicado em software. Opcional (padrão 40).
// #define VOLUME_ALTO_FALANTE 40

// Potenciômetro de volume no GPIO10 (pontas no 3V3 e GND, meio no GPIO10).
// Use -1 se não houver potenciômetro (aí vale o VOLUME_ALTO_FALANTE).
// #define POT_VOLUME_PINO 10
