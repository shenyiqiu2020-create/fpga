@echo off
setlocal
cd /d "%~dp0"
if not defined EA_PYTHON set "EA_PYTHON=C:\Users\sheny\anaconda3\envs\efficientad\python.exe"
if not exist "%EA_PYTHON%" (
  echo Set EA_PYTHON to a Python environment containing torch, numpy and pillow.
  pause
  exit /b 1
)
if not exist build\work\demo mkdir build\work\demo
rem Keep the OS temporary directory: the browser inherits TEMP/TMP when opened.
"%EA_PYTHON%" src\demo\server.py --port 8765 --open
pause
