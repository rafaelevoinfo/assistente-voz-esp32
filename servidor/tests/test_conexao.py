import pytest

from tests.fakes import EnvioFalso, FabricaFalsa, RelogioFalso, SintetizadorFalso, pcm16k
from voz.conexao import CaixaDeSaida, ConexaoPlaca, Estado
from voz.config import Config
from voz.tarefas import ResultadoTarefa

CONFIG = Config(token_placa="t", google_api_key="g", janela_continuacao_s=8.0, espera_resposta_s=6.0)


class Ambiente:
    def __init__(self, memoria=None):
        self.fabrica = FabricaFalsa()
        self.sint = SintetizadorFalso()
        self.caixa = CaixaDeSaida()
        self.relogio = RelogioFalso()
        self.pedidos: list[str] = []
        self.a_frente = 0
        self.envio = EnvioFalso()
        self.conexao = ConexaoPlaca(
            CONFIG, self.fabrica, self.sint, self.enfileirar, self.caixa, relogio=self.relogio,
            memoria=memoria,
        )

    def enfileirar(self, pedido: str) -> int:
        self.pedidos.append(pedido)
        return self.a_frente

    async def conectar(self):
        await self.conexao.conectar(self.envio)
        await self.conexao.ao_texto({"type": "hello", "fw": "1.0"})

    async def mic(self, ms: int, amplitude: int):
        """Envia o mic em blocos de 20 ms, avançando o relógio e chamando tick."""
        dados = pcm16k(ms, amplitude)
        for i in range(0, len(dados), 640):
            await self.conexao.ao_audio(dados[i:i + 640])
            self.relogio.avancar(0.02)
            await self.conexao.tick()

    async def falar(self, ms=400):
        await self.mic(ms, 3000)

    async def silencio(self, ms):
        await self.mic(ms, 50)

    async def esperar(self, s):
        self.relogio.avancar(s)
        await self.conexao.tick()

    async def wake(self):
        await self.conexao.ao_texto({"type": "wake"})

    async def resposta_completa(self, sessao=None):
        sessao = sessao or self.fabrica.ultima
        await sessao.modelo_fala()
        await sessao.modelo_termina()


@pytest.fixture
async def amb():
    a = Ambiente()
    await a.conectar()
    return a


async def test_conectar_e_hello_vai_para_ocioso():
    a = Ambiente()
    await a.conexao.conectar(a.envio)
    assert a.conexao.estado == Estado.DESCONECTADO
    await a.conexao.ao_texto({"type": "hello", "fw": "1.0"})
    assert a.conexao.estado == Estado.OCIOSO
    assert a.envio.mensagens == []


async def test_wake_abre_sessao_e_pede_listen(amb):
    await amb.wake()
    assert amb.envio.textos() == [{"type": "listen"}]
    assert amb.conexao.estado == Estado.OUVINDO
    assert amb.fabrica.ultima.iniciada_com == [None]


async def test_wake_fora_do_ocioso_e_ignorado(amb):
    await amb.wake()
    await amb.wake()
    assert len(amb.fabrica.sessoes) == 1
    assert amb.envio.textos() == [{"type": "listen"}]


async def test_tipo_desconhecido_e_ignorado(amb):
    await amb.conexao.ao_texto({"type": "coisa_nova"})
    assert amb.conexao.estado == Estado.OCIOSO


async def test_audio_do_mic_vai_para_sessao(amb):
    await amb.wake()
    await amb.conexao.ao_audio(b"\x00\x01" * 320)
    assert amb.fabrica.ultima.audio == [b"\x00\x01" * 320]


async def test_audio_do_mic_fora_de_ouvindo_e_descartado(amb):
    await amb.conexao.ao_audio(b"\x00\x01" * 320)
    assert amb.fabrica.sessoes == []


async def test_resposta_do_modelo_vira_stop_listen_e_audio(amb):
    await amb.wake()
    await amb.falar()
    amb.envio.limpar()
    s = amb.fabrica.ultima
    await s.modelo_fala(b"\x01\x00" * 2400)
    assert amb.conexao.estado == Estado.RESPONDENDO
    await s.modelo_termina()
    assert amb.envio.tipos() == ["stop_listen", "audio_start", "bin", "audio_end"]
    assert amb.envio.textos()[1] == {"type": "audio_start", "rate": 24000}
    assert amb.conexao.estado == Estado.TOCANDO


async def test_audio_do_modelo_dividido_em_blocos_pares_de_ate_4800(amb):
    await amb.wake()
    s = amb.fabrica.ultima
    await s.modelo_fala(b"\x01" * 7001)
    await s.modelo_fala(b"\x02" * 3)
    await s.modelo_termina()
    blocos = amb.envio.binarios()
    assert all(len(b) <= 4800 and len(b) % 2 == 0 for b in blocos)
    assert sum(len(b) for b in blocos) == 7004


async def test_playback_done_reabre_escuta_na_mesma_sessao(amb):
    await amb.wake()
    await amb.falar()
    await amb.resposta_completa()
    amb.envio.limpar()
    await amb.conexao.ao_texto({"type": "playback_done"})
    assert amb.envio.textos() == [{"type": "listen"}]
    assert amb.conexao.estado == Estado.OUVINDO
    assert len(amb.fabrica.sessoes) == 1


async def test_duas_respostas_seguidas_esperam_dois_playback_done(amb):
    await amb.wake()
    s = amb.fabrica.ultima
    await amb.resposta_completa()
    await amb.resposta_completa()
    assert amb.envio.tipos().count("audio_end") == 2
    await amb.conexao.ao_texto({"type": "playback_done"})
    assert amb.conexao.estado == Estado.TOCANDO
    await amb.conexao.ao_texto({"type": "playback_done"})
    assert amb.conexao.estado == Estado.OUVINDO
    assert s is amb.fabrica.ultima


async def test_janela_fecha_sem_fala(amb):
    await amb.wake()
    s = amb.fabrica.ultima
    await amb.esperar(7.9)
    assert amb.conexao.estado == Estado.OUVINDO
    await amb.esperar(0.2)
    assert s.encerrada
    assert amb.envio.textos()[-1] == {"type": "session_end"}
    assert amb.conexao.estado == Estado.OCIOSO


async def test_ruido_baixo_nao_segura_a_janela(amb):
    await amb.wake()
    await amb.silencio(8200)
    assert amb.fabrica.ultima.encerrada
    assert amb.conexao.estado == Estado.OCIOSO


async def test_janela_reabre_apos_playback_e_fecha(amb):
    await amb.wake()
    await amb.falar()
    await amb.resposta_completa()
    await amb.conexao.ao_texto({"type": "playback_done"})
    await amb.esperar(8.1)
    assert amb.envio.textos()[-1] == {"type": "session_end"}
    assert amb.fabrica.ultima.encerrada


async def test_silencio_do_modelo_apos_fala_fecha_janela(amb):
    await amb.wake()
    await amb.falar(400)
    await amb.silencio(1100)  # detector emite "fim"
    assert amb.conexao.estado == Estado.OUVINDO
    await amb.esperar(5.0)
    assert amb.conexao.estado == Estado.OUVINDO
    await amb.esperar(1.1)
    assert amb.envio.textos()[-1] == {"type": "session_end"}
    assert amb.conexao.estado == Estado.OCIOSO


async def test_fala_longa_nao_fecha_janela(amb):
    await amb.wake()
    await amb.falar(9000)
    assert amb.conexao.estado == Estado.OUVINDO


async def test_pedido_codigo_enfileira_e_retorna_texto(amb):
    await amb.wake()
    retorno = await amb.fabrica.ultima.modelo_pede_codigo("adicione uma tag de cupom")
    assert amb.pedidos == ["adicione uma tag de cupom"]
    assert "Claude Code" in retorno


async def test_pedido_codigo_com_fila_informa_posicao(amb):
    amb.a_frente = 2
    await amb.wake()
    retorno = await amb.fabrica.ultima.modelo_pede_codigo("x")
    assert "fila" in retorno and "2" in retorno


async def test_resultado_ocioso_e_falado_e_abre_continuacao(amb):
    await amb.conexao.ao_resultado(ResultadoTarefa("p", "Pronto, PR 12 aberto.", True))
    assert amb.sint.textos == ["Pronto, PR 12 aberto."]
    assert amb.envio.tipos()[0] == "audio_start" and amb.envio.tipos()[-1] == "audio_end"
    assert amb.conexao.estado == Estado.TOCANDO
    amb.envio.limpar()
    await amb.conexao.ao_texto({"type": "playback_done"})
    assert amb.fabrica.ultima.iniciada_com == ["Pronto, PR 12 aberto."]
    assert amb.envio.textos() == [{"type": "listen"}]
    assert amb.conexao.estado == Estado.OUVINDO


async def test_resultado_espera_conversa_terminar(amb):
    await amb.wake()
    amb.envio.limpar()
    await amb.conexao.ao_resultado(ResultadoTarefa("p", "Feito.", True))
    assert amb.envio.mensagens == [] and amb.sint.textos == []
    await amb.esperar(8.1)  # janela fecha
    assert amb.sint.textos == ["Feito."]
    assert amb.envio.tipos()[:2] == ["session_end", "audio_start"]


async def test_resultado_durante_resposta_espera(amb):
    await amb.wake()
    await amb.fabrica.ultima.modelo_fala()
    await amb.conexao.ao_resultado(ResultadoTarefa("p", "Feito.", True))
    assert amb.sint.textos == []


async def test_resultado_entregue_apos_reconexao(amb):
    await amb.conexao.desconectar()
    assert amb.conexao.estado == Estado.DESCONECTADO
    await amb.conexao.ao_resultado(ResultadoTarefa("p", "Feito.", True))
    novo = EnvioFalso()
    await amb.conexao.conectar(novo)
    assert novo.mensagens == []
    await amb.conexao.ao_texto({"type": "hello", "fw": "1.0"})
    assert novo.tipos()[0] == "audio_start"
    assert amb.sint.textos == ["Feito."]


async def test_varios_resultados_pendentes_sao_entregues_em_ordem(amb):
    await amb.conexao.desconectar()
    await amb.conexao.ao_resultado(ResultadoTarefa("a", "Primeiro.", True))
    await amb.conexao.ao_resultado(ResultadoTarefa("b", "Segundo.", True))
    await amb.conectar()
    assert amb.sint.textos == ["Primeiro."]
    await amb.conexao.ao_texto({"type": "playback_done"})  # abre continuação
    await amb.esperar(8.1)  # janela fecha sem fala -> próximo resultado
    assert amb.sint.textos == ["Primeiro.", "Segundo."]


async def test_desconectar_encerra_sessao(amb):
    await amb.wake()
    s = amb.fabrica.ultima
    await amb.conexao.desconectar()
    assert s.encerrada
    assert amb.conexao.estado == Estado.DESCONECTADO


async def test_eventos_de_sessao_antiga_sao_ignorados(amb):
    await amb.wake()
    velha = amb.fabrica.ultima
    await amb.esperar(8.1)
    amb.envio.limpar()
    await velha.modelo_fala()
    assert amb.envio.mensagens == []


async def test_playback_done_nao_chega_servidor_assume_apos_timeout(amb):
    """Contrato §1.6: sem playback_done em duração + 6 s após audio_end, o servidor assume."""
    await amb.wake()
    s = amb.fabrica.ultima
    await s.modelo_fala(b"\x01\x00" * 24000)  # 48000 bytes = 1 s a 24 kHz
    await s.modelo_termina()
    assert amb.conexao.estado == Estado.TOCANDO
    amb.envio.limpar()
    await amb.esperar(6.9)
    assert amb.conexao.estado == Estado.TOCANDO and amb.envio.mensagens == []
    await amb.esperar(0.2)
    assert amb.conexao.estado == Estado.OUVINDO
    assert amb.envio.textos() == [{"type": "listen"}]


async def test_timeout_playback_de_resultado_empurrado(amb):
    await amb.conexao.ao_resultado(ResultadoTarefa("p", "Feito.", True))  # 0,5 s de áudio
    await amb.esperar(6.4)
    assert amb.conexao.estado == Estado.TOCANDO
    await amb.esperar(0.2)
    assert amb.conexao.estado == Estado.OUVINDO
    assert amb.fabrica.ultima.iniciada_com == ["Feito."]


async def test_falha_ao_iniciar_sessao_volta_ao_ocioso(amb):
    criar_original = amb.fabrica.criar

    async def falhar(contexto):
        raise RuntimeError("sem rede")

    def criar(eventos):
        sessao = criar_original(eventos)
        sessao.iniciar = falhar
        return sessao

    amb.fabrica.criar = criar
    await amb.wake()
    assert amb.conexao.estado == Estado.OCIOSO
    assert amb.envio.textos()[-1] == {"type": "session_end"}


async def test_falha_no_tts_nao_trava(amb):
    async def falhar(texto):
        raise RuntimeError("tts fora do ar")

    amb.sint.sintetizar = falhar
    await amb.conexao.ao_resultado(ResultadoTarefa("p", "Feito.", True))
    assert amb.conexao.estado == Estado.OCIOSO
    await amb.wake()
    assert amb.conexao.estado == Estado.OUVINDO


def test_caixa_de_saida_fifo():
    c = CaixaDeSaida()
    assert c.retirar() is None
    c.adicionar("a")
    c.adicionar("b")
    c.devolver("z")
    assert [c.retirar(), c.retirar(), c.retirar(), c.retirar()] == ["z", "a", "b", None]


async def test_escuta_tem_duracao_maxima(amb):
    # trava de segurança: se o detector achar que a fala nunca termina (ruído), a sessão
    # não pode ficar aberta para sempre gerando custo no provedor
    await amb.wake()
    s = amb.fabrica.ultima
    await amb.falar()            # detector: "inicio", e nunca chega um "fim"
    await amb.esperar(59)
    assert amb.conexao.estado == Estado.OUVINDO
    await amb.esperar(2)
    assert s.encerrada
    assert amb.envio.textos()[-1] == {"type": "session_end"}
    assert amb.conexao.estado == Estado.OCIOSO



# ------------------------------------------------- memória (spec §7.2)

from voz.memoria import Historico, Memoria  # noqa: E402


async def amb_com_memoria(pasta):
    a = Ambiente(memoria=Memoria(pasta))
    await a.conectar()
    return a


async def test_troca_de_conversa_vai_para_o_historico(tmp_path):
    a = await amb_com_memoria(tmp_path)
    await a.wake()
    s = a.fabrica.ultima
    await a.falar()
    await s.usuario_transcrito("Quanto é 2 mais 2?")
    await s.modelo_fala()
    await s.modelo_transcrito("Qua")
    await s.modelo_transcrito("tro.")
    await s.modelo_termina()
    [troca] = Historico(tmp_path).ultimas(5)
    assert (troca.origem, troca.pergunta, troca.resposta) == ("conversa", "Quanto é 2 mais 2?", "Quatro.")


async def test_cada_resposta_vira_uma_troca(tmp_path):
    a = await amb_com_memoria(tmp_path)
    await a.wake()
    s = a.fabrica.ultima
    for pergunta, resposta in (("primeira", "um"), ("segunda", "dois")):
        await s.usuario_transcrito(pergunta)
        await s.modelo_fala()
        await s.modelo_transcrito(resposta)
        await s.modelo_termina()
        await a.conexao.ao_texto({"type": "playback_done"})
    assert [(t.pergunta, t.resposta) for t in Historico(tmp_path).ultimas(5)] == [("primeira", "um"), ("segunda", "dois")]


async def test_resultado_do_claude_code_vai_para_o_historico(tmp_path):
    a = await amb_com_memoria(tmp_path)
    await a.conexao.ao_resultado(ResultadoTarefa("ajuste a página", "Pronto, PR 42.", True))
    [troca] = Historico(tmp_path).ultimas(5)
    assert (troca.origem, troca.pergunta, troca.resposta) == ("claude_code", "ajuste a página", "Pronto, PR 42.")


async def test_sessao_recebe_a_memoria(tmp_path):
    (tmp_path / "CONTEXTO.md").write_text("Meu nome é Rafael.", encoding="utf-8")
    a = await amb_com_memoria(tmp_path)
    await a.wake()
    assert "Meu nome é Rafael." in a.fabrica.ultima.memorias[0]


async def test_sem_memoria_continua_funcionando(amb):
    await amb.wake()
    assert amb.fabrica.ultima.memorias == [None]
