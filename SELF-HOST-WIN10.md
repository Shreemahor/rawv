# RAWV Self-Host on Windows 10 (No Python/Node install)

This is the easiest setup: Docker Desktop + one-command hosting mode.

## 1) Fix Docker Desktop "virtualization not detected"

Run [scripts/docker-win10-fix.ps1](scripts/docker-win10-fix.ps1) as Administrator on the hosting laptop:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\docker-win10-fix.ps1
```

Then do this manually:
1. Reboot and enter BIOS/UEFI.
2. Enable virtualization:
- Intel: `Intel Virtualization Technology (VT-x)`
- AMD: `SVM / AMD-V`
3. Save and reboot.

After reboot:
```powershell
wsl --install
```
Reboot again if prompted.

Then install Docker Desktop and open it.
If Docker asks you to sign in, sign in once with a free Docker account.

## 2) Put project on the hosting laptop

Get this repo folder onto the machine (clone or zip).

Create `.env` in repo root with:

```dotenv
GROQ_API_KEY=YOUR_REAL_GROQ_KEY
RAWV_CHAT_MODEL=llama-3.1-8b-instant
RAWV_WHISPER_MODEL=whisper-large-v3-turbo
RAWV_TTS_VOICE=en-US-AriaNeural
RAWV_TTS_RATE=+5%
RAWV_RESEARCH_DEFAULT_MODE=normal
RAWV_BROWSER_EVIDENCE=false
RAWV_AUDIO_SAMPLE_RATE=24000
```

## 3) Enter hosting mode (one command)

From repo root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\enter-hosting-mode.ps1
```

What it does:
- Switches Windows to a no-sleep hosting power profile
- Starts Docker Desktop if needed
- Builds and starts RAWV container (if first run)
- Starts Cloudflare quick tunnel container
- Prints your public URL (trycloudflare)

## 4) Exit hosting mode (one command)

```powershell
.\scripts\exit-hosting-mode.ps1
```

What it does:
- Stops RAWV container
- Stops tunnel container
- Restores your normal power profile

Optional: also close Docker Desktop
```powershell
.\scripts\exit-hosting-mode.ps1 -StopDockerDesktop
```

## 5) Does laptop need to stay on?

Yes.
- If laptop sleeps, site goes offline.
- If laptop is off, site goes offline.
- If Wi-Fi drops, site goes offline.

For 1-week uptime: keep it plugged in and in hosting mode the whole week.
Screen can turn off; system must not sleep.

## 6) Quick checks

- Local app: `http://localhost:7860`
- Tunnel logs:
```powershell
docker logs rawv-tunnel
```
- App logs:
```powershell
docker logs rawv
```

## 7) Common Docker startup checks

```powershell
systeminfo | findstr /i "Virtualization"
Get-CimInstance Win32_Processor | Select-Object Name,VirtualizationFirmwareEnabled,SecondLevelAddressTranslationExtensions
wsl --status
```

If virtualization is disabled, Docker Desktop cannot run until BIOS virtualization is enabled.
