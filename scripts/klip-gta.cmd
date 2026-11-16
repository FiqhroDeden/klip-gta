@echo off
rem klip-gta: jalankan dengan environment Python skill ini sendiri (uv). Command Prompt / PowerShell di Windows.
set "HERE=%~dp0.."
where uv >nul 2>nul || (echo uv belum terpasang. Jalankan: winget install astral-sh.uv & exit /b 1)
set PYTHONUTF8=1
uv run --quiet --project "%HERE%" python "%HERE%\scripts\klip.py" %*
