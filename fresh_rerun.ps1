$ErrorActionPreference = 'Stop'
$base = $PSScriptRoot
$target = Join-Path $base ('fresh_run_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
if (Test-Path -LiteralPath $target) { throw 'Target already exists.' }
New-Item -ItemType Directory -Path $target | Out-Null
foreach ($folder in @('sim','config','data','tests')) {
    Copy-Item -LiteralPath (Join-Path $base $folder) -Destination $target -Recurse
}
Get-ChildItem -LiteralPath $base -File | Where-Object {
    $_.Extension -in @('.py','.ps1','.cmd') -or $_.Name -in @('requirements.txt','baseline_reference.json','README_REPAIR.md')
} | Copy-Item -Destination $target
Write-Output "Prepared fresh source-only folder: $target"
Write-Output "First run CHECK_REPAIR.cmd, then RUN_ALL.cmd in that folder."
