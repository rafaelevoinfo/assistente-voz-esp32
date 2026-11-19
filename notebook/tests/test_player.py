import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from player import BufferReproducao, LeitorSerial  # noqa: E402

FLUXO = b"BEGIN 24000\nAUD 4\n\x01\x02\x03\x04END\n"
ESPERADO = [("begin", 24000), ("audio", b"\x01\x02\x03\x04"), ("end", None)]


# ---------------------------------------------------------------- LeitorSerial

def test_log():
    assert LeitorSerial().alimentar(b"LOG oi\n") == [("log", "oi")]


def test_log_com_crlf_e_acentos():
    assert LeitorSerial().alimentar("LOG conexão ok\r\n".encode()) == [("log", "conexão ok")]


def test_begin_audio_end():
    assert LeitorSerial().alimentar(FLUXO) == ESPERADO


def test_audio_em_pedacos():
    leitor = LeitorSerial()
    eventos = []
    for i in range(len(FLUXO)):
        eventos += leitor.alimentar(FLUXO[i:i + 1])
    # Pedaços de áudio podem vir fragmentados; juntando, o conteúdo é o mesmo.
    assert eventos[0] == ("begin", 24000)
    assert eventos[-1] == ("end", None)
    audio = b"".join(d for t, d in eventos if t == "audio")
    assert audio == b"\x01\x02\x03\x04"
    assert all(t in ("begin", "audio", "end") for t, _ in eventos)


def test_audio_em_pedacos_nao_emite_vazio():
    leitor = LeitorSerial()
    eventos = []
    for i in range(len(FLUXO)):
        eventos += leitor.alimentar(FLUXO[i:i + 1])
    assert all(d for t, d in eventos if t == "audio")


def test_bloco_aud_cortado_no_meio():
    leitor = LeitorSerial()
    e1 = leitor.alimentar(b"BEGIN 24000\nAUD 4\n\x01\x02")
    e2 = leitor.alimentar(b"\x03\x04END\nLOG fim\n")
    assert e1 == [("begin", 24000), ("audio", b"\x01\x02")]
    assert e2 == [("audio", b"\x03\x04"), ("end", None), ("log", "fim")]


def test_binario_com_quebra_de_linha():
    payload = b"\n\nLOG \n\r\n"  # bytes que parecem texto
    dados = b"AUD %d\n" % len(payload) + payload + b"LOG depois\n"
    assert LeitorSerial().alimentar(dados) == [("audio", payload), ("log", "depois")]


def test_linha_desconhecida_vira_log():
    assert LeitorSerial().alimentar(b"lixo do boot\n") == [("log", "lixo do boot")]


def test_aud_invalido_vira_log_e_nao_trava():
    assert LeitorSerial().alimentar(b"AUD xx\nLOG ok\n") == [
        ("log", "AUD xx"),
        ("log", "ok"),
    ]


def test_linha_vazia_ignorada():
    assert LeitorSerial().alimentar(b"\n\r\nLOG a\n") == [("log", "a")]


# ------------------------------------------------------------ BufferReproducao

def test_buffer_consome_e_completa_com_silencio():
    b = BufferReproducao()
    b.adicionar(b"\x01\x02\x03\x04")
    assert b.consumir(6) == b"\x01\x02\x03\x04\x00\x00"
    assert b.consumir(2) == b"\x00\x00"


def test_done_so_depois_do_end_e_buffer_vazio():
    b = BufferReproducao()
    b.adicionar(b"\x01\x02\x03\x04")
    assert not b.pegar_done()
    b.fim()
    assert not b.pegar_done()  # ainda há áudio a tocar
    b.consumir(4)
    assert b.pegar_done()
    assert not b.pegar_done()  # DONE só uma vez por END


def test_done_com_end_sem_audio():
    b = BufferReproducao()
    b.fim()
    assert b.pegar_done()


def test_dois_audios_seguidos_um_done_por_end():
    b = BufferReproducao()
    b.adicionar(b"\x01\x02")
    b.fim()
    b.adicionar(b"\x03\x04")  # novo BEGIN/AUD antes de terminar de tocar
    assert not b.pegar_done()
    b.consumir(2)
    assert b.pegar_done()  # tudo até o 1º END já tocou
    b.consumir(2)
    assert not b.pegar_done()  # o segundo áudio ainda não teve END
    b.fim()
    assert b.pegar_done()


def test_tocando():
    b = BufferReproducao()
    assert not b.tocando()
    b.adicionar(b"\x01\x02")
    assert b.tocando()
    b.consumir(2)
    assert not b.tocando()


# ------------------------------------------------- pré-buffer (contra áudio picotado)

def test_prebuffer_espera_acumular_antes_de_tocar():
    b = BufferReproducao(prebuffer_bytes=8)
    b.adicionar(b"\x01\x02\x03\x04")
    assert b.consumir(4) == b"\x00" * 4      # ainda acumulando: toca silêncio, não consome
    b.adicionar(b"\x05\x06\x07\x08")
    assert b.consumir(4) == b"\x01\x02\x03\x04"
    assert b.consumir(4) == b"\x05\x06\x07\x08"


def test_prebuffer_end_libera_audio_curto():
    b = BufferReproducao(prebuffer_bytes=8)
    b.adicionar(b"\x01\x02")
    b.fim()                                   # áudio menor que o pré-buffer: toca mesmo assim
    assert b.consumir(2) == b"\x01\x02"
    assert b.pegar_done()


def test_prebuffer_volta_a_acumular_apos_esvaziar():
    b = BufferReproducao(prebuffer_bytes=4)
    b.adicionar(b"\x01\x02\x03\x04")
    assert b.consumir(4) == b"\x01\x02\x03\x04"
    b.adicionar(b"\x05\x06")                  # chegou pouco depois de esvaziar
    assert b.consumir(2) == b"\x00\x00"       # espera acumular de novo
    b.adicionar(b"\x07\x08")
    assert b.consumir(4) == b"\x05\x06\x07\x08"


# ------------------------------------------------- sinal de "estou ouvindo" (BEEP)

import numpy as np  # noqa: E402

from player import Efeitos, gerar_beep, misturar  # noqa: E402


def test_leitor_reconhece_beep():
    assert LeitorSerial().alimentar(b"BEEP\n") == [("beep", None)]


def test_beep_curto_e_sem_estourar():
    pcm = gerar_beep(24000)
    amostras = np.frombuffer(pcm, dtype="<i2")
    assert 0.2 <= len(amostras) / 24000 <= 0.4            # breve (~310 ms)
    assert 3000 < np.abs(amostras).max() < 20000           # audível, sem saturar
    assert abs(int(amostras[0])) < 200 and abs(int(amostras[-1])) < 200  # sem estalo no começo/fim


def test_beep_sobe_de_tom():
    amostras = np.frombuffer(gerar_beep(24000), dtype="<i2").astype(float)
    metade = len(amostras) // 2

    def freq(trecho):
        espectro = np.abs(np.fft.rfft(trecho))
        return np.fft.rfftfreq(len(trecho), 1 / 24000)[espectro.argmax()]

    assert freq(amostras[metade:]) > freq(amostras[:metade])  # dois tons ascendentes


def test_efeitos_toca_e_esvazia():
    e = Efeitos()
    e.tocar(b"\x01\x00\x02\x00")
    assert e.consumir(6) == b"\x01\x00\x02\x00\x00\x00"
    assert e.consumir(2) == b"\x00\x00"


def test_misturar_soma_e_satura():
    a = np.array([1000, 30000, -30000], dtype="<i2").tobytes()
    b = np.array([500, 10000, -10000], dtype="<i2").tobytes()
    assert np.frombuffer(misturar(a, b), dtype="<i2").tolist() == [1500, 32767, -32768]


def test_beep_nao_gera_done():
    b = BufferReproducao()
    e = Efeitos()
    e.tocar(gerar_beep(24000))
    e.consumir(100000)
    assert not b.pegar_done()   # o efeito não passa pelo buffer de reprodução
