# Notas do spike: Pipecat + Gemini Live + Gemini TTS

**Data:** 2026-11-17
**Situação:** pesquisa feita **lendo o código instalado** no venv (`servidor/.venv`) e a documentação do context7 (`/pipecat-ai/pipecat` v1.14). O `spike/spike_gemini.py` está pronto, mas **ainda não foi executado**: falta a `GOOGLE_API_KEY`. Os itens marcados com "**a confirmar com a chave**" dependem dessa execução.

## Versões instaladas

| Pacote | Versão |
|---|---|
| `pipecat-ai[google]` | **1.16.0** |
| `google-genai` | **3.4.0** |
| `fastapi` / `uvicorn` | 0.163.2 / 0.54.0 |
| Python (local) | 3.13 (a imagem Docker usa 3.12) |

## 1. Serviço Gemini Live

- Import: `from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService`. O pacote `gemini_live/__init__.py` está vazio, então é preciso importar de `.llm`.
- O modelo padrão do Pipecat é `models/gemini-3.8-live`. O nosso padrão em `config.py` é o mesmo e pode ser trocado por `MODELO_VOZ`.
- Configuração pela API canônica `settings=GeminiLiveLLMService.Settings(...)`. Os argumentos `model=`, `voice_id=` e `params=InputParams` estão *deprecated* desde 0.0.105.
  - `model`, `voice` (padrão `"Charon"`), `system_instruction`, `language` (`Language.PT_BR` vira `"pt-BR"`), `vad` (`GeminiVADParams`), `thinking`, `proactivity` e `enable_affective_dialog`.
- Outros argumentos do construtor: `api_key`, `tools=` (um `ToolsSchema` ou uma lista de `FunctionSchema`) e `inference_on_context_initialization` (padrão `True`).
  - Usamos **`False`**. Com `True` e sem mensagens, o Pipecat injeta o system prompt e o modelo **fala primeiro**, o que não queremos depois da wake word.
- **Conexão:** abre no `setup()` do processador, quando o pipeline começa. O áudio só é enviado depois que `_ready_for_realtime_input` vira `True`, e isso só acontece depois que um `LLMContextFrame` chega. Por isso é preciso mandar um `LLMRunFrame()` no início. A `SessaoPipecat.iniciar` espera esse atributo interno (com timeout de 15 s) antes de devolver, para não perder o começo da fala.
- **Ferramentas passadas no `tools=` do construtor, não no `LLMContext`.** Se o contexto trouxer ferramentas próprias, o serviço **reconecta** (`_handle_context` → `_reconnect`).
- O VAD é do servidor por padrão (`vad=None`), e o serviço **não** emite `UserStarted/StoppedSpeakingFrame`. Por isso a lógica da janela usa o nosso `DetectorFala`.

### Proactive Audio: suportado

- O `google-genai` 3.4.0 tem `google.genai.types.ProactivityConfig(proactive_audio: bool, proactive_video: bool)`. A descrição diz: *"If enabled, the model can reject responding to the last prompt… ignore out of context speech or to stay silent if the user did not make a request"*.
- O Pipecat repassa o valor em `_connect`: `config.proactivity = ProactivityConfig(...)` (`llm.py`, ~linha 1497).
- Docstring do Pipecat 1.16: *"The 3.8 Live models have proactive audio on at all times and reject a setup that sets `proactive_audio` to False."*
- **Conclusão:** com o modelo padrão (`gemini-3.8-live`), o Proactive Audio fica **sempre ligado**. Mandamos `ProactivityConfig(proactive_audio=True)`, que é aceito.
  - Em modelos 2.5, só os de áudio nativo suportam a opção. Se um modelo recusar o setup, use `PROACTIVE_AUDIO=0`.
  - **A confirmar com a chave:** se o modelo de fato fica em silêncio diante de fala alheia (Task 12, passo 4).
- A spec §5.2.1 exige avisar o usuário se não houvesse suporte. **Há suporte**, então nenhum aviso é necessário além da confirmação prática.

## 2. Ferramenta (function calling)

- Schema:
  - `from pipecat.adapters.llm.schemas.function_schema import FunctionSchema`
  - `FunctionSchema(name, description, properties: dict, required: list[str])`
  - `from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema`
  - `ToolsSchema(standard_tools=[...])`
- Registro: `llm.register_function("tarefa_de_codigo", handler, cancel_on_interruption=None, timeout_secs=None)`.
- Handler: `async def handler(params: FunctionCallParams)`, com `from pipecat.services.llm_service import FunctionCallParams`.
  - Campos: `function_name`, `tool_call_id`, `arguments` (Mapping), `llm`, `context` e `result_callback`.
  - O resultado é devolvido com `await params.result_callback(<obj>)`. O objeto vira JSON e é enviado à sessão como `FunctionResponse` (`GeminiLiveLLMService.push_frame` intercepta o `FunctionCallResultFrame`).
- **Exige contexto.** O serviço loga *"Function calls are not supported without a context object"* se não houver `LLMContext`. Por isso o pipeline usa `LLMContextAggregatorPair`.
- Assíncrono ou síncrono:
  - `cancel_on_interruption=False` torna a função **NON_BLOCKING** (assíncrona).
  - Nos modelos 3.8, as funções são NON_BLOCKING por padrão. O Pipecat declara `BLOCKING` explicitamente para as funções síncronas (`_tag_tool_behaviors`).
  - Registramos como **síncrona**, que é o padrão. O handler só enfileira e responde na hora ("Tarefa enviada ao Claude Code…"), e o modelo espera esse retorno antes de confirmar em voz. O resultado real chega depois pelo TTS (spec §5.2), fora da sessão.

## 3. Frames e pipeline

| Uso | Classe (import `pipecat.frames.frames`) |
|---|---|
| Áudio do mic → LLM | `InputAudioRawFrame(audio, sample_rate=16000, num_channels=1)` (SystemFrame) |
| Áudio do modelo | `TTSAudioRawFrame` (subclasse de `OutputAudioRawFrame`), `sample_rate=24000` |
| Início/fim da fala do bot | `TTSStartedFrame` / `TTSStoppedFrame`; `LLMFullResponseStartFrame` / `LLMFullResponseEndFrame` (emitidos no `turn_complete`) |
| Disparar o contexto inicial | `LLMRunFrame()` |

- Pipeline (`from pipecat.pipeline.pipeline import Pipeline`): `[agregadores.user(), llm, SumidouroAudio, agregadores.assistant()]`.
  - `from pipecat.processors.aggregators.llm_context import LLMContext`
  - `from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair`. Ele detecta sozinho o serviço realtime (`realtime_service_mode`).
- `PipelineTask` e `PipelineRunner` estão **deprecated desde 1.3.0**. Use:
  - `from pipecat.pipeline.worker import PipelineWorker, PipelineParams`
  - `from pipecat.workers.runner import WorkerRunner`
  - Padrão: `runner = WorkerRunner(handle_sigint=False)`, depois `await runner.add_workers(worker)`, depois `asyncio.create_task(runner.run())`.
  - Encerramento: `await worker.cancel(reason=...)`.
  - `PipelineWorker(pipeline, params=PipelineParams(audio_in_sample_rate=16000, audio_out_sample_rate=24000), idle_timeout_secs=None, enable_rtvi=False)`.
- A "FonteAudio" do plano não precisou de um processador próprio: o áudio entra com `await worker.queue_frame(InputAudioRawFrame(...))`.
- O `SumidouroAudio` é um `FrameProcessor` (`pipecat.processors.frame_processor`):
  - sempre chama `await super().process_frame(...)` e depois `push_frame`;
  - repassa `OutputAudioRawFrame` a `eventos.ao_audio`, reamostrando para 24 kHz se precisar;
  - chama `eventos.ao_fim_resposta` no `LLMFullResponseEndFrame`.
- O ciclo de vida (iniciar → áudio → resposta → encerrar) foi validado **sem rede** com um LLM falso no teste `test_ciclo_de_vida_do_pipeline_com_llm_falso`.

## 4. Taxa de saída

- `GeminiLiveLLMService._sample_rate = 24000`, conferida contra o mime `audio/pcm;rate=24000`. Saída: PCM 16 bits mono 24 kHz, igual a `TAXA_SAIDA`.
- O OpenAI Realtime também sai em 24 kHz. O sumidouro reamostra qualquer taxa diferente.

## 5. TTS do Gemini (`google-genai`)

- Chamada (igual ao `GeminiTTSService._run_genai_tts` do Pipecat):
  ```python
  client = genai.Client(api_key=...)
  resp = await client.aio.models.generate_content(
      model=MODELO_TTS, contents=[types.Content(role="user", parts=[types.Part(text=texto)])],
      config=types.GenerateContentConfig(
          response_modalities=["AUDIO"],
          speech_config=types.SpeechConfig(language_code="pt-BR",
              voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")))))
  dados = resp.candidates[0].content.parts[0].inline_data.data
  ```
- **Modelo sugerido: `gemini-3.8-flash-lite-tts`**, o padrão do Pipecat 1.16 na Gemini API.
  - O comentário no código diz: *"the Gemini API retires `gemini-3.1-flash-tts-preview` on November 17, 2026 in favour of `gemini-3.8-flash-lite-tts`"*, ou seja, hoje.
  - Alternativas: `gemini-3.8-flash-tts`.
- **Formato do retorno:** os modelos 3.8 devolvem **WAV por padrão em chamadas não-streaming** e PCM L16 24 kHz cru no streaming. O `tts_gemini.pcm_de_resposta` trata os dois casos: remove o cabeçalho WAV e reamostra se a taxa não for 24 kHz.
  - **A confirmar com a chave:** o mime exato.
- Nos modelos 3.8, o texto é tratado como transcrição literal. Estilo vai em `speech_metadata`, que não usamos. Isso combina com o anti-objetivo de falar o resultado *exatamente como veio*.

## 6. OpenAI Realtime (alternativa, só configurada)

- `from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService` e `from pipecat.services.openai.realtime import events`.
- Modelo padrão do Pipecat: `gpt-realtime-2.1`. A voz vai em `events.SessionProperties(audio=events.AudioConfiguration(output=events.AudioOutput(voice=...)))`.
- Não foi validada (spec §7.1).

## Pendências que dependem da chave

1. Rodar `python spike/spike_gemini.py --pergunta pergunta.wav --pedido pedido_codigo.wav` e ouvir `resposta.wav`, `resposta_pedido.wav` e `tts.wav`.
2. Confirmar que o handler de `tarefa_de_codigo` recebe o pedido literal.
3. Confirmar o mime do TTS e a latência de abertura da sessão. O `ESPERA_PRONTO_S` atual é 15 s.
4. Task 7, passos 3 e 4: servidor real com `scripts/teste_real.py`.

## Descoberto ao rodar o spike (2026-11-17)

- **Use `api_version="v1beta"` no `genai.Client`.** Na `v1`, que é o padrão do google-genai 3.4.0, os modelos de TTS e Live não aparecem: o TTS falha com `400 Unknown name "speechConfig"` e o Live com HTTP 404. O Pipecat já usa `v1beta` por padrão no `GeminiLiveLLMService`.
- Resultado: os três itens do spike funcionaram. A pergunta foi respondida em áudio, o handler de `tarefa_de_codigo` recebeu o pedido literal e o TTS devolveu WAV de 24 kHz mono.
