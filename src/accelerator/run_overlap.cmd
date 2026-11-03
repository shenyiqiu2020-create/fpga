@echo off
echo Loading PE40 125MHz kernel temporarily through JTAG. No Flash programming.
call D:\amd\2025.2\Vitis\bin\xsdb.bat "%~dp0scripts\deploy_jtag.tcl"
echo Watch COM11 115200 8N1. After both images finish run READ_PROFILE.cmd.
pause
