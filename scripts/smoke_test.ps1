<#!
.SYNOPSIS
  End-to-end smoke test for a LabelOps installation.

.DESCRIPTION
  Validates config, required folders, template availability, and runs the
  pipeline in dry-run and real modes for a generated sample batch.
#>

$ErrorActionPreference = "Stop"

$LabelOpsRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $LabelOpsRoot "config\clients.yaml"
$RequiredFolders = @(
    "assets",
    "config",
    "Clients",
    "Logs"
)

$results = New-Object System.Collections.Generic.List[object]

function Add-Result {
    param(
        [string]$Name,
        [bool]$Success,
        [string]$Detail
    )
    $results.Add([pscustomobject]@{
        Name = $Name
        Success = $Success
        Detail = $Detail
    }) | Out-Null
    $status = if ($Success) { "PASS" } else { "FAIL" }
    Write-Host ("[{0}] {1} - {2}" -f $status, $Name, $Detail)
}

Write-Host "Starting LabelOps smoke test..." -ForegroundColor Cyan

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}

$exeCandidates = @(
    Join-Path $LabelOpsRoot "LabelOps.exe",
    Join-Path $LabelOpsRoot "LabelOpsDaemon.exe",
    Join-Path $LabelOpsRoot "LabelOpsGui.exe"
)
$exeFound = $exeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($pythonCmd -or $exeFound) {
    $detail = if ($pythonCmd) { "Python found: $($pythonCmd.Source)" } else { "Executable found: $exeFound" }
    Add-Result "Python or executable availability" $true $detail
} else {
    Add-Result "Python or executable availability" $false "Neither python/py nor known executables were found."
}

foreach ($folder in $RequiredFolders) {
    $path = Join-Path $LabelOpsRoot $folder
    Add-Result "Required folder: $folder" (Test-Path $path) $path
}

if (-not (Test-Path $ConfigPath)) {
    Add-Result "Config file exists" $false $ConfigPath
} else {
    Add-Result "Config file exists" $true $ConfigPath
}

$pythonExe = if ($pythonCmd) { $pythonCmd.Source } else { $null }

$clientMeta = $null
if ($pythonExe) {
    $configScript = @"
import json
import sys
sys.path.insert(0, r"$LabelOpsRoot")
from app import config
cfg = config.load_config(r"$ConfigPath")
config.validate_config(cfg)
client_id = sorted(cfg.keys())[0]
settings = config.resolve_client_settings(cfg, client_id)
print(json.dumps({
    "client_id": client_id,
    "template_path": settings.get("clickdrop", {}).get("template_path"),
    "folders": settings.get("folders", {})
}))
"@
    try {
        $clientMeta = & $pythonExe -c $configScript | ConvertFrom-Json
        Add-Result "Config parsing (app/config.py)" $true "Validated $($clientMeta.client_id)"
    } catch {
        Add-Result "Config parsing (app/config.py)" $false $_.Exception.Message
    }
} else {
    Add-Result "Config parsing (app/config.py)" $false "Python not available"
}

if ($clientMeta) {
    $templatePath = $clientMeta.template_path
    $templateExists = $false
    if ($templatePath) {
        $templateExists = Test-Path $templatePath
    }
    Add-Result "Template XLSX exists" $templateExists $templatePath

    foreach ($folderEntry in $clientMeta.folders.PSObject.Properties) {
        $folderPath = $folderEntry.Value
        Add-Result "Client folder: $($folderEntry.Name)" (Test-Path $folderPath) $folderPath
    }
}

if ($pythonExe -and $clientMeta) {
    $dryRunScript = @"
import json
import os
import tempfile
import sys
sys.path.insert(0, r"$LabelOpsRoot")
from app import config, pipeline
cfg = config.load_config(r"$ConfigPath")
config.validate_config(cfg)
client_id = "$($clientMeta.client_id)"
settings = config.resolve_client_settings(cfg, client_id)
sample = """Grace O'Neil
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
"""
result = pipeline.run_pipeline(
    client_id=client_id,
    client_settings=settings,
    raw_text=sample,
    input_files=[os.path.join(tempfile.gettempdir(), "labelops_smoke.txt")],
    use_ai=False,
    auto_apply_max_risk="low",
    max_ai_calls=0,
    source="smoke_test",
    dry_run=True,
)
print(json.dumps(result))
"@
    try {
        $dryResult = & $pythonExe -c $dryRunScript | ConvertFrom-Json
        Add-Result "Dry-run pipeline" $true "Records: $($dryResult.record_count)"
    } catch {
        Add-Result "Dry-run pipeline" $false $_.Exception.Message
    }

    $realRunScript = @"
import json
import os
import tempfile
import sys
sys.path.insert(0, r"$LabelOpsRoot")
from app import config, pipeline
cfg = config.load_config(r"$ConfigPath")
config.validate_config(cfg)
client_id = "$($clientMeta.client_id)"
settings = config.resolve_client_settings(cfg, client_id)
sample = """Grace O'Neil
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
"""
result = pipeline.run_pipeline(
    client_id=client_id,
    client_settings=settings,
    raw_text=sample,
    input_files=[os.path.join(tempfile.gettempdir(), "labelops_smoke.txt")],
    use_ai=False,
    auto_apply_max_risk="low",
    max_ai_calls=0,
    source="smoke_test",
    dry_run=False,
)
print(json.dumps(result))
"@
    try {
        $realResult = & $pythonExe -c $realRunScript | ConvertFrom-Json
        $xlsxExists = Test-Path $realResult.output_xlsx
        $trackingExists = Test-Path $realResult.tracking_csv
        $outputsOk = $xlsxExists -and $trackingExists
        $detail = "XLSX: $($realResult.output_xlsx) (exists=$xlsxExists); Tracking: $($realResult.tracking_csv) (exists=$trackingExists)"
        Add-Result "Real pipeline + outputs" $outputsOk $detail
    } catch {
        Add-Result "Real pipeline + outputs" $false $_.Exception.Message
    }
} else {
    Add-Result "Dry-run pipeline" $false "Missing python or config metadata"
    Add-Result "Real pipeline + outputs" $false "Missing python or config metadata"
}

$failed = $results | Where-Object { -not $_.Success }
Write-Host "" 
Write-Host "Smoke test summary:" -ForegroundColor Cyan
if ($failed.Count -eq 0) {
    Write-Host "PASS: All checks succeeded." -ForegroundColor Green
    exit 0
}

Write-Host ("FAIL: {0} checks failed." -f $failed.Count) -ForegroundColor Red
foreach ($item in $failed) {
    Write-Host (" - {0}: {1}" -f $item.Name, $item.Detail) -ForegroundColor Red
}
exit 1
