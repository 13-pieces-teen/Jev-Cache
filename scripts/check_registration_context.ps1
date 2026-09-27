param([Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference = 'Stop'
$key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Software\Microsoft\Edge\NativeMessagingHosts\ai.typesafe.jevcache')
$manifest = if ($key) { $key.GetValue('') } else { $null }
if ($key) { $key.Dispose() }
$result = @{
    pid = $PID
    local_app_data = $env:LOCALAPPDATA
    manifest = $manifest
    manifest_exists = $manifest -and (Test-Path -LiteralPath $manifest)
}
[System.IO.File]::WriteAllText($OutputPath, ($result | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))
