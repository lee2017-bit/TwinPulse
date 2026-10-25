# SPDX-License-Identifier: Apache-2.0
# Preserve, rather than delete, the dead test launch's exact generated lock.
$ErrorActionPreference='Stop'
$tpRepo=Split-Path $PSScriptRoot -Parent
$tpLockPath=Join-Path $env:LOCALAPPDATA 'TwinPulse\runtime\launcher.lock'
$tpTarget=Join-Path $tpRepo 'outputs\environment-task-loop-20261025-01\aborted13\launcher.lock.pre-abort.json'
$tpLock=Get-Content -LiteralPath $tpLockPath -Raw | ConvertFrom-Json
if($tpLock.launch_id -ne '7153b94b62e54420b5689c2ea1b9f72e' -or $tpLock.owner_pid -ne 12864){throw 'LOCK_IDENTITY_CHANGED'}
if(Get-Process -Id 12864,31272,21256 -ErrorAction SilentlyContinue){throw 'OLD_OWNED_PID_STILL_EXISTS'}
if(Test-Path -LiteralPath $tpTarget){throw 'PRESERVATION_TARGET_EXISTS'}
Move-Item -LiteralPath $tpLockPath -Destination $tpTarget -ErrorAction Stop
[pscustomobject]@{status='EXACT_DEAD_TEST_OWNER_LOCK_PRESERVED';path=$tpTarget;sha256=(Get-FileHash -LiteralPath $tpTarget -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json
