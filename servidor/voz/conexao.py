"""Máquina de estados da conexão com a placa (ver docs/contrato.md e spec §5).

Não importa pipecat nem google.genai: fala com o provedor só pelas interfaces
de ``voz.interfaces``.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from enum import Enum
from typing import Callable, Protocol

from voz.config import Config
from voz.detector_fala import DetectorFala
from voz.memoria import Memoria
from voz.interfaces import EventosSessao, FabricaSessaoVoz, SessaoVoz, Sintetizador
from voz.protocolo import TAXA_SAIDA, codificar
from voz.tarefas import ResultadoTarefa

log = logging.getLogger(__name__)

BLOCO_SAIDA = 4800  # bytes = 100 ms a 24 kHz
BYTES_POR_SEGUNDO_SAIDA = TAXA_SAIDA * 2
FOLGA_PLAYBACK_S = 6.0  # contrato §1.6: duração do áudio + 6 s
LIMITE_SILENCIO_RESPOSTA_S = 15.0  # modelo parou de mandar áudio sem fechar o turno


class Envio(Protocol):
    async def texto(self, msg: str) -> None: ...
    async def binario(self, dados: bytes) -> None: ...


class CaixaDeSaida:
    """Resultados que ainda não puderam ser falados. Uma por servidor (sobrevive a reconexões)."""

    def __init__(self) -> None:
        self._itens: deque[str] = deque()

    def adicionar(self, texto: str) -> None:
        self._itens.append(texto)

    def devolver(self, texto: str) -> None:
        """Recoloca no início (entrega interrompida)."""
        self._itens.appendleft(texto)

    def retirar(self) -> str | None:
        return self._itens.popleft() if self._itens else None

    def __len__(self) -> int:
        return len(self._itens)


class Estado(Enum):
    DESCONECTADO = "desconectado"
    OCIOSO = "ocioso"
    OUVINDO = "ouvindo"
    RESPONDENDO = "respondendo"
    TOCANDO = "tocando"


def texto_retorno_ferramenta(a_frente: int) -> str:
    if a_frente == 0:
        return "Tarefa enviada ao Claude Code. Avise o usuário em uma frase curta."
    return (
        f"Tarefa colocada na fila; há {a_frente} tarefa(s) antes dela. "
        "Avise o usuário em uma frase curta."
    )


class ConexaoPlaca:
    def __init__(
        self,
        config: Config,
        fabrica: FabricaSessaoVoz,
        sintetizador: Sintetizador,
        enfileirar: Callable[[str], int],
        caixa: CaixaDeSaida,
        relogio: Callable[[], float] = time.monotonic,
        memoria: "Memoria | None" = None,
    ):
        self._config = config
        self._memoria = memoria
        self._pergunta: list[str] = []  # transcrição da fala desde a última resposta
        self._resposta: list[str] = []  # transcrição da resposta em andamento
        self._fabrica = fabrica
        self._sintetizador = sintetizador
        self._enfileirar = enfileirar
        self._caixa = caixa
        self._relogio = relogio

        self._estado = Estado.DESCONECTADO
        self._envio: Envio | None = None
        self._geracao = 0  # muda a cada conectar/desconectar
        self._sessao: SessaoVoz | None = None
        self._detector = DetectorFala()
        self.ultimo_texto: str | None = None

        # janela de escuta
        self._janela_desde = 0.0
        self._fala_iniciada = False
        self._fim_fala_em: float | None = None

        # resposta / reprodução
        self._resto = b""  # byte ímpar pendente do áudio do modelo
        self._bytes_resposta = 0
        self._ultimo_audio_modelo = 0.0
        self._audios_tocando = 0  # audio_end enviados sem playback_done
        self._prazo_playback: float | None = None

    @property
    def estado(self) -> Estado:
        return self._estado

    # ------------------------------------------------------------------ conexão

    async def conectar(self, envio: Envio) -> None:
        self._geracao += 1
        self._envio = envio
        self._estado = Estado.DESCONECTADO  # aguarda o hello
        self._zerar_reproducao()

    async def desconectar(self) -> None:
        self._geracao += 1
        self._envio = None
        self._estado = Estado.DESCONECTADO
        self._zerar_reproducao()
        await self._descartar_sessao()

    # ---------------------------------------------------------- mensagens placa

    async def ao_texto(self, msg: dict) -> None:
        tipo = msg.get("type")
        if tipo == "hello":
            await self._ao_hello(msg)
        elif tipo == "wake":
            await self._ao_wake()
        elif tipo == "playback_done":
            await self._ao_playback_done()
        else:
            log.info("mensagem ignorada da placa: %r", tipo)

    async def _ao_hello(self, msg: dict) -> None:
        if self._envio is None:
            return
        log.info("placa conectada (fw=%s)", msg.get("fw"))
        if self._estado != Estado.DESCONECTADO:
            # hello repetido na mesma conexão: recomeça do zero
            await self._descartar_sessao()
            self._zerar_reproducao()
        self._estado = Estado.OCIOSO
        await self._entregar_proximo()

    async def _ao_wake(self) -> None:
        if self._estado != Estado.OCIOSO:
            log.info("wake ignorado no estado %s", self._estado.name)
            return
        await self._abrir_sessao(contexto=None)

    async def _ao_playback_done(self) -> None:
        if self._audios_tocando > 0:
            self._audios_tocando -= 1
        if self._estado == Estado.TOCANDO and self._audios_tocando == 0 and self._prazo_playback is not None:
            await self._apos_tocar()

    async def ao_audio(self, pcm16k: bytes) -> None:
        if self._estado != Estado.OUVINDO or self._sessao is None:
            return
        sessao = self._sessao
        try:
            await sessao.enviar_audio(pcm16k)
        except Exception:
            log.exception("falha ao enviar áudio do mic ao provedor")
        evento = self._detector.processar(pcm16k)
        if evento == "inicio":
            self._fala_iniciada = True
            self._fim_fala_em = None
        elif evento == "fim":
            self._fim_fala_em = self._relogio()

    # ----------------------------------------------------------- resultados

    async def ao_resultado(self, r: ResultadoTarefa) -> None:
        log.info("resultado do Claude Code (sucesso=%s): %s", r.sucesso, r.texto)
        if self._memoria is not None:
            try:
                self._memoria.registrar_tarefa(r.pedido, r.texto)
            except Exception:
                log.exception("falha ao gravar o resultado no histórico")
        if self._estado == Estado.OCIOSO and self._envio is not None:
            await self._entregar(r.texto)
        else:
            self._caixa.adicionar(r.texto)

    # ------------------------------------------------------------------ tick

    async def tick(self) -> None:
        agora = self._relogio()
        if self._estado == Estado.OUVINDO and self._sessao is not None:
            if not self._fala_iniciada and agora - self._janela_desde >= self._config.janela_continuacao_s:
                log.info("janela de escuta fechou sem fala")
                await self._fechar_sessao()
            elif self._fim_fala_em is not None and agora - self._fim_fala_em >= self._config.espera_resposta_s:
                log.info("modelo não respondeu após a fala; fechando a sessão")
                await self._fechar_sessao()
            elif agora - self._janela_desde >= self._config.escuta_max_s:
                log.warning("escuta passou de %.0f s sem resposta do modelo; fechando a sessão",
                            self._config.escuta_max_s)
                await self._fechar_sessao()
        elif self._estado == Estado.RESPONDENDO:
            if agora - self._ultimo_audio_modelo >= LIMITE_SILENCIO_RESPOSTA_S:
                log.warning("modelo parou de mandar áudio sem fechar a resposta")
                await self._fim_resposta_modelo()
        elif self._estado == Estado.TOCANDO:
            if self._prazo_playback is not None and agora >= self._prazo_playback:
                log.warning("playback_done não chegou; assumindo fim da reprodução")
                self._audios_tocando = 0
                await self._apos_tocar()

    # --------------------------------------------------------------- sessão

    def _criar_eventos(self, sessao_ref: list) -> EventosSessao:
        def atual() -> bool:
            return bool(sessao_ref) and sessao_ref[0] is self._sessao and self._sessao is not None

        async def ao_audio(pcm: bytes) -> None:
            if atual():
                await self._audio_modelo(pcm)

        async def ao_fim_resposta() -> None:
            if atual():
                await self._fim_resposta_modelo()

        async def ao_texto_usuario(texto: str) -> None:
            if atual() and texto.strip():
                self._pergunta.append(texto.strip())

        async def ao_texto_modelo(texto: str) -> None:
            if atual():
                self._resposta.append(texto)

        async def ao_pedido_codigo(pedido: str) -> str:
            a_frente = self._enfileirar(pedido)
            if atual() and self._fim_fala_em is not None:
                self._fim_fala_em = self._relogio()  # dá tempo para o modelo confirmar
            return texto_retorno_ferramenta(a_frente)

        return EventosSessao(
            ao_audio=ao_audio,
            ao_fim_resposta=ao_fim_resposta,
            ao_pedido_codigo=ao_pedido_codigo,
            ao_texto_usuario=ao_texto_usuario,
            ao_texto_modelo=ao_texto_modelo,
        )

    async def _abrir_sessao(self, contexto: str | None) -> None:
        geracao = self._geracao
        ref: list = []
        sessao = self._fabrica.criar(self._criar_eventos(ref))
        ref.append(sessao)
        self._sessao = sessao
        self._estado = Estado.OUVINDO
        self._fala_iniciada = False
        self._fim_fala_em = None
        self._janela_desde = self._relogio()
        self._pergunta, self._resposta = [], []
        memoria = None
        if self._memoria is not None:
            try:
                memoria = self._memoria.texto_para_sessao()
            except Exception:
                log.exception("falha ao ler a memória; seguindo sem ela")
        try:
            await sessao.iniciar(contexto, memoria)
        except Exception:
            log.exception("falha ao iniciar a sessão de voz")
            if self._sessao is sessao:
                self._sessao = None
            await self._encerrar_sessao_silencioso(sessao)
            if geracao == self._geracao and self._envio is not None:
                self._estado = Estado.OCIOSO
                await self._enviar_texto("session_end")
                await self._entregar_proximo()
            return
        if geracao != self._geracao or self._sessao is not sessao:
            await self._encerrar_sessao_silencioso(sessao)
            return
        await self._abrir_escuta()

    async def _abrir_escuta(self) -> None:
        self._estado = Estado.OUVINDO
        self._detector.reset()
        self._fala_iniciada = False
        self._fim_fala_em = None
        self._janela_desde = self._relogio()
        await self._enviar_texto("listen")

    async def _fechar_sessao(self) -> None:
        """Fecha a sessão no provedor, manda session_end e volta ao ocioso."""
        sessao = self._sessao
        self._sessao = None
        self._estado = Estado.OCIOSO
        self._zerar_reproducao()
        await self._enviar_texto("session_end")
        if sessao is not None:
            await self._encerrar_sessao_silencioso(sessao)
        if self._estado == Estado.OCIOSO:
            await self._entregar_proximo()

    async def _descartar_sessao(self) -> None:
        sessao = self._sessao
        self._sessao = None
        if sessao is not None:
            await self._encerrar_sessao_silencioso(sessao)

    @staticmethod
    async def _encerrar_sessao_silencioso(sessao: SessaoVoz) -> None:
        try:
            await sessao.encerrar()
        except Exception:
            log.exception("falha ao encerrar a sessão de voz")

    # ------------------------------------------------------- áudio do modelo

    async def _audio_modelo(self, pcm: bytes) -> None:
        if self._envio is None:
            return
        if self._estado == Estado.OUVINDO:
            await self._enviar_texto("stop_listen")
            await self._iniciar_resposta()
        elif self._estado == Estado.TOCANDO:
            # nova fala do modelo enquanto a anterior ainda toca (ex.: após a ferramenta)
            await self._iniciar_resposta()
        elif self._estado != Estado.RESPONDENDO:
            return
        self._ultimo_audio_modelo = self._relogio()
        dados = self._resto + pcm
        corte = len(dados) - (len(dados) % 2)
        self._resto = dados[corte:]
        await self._enviar_blocos(dados[:corte])

    async def _iniciar_resposta(self) -> None:
        self._estado = Estado.RESPONDENDO
        self._resto = b""
        self._bytes_resposta = 0
        self._prazo_playback = None
        self._ultimo_audio_modelo = self._relogio()
        await self._enviar_texto("audio_start", rate=TAXA_SAIDA)

    async def _fim_resposta_modelo(self) -> None:
        if self._estado != Estado.RESPONDENDO:
            return
        self._resto = b""  # um byte solto não forma amostra
        self._registrar_troca()
        await self._finalizar_audio()

    def _registrar_troca(self) -> None:
        pergunta = " ".join(self._pergunta).strip()
        resposta = "".join(self._resposta).strip()
        self._pergunta, self._resposta = [], []
        if self._memoria is None or not (pergunta or resposta):
            return
        try:
            self._memoria.registrar_conversa(pergunta, resposta)
        except Exception:
            log.exception("falha ao gravar a troca no histórico")

    async def _enviar_blocos(self, dados: bytes) -> None:
        for i in range(0, len(dados), BLOCO_SAIDA):
            bloco = dados[i:i + BLOCO_SAIDA]
            self._bytes_resposta += len(bloco)
            await self._enviar_binario(bloco)

    async def _finalizar_audio(self) -> None:
        await self._enviar_texto("audio_end")
        self._estado = Estado.TOCANDO
        self._audios_tocando += 1
        duracao = self._bytes_resposta / BYTES_POR_SEGUNDO_SAIDA
        self._prazo_playback = self._relogio() + duracao + FOLGA_PLAYBACK_S

    async def _apos_tocar(self) -> None:
        self._prazo_playback = None
        if self._envio is None:
            return
        if self._sessao is not None:
            await self._abrir_escuta()
        else:
            await self._abrir_sessao(contexto=self.ultimo_texto)

    def _zerar_reproducao(self) -> None:
        self._resto = b""
        self._bytes_resposta = 0
        self._audios_tocando = 0
        self._prazo_playback = None

    # ------------------------------------------------------------- entrega

    async def _entregar_proximo(self) -> None:
        if self._estado != Estado.OCIOSO or self._envio is None:
            return
        texto = self._caixa.retirar()
        if texto is not None:
            await self._entregar(texto)

    async def _entregar(self, texto: str) -> None:
        """Sintetiza o texto e empurra o áudio à placa (resultado sem conversa)."""
        geracao = self._geracao
        self._estado = Estado.TOCANDO  # ocupado enquanto sintetiza
        self._prazo_playback = None
        try:
            pcm = await self._sintetizador.sintetizar(texto)
        except Exception:
            log.exception("falha no TTS; o resultado não será falado: %s", texto)
            if geracao == self._geracao and self._envio is not None:
                self._estado = Estado.OCIOSO
                await self._entregar_proximo()
            return
        if geracao != self._geracao or self._envio is None:
            self._caixa.devolver(texto)
            return
        pcm = pcm[: len(pcm) - (len(pcm) % 2)]
        self.ultimo_texto = texto
        self._bytes_resposta = 0
        await self._enviar_texto("audio_start", rate=TAXA_SAIDA)
        await self._enviar_blocos(pcm)
        await self._finalizar_audio()

    # ------------------------------------------------------------- envio

    async def _enviar_texto(self, tipo: str, **campos) -> None:
        envio = self._envio
        if envio is None:
            return
        try:
            await envio.texto(codificar(tipo, **campos))
        except Exception as e:
            log.warning("falha ao enviar %s à placa: %s", tipo, e)

    async def _enviar_binario(self, dados: bytes) -> None:
        envio = self._envio
        if envio is None:
            return
        try:
            await envio.binario(dados)
        except Exception as e:
            log.warning("falha ao enviar áudio à placa: %s", e)
