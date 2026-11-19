"""Player do notebook: toca o áudio que a placa repassa pela USB serial.

Protocolo (docs/contrato.md §2):
  placa → notebook: "LOG <texto>\\n", "BEGIN <rate>\\n", "AUD <n>\\n" + n bytes PCM, "END\\n"
  notebook → placa: "DONE\\n" quando todo o áudio até um END terminou de tocar.

Uso: python player.py --porta COM4
"""

from __future__ import annotations

import argparse
import sys
import threading
import time

TAXA_PADRAO = 24000
PREBUFFER_MS = 300  # folga antes de começar a tocar (contra áudio picotado)
BAUD = 921600


class LeitorSerial:
    """Parser incremental do fluxo vindo da placa.

    `alimentar(dados)` aceita pedaços arbitrários (inclusive cortando um bloco
    AUD no meio) e devolve a lista de eventos completos até ali:
      ("log", str) | ("begin", int) | ("audio", bytes) | ("end", None)

    Um bloco AUD cortado gera vários eventos "audio" (nunca vazios); juntos,
    eles têm exatamente os n bytes anunciados. Linhas desconhecidas viram "log".
    """

    def __init__(self) -> None:
        self._linha = bytearray()
        self._faltam = 0  # bytes de áudio ainda esperados do AUD atual

    def alimentar(self, dados: bytes) -> list[tuple]:
        eventos: list[tuple] = []
        i = 0
        n = len(dados)
        while i < n:
            if self._faltam > 0:
                pedaco = dados[i:i + self._faltam]
                self._faltam -= len(pedaco)
                i += len(pedaco)
                eventos.append(("audio", bytes(pedaco)))
                continue
            fim = dados.find(b"\n", i)
            if fim < 0:
                self._linha += dados[i:]
                break
            self._linha += dados[i:fim]
            i = fim + 1
            evento = self._interpretar(bytes(self._linha))
            self._linha.clear()
            if evento is not None:
                eventos.append(evento)
        return eventos

    def _interpretar(self, linha: bytes):
        texto = linha.rstrip(b"\r").decode("utf-8", errors="replace")
        if not texto:
            return None
        if texto.startswith("LOG "):
            return ("log", texto[4:])
        if texto == "LOG":
            return ("log", "")
        if texto == "END":
            return ("end", None)
        if texto == "BEEP":
            return ("beep", None)
        if texto.startswith("BEGIN "):
            try:
                return ("begin", int(texto[6:]))
            except ValueError:
                return ("log", texto)
        if texto.startswith("AUD "):
            try:
                tamanho = int(texto[4:])
            except ValueError:
                return ("log", texto)
            if tamanho < 0:
                return ("log", texto)
            self._faltam = tamanho
            return None
        return ("log", texto)


class BufferReproducao:
    """Fila de bytes PCM entre o leitor da serial e o callback de áudio.

    Cada `fim()` (END) marca a posição do fluxo; quando o callback consumiu
    tudo até essa marca, `pegar_done()` devolve True (uma vez por END).
    """

    def __init__(self, prebuffer_bytes: int = 0) -> None:
        self._dados = bytearray()
        self._trava = threading.Lock()
        self._recebidos = 0
        self._consumidos = 0
        self._marcas: list[int] = []
        # Pré-buffer: só começa a tocar com `prebuffer_bytes` acumulados (ou com um END
        # pendente), e volta a acumular quando esvazia. O áudio chega no ritmo exato da
        # fala; sem folga, qualquer atraso vira um "buraco" (áudio picotado).
        self._prebuffer = prebuffer_bytes
        self._tocando_stream = False

    def adicionar(self, dados: bytes) -> None:
        with self._trava:
            self._dados += dados
            self._recebidos += len(dados)

    def fim(self) -> None:
        with self._trava:
            self._marcas.append(self._recebidos)

    def consumir(self, n: int) -> bytes:
        """Tira n bytes da fila; completa com silêncio se faltar."""
        with self._trava:
            if not self._tocando_stream:
                end_pendente = any(m > self._consumidos for m in self._marcas)
                if len(self._dados) >= max(self._prebuffer, 1) or (end_pendente and self._dados):
                    self._tocando_stream = True
                else:
                    return b"\x00" * n
            pedaco = bytes(self._dados[:n])
            del self._dados[:n]
            self._consumidos += len(pedaco)
            if not self._dados:
                self._tocando_stream = False
        if len(pedaco) < n:
            pedaco += b"\x00" * (n - len(pedaco))
        return pedaco

    def tocando(self) -> bool:
        with self._trava:
            return len(self._dados) > 0

    def pegar_done(self) -> bool:
        with self._trava:
            prontas = [m for m in self._marcas if m <= self._consumidos]
            if not prontas:
                return False
            self._marcas = [m for m in self._marcas if m > self._consumidos]
            return True

    def limpar(self) -> None:
        with self._trava:
            self._dados.clear()
            self._consumidos = self._recebidos
            # marcas antigas ficam satisfeitas: o DONE sai para não travar a placa


# ------------------------------------------------------------------------ CLI

# ---------------------------------------------- sinal de "estou ouvindo"

def gerar_beep(taxa: int) -> bytes:
    """Três notas rápidas subindo (sol -> dó -> mi, ~310 ms), cada uma como uma "gota".

    Escolhido pelo usuário (variação "C") entre três opções; o anterior era agudo demais.
    """
    import numpy as np

    def nota(freq: float, ms: int) -> "np.ndarray":
        n = taxa * ms // 1000
        t = np.arange(n) / taxa
        ataque = np.minimum(1.0, np.arange(n) / max(1, taxa * 8 // 1000))   # 8 ms: sem estalo
        queda = np.exp(-5.0 * t / (ms / 1000))                               # se apaga como gota
        fim = np.minimum(1.0, (n - np.arange(n)) / (taxa * 0.005))           # 5 ms: sem estalo
        return np.sin(2 * np.pi * freq * t) * ataque * queda * fim

    sobreposicao = taxa * 10 // 1000
    notas = [nota(392.0, 80), nota(523.25, 80), nota(659.25, 170)]
    onda = np.zeros(sum(len(x) for x in notas) - sobreposicao * (len(notas) - 1))
    pos = 0
    for x in notas:
        onda[pos:pos + len(x)] += x
        pos += len(x) - sobreposicao
    onda /= max(1e-9, float(np.abs(onda).max()))
    return (onda * 6500).astype("<i2").tobytes()


def misturar(a: bytes, b: bytes) -> bytes:
    """Soma dois trechos PCM 16 bits do mesmo tamanho, com saturação."""
    import numpy as np

    soma = np.frombuffer(a, dtype="<i2").astype(np.int32) + np.frombuffer(b, dtype="<i2").astype(np.int32)
    return np.clip(soma, -32768, 32767).astype("<i2").tobytes()


class Efeitos:
    """Sons locais (BEEP) tocados por cima do áudio, fora do BufferReproducao (não geram DONE)."""

    def __init__(self) -> None:
        self._dados = bytearray()
        self._trava = threading.Lock()

    def tocar(self, pcm: bytes) -> None:
        with self._trava:
            self._dados = bytearray(pcm)  # um novo sinal substitui o anterior

    def consumir(self, n: int) -> bytes:
        with self._trava:
            pedaco = bytes(self._dados[:n])
            del self._dados[:n]
        return pedaco + b"\x00" * (n - len(pedaco))


class Saida:
    """Stream de áudio (sounddevice) alimentado pelo BufferReproducao."""

    def __init__(self, buffer: BufferReproducao, efeitos: "Efeitos | None" = None) -> None:
        self.buffer = buffer
        self.efeitos = efeitos or Efeitos()
        self.taxa = 0
        self.stream = None
        self.latencia = 0.0

    def abrir(self, taxa: int) -> None:
        if self.stream is not None and taxa == self.taxa:
            return
        import sounddevice as sd

        self.fechar()

        def callback(outdata, frames, tempo, status):  # noqa: ARG001
            outdata[:] = misturar(self.buffer.consumir(frames * 2), self.efeitos.consumir(frames * 2))

        self.stream = sd.RawOutputStream(
            samplerate=taxa, channels=1, dtype="int16", callback=callback
        )
        self.stream.start()
        self.taxa = taxa
        self.latencia = float(self.stream.latency or 0.0)
        print(f"[player] áudio {taxa} Hz, latência {self.latencia * 1000:.0f} ms", flush=True)

    def fechar(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None


def abrir_serial(porta: str):
    import serial

    while True:
        try:
            s = serial.Serial(porta, BAUD, timeout=0.02)
            print(f"[player] conectado em {porta}", flush=True)
            return s
        except serial.SerialException as e:
            print(f"[player] aguardando {porta}... ({e})", flush=True)
            time.sleep(2)


def executar(porta: str) -> None:
    import serial

    buffer = BufferReproducao(prebuffer_bytes=TAXA_PADRAO * 2 * PREBUFFER_MS // 1000)
    saida = Saida(buffer)
    saida.abrir(TAXA_PADRAO)
    done_em: list[float] = []  # instantes (monotonic) em que enviar DONE

    while True:
        ser = abrir_serial(porta)
        leitor = LeitorSerial()
        try:
            while True:
                dados = ser.read(ser.in_waiting or 1)
                for tipo, valor in leitor.alimentar(dados) if dados else []:
                    if tipo == "log":
                        print(f"[placa] {valor}", flush=True)
                    elif tipo == "begin":
                        saida.abrir(valor)
                        print(f"[player] BEGIN {valor}", flush=True)
                    elif tipo == "audio":
                        buffer.adicionar(valor)
                    elif tipo == "end":
                        buffer.fim()
                        print("[player] END", flush=True)
                    elif tipo == "beep":
                        saida.efeitos.tocar(gerar_beep(saida.taxa or TAXA_PADRAO))

                agora = time.monotonic()
                if buffer.pegar_done():
                    # o callback já entregou tudo; espera a latência do dispositivo
                    done_em.append(agora + saida.latencia)
                while done_em and done_em[0] <= agora:
                    done_em.pop(0)
                    ser.write(b"DONE\n")
                    print("[player] DONE", flush=True)
        except (serial.SerialException, OSError) as e:
            print(f"[player] serial caiu: {e}. Reabrindo...", flush=True)
            buffer.limpar()
            done_em.clear()
            try:
                ser.close()
            except Exception:
                pass
            time.sleep(1)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Toca o áudio recebido da placa pela USB serial.")
    p.add_argument("--porta", default="COM4", help="porta serial da placa (padrão COM4)")
    args = p.parse_args(argv)
    try:
        executar(args.porta)
    except KeyboardInterrupt:
        print("\n[player] encerrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
