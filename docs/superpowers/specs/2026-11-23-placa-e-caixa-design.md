# Placa de circuito e caixa do assistente "Hi ESP" — design

Data: 2026-11-23 · Status: aguardando aprovação (potenciômetro revisado: soldado na placa, botão na lateral direita)

## Por quê

Tirar o assistente da protoboard e transformá-lo num aparelho de mesa: uma placa de
circuito que recebe os módulos já usados nos testes e uma caixa impressa em 3D em volta
dela. A protoboard tem mau contato, fios longos que derrubam a tensão nos picos do
amplificador, e não dá para deixar na mesa.

## Uso

- Fica **sobre uma mesa**; o usuário fala de **até 3 metros**.
- Para regravar o firmware, o usuário **abre a caixa** (não precisa de acesso externo a BOOT/RST).
- Alimentação pelo **USB-C** do ESP32 (carregador de tomada 5 V / 2 A).

## Metas

- Som mais alto e limpo que na protoboard (câmara fechada atrás do alto-falante, fios curtos, capacitores de alimentação perto do amplificador).
- Microfone ouvindo bem a 3 m e o mais isolado possível do alto-falante (eco hoje e, no futuro, interrupção por voz com cancelamento de eco).
- Montagem e manutenção simples: abrir, puxar a placa, regravar, fechar.
- Impressão fácil em impressora FDM comum, sem suportes difíceis.

## Fora do escopo

- Bateria, botões extras, tela.
- Mudanças no firmware (a placa usa os mesmos pinos de hoje).

## Anti-metas (seria um fracasso mesmo "funcionando")

- Microfone que capta o próprio alto-falante pela caixa (ressonância/eco interno).
- Wi-Fi ruim por causa de cobre ou fios sobre a antena do ESP32.
- Caixa que precisa ser quebrada ou que espana a rosca para abrir.

## Componentes (os que o usuário já tem)

| Componente | Montagem |
|---|---|
| YD-ESP32-S3 N16R8 | encaixado em barras de pinos fêmea na placa; USB-C virado para trás |
| INMP441 (módulo redondo, furo na face de cima) | barra fêmea na placa, furo apontando para o topo |
| MAX98357A (módulo roxo com borne verde) | barra fêmea na placa |
| Alto-falante 4 Ω, Ø 40 mm × 20 mm | preso na frente da caixa; 2 fios até o borne do MAX98357A |
| Potenciômetro B10K tipo **WH148** (pinos de placa + rosca; eixo **paralelo** à placa; padrão: corpo Ø 16 mm, rosca M7, eixo serrilhado Ø 6 mm, pinos a 5 mm) | **soldado direto na borda da placa**; o eixo atravessa a **lateral direita** da caixa; a porca não é usada |
| 1 ou 2 capacitores eletrolíticos (até Ø 10 mm, ex. 1000 µF / 10 V) | soldados na placa, em paralelo entre 5V e GND |

## Ligações (iguais à protoboard; ver docs/ligacoes.png)

- INMP441: VDD→3V3, GND→GND, L/R→GND, WS→GPIO4, SCK→GPIO5, SD→GPIO8.
- MAX98357A: LRC→GPIO6, BCLK→GPIO7, DIN→GPIO9, VIN→5Vin, GND→GND; SD sem ligação.
- Potenciômetro: pontas→3V3 e GND, meio→GPIO10.
- Jumpers da YD-ESP32-S3 já fechados: RGB (LED no GPIO48) e IN-OUT (5V no 5Vin).

## Abordagens consideradas (forma da caixa)

- **A) Caixa deitada, alto-falante para cima:** espalha o som pela sala, mas ocupa mais mesa, deixa o microfone perto do alto-falante e manda o som para o teto (menos volume percebido a 3 m).
- **B) Caixa em pé, alto-falante virado para o usuário — ESCOLHIDA.** Som direto para quem fala, microfone no topo longe do alto-falante, pouca área de mesa, impressão fácil.
- (Aparência: o usuário deixou livre — "caixa retangular, o que for mais fácil e eficiente".)

## Arranjo escolhido

```
  vista lateral (frente à esquerda)           vista de cima
  ┌──────────────┐  ← topo                   ┌──────────────┐
  │▄▄▄▄▄▄▄▄▄▄▄▄▄▄│  ← placa deitada          │ ○mic     ▫LED │
  │              │                           └──────────────┘
  │░(◯)          │  ← alto-falante + câmara fechada
  │░             │
  └──────────────┘  ← traseira removível (USB-C)
```

- **Uma placa só, deitada logo abaixo do topo**, com o ESP32, o INMP441, o MAX98357A e os capacitores. Ela **desliza em trilhos** e sai pela traseira.
- **Traseira removível** presa por parafusos M3 em **insertos de latão** (aguentam muitas aberturas). Tem o recorte do USB-C.
- **Topo** (fixo, parte do corpo): furo do microfone (~2–3 mm) com anel de vedação de espuma/borracha até o módulo; janela do LED (parede fina ou peça translúcida) sobre o LED RGB da YD-ESP32-S3.
- **Lateral direita, no alto**: furo para o eixo do potenciômetro (soldado na borda da placa). O botão é de encaixe por pressão: para tirar a placa, puxa-se o botão e a placa desliza pela traseira, com o eixo saindo pelo furo.
- **Frente**: grade de furos para o alto-falante; o alto-falante fica preso por dentro (anel com parafusos ou encaixe) com vedação.
- **Parede interna** separando a **câmara fechada do alto-falante** (embaixo, ~50 × 50 × 40 mm internos) da eletrônica (em cima). Passagem selada para os 2 fios do alto-falante.
- Tamanho estimado: **~80 × 80 × 110 mm** (largura × profundidade × altura), a confirmar no desenho.
- Material: **PLA** (uso doméstico, sem calor).

## Placa de circuito (decisões)

- Desenhada no **KiCad**, 2 camadas, fabricada na JLCPCB/PCBWay; o usuário revisa visualmente (imagens 3D/renders) antes de encomendar.
- Módulos em **barras de pinos fêmea** (trocáveis), não soldados direto.
- **Duas posições para capacitores** eletrolíticos em paralelo entre 5V e GND, coladas no VIN/GND do MAX98357A, faixa "−" das duas do mesmo lado, até Ø 10 mm; furação que permite montar em pé ou deitado.
- **Seletor de ganho do MAX98357A** na placa (jumper de 3 posições: solto = 9 dB, GND = 12 dB, 100 kΩ ao GND = 15 dB) — nos testes 15 dB fez o amplificador cortar; o padrão recomendado é 12 dB.
- O alto-falante liga no **borne do próprio MAX98357A**; os fios têm folga para puxar a placa alguns centímetros e soltar o borne. O potenciômetro é **soldado na borda direita da placa**, com o eixo para fora (sem fios nem conector).
- Trilhas de 5V e GND do amplificador **largas e curtas**; plano de GND.
- **Antena do ESP32 sobrando para fora da borda da placa**, sem cobre embaixo, longe de fios.
- Furos de fixação/guia compatíveis com os trilhos da caixa.

## Deixado para quem for desenhar

- Medidas exatas da YD-ESP32-S3 (pitch entre as fileiras de pinos, posição do LED, do USB-C e da antena) — conferir no desenho oficial/medição.
- Posição exata de cada módulo na placa (respeitando: mic perto da borda do topo e longe do alto-falante; MAX98357A perto da parede interna/alto-falante; antena para fora).
- Espessuras de parede (sugestão 2–2,4 mm), folgas (0,2–0,3 mm) e tamanho da grade.
- Confirmar com o usuário as medidas do potenciômetro (régua) antes de encomendar a placa.
- Botão (knob) para eixo serrilhado de 6 mm: comprado ou impresso.

## Ordem

1. Placa no KiCad → revisão do usuário → encomenda.
2. Caixa (modelo paramétrico, ex. OpenSCAD) desenhada em volta da placa → impressão de teste → ajustes.

## Pendências que não bloqueiam

- Investigação do travamento (heap corrompido) no firmware continua em paralelo.
