@echo off
rem ============================================================
rem  Assistente de voz "Hi ESP" - inicia tudo localmente
rem  Abre duas janelas: o SERVIDOR e o PLAYER do notebook.
rem  Para parar: feche as janelas (ou Ctrl+C em cada uma).
rem
rem  Uso: de dois cliques neste arquivo, ou rode "iniciar.bat"
rem       "iniciar.bat teste" so confere a configuracao.
rem ============================================================

rem ---- Ajustes ----------------------------------------------
rem Porta USB da placa
set "PORTA=COM4"
rem 1 = Claude Code de DEMONSTRACAO (nao mexe em nenhum projeto)
rem 0 = Claude Code de verdade instalado neste notebook
set "CLAUDE_DEMO=1"
rem -----------------------------------------------------------

chcp 65001 >nul
setlocal
set "RAIZ=%~dp0"
set "SERVIDOR=%RAIZ%servidor"
set "NOTEBOOK=%RAIZ%notebook"
set "PYTHONIOENCODING=utf-8"

if not exist "%SERVIDOR%\.env" (
  echo [ERRO] Nao encontrei "%SERVIDOR%\.env".
  echo        Copie servidor\.env.example para servidor\.env e preencha.
  pause
  exit /b 1
)
if not exist "%SERVIDOR%\.venv\Scripts\python.exe" (
  echo [ERRO] Ambiente Python do servidor nao encontrado. Veja servidor\README.md.
  pause
  exit /b 1
)
if not exist "%NOTEBOOK%\.venv\Scripts\python.exe" (
  echo [ERRO] Ambiente Python do player nao encontrado. Veja notebook\README.md.
  pause
  exit /b 1
)

rem Carrega servidor\.env (ignora linhas vazias e comentarios com #)
for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%SERVIDOR%\.env") do (
  if not "%%b"=="" set "%%a=%%b"
)

if "%CLAUDE_DEMO%"=="1" (
  set "CLAUDE_CMD=%SERVIDOR%\.venv\Scripts\python.exe %SERVIDOR%\tests\fake_claude.py"
  set "WORKSPACE_DIR=%TEMP%\voz-workspace"
)
if not "%WORKSPACE_DIR%"=="" if not exist "%WORKSPACE_DIR%" mkdir "%WORKSPACE_DIR%" 2>nul

rem Memoria local (CONTEXTO.md + historico.jsonl): pasta "memoria" na raiz, fora do git
set "MEMORIA_DIR=%RAIZ%memoria"
if not exist "%MEMORIA_DIR%" mkdir "%MEMORIA_DIR%" 2>nul
if not exist "%MEMORIA_DIR%\CONTEXTO.md" copy "%SERVIDOR%\CONTEXTO.example.md" "%MEMORIA_DIR%\CONTEXTO.md" >nul

if /i "%~1"=="teste" (
  echo Configuracao:
  if defined TOKEN_PLACA    (echo   TOKEN_PLACA     ok) else (echo   TOKEN_PLACA     FALTANDO)
  if defined GOOGLE_API_KEY (echo   GOOGLE_API_KEY  ok) else (echo   GOOGLE_API_KEY  FALTANDO)
  echo   MODELO_VOZ      %MODELO_VOZ%
  echo   CLAUDE_DEMO     %CLAUDE_DEMO%
  echo   WORKSPACE_DIR   %WORKSPACE_DIR%
  echo   MEMORIA_DIR     %MEMORIA_DIR%
  echo   PORTA           %PORTA%
  exit /b 0
)

echo Iniciando o servidor (porta 8000) e o player (%PORTA%)...
start "Servidor de voz" /D "%SERVIDOR%" cmd /k ".venv\Scripts\python.exe -m uvicorn voz.app:app --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul
start "Player (%PORTA%)" /D "%NOTEBOOK%" cmd /k ".venv\Scripts\python.exe player.py --porta %PORTA%"
echo Pronto. Diga "Hi ESP" perto da placa.
endlocal
