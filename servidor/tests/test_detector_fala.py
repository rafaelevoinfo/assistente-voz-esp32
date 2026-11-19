import numpy as np

from voz.detector_fala import DetectorFala

TAXA = 16000


def pcm(ms: int, amplitude: int) -> bytes:
    n = TAXA * ms // 1000
    t = np.arange(n) / TAXA
    return (amplitude * np.sin(2 * np.pi * 440 * t)).astype("<i2").tobytes()


def fala(ms):
    return pcm(ms, 3000)


def silencio(ms):
    return pcm(ms, 50)


def alimentar_em_blocos(det: DetectorFala, dados: bytes, bloco: int = 640):
    eventos = []
    for i in range(0, len(dados), bloco):
        ev = det.processar(dados[i:i + bloco])
        if ev:
            eventos.append(ev)
    return eventos


def test_silencio_nao_dispara():
    assert alimentar_em_blocos(DetectorFala(), silencio(3000)) == []


def test_inicio_apos_min_fala():
    det = DetectorFala()
    assert alimentar_em_blocos(det, fala(100)) == []
    assert alimentar_em_blocos(det, fala(100)) == ["inicio"]
    assert alimentar_em_blocos(det, fala(500)) == []


def test_fim_apos_silencio():
    det = DetectorFala()
    assert alimentar_em_blocos(det, fala(300)) == ["inicio"]
    assert alimentar_em_blocos(det, silencio(900)) == []
    assert alimentar_em_blocos(det, silencio(100)) == ["fim"]


def test_pausa_curta_nao_encerra():
    det = DetectorFala()
    eventos = alimentar_em_blocos(det, fala(300) + silencio(500) + fala(300) + silencio(500))
    assert eventos == ["inicio"]


def test_fala_curta_interrompida_nao_inicia():
    det = DetectorFala()
    assert alimentar_em_blocos(det, fala(100) + silencio(40) + fala(100)) == []


def test_reset_volta_ao_estado_inicial():
    det = DetectorFala()
    alimentar_em_blocos(det, fala(300))
    det.reset()
    assert alimentar_em_blocos(det, silencio(2000)) == []
    assert alimentar_em_blocos(det, fala(200)) == ["inicio"]


def test_blocos_de_tamanho_arbitrario():
    det = DetectorFala()
    assert alimentar_em_blocos(det, fala(300) + silencio(1100), bloco=333) == ["inicio", "fim"]


# --- ronco grave (bug real: o mic da placa tem ~97% da energia do "silêncio" abaixo de
# 100 Hz; somado ao RMS, isso mantinha a janela de escuta aberta para sempre)

def ronco(ms, amplitude=1500):
    n = TAXA * ms // 1000
    t = np.arange(n) / TAXA
    return (amplitude * np.sin(2 * np.pi * 30 * t)).astype("<i2").tobytes()


def somar(a: bytes, b: bytes) -> bytes:
    x = np.frombuffer(a, "<i2").astype(np.int32) + np.frombuffer(b, "<i2").astype(np.int32)
    return np.clip(x, -32768, 32767).astype("<i2").tobytes()


def test_ronco_grave_nao_dispara():
    assert alimentar_em_blocos(DetectorFala(), ronco(5000)) == []


def test_fala_sobre_ronco_grave_inicia_e_termina():
    det = DetectorFala()
    audio = somar(ronco(2500), fala(1000) + silencio(1500))
    assert alimentar_em_blocos(det, audio) == ["inicio", "fim"]
