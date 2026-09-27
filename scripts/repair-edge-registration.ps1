$ErrorActionPreference = 'Stop'
$bundleRoot = if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'JevCache.exe')) {
    $PSScriptRoot
} else {
    [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\dist\JevCache'))
}
$manifestPath = Join-Path $bundleRoot 'native-messaging.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'Open Jev-Cache settings and prepare Edge first.' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.name -ne 'ai.typesafe.jevcache' -or $manifest.type -ne 'stdio') { throw 'Unexpected native host manifest.' }
if (-not (Test-Path -LiteralPath $manifest.path)) { throw 'The prepared native host executable is missing.' }
foreach ($view in @([Microsoft.Win32.RegistryView]::Registry32, [Microsoft.Win32.RegistryView]::Registry64)) {
    $baseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser, $view)
    try {
        $key = $baseKey.CreateSubKey('Software\Microsoft\Edge\NativeMessagingHosts\ai.typesafe.jevcache')
        try { $key.SetValue('', $manifestPath, [Microsoft.Win32.RegistryValueKind]::String) } finally { $key.Dispose() }
    } finally { $baseKey.Dispose() }
}
$result = @{registration_written=$true; connection_verified=$false; manifest=$manifestPath; pid=$PID}
[System.IO.File]::WriteAllText((Join-Path $bundleRoot 'edge-repair-result.json'), ($result | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))
Write-Output 'Jev-Cache registration repaired for this Windows user.'
Write-Output 'Open the Jev-Cache extension popup and click Reconnect.'
