param(
    [string]$AudioDir = "",
    [string]$HostName = "",
    [int]$Port = 0,
    [int]$WebPort = 0,
    [ValidateSet("loop", "shuffle")]
    [string]$Mode = ""
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Resolve-Path (Join-Path $ScriptDir "..")
$DefaultAudioDir = Join-Path $ProjectDir "audio"
$ExplicitAudioDir = -not [string]::IsNullOrWhiteSpace($AudioDir)

if ([string]::IsNullOrWhiteSpace($AudioDir)) {
    if ([string]::IsNullOrWhiteSpace($env:RADIO_AUDIO_DIR)) {
        $AudioDir = $DefaultAudioDir
    } else {
        $AudioDir = $env:RADIO_AUDIO_DIR
    }
}

if ($ExplicitAudioDir -and -not (Test-Path -Path $AudioDir -PathType Container)) {
    throw "Audio directory does not exist: $AudioDir"
}

if (-not $ExplicitAudioDir) {
    New-Item -ItemType Directory -Force $AudioDir | Out-Null
}

New-Item -ItemType Directory -Force (Join-Path $ProjectDir "public/hls") | Out-Null

$env:RADIO_BASE_DIR = $ProjectDir
$env:RADIO_AUDIO_DIR = $AudioDir

$arguments = @("-m", "app.main", "--audio-dir", $AudioDir)

if (-not [string]::IsNullOrWhiteSpace($HostName)) {
    $arguments += @("--host", $HostName)
}

if ($Port -gt 0) {
    $arguments += @("--port", "$Port")
}

if ($WebPort -gt 0) {
    $arguments += @("--web-port", "$WebPort")
}

if (-not [string]::IsNullOrWhiteSpace($Mode)) {
    $arguments += @("--mode", $Mode)
}

Set-Location $ProjectDir
python $arguments
