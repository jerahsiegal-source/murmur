# 10 timed end-to-end dictations against the real app (fake mic = WAV clips).
param([string]$DataDir = "$PSScriptRoot\..\data\testrun")
$root = Resolve-Path "$PSScriptRoot\.."
$py = "$root\.venv\Scripts\python.exe"
$runs = @(
  @("dictation30.wav", 33.6, "hold"), @("short.wav", 5.7, "hold"), @("long60.wav", 43.1, "hold"),
  @("dictation30.wav", 33.6, "handsfree"), @("short.wav", 5.7, "handsfree"), @("long60.wav", 43.1, "handsfree"),
  @("dictation30.wav", 33.6, "hold"), @("short.wav", 5.7, "hold"), @("long60.wav", 43.1, "hold"),
  @("dictation30.wav", 33.6, "handsfree")
)
$env:MURMUR_DATA_DIR = $DataDir
$i = 0
foreach ($r in $runs) {
  $i++
  $env:MURMUR_FAKE_MIC = "$root\data\test\$($r[0])"
  $p = Start-Process -FilePath $py -ArgumentList "-m","murmur" -PassThru -WindowStyle Hidden
  Start-Sleep 3
  $out = & $py "$root\tools\e2e_dictation.py" $r[1] $r[2]
  "#$i $($r[0]) ($($r[1])s, $($r[2])): $(($out | Select-String 'RESULT') -replace 'RESULT ','')"
  Stop-Process -Id $p.Id -ErrorAction SilentlyContinue
  Start-Sleep 1
}
