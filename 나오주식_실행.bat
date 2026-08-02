@echo off
chcp 65001 > nul
title 나오 주식 - 준비 중
cd /d "%~dp0"

echo.
echo   ================================
echo      나오 주식
echo   ================================
echo.

REM 파이썬 확인
python --version > nul 2>&1
if errorlevel 1 (
  echo   [!] 파이썬이 설치되어 있지 않습니다.
  echo       python.org 에서 설치한 뒤 다시 실행해 주세요.
  echo       설치할 때 "Add Python to PATH" 를 꼭 체크하세요.
  echo.
  pause
  exit /b
)

REM 필요한 것 자동 설치(처음 한 번만 시간이 걸립니다)
python -c "import flask, numpy, requests, webview" > nul 2>&1
if errorlevel 1 (
  echo   처음 실행이라 필요한 프로그램을 설치합니다. 몇 분 걸릴 수 있어요...
  python -m pip install --quiet --upgrade pip
  python -m pip install --quiet flask numpy requests pandas finance-datareader pywebview
  echo   설치 완료.
  echo.
)

REM 콘솔 없이 띄우는 pythonw 경로 찾기
for /f "delims=" %%P in ('python -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set "PYW=%%P"
if not exist "%PYW%" set "PYW=pythonw.exe"

REM 바탕화면 바로가기 만들기(이미 있으면 새로 고침)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\make_shortcut.ps1" > nul 2>&1
echo   바탕화면에 [나오 주식] 아이콘을 만들었습니다.
echo   다음부터는 그 아이콘을 두 번 누르면 바로 열립니다.
echo.
echo   지금 시작합니다...

REM 프로그램 창으로 실행(검은 창 없음) 후 이 창은 닫는다
start "" "%PYW%" "%~dp0나오주식.pyw"
timeout /t 2 > nul
exit
