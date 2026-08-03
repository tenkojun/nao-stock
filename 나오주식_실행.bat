@echo off
REM ============================================================
REM  NAO STOCK - setup and launch
REM
REM  ASCII ONLY. Do not put Korean text in this file.
REM  If this .bat contains non-ASCII bytes, "chcp 65001" makes
REM  cmd lose its read position in the file and commands get
REM  split into garbage. Korean messages live in tools/setup.py.
REM ============================================================
chcp 65001 > nul
title NAO STOCK
cd /d "%~dp0"

python --version > nul 2>&1
if errorlevel 1 (
  echo.
  echo   [!] Python is not installed.
  echo       Get it from python.org, and make sure to check
  echo       "Add Python to PATH" during installation.
  echo.
  pause
  exit /b 1
)

REM setup.py launches the app detached, so this window can close right away.
REM Do NOT use "timeout" here - it fails with "Input redirection is not
REM supported" whenever stdin is not a console, which turns a successful
REM install into a false failure.
python "%~dp0tools\setup.py"
if errorlevel 1 pause
exit
