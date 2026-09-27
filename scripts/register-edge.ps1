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
$assistantExe = Join-Path $installedRoot 'JevCache.exe'
if (-not (Test-Path -LiteralPath $assistantExe)) { throw 'Build the complete application first.' }
# Use the same implementation as the settings button, including the resolved
# credential file that connects an Edge-launched host to this assistant.
$registrationProcess = Start-Process -FilePath $assistantExe -ArgumentList '--prepare-edge' -WindowStyle Hidden -Wait -PassThru
if ($registrationProcess.ExitCode -ne 0) { throw 'Preparing the native messaging host failed.' }
Write-Output 'Registered the local bridge for this Windows user.'
Write-Output "Load unpacked extension: $(Join-Path $installedRoot 'extensions\edge')"
