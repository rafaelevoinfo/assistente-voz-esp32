# Placa perfurada: lista de fios

Furos como **(coluna, linha)**, contados na vista de CIMA a partir do canto de trás-esquerda (coluna 0 à esquerda, linha 0 do lado dos USB-C). Na vista de baixo a placa fica espelhada: a coluna 0 passa para a direita. Fios **grossos** (22 AWG) são a alimentação; os demais, 26-30 AWG.

**Use sempre fio encapado (cabinho):** os fios passam por cima de outras ilhas e, nus, dariam curto. Desencape só ~2 mm nas pontas, passe pelo furo ao lado do pino e solde junto com ele.

| Nº | Ligação | De | Para | Fio |
|---|---|---|---|---|
| 1 | 3V3 | U1 3V3 (11, 22) | RV1 1 (24, 9) | fino |
| 2 | 3V3 | RV1 1 (24, 9) | U2 VDD (18, 4) | fino |
| 3 | GND | U1 GND (11, 1) | U2 GND (17, 4) | grosso |
| 4 | GND | U2 GND (17, 4) | U2 L/R (17, 7) | grosso |
| 5 | GND | U2 L/R (17, 7) | C1 - (16, 13) | grosso |
| 6 | GND | C1 - (16, 13) | U3 GND (18, 17) | grosso |
| 7 | GND | U3 GND (18, 17) | JP1 1 (22, 17) | grosso |
| 8 | GND | JP1 1 (22, 17) | C2 - (21, 13) | grosso |
| 9 | GND | C2 - (21, 13) | RV1 3 (24, 13) | grosso |
| 10 | GND | RV1 3 (24, 13) | R1 2 (25, 21) | grosso |
| 11 | 5V | U1 5Vin (11, 2) | C1 + (14, 13) | grosso |
| 12 | 5V | C1 + (14, 13) | C2 + (19, 13) | grosso |
| 13 | 5V | C2 + (19, 13) | U3 VIN (19, 17) | grosso |
| 14 | WS (GPIO4) | U1 4 (11, 19) | U2 WS (18, 7) | fino |
| 15 | SCK (GPIO5) | U1 5 (11, 18) | U2 SCK (19, 7) | fino |
| 16 | SD (GPIO8) | U1 8 (11, 11) | U2 SD (19, 4) | fino |
| 17 | LRC (GPIO6) | U1 6 (11, 17) | U3 LRC (13, 17) | fino |
| 18 | BCLK (GPIO7) | U1 7 (11, 16) | U3 BCLK (14, 17) | fino |
| 19 | DIN (GPIO9) | U1 9 (11, 8) | U3 DIN (15, 17) | fino |
| 20 | volume (GPIO10) | U1 10 (11, 7) | RV1 2 (24, 11) | fino |
| 21 | ganho | U3 GAIN (16, 17) | JP1 2 (22, 18) | fino |
| 22 | ganho 15 dB | JP1 3 (22, 19) | R1 1 (22, 21) | fino |

U1 = ESP32 · U2 = microfone · U3 = amplificador · RV1 = potenciômetro · C1/C2 = capacitores ("+" à esquerda) · JP1 = jumper de ganho (1-2 = 12 dB) · R1 = 100 kΩ
