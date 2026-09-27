$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $projectRoot
$distPath = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'dist'))
if (-not $distPath.StartsWith($projectRoot + [System.IO.Path]::DirectorySeparatorChar)) { throw 'Invalid build target' }
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$pythonBase = & $python -c "import sys; print(sys.base_prefix)"
if ($LASTEXITCODE -ne 0) { throw 'Python environment unavailable' }
# Isolate dependency discovery from unrelated Conda / Poppler DLLs on the host PATH.
$originalSearchPath = $env:PATH
$env:PATH = @((Split-Path -Parent $python), $pythonBase, (Join-Path $env:SystemRoot 'System32'), $env:SystemRoot) -join ';'
try {
& $python -m PyInstaller --clean --noconfirm --onedir --windowed --name JevCache --icon (Join-Path $projectRoot 'assets\jev-cache.ico') --paths src --specpath build --distpath dist --workpath build/desktop scripts/desktop_entry.py
if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed' }
& $python -m PyInstaller --clean --noconfirm --onedir --console --name JevCacheNativeHost --paths src --specpath build --distpath dist/JevCache/browser-host --workpath build/host scripts/native_entry.py
if ($LASTEXITCODE -ne 0) { throw 'Browser host build failed' }
foreach ($file in @('README.md','EDGE-SETUP.md','VALIDATION.md')) { Copy-Item -LiteralPath $file -Destination (Join-Path $distPath 'JevCache') -Force }
Copy-Item -LiteralPath 'docs' -Destination (Join-Path $distPath 'JevCache') -Recurse -Force
$evidenceTarget = Join-Path $distPath 'JevCache\artifacts'
New-Item -ItemType Directory -Path $evidenceTarget -Force | Out-Null
foreach ($file in @('packaged-main.png','smoke-state.json','controlled-close.json','native-host-check.json','profile-source.json','real-jev-connection.json','real-jev-shadow.json')) {
    $source = Join-Path 'artifacts' $file
    if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $evidenceTarget -Force }
}
$extensionTarget = Join-Path $distPath 'JevCache\extensions\edge'
New-Item -ItemType Directory -Path $extensionTarget -Force | Out-Null
foreach ($file in @('manifest.json','popup.html','popup.js')) {
    Copy-Item -LiteralPath (Join-Path 'extensions\edge' $file) -Destination $extensionTarget -Force
}
Copy-Item -LiteralPath 'extensions\edge\dist' -Destination $extensionTarget -Recurse -Force
Copy-Item -LiteralPath 'scripts\register-edge.ps1' -Destination (Join-Path $distPath 'JevCache') -Force
Copy-Item -LiteralPath 'scripts\repair-edge-registration.ps1' -Destination (Join-Path $distPath 'JevCache') -Force
Copy-Item -LiteralPath 'scripts\repair-edge.cmd' -Destination (Join-Path $distPath 'JevCache') -Force
Write-Output (Join-Path $distPath 'JevCache\JevCache.exe')
} finally {
    $env:PATH = $originalSearchPath
}
