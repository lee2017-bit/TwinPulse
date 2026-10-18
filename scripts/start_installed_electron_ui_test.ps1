# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
# Test the same user-facing optional testing entry, never an inherited env flag.
$ErrorActionPreference = 'Stop'
$tpInstalled = Join-Path $env:LOCALAPPDATA 'TwinPulse\installed'
$tpState = Join-Path $env:LOCALAPPDATA 'TwinPulse\runtime'
if (Test-Path -LiteralPath (Join-Path $tpState 'launcher.lock')) {
    throw 'Exit the current TwinPulse normally before starting this new test session.'
}
$tpEntry = Join-Path (Split-Path $PSScriptRoot -Parent) 'Start-TwinPulse-Test.cmd'
if (-not (Test-Path -LiteralPath $tpEntry)) { throw 'Install the current test-enabled package first.' }
$tpActive = Get-Content -LiteralPath (Join-Path $tpInstalled 'active-release.json') -Raw | ConvertFrom-Json
$tpExpected = Join-Path (Split-Path (Join-Path $tpInstalled $tpActive.exe)) 'desktop\TwinPulseDesktop.exe'
Start-Process -FilePath $tpEntry -WindowStyle Hidden | Out-Null
$tpUntil = [DateTime]::UtcNow.AddSeconds(120)
do {
    $tpOwnerPath = Join-Path $tpState 'launcher.lock'
    if (Test-Path -LiteralPath $tpOwnerPath) {
        $tpOwner = Get-Content -LiteralPath $tpOwnerPath -Raw | ConvertFrom-Json
        $tpModePath = Join-Path $tpState ('launches\'+$tpOwner.launch_id+'\desktop-automation.json')
        if (Test-Path -LiteralPath $tpModePath) {
            $tpMode = Get-Content -LiteralPath $tpModePath -Raw | ConvertFrom-Json
            if ($tpMode.enabled -ne $true) { throw 'The opened launch is not testing mode.' }
            $tpListeners = @(Get-NetTCPConnection -State Listen -LocalPort $tpMode.port -ErrorAction SilentlyContinue)
            if ($tpListeners.Count) {
                if ($tpListeners.Count -ne 1 -or $tpListeners[0].LocalAddress -ne '127.0.0.1') { throw 'Unexpected debugger listener.' }
                $tpProcess = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $tpListeners[0].OwningProcess)
                if ($tpProcess.ExecutablePath -ne $tpExpected -or $tpProcess.ParentProcessId -ne $tpOwner.owner_pid) {
                    throw 'Debugger is not this installed launcher child.'
                }
                [pscustomobject]@{cdp_endpoint=("http://127.0.0.1:"+$tpMode.port);launch_id=$tpOwner.launch_id;
                    owner_pid=$tpOwner.owner_pid;desktop_pid=$tpProcess.ProcessId;executable=$tpProcess.ExecutablePath;
                    entry=$tpEntry;native_double_click='NOT_RUN'} | ConvertTo-Json
                exit 0
            }
        }
    }
    Start-Sleep -Seconds 1
} while ([DateTime]::UtcNow -lt $tpUntil)
throw 'The installed test window did not start. Inspect its launch; no process was terminated.'
