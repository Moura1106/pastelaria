@echo off
REM Roda o Caixa da Pastelaria com dados ficticios. Basta dar dois cliques neste arquivo.
REM 1a vez: cria o ambiente, instala as bibliotecas e monta o banco de exemplo (alguns minutos).
REM Depois: so liga o servidor.
setlocal
cd /d "%~dp0"
title Caixa da Pastelaria - demonstracao

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERRO] Python 3.10 ou mais novo nao encontrado.
    echo Instale em https://www.python.org/downloads/ e marque "Add python.exe to PATH".
    goto fim
)

if not exist ".venv\Scripts\python.exe" (
    echo Criando o ambiente virtual .venv ...
    python -m venv .venv || goto erro
)

if not exist ".venv\instalado.ok" (
    echo Instalando as bibliotecas - pode levar alguns minutos ...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto erro
    echo ok> ".venv\instalado.ok"
)

if not exist "pastelaria.db" (
    echo Montando o banco de exemplo com dados ficticios ...
    ".venv\Scripts\flask.exe" db upgrade || goto erro
    ".venv\Scripts\flask.exe" dados-demo || goto erro
)

echo.
echo ============================================================
echo   Abra http://127.0.0.1:5000
echo   Login: demo@exemplo.com   Senha: demo12345
echo   Para desligar, feche esta janela.
echo ============================================================
echo.
if not defined DEMO_SEM_NAVEGADOR start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:5000"
".venv\Scripts\flask.exe" run
goto fim

:erro
echo.
echo [ERRO] Algo deu errado no passo acima.
echo Se a mensagem fala em "Long Path" ou "No such file or directory", mova a pasta do projeto
echo para um caminho curto (ex.: C:\projetos\pastelaria), apague a pasta .venv e rode de novo.

:fim
echo.
pause
