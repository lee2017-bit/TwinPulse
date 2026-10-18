# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
param(
    [string]$TransferRoot = "",
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
if (-not $TransferRoot) { $TransferRoot = Split-Path -Parent $PSScriptRoot }
$TransferRoot = (Resolve-Path -LiteralPath $TransferRoot).Path
if (-not $OutputRoot) { $OutputRoot = Join-Path $TransferRoot "unpacked" }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$transferPath = Join-Path $TransferRoot "transfer-manifest.json"
if (-not (Test-Path -LiteralPath $transferPath)) { throw "transfer-manifest.json is missing" }
$transfer = Get-Content -LiteralPath $transferPath -Raw | ConvertFrom-Json
if ($transfer.schema -ne "twinpulse-transfer-1.0" -or
    [string]$transfer.release_id -notmatch '^[a-zA-Z0-9._-]{1,80}$' -or
    [string]$transfer.archive_sha256 -notmatch '^[a-f0-9]{64}$') { throw "Invalid transfer manifest" }
$parts = @($transfer.parts)
if ($parts.Count -lt 1 -or $parts.Count -gt 100) { throw "Invalid transfer part count" }
$total = [long]0
for ($i = 0; $i -lt $parts.Count; $i++) {
    $part = $parts[$i]
    $expectedName = "{0}.part{1:D4}" -f $transfer.release_id, ($i + 1)
    if ($part.name -cne $expectedName -or [long]$part.bytes -lt 1 -or
        [long]$part.bytes -gt 900000000 -or [string]$part.sha256 -notmatch '^[a-f0-9]{64}$') {
        throw "Invalid transfer part metadata: $expectedName"
    }
    $path = Join-Path $TransferRoot $expectedName
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing transfer part: $expectedName" }
    if ((Get-Item -LiteralPath $path).Length -ne [long]$part.bytes -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne [string]$part.sha256) {
        throw "Corrupt transfer part: $expectedName"
    }
    $total += [long]$part.bytes
}
if ($total -ne [long]$transfer.archive_bytes -or $total -gt 10000000000) { throw "Transfer total size is invalid" }
if (-not (Test-Path -LiteralPath $OutputRoot)) { New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null }
$target = Join-Path $OutputRoot ([string]$transfer.release_id)
if (Test-Path -LiteralPath $target) { throw "Target release already exists: $target" }
$tempArchive = Join-Path $OutputRoot ("." + [Guid]::NewGuid().ToString("N") + ".zip")
$tempRoot = Join-Path $OutputRoot ("." + [Guid]::NewGuid().ToString("N"))
$outputPrefix = $OutputRoot.TrimEnd('\') + '\'
if (-not ([IO.Path]::GetFullPath($target)).StartsWith($outputPrefix, [StringComparison]::OrdinalIgnoreCase) -or
    -not ([IO.Path]::GetFullPath($tempRoot)).StartsWith($outputPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Reassembly target escaped the selected output directory"
}
try {
    $output = [IO.File]::Create($tempArchive)
    try {
        foreach ($part in $parts) {
            $inputStream = [IO.File]::OpenRead((Join-Path $TransferRoot ([string]$part.name)))
            try { $inputStream.CopyTo($output) } finally { $inputStream.Dispose() }
        }
    } finally { $output.Dispose() }
    if ((Get-FileHash -LiteralPath $tempArchive -Algorithm SHA256).Hash.ToLowerInvariant() -cne
        [string]$transfer.archive_sha256) { throw "Reassembled archive hash mismatch" }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($tempArchive)
    try {
        $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        $expandedBytes = [long]0
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName.Replace('\', '/')
            $expandedBytes += [long]$entry.Length
            $unixType = ($entry.ExternalAttributes -shr 16) -band 0xF000
            if ($name -notmatch '^[A-Za-z0-9._/-]+$' -or $name.StartsWith('/') -or
                $name -match '(^|/)\.\.?(/|$)' -or $name.Contains('//') -or
                -not $seen.Add($name) -or $entry.Length -gt 1000000000 -or
                $expandedBytes -gt 2000000000 -or $seen.Count -gt 1000 -or $unixType -eq 0xA000) {
                throw "Unsafe archive entry: $name"
            }
        }
    } finally { $zip.Dispose() }
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    [IO.Compression.ZipFile]::ExtractToDirectory($tempArchive, $tempRoot)
    Move-Item -LiteralPath $tempRoot -Destination $target
    Write-Host "TWINPULSE_REASSEMBLE=PASS path=$target"
    Write-Host "Run: $(Join-Path $target 'Install-Offline.cmd')"
} finally {
    if (Test-Path -LiteralPath $tempArchive) { Remove-Item -LiteralPath $tempArchive -Force }
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
}
