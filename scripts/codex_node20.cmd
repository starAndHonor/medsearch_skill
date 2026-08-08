@echo off
setlocal
set "NODE20=%LOCALAPPDATA%\nvm\v20.19.5"
set "CODEX_NPM=%APPDATA%\npm-codex"
set "PATH=%NODE20%;%CODEX_NPM%;%PATH%"
"%CODEX_NPM%\codex.cmd" %*
