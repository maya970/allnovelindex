@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
echo 正在打开采集窗口（置顶、带实时日志）…
where pyw >nul 2>nul
if %errorlevel%==0 (
  start "马克书库采集" pyw -3 tools\crawl_panel.py
  goto :eof
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "马克书库采集" pythonw tools\crawl_panel.py
  goto :eof
)
where py >nul 2>nul
if %errorlevel%==0 (
  start "马克书库采集" py -3 tools\crawl_panel.py
  goto :eof
)
start "马克书库采集" python tools\crawl_panel.py
