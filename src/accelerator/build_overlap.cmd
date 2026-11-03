@echo off
setlocal
pushd "%~dp0"
if not defined EA_PYTHON set "EA_PYTHON=C:\Users\sheny\anaconda3\python.exe"
if not exist logs mkdir logs
set "EA_FIXTURE=%CD%\generated\pe40_tests.bin"
set "EA_STAGE=prepare"
call D:\amd\2025.2\Vitis\bin\vitis-run.bat --mode hls --tcl scripts/build_hls.tcl >logs\hls_prepare.log 2>&1
if errorlevel 1 goto failed
set "EA_STAGE=cosim"
call D:\amd\2025.2\Vitis\bin\vitis-run.bat --mode hls --tcl scripts/build_hls.tcl >logs\hls_cosim.log 2>&1
if errorlevel 1 goto failed
"%EA_PYTHON%" scripts\check_rtl.py --record-cosim
if errorlevel 1 goto failed
call D:\amd\2025.2\Vivado\bin\vivado.bat -mode batch -source scripts/build_vivado.tcl -log logs/vivado.log -journal logs/vivado.jou >logs\vivado_console.log 2>&1
if errorlevel 1 goto failed
"%EA_PYTHON%" scripts\finalize_hardware.py
if errorlevel 1 goto failed
"%EA_PYTHON%" scripts\build_app.py >logs\build_app.log 2>&1
if errorlevel 1 goto failed
echo BUILD PASSED. Overlapped PE40 ready. No board programming started.
popd
exit /b 0
:failed
echo BUILD FAILED. Inspect logs. No board programming started.
popd
exit /b 1
