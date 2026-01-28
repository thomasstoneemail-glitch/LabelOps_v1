<#!
.SYNOPSIS
  Build LabelOps executables and a versioned release folder.

.DESCRIPTION
  - Creates a build venv in .venv_build
  - Installs dependencies + PyInstaller
  - Builds GUI, Daemon, and Pipeline executables (one-folder mode)
  - Copies starter configs and assets into the release folder
  - Writes BUILD_INFO.txt

.NOTES
  Run from PowerShell on Windows WorkSpaces/Server.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $repoRoot ".venv_build"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$distRoot = "D:\\LabelOps\\dist"

Write-Host "[LabelOps] Repo root: $repoRoot"
Write-Host "[LabelOps] Dist root: $distRoot"

if (-not (Test-Path $venvPath)) {
    Write-Host "[LabelOps] Creating build venv at $venvPath"
    python -m venv $venvPath
}

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found in build venv: $pythonExe"
}

Write-Host "[LabelOps] Upgrading pip"
& $pythonExe -m pip install --upgrade pip

Write-Host "[LabelOps] Installing LabelOps dependencies"
& $pythonExe -m pip install -e $repoRoot

Write-Host "[LabelOps] Installing PyInstaller"
& $pythonExe -m pip install pyinstaller

$releaseDir = & $pythonExe "$repoRoot\scripts\build.py" release-dir --dist-root $distRoot
if (-not $releaseDir) {
    throw "Failed to determine release directory."
}
Write-Host "[LabelOps] Release directory: $releaseDir"

$gitCommit = "unknown"
try {
    $gitCommit = (git -C $repoRoot rev-parse --short HEAD).Trim()
} catch {
    Write-Warning "Git commit not available; using 'unknown'."
}

$buildWork = Join-Path $repoRoot "build"
$specDir = Join-Path $repoRoot "build"

$commonArgs = @(
    "--noconfirm",
    "--clean",
    "--onedir",
    "--distpath", $releaseDir,
    "--workpath", $buildWork,
    "--specpath", $specDir,
    "--collect-all", "PySide6",
    "--collect-submodules", "PySide6"
)

Write-Host "[LabelOps] Building GUI executable"
& $pythonExe -m PyInstaller @commonArgs --name "LabelOpsGUI" --windowed "$repoRoot\app\gui_main.py"

Write-Host "[LabelOps] Building Daemon executable"
& $pythonExe -m PyInstaller @commonArgs --name "LabelOpsDaemon" "$repoRoot\app\daemon.py"

Write-Host "[LabelOps] Building Pipeline executable"
& $pythonExe -m PyInstaller @commonArgs --name "LabelOpsPipeline" "$repoRoot\app\pipeline.py"

Write-Host "[LabelOps] Copying starter config + assets"
& $pythonExe "$repoRoot\scripts\build.py" copy-starters --release-dir $releaseDir

Write-Host "[LabelOps] Writing BUILD_INFO.txt"
& $pythonExe "$repoRoot\scripts\build.py" write-build-info --release-dir $releaseDir --git-commit $gitCommit

Write-Host "[LabelOps] Build complete"
