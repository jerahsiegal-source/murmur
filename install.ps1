# Murmur installer: creates a local Python environment, installs dependencies, downloads the
# speech models (~650 MB, one time), and optionally adds a Start Menu shortcut.
#
#   powershell -ExecutionPolicy Bypass -File install.ps1            # install + Start Menu shortcut
#   powershell -ExecutionPolicy Bypass -File install.ps1 -NoShortcut
param([switch]$NoShortcut)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# Python 3.10-3.13 (3.14 may lack audio wheels)
$py = $null
foreach ($v in "3.12", "3.13", "3.11", "3.10") {
  try { & py "-$v" -c "import sys" 2>$null; if ($LASTEXITCODE -eq 0) { $py = @("py", "-$v"); break } } catch {}
}
if (-not $py) { throw "Python 3.10-3.13 not found. Install Python 3.12 from python.org (tick 'Add to PATH'), then rerun." }
Write-Host "Using Python $($py[1].TrimStart('-'))"

if (-not (Test-Path "$root\.venv")) { & $py[0] $py[1] -m venv "$root\.venv" }
$venvPy = "$root\.venv\Scripts\python.exe"
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -e "$root"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "Downloading speech models (one time, ~650 MB)..."
& $venvPy -c "from murmur.stt import Transcriber; import numpy as np; t = Transcriber('nemo-parakeet-tdt-0.6b-v2', 'int8', 4, 0); t.ensure_loaded(); t.transcribe_segments(np.zeros(16000, np.float32)); print('models ready')"
if ($LASTEXITCODE -ne 0) { throw "model download failed" }

if (-not $NoShortcut) {
  $lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "Murmur.lnk"
  $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
  $s.TargetPath = "$root\.venv\Scripts\pythonw.exe"
  $s.Arguments = "-m murmur"
  $s.WorkingDirectory = $root
  $s.Description = "Murmur - hotkey dictation and meeting notes"
  $s.Save()
  Write-Host "Start Menu shortcut created: $lnk"
}
Write-Host ""
Write-Host "Done. Start Murmur from the Start Menu (or: .venv\Scripts\pythonw.exe -m murmur)."
Write-Host "Then right-click the bar at the bottom of the screen -> AI cleanup -> paste your API key -> Save."
