param([switch]$Unregister)
$ErrorActionPreference = 'Stop'
$hostName = 'ai.typesafe.jevcache'
$regPath = "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\$hostName"
if ($Unregister) {
    if (Test-Path -LiteralPath $regPath) { Remove-Item -LiteralPath $regPath }
    Write-Output 'Removed the Jev-Cache current-user native messaging registration.'
    exit
}
$installedRoot = if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'JevCache.exe')) {
    $PSScriptRoot
} else {
    [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\dist\JevCache'))
}
$hostExe = Join-Path $installedRoot 'browser-host\JevCacheNativeHost\JevCacheNativeHost.exe'
$extensionManifest = Join-Path $installedRoot 'extensions\edge\manifest.json'
if (-not (Test-Path -LiteralPath $hostExe)) { throw 'Build the application and browser host first.' }
$manifest = Get-Content -LiteralPath $extensionManifest -Raw | ConvertFrom-Json
$publicKey = [Convert]::FromBase64String($manifest.key)
$sha = [System.Security.Cryptography.SHA256]::Create()
$digest = $sha.ComputeHash($publicKey)
$extensionId = -join ($digest[0..15] | ForEach-Object { [char](97 + ($_ -shr 4)); [char](97 + ($_ -band 15)) })
$target = Join-Path $installedRoot 'native-messaging.json'
$registration = @{name=$hostName; description='Jev-Cache local Edge bridge'; path=$hostExe; type='stdio'; allowed_origins=@("chrome-extension://$extensionId/")}
[System.IO.File]::WriteAllText($target, ($registration | ConvertTo-Json -Depth 3), [System.Text.UTF8Encoding]::new($false))
New-Item -Path $regPath -Force | Out-Null
Set-Item -LiteralPath $regPath -Value $target
Write-Output "Registered for this Windows user. Extension ID: $extensionId"
Write-Output "Load unpacked extension: $(Join-Path $installedRoot 'extensions\edge')"
