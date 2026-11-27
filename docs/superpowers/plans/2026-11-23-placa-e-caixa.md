# Placa de circuito e caixa do "Hi ESP" — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gerar a placa de circuito (arquivos para a JLCPCB) e a caixa impressa em 3D (STLs) do assistente, a partir de scripts reproduzíveis.

**Architecture:** Uma fonte única de medidas (`hardware/medidas.json`) alimenta tudo. A placa é gerada por código: netlist em Python (SKiDL), posicionamento pela API Python do KiCad (`pcbnew`), roteamento automático pelo Freerouting, verificação e exportação pelo `kicad-cli`. A caixa é um modelo OpenSCAD paramétrico que lê as medidas (convertidas para `.scad`) e o contorno da placa. Cada etapa tem um teste automático (pytest) que confere o resultado.

**Tech Stack:** KiCad 9 (`pcbnew` + `kicad-cli`), SKiDL, Freerouting (Java), OpenSCAD, Python 3 + pytest.

**Spec:** `docs/superpowers/specs/2026-11-23-placa-e-caixa-design.md`

## Global Constraints

- Ligações: INMP441 VDD→3V3, GND→GND, L/R→GND, WS→GPIO4, SCK→GPIO5, SD→GPIO8. MAX98357A LRC→GPIO6, BCLK→GPIO7, DIN→GPIO9, VIN→5Vin, GND→GND, SD sem ligação. Potenciômetro: pontas→3V3 e GND, meio→GPIO10.
- Módulos (YD-ESP32-S3, INMP441, MAX98357A) em **barras de pinos fêmea**; potenciômetro WH148 **soldado na borda direita**, eixo paralelo à placa, saindo pela lateral direita.
- **Duas posições** de eletrolítico em paralelo 5V–GND, coladas no VIN/GND do MAX98357A, até Ø 10 mm, faixa "−" das duas do mesmo lado, furação para montar em pé ou deitado.
- **Jumper de ganho** de 3 posições no GAIN do MAX98357A: solto = 9 dB, GND = 12 dB, 100 kΩ ao GND = 15 dB; serigrafia indica **12 dB recomendado**.
- **Antena do ESP32 para fora da borda**, sem cobre (nem plano de GND) embaixo.
- Placa 2 camadas, plano de GND, trilhas 5V/GND do amplificador largas (≥ 1 mm).
- Caixa B (em pé), PLA, ~80 × 80 × 110 mm; parede 2–2,4 mm; folga 0,2–0,3 mm; traseira removível com M3 em insertos de latão; câmara fechada do alto-falante (~50 × 50 × 40 mm internos) para alto-falante Ø 40 × 20 mm; furo do mic 2–3 mm com anel de vedação; janela do LED no topo; recorte do USB-C na traseira.
- Medidas não confirmadas (YD-ESP32-S3, potenciômetro) devem ser medidas pelo usuário com régua antes da encomenda.

## Review Focus

1. **ESP32 encaixado invertido/espelhado** — a ordem dos pinos na placa deve bater com a serigrafia da YD-ESP32-S3 (fileira usada em `docs/gerar_ligacoes.py`); teste na Task 2.
2. **Capacitor com polaridade trocada** — o pad "+" das duas posições no 5V e as duas com a mesma rotação; teste na Task 3.
3. **USB-C não alinha com o recorte da traseira** — a posição do conector vem do mesmo `medidas.json`; teste na Task 6.
4. **Cobre sob a antena** derrubando o Wi-Fi — nenhuma trilha/zona na área da antena; teste na Task 4.
5. **Eixo do potenciômetro curto demais** para atravessar a parede e segurar o botão — sobra ≥ 8 mm para fora da parede; teste na Task 6.

---

### Task 1: Ferramentas e medidas

**Files:**
- Create: `hardware/README.md` (como regenerar tudo)
- Create: `hardware/medidas.json`
- Create: `hardware/gerar_medidas_scad.py` → gera `hardware/caixa/medidas.scad`
- Test: `hardware/tests/test_medidas.py`

**Interfaces:**
- Produces: `hardware/medidas.json` com, em mm: `esp.{comprimento, largura, pitch_fileiras, usb_c.{x,y,largura,altura}, led.{x,y}, antena.comprimento}`, `mic.{diametro, furo.{x,y}}`, `amp.{comprimento, largura}`, `pot.{corpo_diametro, rosca, eixo_diametro, eixo_comprimento, pitch_pinos}`, `falante.{diametro, profundidade}`, `cap.diametro_max`, `caixa.{parede, folga, largura, profundidade, altura}`. `gerar_medidas_scad.py` escreve `medidas.scad` com as mesmas chaves (ex.: `esp_comprimento = 63.5;`).

- [ ] **Step 1:** Instalar KiCad 9, OpenSCAD e um Java 17+ (`winget install KiCad.KiCad OpenSCAD.OpenSCAD EclipseAdoptium.Temurin.17.JRE`); baixar o `freerouting-*.jar` para `hardware/ferramentas/` (fora do git). Verificar: `kicad-cli version`, `openscad --version`, `java -version`.
- [ ] **Step 2:** Pedir ao usuário as medidas com régua da YD-ESP32-S3 (comprimento, largura, distância entre fileiras, posição do LED, do USB-C e onde a antena começa) e do potenciômetro (eixo e rosca); preencher o `medidas.json` (valores do spec para alto-falante 40 × 20, cap 10, caixa 80 × 80 × 110, parede 2.2, folga 0.25).
- [ ] **Step 3: Teste** `test_medidas_completas_e_coerentes`: todas as chaves acima existem; `falante.diametro == 40`, `falante.profundidade == 20`, `cap.diametro_max == 10`; `2 <= caixa.parede <= 2.4`; `0.2 <= caixa.folga <= 0.3`; `esp.largura < caixa.largura - 2*caixa.parede`. E `test_scad_gerado_bate_com_json`: roda o gerador e confere cada chave no `.scad`.
- [ ] **Step 4:** `pytest hardware/tests -v` → PASS.
- [ ] **Step 5:** Commit (`hardware/`, sem `ferramentas/`; adicionar `hardware/ferramentas/` ao `.gitignore`).

### Task 2: Netlist da placa

**Files:**
- Create: `hardware/placa/netlist.py` (SKiDL) → `hardware/placa/assistente.net`
- Test: `hardware/tests/test_netlist.py`

**Interfaces:**
- Consumes: `medidas.json` (nada elétrico; só nomes).
- Produces: `assistente.net` com referências fixas: `U1` (YD-ESP32-S3, 2 × barra fêmea 1×22, pinos numerados na ordem da serigrafia), `U2` (INMP441, 1×6), `U3` (MAX98357A, 1×7), `RV1` (WH148), `C1`/`C2` (eletrolítico radial, pad 1 = "+"), `JP1` (jumper 1×3 do GAIN), `R1` (100 kΩ, ligado entre JP1 pino 3 e GND). Nets: `+5V`, `+3V3`, `GND`, `I2S_WS`, `I2S_SCK`, `I2S_SD`, `AMP_LRC`, `AMP_BCLK`, `AMP_DIN`, `VOL`, `GAIN`.

- [ ] **Step 1: Testes** (lendo o `.net` gerado):
  - `test_ligacoes_do_mic`: U2.VDD∈+3V3, U2.GND e U2.L/R∈GND, U2.WS↔U1 GPIO4, U2.SCK↔GPIO5, U2.SD↔GPIO8.
  - `test_ligacoes_do_amp`: U3.LRC↔GPIO6, BCLK↔GPIO7, DIN↔GPIO9, VIN∈+5V (pino 5Vin do U1), GND∈GND, U3.SD sem net.
  - `test_potenciometro`: RV1 pontas em +3V3 e GND, cursor em VOL = U1 GPIO10.
  - `test_capacitores_em_paralelo`: C1.1 e C2.1 em +5V; C1.2 e C2.2 em GND.
  - `test_jumper_de_ganho`: JP1.2 = U3.GAIN; JP1.1 = GND; JP1.3 → R1 → GND (sem jumper = solto = 9 dB).
  - `test_ordem_dos_pinos_do_esp` (Review Focus 1): a fileira do U1 segue exatamente `["3V3","3V3","RST","4","5","6","7","15","16","17","18","8","3","46","9","10","11","12","13","14","5Vin","GND"]`.
- [ ] **Step 2:** `pytest hardware/tests/test_netlist.py -v` → FAIL (arquivo não existe).
- [ ] **Step 3:** Implementar `netlist.py` com SKiDL e footprints padrão do KiCad (`Connector_PinSocket_2.54mm`, `Capacitor_THT:CP_Radial_D10.0mm_P5.00mm`, potenciômetro `Potentiometer_THT:Potentiometer_Alpha_RD901F-40-00D_Single_Vertical` ou footprint próprio do WH148 a partir de `pot.pitch_pinos`).
- [ ] **Step 4:** `pytest hardware/tests/test_netlist.py -v` → PASS.
- [ ] **Step 5:** Commit.

### Task 3: Contorno e posicionamento

**Files:**
- Create: `hardware/placa/montar_pcb.py` (roda com o Python do KiCad) → `hardware/placa/assistente.kicad_pcb`
- Test: `hardware/tests/test_posicionamento.py` (abre o `.kicad_pcb` com `pcbnew`)

**Interfaces:**
- Consumes: `assistente.net`, `medidas.json`.
- Produces: `assistente.kicad_pcb` com contorno retangular que cabe na caixa (largura ≤ `caixa.largura - 2*parede - 2*folga - 2` p/ trilhos), footprints posicionados, área `ANTENA` (keepout de cobre) marcada na borda do U1.

- [ ] **Step 1: Testes:**
  - `test_tudo_dentro_do_contorno`: todos os footprints dentro do contorno, exceto a antena do U1 (sobra além da borda) e o eixo do RV1 (sai pela borda direita).
  - `test_antena_para_fora`: a área da antena (comprimento `esp.antena.comprimento`) fica inteira fora do contorno.
  - `test_pot_na_borda_direita`: RV1 encostado na borda direita, eixo apontando para +X.
  - `test_caps_colados_no_amp`: C1 e C2 a ≤ 15 mm dos pinos VIN/GND do U3, mesma rotação, pad "+" do mesmo lado (Review Focus 2).
  - `test_usb_c_na_borda_traseira`: o USB-C do U1 alinhado com a borda traseira (posição salva para a Task 6).
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3:** Implementar `montar_pcb.py`: lê o netlist, cria contorno e furos de guia dos trilhos, posiciona: U1 junto à borda traseira (USB-C para trás, antena sobrando pela lateral esquerda), U2 perto da borda traseira-esquerda (longe do alto-falante, que fica na frente), U3 + C1/C2 + JP1/R1 perto da frente (perto do alto-falante), RV1 na borda direita.
- [ ] **Step 4:** rodar → PASS.
- [ ] **Step 5:** Commit.

### Task 4: Roteamento e DRC

**Files:**
- Create: `hardware/placa/rotear.py` (exporta DSN → Freerouting → importa SES → zonas de GND nas 2 camadas com keepout na antena)
- Test: `hardware/tests/test_roteamento.py`

**Interfaces:**
- Consumes: `assistente.kicad_pcb` da Task 3.
- Produces: `assistente.kicad_pcb` roteado e com zonas.

- [ ] **Step 1: Testes:**
  - `test_drc_limpo`: `kicad-cli pcb drc --format json --severity-error` → 0 violações e 0 itens não conectados.
  - `test_trilhas_de_potencia_largas`: toda trilha das nets `+5V` e `GND` ≥ 1,0 mm.
  - `test_sem_cobre_na_antena` (Review Focus 4): nenhuma trilha, via ou zona preenchida intersecta a área da antena.
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3:** Implementar `rotear.py` (regras de net class: `Power` 1,0 mm para +5V/GND; padrão 0,3 mm; Freerouting em modo batch `-de assistente.dsn -do assistente.ses`).
- [ ] **Step 4:** rodar → PASS.
- [ ] **Step 5:** Commit.

### Task 5: Arquivos de fabricação e revisão do usuário

**Files:**
- Create: `hardware/placa/exportar.py` → `hardware/placa/fabricacao/` (gerbers + furação em zip no formato JLCPCB), `hardware/placa/renders/{topo,baixo}.png`, `hardware/placa/assistente.step`
- Test: `hardware/tests/test_fabricacao.py`

**Interfaces:**
- Consumes: placa roteada.
- Produces: `assistente.step` (usado na Task 6), zip de fabricação.

- [ ] **Step 1: Testes:** `test_zip_tem_camadas`: o zip contém F.Cu, B.Cu, F.Mask, B.Mask, F.SilkS, Edge.Cuts e o arquivo de furação; `test_step_existe_e_tem_tamanho_da_placa`.
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3:** Implementar com `kicad-cli pcb export gerbers/drill/step` e `kicad-cli pcb render`.
- [ ] **Step 4:** rodar → PASS.
- [ ] **Step 5:** **Ponto de parada:** mostrar ao usuário os renders (topo/baixo) e a lista de peças; confirmar as medidas do potenciômetro com régua. Só seguir com aprovação. Commit.

### Task 5b: Mapa de montagem da placa perfurada (decisão do usuário em 2026-11-26)

**Files:**
- Create: `hardware/perfurada/layout.py` (posição de cada pino na grade e lista de fios, a partir do `netlist.py`)
- Create: `hardware/perfurada/desenhar.py` → `hardware/perfurada/{cima,baixo}.png` + `fios.md`
- Test: `hardware/tests/test_perfurada.py`

**Interfaces:**
- Consumes: `netlist.COMPONENTES`, `netlist.NETS`, `medidas.json`.
- Produces: `layout.GRADE = (colunas, linhas)`; `layout.furo(ref, numero) -> (col, lin)`; `layout.FIOS: list[(net, (col, lin), (col, lin))]`; `posicoes.json` da perfurada para a caixa.

- [ ] **Step 1: Testes:** `test_cabe_na_placa_cortada` (todos os furos na grade de ~70 × 68 mm); `test_nenhum_furo_dividido`; `test_fileiras_do_esp_a_10_furos` (25,4 mm) e `test_fileiras_do_mic_a_3_furos` (7,62 mm); `test_todas_as_ligacoes_existem` (para cada net, os fios formam um caminho que liga todos os seus pinos); `test_nenhum_fio_liga_nets_diferentes` (fios só começam/terminam em pinos da própria net).
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3:** Implementar `layout.py` e `desenhar.py` (vista de baixo espelhada; cores por net como em docs/ligacoes.png; fios numerados).
- [ ] **Step 4:** rodar → PASS; conferir as imagens.
- [ ] **Step 5:** Commit; mostrar ao usuário.

### Task 6: Caixa paramétrica

**Files:**
- Create: `hardware/caixa/caixa.scad` (módulos `corpo()`, `traseira()`, `botao()`, `anel_mic()`; `parte = "corpo"` escolhe o que renderizar)
- Create: `hardware/caixa/exportar.py` → `hardware/caixa/stl/{corpo,traseira,botao,anel_mic}.stl` e `hardware/caixa/renders/*.png`
- Test: `hardware/tests/test_caixa.py`

**Interfaces:**
- Consumes: `medidas.scad` (Task 1), contorno e posições (U1 USB-C, LED, U2 furo, RV1 eixo) exportados pela Task 3 para `hardware/placa/posicoes.json`.
- Produces: STLs prontos para fatiar.

- [ ] **Step 1: Testes** (renderizando com `openscad -o x.stl -D parte="..."` e lendo a caixa delimitadora do STL):
  - `test_todas_as_partes_renderizam`: as 4 partes geram STL sem erro.
  - `test_tamanho_externo`: corpo ≈ 80 × 80 × 110 mm (±5).
  - `test_usb_c_alinhado` (Review Focus 3): o recorte da traseira contém o retângulo do USB-C (de `posicoes.json`) com folga ≥ 0,5 mm em volta.
  - `test_eixo_do_pot_sobra` (Review Focus 5): `pot.eixo_comprimento` − (distância do corpo do pot até a face externa da lateral) ≥ 8 mm.
  - `test_camara_do_falante`: volume interno da câmara ≥ 50 × 50 × 40 mm e diâmetro do assento = 40 + 2·folga.
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3:** Implementar `caixa.scad`: corpo impresso de frente para a mesa (grade de furos na frente), trilhos internos para a placa, parede interna selando a câmara do alto-falante (passagem dos 2 fios), furo do mic 2,5 mm + rebaixo para o anel, janela do LED com parede de 0,6 mm, furo do eixo do pot na lateral direita, 4 bossas para insertos M3 (Ø 4,0 mm) na traseira; traseira com recorte do USB-C; botão para eixo serrilhado Ø 6 mm (encaixe por pressão).
- [ ] **Step 4:** rodar → PASS; gerar renders.
- [ ] **Step 5:** Mostrar os renders ao usuário. Commit.

### Task 7: Impressão de teste e ajustes

- [ ] **Step 1:** Usuário imprime `corpo` e `traseira`; verifica: placa desliza nos trilhos, USB-C encaixa, eixo do pot passa, alto-falante assenta e veda, LED aparece.
- [ ] **Step 2:** Ajustar `medidas.json` / `caixa.scad` conforme o retorno; rodar `pytest hardware/tests -v` → PASS; regenerar STLs.
- [ ] **Step 3:** Commit com a versão final e atualizar `README.md` raiz (seção hardware).
