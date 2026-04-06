# Run this script in an elevated PowerShell (Run as Administrator)

$ErrorActionPreference = "Stop"

Write-Host "Enabling required Windows features for Docker Desktop..."
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux -All -NoRestart
Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -All -NoRestart

# Hyper-V is only available on Pro/Enterprise. Ignore failure on Home.
try {
    Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -All -NoRestart
}
catch {
    Write-Host "Hyper-V feature unavailable (likely Windows Home). This is okay when using WSL2 backend." -ForegroundColor Yellow
}

bcdedit /set hypervisorlaunchtype auto | Out-Null

Write-Host ""
Write-Host "Now do these manual BIOS checks:" -ForegroundColor Cyan
Write-Host "1) Reboot and enter BIOS/UEFI"
Write-Host "2) Enable Intel VT-x or AMD-V (SVM) virtualization"
Write-Host "3) Save and reboot"
Write-Host ""
Write-Host "After reboot, run: wsl --install"
Write-Host "Then install/start Docker Desktop and sign in once."
