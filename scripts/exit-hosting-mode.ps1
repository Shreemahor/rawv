param(
    [string]$AppContainerName = "rawv",
    [string]$TunnelContainerName = "rawv-tunnel",
    [switch]$StopDockerDesktop
)

$ErrorActionPreference = "Stop"

$stateDir = Join-Path $PSScriptRoot ".host-state"
$normalFile = Join-Path $stateDir "normal-plan-guid.txt"

if (Get-Command docker -ErrorAction SilentlyContinue) {
    $containers = docker ps --format "{{.Names}}"
    if ($containers -contains $TunnelContainerName) {
        docker stop $TunnelContainerName | Out-Null
        Write-Host "Stopped tunnel container '$TunnelContainerName'."
    }
    if ($containers -contains $AppContainerName) {
        docker stop $AppContainerName | Out-Null
        Write-Host "Stopped app container '$AppContainerName'."
    }
}

if (Test-Path $normalFile) {
    $normalGuid = (Get-Content $normalFile -Raw).Trim()
    if ($normalGuid) {
        powercfg /SETACTIVE $normalGuid
        Write-Host "Restored normal power profile."
    }
}
else {
    Write-Host "Normal power profile not found; leaving current profile unchanged." -ForegroundColor Yellow
}

if ($StopDockerDesktop) {
    Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue | Stop-Process -Force
    Get-Process -Name "com.docker.backend" -ErrorAction SilentlyContinue | Stop-Process -Force
    Write-Host "Docker Desktop processes stopped."
}

Write-Host ""
Write-Host "Normal mode enabled." -ForegroundColor Green
