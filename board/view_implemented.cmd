@echo off
cd /d "%~dp0.."
call D:\amd\2025.2\Vivado\bin\vivado.bat -mode gui -source board/view_implemented.tcl
