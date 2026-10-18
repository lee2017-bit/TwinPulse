# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
param(
    [Parameter(Mandatory=$true)][string]$ReleaseRoot,
    [Parameter(Mandatory=$true)][string]$OutputRoot,
    [long]$PartBytes = 900000000
)

$ErrorActionPreference = "Stop"
if ($PartBytes -lt 1024 -or $PartBytes -gt 900000000) { throw "PartBytes must be 1024..900000000" }
$ReleaseRoot = (Resolve-Path -LiteralPath $ReleaseRoot).Path
$releaseId = Split-Path -Leaf $ReleaseRoot
if ($releaseId -notmatch '^[a-zA-Z0-9._-]{1,80}$' -or
    -not (Test-Path -LiteralPath (Join-Path $ReleaseRoot "release-manifest.json"))) { throw "Prepared release folder required" }
if (Test-Path -LiteralPath $OutputRoot) { throw "Output folder already exists; will not overwrite: $OutputRoot" }
Add-Type -AssemblyName System.IO.Compression.FileSystem
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$archive = Join-Path $OutputRoot "$releaseId.zip"
[IO.Compression.ZipFile]::CreateFromDirectory($ReleaseRoot, $archive, [IO.Compression.CompressionLevel]::Optimal, $false)
$archiveItem = Get-Item -LiteralPath $archive
$archiveLength = [long]$archiveItem.Length
$archiveHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
$parts = @()
$inputStream = [IO.File]::OpenRead($archive)
try {
    $buffer = New-Object byte[] 1048576
    $index = 0
    while ($inputStream.Position -lt $inputStream.Length) {
        $index++
        $name = "{0}.part{1:D4}" -f $releaseId, $index
        $partPath = Join-Path $OutputRoot $name
        $outputStream = [IO.File]::Create($partPath)
        try {
            $written = [long]0
            while ($written -lt $PartBytes -and $inputStream.Position -lt $inputStream.Length) {
                $count = [int][Math]::Min($buffer.Length, $PartBytes - $written)
                $read = $inputStream.Read($buffer, 0, $count)
                if ($read -le 0) { break }
                $outputStream.Write($buffer, 0, $read)
                $written += $read
            }
        } finally { $outputStream.Dispose() }
        $parts += [ordered]@{
            name = $name; bytes = $written
            sha256 = (Get-FileHash -LiteralPath $partPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
} finally { $inputStream.Dispose() }
Remove-Item -LiteralPath $archive
$transfer = [ordered]@{
    schema = "twinpulse-transfer-1.0"; release_id = $releaseId
    archive_bytes = $archiveLength; archive_sha256 = $archiveHash; parts = $parts
}
$transfer | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputRoot "transfer-manifest.json") -Encoding UTF8
Copy-Item -LiteralPath (Join-Path (Split-Path -Parent $PSScriptRoot) "Reassemble-TwinPulse.cmd") -Destination $OutputRoot
New-Item -ItemType Directory -Path (Join-Path $OutputRoot "scripts") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "reassemble_offline_release.ps1") -Destination (Join-Path $OutputRoot "scripts")
Write-Host "TWINPULSE_TRANSFER=PASS parts=$($parts.Count) archive_bytes=$archiveLength max_part_bytes=$PartBytes"
