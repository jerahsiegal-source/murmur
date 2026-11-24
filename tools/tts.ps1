# Generate a 16 kHz mono WAV from text using the built-in Windows voice (for local tests only).
param([Parameter(Mandatory)][string]$Text, [Parameter(Mandatory)][string]$Out, [int]$Rate = 0)
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = $Rate
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile($Out, $fmt)
$s.Speak($Text)
$s.Dispose()
