# Dot-source from the project root: . .\scripts\postgis-env.ps1
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    throw 'Missing .env. Copy .env.example and set CLIMATE_DB_PASSWORD first.'
}
$passwordLine = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^CLIMATE_DB_PASSWORD=' } | Select-Object -First 1
if (-not $passwordLine) {
    throw 'CLIMATE_DB_PASSWORD is missing from .env.'
}
$password = $passwordLine.Substring('CLIMATE_DB_PASSWORD='.Length).Trim()
if ($password -notmatch '^[a-zA-Z0-9]+$') {
    throw 'CLIMATE_DB_PASSWORD must contain only letters and digits for this local URL helper.'
}
$env:DATABASE_URL = "postgresql+psycopg://climate:${password}@127.0.0.1:5432/climate"
