[CmdletBinding()]
param(
    [switch]$Yes,
    [switch]$DryRun,
    [ValidateRange(1, 65535)]
    [int]$Port = 5432
)

$ErrorActionPreference = "Stop"

$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Write-SetupLog($Message) {
    Write-Host "[setup] $Message"
}

function Test-Command($Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-LocalPort($HostName, $Port) {
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(1000)) {
            $client.Close()
            return $false
        }
        $client.EndConnect($async)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

function Add-MissingRequirement($Name, $Help) {
    $script:missing += $Name
    $script:guidance += $Help
    Write-SetupLog "확인 실패: $Name"
}

Write-SetupLog "프로젝트 루트로 이동했습니다: $Root"
Write-SetupLog "Windows 로컬 개발에 필요한 항목을 확인합니다."
Write-SetupLog "PostgreSQL 포트: $Port"

$missing = @()
$guidance = @()
if (Test-Command "uv") {
    Write-SetupLog "확인 완료: uv"
} else {
    Add-MissingRequirement "uv" "uv를 설치하고 새 PowerShell에서 'uv --version'이 동작하는지 확인하세요."
}

if (Test-Command "node") {
    Write-SetupLog "확인 완료: node"
} else {
    Add-MissingRequirement "node" "Node.js LTS를 설치하고 새 PowerShell에서 'node --version'이 동작하는지 확인하세요."
}

if (Test-Command "npm") {
    Write-SetupLog "확인 완료: npm"
} else {
    Add-MissingRequirement "npm" "Node.js 설치 후 새 PowerShell에서 'npm --version'이 동작하는지 확인하세요."
}

if (Test-LocalPort "localhost" $Port) {
    Write-SetupLog "확인 완료: PostgreSQL이 localhost:${Port}에서 응답합니다."
} else {
    Add-MissingRequirement "local PostgreSQL on localhost:$Port" "PostgreSQL/PostGIS를 localhost:${Port}에서 실행하고 postgres/postgres 계정으로 접속할 수 있게 준비하세요."
}

if ($missing.Count -gt 0 -and -not $DryRun) {
    Write-Host ""
    Write-SetupLog "필수 항목이 준비되지 않아 설정을 중단합니다."
    Write-Host "빠진 항목: $($missing -join ', ')"
    Write-Host ""
    Write-Host "해야 할 일:"
    foreach ($item in $guidance) {
        Write-Host "  - $item"
    }
    Write-Host ""
    Write-Host "준비가 끝나면 다시 실행하세요: pwsh ./setup.ps1"
    exit 2
}

if ($missing.Count -gt 0 -and $DryRun) {
    Write-SetupLog "DryRun 모드라 필수 항목 누락이 있어도 미리보기만 계속합니다."
}

$ApiPath = Join-Path $Root "apps/api"
Write-SetupLog "Python 모듈 경로를 설정합니다: $ApiPath"
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$ApiPath;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $ApiPath
}
$argsList = @("-m", "app.setup_cli", "--mode", "local-pg", "--pg-port", "$Port")
if ($Yes -or -not [Environment]::UserInteractive) {
    $argsList += "--yes"
}
if ($DryRun) {
    $argsList += "--dry-run"
}

$launcher = "uv"
$launcherArgs = @("run", "python")
if (-not (Test-Command "uv")) {
    if ($DryRun -and (Test-Command "python")) {
        $launcher = "python"
        $launcherArgs = @()
        Write-SetupLog "uv가 없어 DryRun은 시스템 python으로 설정 도우미만 실행합니다."
    } else {
        Write-Host ""
        Write-SetupLog "Python 설정 도우미를 실행할 수 없습니다."
        Write-Host "해야 할 일:"
        Write-Host "  - uv를 설치하고 새 PowerShell에서 'uv --version'이 동작하는지 확인하세요."
        Write-Host "  - 준비가 끝나면 다시 실행하세요: pwsh ./setup.ps1"
        exit 2
    }
}

$displayCommand = "$launcher $($launcherArgs + $argsList -join ' ')"
Write-SetupLog "Python 설정 도우미를 실행합니다: $displayCommand"
& $launcher @launcherArgs @argsList
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-SetupLog "Python 설정 도우미가 실패했습니다."
    Write-Host "해야 할 일:"
    Write-Host "  - 위 오류 메시지에서 빠진 항목을 먼저 해결하세요."
    Write-Host "  - PostgreSQL을 쓰는 경우 localhost:${Port}가 열려 있고 geodata DB가 준비되어 있는지 확인하세요."
    Write-Host "  - 준비가 끝나면 다시 실행하세요: pwsh ./setup.ps1"
    exit $LASTEXITCODE
}

Write-SetupLog "setup.ps1 작업이 끝났습니다."
