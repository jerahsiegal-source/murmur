# Yappr installer: creates a local Python environment, installs dependencies, downloads the
# speech and voice models (~750 MB, one time), and optionally adds a Start Menu shortcut.
#
#   powershell -ExecutionPolicy Bypass -File install.ps1            # install + Start Menu shortcut, then start Yappr
#   powershell -ExecutionPolicy Bypass -File install.ps1 -NoShortcut -NoStart
param([switch]$NoShortcut, [switch]$NoStart)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Step($n, $text) { Write-Host ""; Write-Host "  [$n/4] $text" -ForegroundColor Yellow }
function Ok($text) { Write-Host "        $([char]0x2713) $text" -ForegroundColor Green }

Write-Host ""
Write-Host "  Yappr: talk instead of type. Setting things up (about 5 minutes, mostly downloads)." -ForegroundColor White

# Python 3.10-3.13 (3.14 may lack audio wheels)
$py = $null
foreach ($v in "3.12", "3.13", "3.11", "3.10") {
  try { & py "-$v" -c "import sys" 2>$null; if ($LASTEXITCODE -eq 0) { $py = @("py", "-$v"); break } } catch {}
}
if (-not $py) { throw "Python 3.10-3.13 not found. Install Python 3.12 from python.org (tick 'Add to PATH'), then rerun." }
Step 1 "Setting up Python"
Ok "Using Python $($py[1].TrimStart('-'))"

if (-not (Test-Path "$root\.venv")) { & $py[0] $py[1] -m venv "$root\.venv" }
$venvPy = "$root\.venv\Scripts\python.exe"
& $venvPy -m pip install --quiet --upgrade pip
# The app used to be called Murmur: drop its old package entry from this environment if present.
try { & $venvPy -m pip uninstall --quiet -y murmur-dictation 2>$null } catch {}  # stderr only says "not installed"
& $venvPy -m pip install --quiet -e "$root"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
Ok "Yappr and its parts are installed"

Step 2 "Downloading the speech engine (one time, about 650 MB). It runs on this PC, so your voice never leaves it."
& $venvPy -c "from yappr.stt import Transcriber; import numpy as np; t = Transcriber('nemo-parakeet-tdt-0.6b-v2', 'int8', 4, 0); t.ensure_loaded(); t.transcribe_segments(np.zeros(16000, np.float32)); print('models ready')"
if ($LASTEXITCODE -ne 0) { throw "model download failed" }
Step 3 "Downloading the read-aloud voice (one time, about 100 MB)"
& $venvPy -c "from yappr.config import data_dir; from yappr.tts import Voice; Voice(data_dir()).ensure_loaded(); print('voice ready')"
if ($LASTEXITCODE -ne 0) { throw "voice download failed" }

Step 4 "Adding Yappr to the Start Menu"
if (-not $NoShortcut) {
  $programs = [Environment]::GetFolderPath("Programs")
  $old = Join-Path $programs "Murmur.lnk"  # old name; its command no longer works
  if (Test-Path $old) { Remove-Item $old; Write-Host "Removed the old Murmur shortcut." }
  $lnk = Join-Path $programs "Yappr.lnk"
  $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
  $s.TargetPath = "$root\.venv\Scripts\pythonw.exe"
  $s.Arguments = "-m yappr"
  $s.WorkingDirectory = $root
  $s.Description = "Yappr - hotkey dictation, read-aloud and meeting notes"
  $s.IconLocation = "$root\yappr\assets\yappr.ico,0"
  $s.Save()
  Ok "Start Menu shortcut created"
} else { Ok "Skipped (-NoShortcut)" }
Write-Host ""
Write-Host "  All set." -ForegroundColor Green
Write-Host "  Yappr lives in the bar at the bottom of your screen and the tray icon by the clock."
Write-Host "  Hold Ctrl+Win in any text box and talk. Next time, start it from the Start Menu."
if (-not $NoStart) {
  Start-Process -FilePath "$root\.venv\Scripts\pythonw.exe" -ArgumentList "-m", "yappr" -WorkingDirectory $root
  Write-Host "  Starting Yappr now: a welcome window will show you around." -ForegroundColor White
}
