# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025-2026 Lorenz Zhao
#
# Build the Windows release files: a portable ZIP and an Inno Setup installer.
# Requirements: Python 3.11+ on PATH (python), Inno Setup 6 (iscc).
# Output: release\ (relative to the repository root)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $Root
$Temp = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$Work = Join-Path $Temp "pdfms-build"
$Out = Join-Path $Root "release"
$AppId = "pdf-multifile-searcher"

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Exe failed with exit code $LASTEXITCODE" }
}

Write-Host "== Creating the build environment"
if (Test-Path $Work) { Remove-Item -Recurse -Force $Work }
New-Item -ItemType Directory -Force -Path $Work, $Out | Out-Null
Invoke-Checked python @("-m", "venv", "$Work\venv")
$Py = "$Work\venv\Scripts\python.exe"
Invoke-Checked $Py @("-m", "pip", "install", "--quiet", "--upgrade", "pip")
Invoke-Checked $Py @("-m", "pip", "install", "--quiet", $Root, "pyinstaller")
$Version = (& $Py -c "from importlib.metadata import version; print(version('pdf-multifile-searcher'))").Trim()
Write-Host "Version: $Version"

Write-Host "== Building the program folder"
Invoke-Checked "$Work\venv\Scripts\pyinstaller.exe" @(
    "packaging\pdf-multifile-searcher.spec", "--noconfirm",
    "--distpath", "$Work\dist", "--workpath", "$Work\pyinstaller")
$Bundle = "$Work\dist\$AppId"
Copy-Item -Recurse "$Bundle\_internal\licenses" "$Bundle\licenses"
Copy-Item "packaging\README-binary.txt" "$Bundle\README.txt"

Write-Host "== Smoke tests"
$Cli = "$Bundle\pdf-multifile-search.exe"
Invoke-Checked $Cli @("--version")
$Lines = @(& $Cli -f "tests\data" -p "Zephyria" --no-cache)
if ($LASTEXITCODE -ne 0 -or $Lines.Count -ne 4) { throw "Expected 4 matches, got $($Lines.Count)" }
$env:QT_QPA_PLATFORM = "offscreen"
$Gui = Start-Process -FilePath "$Bundle\pdf-multifile-searcher.exe" -PassThru
Start-Sleep -Seconds 8
if ($Gui.HasExited) { throw "The window program exited early with code $($Gui.ExitCode)" }
Stop-Process -Id $Gui.Id -Force
Remove-Item Env:QT_QPA_PLATFORM
Start-Sleep -Seconds 2

Write-Host "== Portable ZIP"
$Zip = "$Out\$AppId-$Version-windows-x64-portable.zip"
if (Test-Path $Zip) { Remove-Item $Zip }
Compress-Archive -Path $Bundle -DestinationPath $Zip -CompressionLevel Optimal

Write-Host "== Installer"
$Command = Get-Command iscc -ErrorAction SilentlyContinue
$Iscc = if ($Command) { $Command.Source } else { "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
Invoke-Checked $Iscc @("/Q", "/DAppVersion=$Version", "/DSourceDir=$Bundle", "/DOutputDir=$Out",
    "packaging\windows\installer.iss")

Write-Host "== Testing the installer"
$Setup = "$Out\$AppId-$Version-windows-x64-setup.exe"
$InstallDir = "$Work\installed"
$Proc = Start-Process -FilePath $Setup -Wait -PassThru -ArgumentList @(
    "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/DIR=`"$InstallDir`"")
if ($Proc.ExitCode -ne 0) { throw "Installer failed with exit code $($Proc.ExitCode)" }
$Lines = @(& "$InstallDir\pdf-multifile-search.exe" -f "tests\data" -p "Zephyria" --no-cache)
if ($Lines.Count -ne 4) { throw "Installed program: expected 4 matches, got $($Lines.Count)" }
$Proc = Start-Process -FilePath "$InstallDir\unins000.exe" -Wait -PassThru -ArgumentList @(
    "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
if ($Proc.ExitCode -ne 0) { throw "Uninstaller failed with exit code $($Proc.ExitCode)" }

Get-ChildItem $Out
