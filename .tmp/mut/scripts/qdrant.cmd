@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0qdrant.ps1" %*
