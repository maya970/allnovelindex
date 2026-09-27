@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo stop> .crawl_stop
echo 已发出停止指令。补全程序会在当前这本结束后保存进度退出。
pause
