@echo off
setlocal
cd /d "%~dp0.."
if not defined EA_PYTHON set "EA_PYTHON=C:\Users\sheny\anaconda3\python.exe"
"%EA_PYTHON%" build\restore_prebuilt.py
if errorlevel 1 exit /b 1
call src\accelerator\build_overlap.cmd
exit /b %errorlevel%
