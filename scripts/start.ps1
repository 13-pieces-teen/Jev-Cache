$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run uv sync first.' }
Start-Process -FilePath $python -ArgumentList @('-m','jev_cache') -WorkingDirectory $projectRoot -WindowStyle Hidden
