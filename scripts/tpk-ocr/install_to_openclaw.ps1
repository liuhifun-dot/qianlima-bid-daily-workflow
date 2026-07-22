$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TargetRoot = Join-Path $env:USERPROFILE ".openclaw\skills"
$TargetDir = Join-Path $TargetRoot "tpk-ocr"

New-Item -ItemType Directory -Force $TargetRoot | Out-Null
if (Test-Path $TargetDir) {
    Remove-Item -Recurse -Force $TargetDir
}
Copy-Item -Recurse -Force $SourceDir $TargetDir

Write-Host "Installed tpk-ocr to: $TargetDir"
Write-Host "Next: cd `"$TargetDir`"; py -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt"
