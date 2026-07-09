param(
    [int]$Port = 2000,
    [string]$CarlaRoot = "D:\Simulator\CARLA_0.9.10.1"
)

$ErrorActionPreference = "Stop"

$CarlaExe = Join-Path $CarlaRoot "CarlaUE4.exe"

if (!(Test-Path $CarlaExe)) {
    Write-Error "CARLA executable not found: $CarlaExe"
    exit 1
}

Write-Host "Starting CARLA Server..."
Write-Host "CARLA Root: $CarlaRoot"
Write-Host "RPC Port: $Port"

Start-Process `
    -FilePath $CarlaExe `
    -WorkingDirectory $CarlaRoot `
    -ArgumentList @(
        "-carla-rpc-port=$Port",
        "-quality-level=Low",
        "-ResX=800",
        "-ResY=600",
        "-windowed",
        "-NoSound"
    )