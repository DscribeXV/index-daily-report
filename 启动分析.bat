@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 全球主要指数分析 - 启动
echo ============================================
echo   全球主要指数分析
echo   正在采集数据并生成 PDF ...
echo ============================================
echo.
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo  [提示] 没找到 .venv，改用系统 python。建议先按 README 创建虚拟环境。
    set "PY=python"
)
"%PY%" "run_report.py"
set EXITCODE=%ERRORLEVEL%
echo.
if %EXITCODE% NEQ 0 (
    echo [错误] 脚本退出码 %EXITCODE%
) else (
    echo [完成] PDF 已生成在 output 目录下
)
echo.
pause
