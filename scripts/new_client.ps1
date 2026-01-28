<#!
.SYNOPSIS
  Bootstrap a new LabelOps client configuration and folder structure.

.DESCRIPTION
  Prompts for client details, creates the client folder structure under
  D:\LabelOps\Clients, appends a client block to config/clients.yaml,
  validates config, and seeds an example TEST.txt in IN_TXT.
#>

$ErrorActionPreference = "Stop"

$LabelOpsRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $LabelOpsRoot "config\clients.yaml"
$ClientsRoot = Join-Path $LabelOpsRoot "Clients"

Write-Host "LabelOps new client bootstrap" -ForegroundColor Cyan

$clientId = Read-Host "Enter client_id (format: client_XX)"
if ($clientId -notmatch '^client_\d{2}$') {
    Write-Error "client_id must match format client_XX (e.g., client_03)."
    exit 1
}

$displayName = Read-Host "Enter display_name"
$defaultService = Read-Host "Enter default service (e.g., T24)"
$defaultWeightRaw = Read-Host "Enter default weight_kg (e.g., 1.0)"

$parsedWeight = 0
if (-not [double]::TryParse($defaultWeightRaw, [ref]$parsedWeight)) {
    Write-Error "weight_kg must be a numeric value."
    exit 1
}

$clientRoot = Join-Path $ClientsRoot $clientId
$folders = @{
    in_txt = Join-Path $clientRoot "IN_TXT"
    ready_xlsx = Join-Path $clientRoot "READY_XLSX"
    archive = Join-Path $clientRoot "ARCHIVE"
    tracking_out = Join-Path $clientRoot "TRACKING_OUT"
}

foreach ($folderPath in $folders.Values) {
    New-Item -ItemType Directory -Path $folderPath -Force | Out-Null
}

if (-not (Test-Path $ConfigPath)) {
    Write-Error "Config file not found: $ConfigPath"
    exit 1
}

$configContent = Get-Content -Path $ConfigPath -Raw
if ($configContent -match "(?m)^$([regex]::Escape($clientId)):") {
    Write-Host "Client $clientId already exists in config. Skipping append." -ForegroundColor Yellow
} else {
    $yamlBlock = @"

$clientId:
  display_name: \"$displayName\"
  defaults:
    service: \"$defaultService\"
    weight_kg: $parsedWeight
    country: \"UNITED KINGDOM\"
  services:
    - name: \"$defaultService\"
      trigger: { type: \"default\" }
    - name: \"SD\"
      trigger: { type: \"tag\", tag: \"SD\" }
  clickdrop:
    template_path: \"D:\\LabelOps\\assets\\ClickDrop_import_template_no_header.xlsx\"
    column_mapping:
      full_name: 1
      address_line_1: 2
      address_line_2: 3
      town_city: 4
      county: 5
      postcode: 6
      country: 7
      service: 8
      weight_kg: 9
      reference: 10
  folders:
    in_txt: \"D:\\LabelOps\\Clients\\$clientId\\IN_TXT\"
    ready_xlsx: \"D:\\LabelOps\\Clients\\$clientId\\READY_XLSX\"
    archive: \"D:\\LabelOps\\Clients\\$clientId\\ARCHIVE\"
    tracking_out: \"D:\\LabelOps\\Clients\\$clientId\\TRACKING_OUT\"
"@

    Add-Content -Path $ConfigPath -Value $yamlBlock
    Write-Host "Appended new client block to $ConfigPath" -ForegroundColor Green
}

$testFilePath = Join-Path $folders.in_txt "TEST.txt"
$testContent = @"
Grace O'Neil
Flat 2, 10 High Street
Stonehaven
Aberdeenshire
AB538HY
UK

Martin Wilkie
Unit 7, Riverside Estate
Dock Road
Barry
CF644BU
United Kingdom
"@
$testContent | Set-Content -Path $testFilePath -Encoding UTF8
Write-Host "Created sample input at $testFilePath" -ForegroundColor Green

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}

if (-not $pythonCmd) {
    Write-Warning "Python not found. Skipping config validation."
    exit 0
}

$pythonExe = $pythonCmd.Source
$validateScript = @"
import sys
sys.path.insert(0, r"$LabelOpsRoot")
from app import config
cfg = config.load_config(r"$ConfigPath")
config.validate_config(cfg)
print("OK")
"@

try {
    & $pythonExe -c $validateScript | Out-Host
    Write-Host "Config validation passed." -ForegroundColor Green
} catch {
    Write-Error "Config validation failed: $($_.Exception.Message)"
    exit 1
}
