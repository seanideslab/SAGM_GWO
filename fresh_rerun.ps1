$ErrorActionPreference = 'Stop'
$base = $PSScriptRoot
$target = Join-Path $base ('fresh_run_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
if (Test-Path -LiteralPath $target) { throw 'Target already exists.' }
New-Item -ItemType Directory -Path $target | Out-Null
$manifest = Get-Content -LiteralPath (Join-Path $base 'provenance\manifest.json') -Raw | ConvertFrom-Json
$renames = Get-Content -LiteralPath (Join-Path $base 'provenance\source_path_renames.json') -Raw | ConvertFrom-Json
$names = @($manifest.source_hashes.PSObject.Properties.Name) + @('RUN_ALL.cmd','RUN_ALL.ps1','requirements.txt')
foreach ($name in ($names | Select-Object -Unique)) {
    $mapped = $renames.PSObject.Properties[$name]
    if ($null -ne $mapped) { $name = [string]$mapped.Value }
    $source = Join-Path $base $name
    $output = Join-Path $target $name
    New-Item -ItemType Directory -Path (Split-Path $output) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $output
}
Write-Output "Prepared fresh source-only folder: $target"
Write-Output "To begin the full rerun, open RUN_ALL.cmd in that folder."
