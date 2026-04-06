param(
    [string]$ProjectPath = "$PSScriptRoot\..",
    [string]$ImageName = "rawv:latest",
    [string]$AppContainerName = "rawv",
    [string]$TunnelContainerName = "rawv-tunnel",
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

function Get-ActiveSchemeGuid {
    $output = powercfg /GETACTIVESCHEME
    if ($output -match "([A-Fa-f0-9\-]{36})") {
        return $matches[1]
    }
    throw "Could not determine active power scheme GUID."
}

function Ensure-HostingPlan {
    param([string]$NormalGuid, [string]$StateDir)

    $hostPlanFile = Join-Path $StateDir "host-plan-guid.txt"
    if (Test-Path $hostPlanFile) {
        return (Get-Content $hostPlanFile -Raw).Trim()
    }

    $dup = powercfg /DUPLICATESCHEME $NormalGuid
    if ($dup -notmatch "([A-Fa-f0-9\-]{36})") {
        throw "Could not create hosting power plan."
    }
    $hostGuid = $matches[1]
    powercfg /CHANGENAME $hostGuid "RAWV Hosting"

    # Plugged-in hosting profile.
    powercfg /SETACVALUEINDEX $hostGuid SUB_SLEEP STANDBYIDLE 0
    powercfg /SETACVALUEINDEX $hostGuid SUB_SLEEP HIBERNATEIDLE 0
    powercfg /SETACVALUEINDEX $hostGuid SUB_VIDEO VIDEOIDLE 1
    powercfg /SETACVALUEINDEX $hostGuid SUB_BUTTONS LIDACTION 0

    Set-Content -Path $hostPlanFile -Value $hostGuid -NoNewline
    return $hostGuid
}

function Ensure-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI not found. Install Docker Desktop first."
    }

    try {
        docker info | Out-Null
        return
    }
    catch {
        $dockerDesktopPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        if (-not (Test-Path $dockerDesktopPath)) {
            throw "Docker Desktop not found at '$dockerDesktopPath'."
        }
        Start-Process -FilePath $dockerDesktopPath | Out-Null
        Write-Host "Starting Docker Desktop..."

        $tries = 0
        while ($tries -lt 40) {
            Start-Sleep -Seconds 3
            try {
                docker info | Out-Null
                Write-Host "Docker is ready."
                return
            }
            catch {
                $tries++
            }
        }
        throw "Docker engine did not become ready in time."
    }
}

function Ensure-AppContainer {
    param([string]$ProjectPath, [string]$ImageName, [string]$AppContainerName, [string]$EnvFile)

    $resolvedProject = (Resolve-Path $ProjectPath).Path
    $envPath = Join-Path $resolvedProject $EnvFile
    if (-not (Test-Path $envPath)) {
        throw "Missing env file at '$envPath'."
    }

    $exists = docker ps -a --format "{{.Names}}" | Select-String -SimpleMatch $AppContainerName
    if ($exists) {
        docker start $AppContainerName | Out-Null
        return
    }

    Write-Host "Building image $ImageName..."
    docker build -t $ImageName $resolvedProject | Out-Host

    Write-Host "Starting app container $AppContainerName..."
    docker run -d --name $AppContainerName --restart unless-stopped --env-file $envPath -p 7860:7860 $ImageName | Out-Host
}

function Ensure-TunnelContainer {
    param([string]$TunnelContainerName)

    $exists = docker ps -a --format "{{.Names}}" | Select-String -SimpleMatch $TunnelContainerName
    if ($exists) {
        docker start $TunnelContainerName | Out-Null
    }
    else {
        docker run -d --name $TunnelContainerName --restart unless-stopped cloudflare/cloudflared:latest tunnel --no-autoupdate --url http://host.docker.internal:7860 | Out-Host
    }

    Start-Sleep -Seconds 3
    $logs = docker logs $TunnelContainerName 2>&1
    $url = $null
    foreach ($line in $logs) {
        if ($line -match "https://[-a-zA-Z0-9\.]+\.trycloudflare\.com") {
            $url = $matches[0]
        }
    }

    if ($url) {
        Write-Host ""
        Write-Host "Public URL: $url" -ForegroundColor Cyan
    }
    else {
        Write-Host "Tunnel started. Run: docker logs $TunnelContainerName" -ForegroundColor Yellow
    }
}

$stateDir = Join-Path $PSScriptRoot ".host-state"
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null

$currentGuid = Get-ActiveSchemeGuid
$normalFile = Join-Path $stateDir "normal-plan-guid.txt"
if (-not (Test-Path $normalFile)) {
    Set-Content -Path $normalFile -Value $currentGuid -NoNewline
}

$normalGuid = (Get-Content $normalFile -Raw).Trim()
$hostGuid = Ensure-HostingPlan -NormalGuid $normalGuid -StateDir $stateDir

powercfg /SETACTIVE $hostGuid
Write-Host "Switched to RAWV Hosting power profile."

Ensure-Docker
Ensure-AppContainer -ProjectPath $ProjectPath -ImageName $ImageName -AppContainerName $AppContainerName -EnvFile $EnvFile
Ensure-TunnelContainer -TunnelContainerName $TunnelContainerName

Write-Host ""
Write-Host "Hosting mode enabled." -ForegroundColor Green
Write-Host "Local URL: http://localhost:7860"
Write-Host "To exit hosting mode, run scripts\exit-hosting-mode.ps1"
