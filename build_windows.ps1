param(
    [string]$TesseractDir = "",
    [string]$Python = "py -3.13"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Assert-Asset([string]$Path, [string]$Description) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing $Description at '$Path'. Read BUILDING.md."
    }
}

if (-not $TesseractDir) {
    $TesseractDir = Join-Path $root "vendor\tesseract"
}

$tesseractExe = Join-Path $TesseractDir "tesseract.exe"
$englishData = Join-Path $TesseractDir "tessdata\eng.traineddata"
Assert-Asset $tesseractExe "staged Tesseract executable (no installer will be launched)"
Assert-Asset $englishData "staged English Tesseract trained data"
Assert-Asset (Join-Path $TesseractDir "tessdata\configs\tsv") "Tesseract TSV output config"
$dlls = @(Get-ChildItem -LiteralPath $TesseractDir -Recurse -File |
    Where-Object { $_.Extension -in ".dll", ".pyd" })
if ($dlls.Count -eq 0) { throw "No Tesseract runtime DLLs found in '$TesseractDir'." }

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Invoke-Expression "$Python -m venv .venv"
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python virtual environment." }
}
function Invoke-BuildPython([string[]]$Arguments) {
    & $venvPython @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python build command failed ($LASTEXITCODE): $($Arguments -join ' ')"
    }
}
Invoke-BuildPython @("-m", "pip", "install", "-r", "requirements.txt", "-r", "requirements-presidio-optional.txt", "pyinstaller==6.22.0")

$modelWheel = Join-Path $env:TEMP "en_core_web_sm-3.8.0-py3-none-any.whl"
if (-not (Test-Path $modelWheel)) {
    $modelUrl = "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
    Invoke-WebRequest -Uri $modelUrl -OutFile $modelWheel -UseBasicParsing
}
$modelSha256 = "1932429DB7277D4BFF3DEED6B34CFC05DF17794F4A52EEB26CF8928F7C1A0FB85"
if ((Get-FileHash -LiteralPath $modelWheel -Algorithm SHA256).Hash -ne $modelSha256) {
    throw "spaCy model wheel SHA-256 did not match the pinned asset."
}
Invoke-BuildPython @("-m", "pip", "install", $modelWheel)

$modelAsset = Join-Path $root "vendor\en_core_web_sm"
if (-not (Test-Path (Join-Path $modelAsset "meta.json"))) {
    New-Item -ItemType Directory -Path $modelAsset -Force | Out-Null
    Invoke-BuildPython @("scripts/stage_assets.py")
}
Assert-Asset (Join-Path $modelAsset "meta.json") "staged spaCy model metadata"
Assert-Asset (Join-Path $modelAsset "en_core_web_sm-3.8.0\config.cfg") "staged spaCy model files"

Invoke-BuildPython @("-c", "import en_core_web_sm, presidio_analyzer, spacy; print('Presidio ready'); print('spaCy', spacy.__version__); print('Model', en_core_web_sm.__version__)")

Invoke-BuildPython @("-m", "PyInstaller", "--noconfirm", "--clean", "RedactionTool.spec")

$selftestPath = Join-Path $root "exe_selftest.txt"
$quotedSelftestPath = '"' + $selftestPath + '"'
Start-Process -FilePath (Join-Path $root "dist\RedactionTool.exe") -ArgumentList @(
    "--selftest", $quotedSelftestPath, "--require-ocr", "--require-presidio"
) -Wait -PassThru | ForEach-Object {
    if ($_.ExitCode -ne 0) { throw "Packaged self-test failed with exit $($_.ExitCode). See exe_selftest.txt." }
}
Assert-Asset (Join-Path $root "exe_selftest.txt") "packaged self-test report"
if ((Get-Content (Join-Path $root "exe_selftest.txt") -Raw) -notmatch "PASS bundled OCR" -or
    (Get-Content (Join-Path $root "exe_selftest.txt") -Raw) -notmatch "PASS bundled Presidio") {
    throw "Packaged OCR or Presidio self-test did not pass. See exe_selftest.txt."
}
Get-Content exe_selftest.txt
Write-Host "Built dist\RedactionTool.exe"

# --- Optional: Inno Setup installer -------------------------------------
# The exe above is the primary artifact. If Inno Setup 6 is installed, also
# compile installer\RedactionTool.iss; otherwise warn and finish successfully.
function Find-Iscc {
    $candidates = @()
    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if ($base) { $candidates += (Join-Path $base "Inno Setup 6\ISCC.exe") }
    }
    if ($env:LOCALAPPDATA) {
        $candidates += (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    $onPath = Get-Command iscc -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    return $null
}

$packageVersion = & $venvPython -c `
    "import sys; sys.path.insert(0, sys.argv[1]); import version_file; print(version_file.read_package_version())" `
    (Join-Path $root "scripts")
if ($LASTEXITCODE -ne 0 -or -not $packageVersion) {
    throw "Could not read the package version from redaction_tool/__init__.py."
}
$packageVersion = ("$packageVersion").Trim()

$iscc = Find-Iscc
if (-not $iscc) {
    Write-Warning @"
Inno Setup 6 (ISCC.exe) was not found, so no installer was built.
dist\RedactionTool.exe above is still complete and usable.
To also produce installer\Output\RedactionTool-Setup-$packageVersion.exe:
  winget install --id JRSoftware.InnoSetup -e
then re-run .\build_windows.ps1 (or compile installer\RedactionTool.iss directly).
"@
} else {
    Write-Host "Compiling installer with $iscc (version $packageVersion)"
    & $iscc "/DAppVersion=$packageVersion" (Join-Path $root "installer\RedactionTool.iss")
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
    }
    $setupPath = Join-Path $root "installer\Output\RedactionTool-Setup-$packageVersion.exe"
    if (-not (Test-Path -LiteralPath $setupPath)) {
        throw "Installer compiled but expected output was not created: $setupPath"
    }
    Write-Host "Built $setupPath"
}
