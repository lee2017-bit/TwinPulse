param(
    [string]$IsaacRoot = "C:\isaacsim",
    [int]$Port = 0,
    [string]$Browser = "",
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $repoRoot "apps\twinpulse-web"
$isaacPython = Join-Path $IsaacRoot "python.bat"
$repoPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$appPython = if ($PythonExecutable) {
    $PythonExecutable
} elseif (Test-Path -LiteralPath $repoPython) {
    $repoPython
} else {
    "python"
}

if (-not (Test-Path -LiteralPath $isaacPython)) {
    throw "Isaac Sim Python launcher not found: $isaacPython"
}

Push-Location $repoRoot
try {
    & $appPython -c "import PIL; assert tuple(map(int, PIL.__version__.split('.')[:2])) >= (12, 2)"
    if ($LASTEXITCODE -ne 0) {
        throw "TwinPulse Python image decoder is missing. Create .venv and install config\python-runtime-requirements.lock with --require-hashes."
    }
    if (Get-Command pnpm -ErrorAction SilentlyContinue) {
        pnpm --dir $webRoot build
    } elseif (Get-Command npm -ErrorAction SilentlyContinue) {
        npm exec --yes --package=pnpm@11.19.0 -- pnpm --dir $webRoot build
    } else {
        throw "Node.js and pnpm/npm are required. Run Install-TwinPulse.cmd first."
    }
    if ($LASTEXITCODE -ne 0) { throw "TwinPulse React production build failed" }

    $arguments = @("scripts\twinpulse_launcher.py", "--isaac-root", $IsaacRoot, "--port", "$Port")
    if ($Browser) { $arguments += @("--browser", $Browser) }
    & $appPython @arguments
    if ($LASTEXITCODE -ne 0) { throw "TwinPulse launcher exited with code $LASTEXITCODE" }
}
finally {
    Pop-Location
}
