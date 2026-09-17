@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo VoiceFont has not been provisioned. See docs\local-setup.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\launch_voicefont.py" %*
if errorlevel 1 (
  echo VoiceFont could not start. Read the error above and docs\local-setup.md.
  pause
  exit /b 1
)
