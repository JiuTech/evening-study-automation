@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON_EXE="

rem 优先使用本机 Anaconda；下面第一项是当前电脑已检测到的安装位置。
if exist "D:\Softwares\anaconda\python.exe" set "PYTHON_EXE=D:\Softwares\anaconda\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\anaconda3\python.exe" set "PYTHON_EXE=%USERPROFILE%\anaconda3\python.exe"
if not defined PYTHON_EXE if exist "C:\ProgramData\anaconda3\python.exe" set "PYTHON_EXE=C:\ProgramData\anaconda3\python.exe"

rem 若以后移动或卸载 Anaconda，则自动尝试 Codex 自带 Python 和系统 Python。
if not defined PYTHON_EXE if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not defined PYTHON_EXE for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"

if not defined PYTHON_EXE goto :no_python

echo 正在使用：%PYTHON_EXE%
echo 浏览器稍后会自动打开，请不要关闭这个窗口。
"%PYTHON_EXE%" server.py

if errorlevel 1 (
  echo.
  echo 启动失败，请把本窗口中的提示截图发给软件维护同学。
  pause
)
exit /b

:no_python
echo.
echo 没有找到 Python。请先打开 Anaconda Prompt，再运行 server.py。
pause
