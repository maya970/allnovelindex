@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 tools\catalog_tool.py
) else (
  python tools\catalog_tool.py
)
if errorlevel 1 pause
