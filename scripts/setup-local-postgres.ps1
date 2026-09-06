<#
.SYNOPSIS
  Sets up a local PostgreSQL instance for the Adventour seed -- no admin required.

.DESCRIPTION
  The winget/EDB installer needs UAC elevation, which a non-interactive session
  cannot accept. This uses EDB's portable binary archive instead: nothing is
  installed system-wide, no service is registered, and removing the directory
  removes the instance completely.

  Runs on port 5433 to avoid colliding with any Postgres installed later.

.NOTES
  Development only. The password below is a local dev credential for an instance
  listening on localhost; do not reuse it for anything reachable.
#>
[CmdletBinding()]
param(
    [string]$Root = (Join-Path $env:LOCALAPPDATA 'Adventour'),
    [int]$Port = 5433,
    [string]$Password = 'adventour_dev',
    [string]$Database = 'adventour',
    [string]$Version = '17.11-1'
)

$ErrorActionPreference = 'Stop'

$Url     = "https://get.enterprisedb.com/postgresql/postgresql-$Version-windows-x64-binaries.zip"
$Zip     = Join-Path $Root 'pgsql.zip'
$Bin     = Join-Path $Root 'pgsql\bin'
$DataDir = Join-Path $Root 'pgdata'
$LogFile = Join-Path $Root 'postgres.log'

New-Item -ItemType Directory -Force -Path $Root | Out-Null

if (-not (Test-Path $Bin)) {
    if (-not (Test-Path $Zip)) {
        Write-Host "Downloading PostgreSQL $Version binaries (~325 MB) ..."
        Invoke-WebRequest -Uri $Url -OutFile $Zip -UseBasicParsing
    }
    Write-Host 'Extracting ...'
    Expand-Archive -Path $Zip -DestinationPath $Root -Force
} else {
    Write-Host 'Binaries already present.'
}

if (-not (Test-Path (Join-Path $DataDir 'PG_VERSION'))) {
    Write-Host 'Initializing data directory ...'
    $pwFile = Join-Path $Root 'pw.txt'
    # initdb reads the password from a file; remove it immediately afterwards.
    Set-Content -Path $pwFile -Value $Password -NoNewline -Encoding ascii
    & (Join-Path $Bin 'initdb.exe') -D $DataDir -U postgres --pwfile=$pwFile --encoding=UTF8 | Out-Null
    Remove-Item $pwFile -Force
} else {
    Write-Host 'Data directory already initialized.'
}

$status = & (Join-Path $Bin 'pg_ctl.exe') -D $DataDir status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Starting PostgreSQL on port $Port ..."
    & (Join-Path $Bin 'pg_ctl.exe') -D $DataDir -l $LogFile -o "-p $Port" -w start
} else {
    Write-Host 'Server already running.'
}

$env:PGPASSWORD = $Password
$exists = & (Join-Path $Bin 'psql.exe') -U postgres -h localhost -p $Port -tAc `
    "SELECT 1 FROM pg_database WHERE datname='$Database'"
if ($exists -ne '1') {
    Write-Host "Creating database '$Database' ..."
    & (Join-Path $Bin 'createdb.exe') -U postgres -h localhost -p $Port $Database
} else {
    Write-Host "Database '$Database' already exists."
}

Write-Host ''
Write-Host 'Ready.'
Write-Host "  binaries : $Bin"
Write-Host "  data     : $DataDir"
Write-Host "  log      : $LogFile"
Write-Host "  connect  : postgresql://postgres:$Password@localhost:$Port/$Database"
Write-Host ''
Write-Host "  stop with: & '$Bin\pg_ctl.exe' -D '$DataDir' stop"
