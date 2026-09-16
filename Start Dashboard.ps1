$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$logs = Join-Path $root ".logs"
New-Item -ItemType Directory -Path $logs -Force | Out-Null

function Test-LocalPort([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

if (-not (Test-LocalPort 8000)) {
    $python = Join-Path $root "backend\.venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        throw "Backend virtual environment is missing: $python"
    }
    Start-Process -FilePath $python `
        -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--reload" `
        -WorkingDirectory (Join-Path $root "backend") `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs "backend.out.log") `
        -RedirectStandardError (Join-Path $logs "backend.err.log")
}

if (-not (Test-LocalPort 5173)) {
    $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
    Start-Process -FilePath $npm `
        -ArgumentList "run", "dev" `
        -WorkingDirectory (Join-Path $root "frontend") `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs "frontend.out.log") `
        -RedirectStandardError (Join-Path $logs "frontend.err.log")
}

$ready = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if ((Test-LocalPort 5173) -and (Test-LocalPort 8000)) {
        $ready = $true
        break
    }
    Start-Sleep -Milliseconds 500
}

if (-not $ready) {
    throw "Dashboard services did not start. Check the .logs folder for details."
}

$url = "http://127.0.0.1:5173/"
$chromeCandidates = @(
    (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
    (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
)
$chrome = $chromeCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if ($chrome) {
    Start-Process -FilePath $chrome -ArgumentList $url
} else {
    Start-Process $url
}
