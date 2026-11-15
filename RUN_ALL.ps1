param([switch]$CheckOnly, [switch]$RepairCheck, [switch]$SkipMisocp)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$cs = Get-CimInstance Win32_ComputerSystem
$osInfo = Get-CimInstance Win32_OperatingSystem
$installed = (Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum
$hardware = [ordered]@{
    CPU = $cpu.Name
    Cores = $cpu.NumberOfCores
    LogicalProcessors = $cpu.NumberOfLogicalProcessors
    InstalledRAM_GiB = [math]::Round($installed / 1GB, 2)
    OSVisibleRAM_GiB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 2)
    OS = $osInfo.Caption
    OSVersion = $osInfo.Version
    ComputerName = $env:COMPUTERNAME
}
$hardware | ConvertTo-Json | Set-Content -LiteralPath hardware.json -Encoding UTF8
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 virtual environment creation failed.' }
}
if (-not (Test-Path -LiteralPath '.venv\deps.ready')) {
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. No experiment was started.' }
    Set-Content -LiteralPath '.venv\deps.ready' -Value 'installed'
}
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class RunPower {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint flags);
    [DllImport("kernel32.dll")] public static extern IntPtr GetStdHandle(int which);
    [DllImport("kernel32.dll")] public static extern bool GetConsoleMode(IntPtr h, out uint mode);
    [DllImport("kernel32.dll")] public static extern bool SetConsoleMode(IntPtr h, uint mode);
}
'@
$inputHandle = [RunPower]::GetStdHandle(-10)
[uint32]$oldConsoleMode = 0
$haveConsoleMode = [RunPower]::GetConsoleMode($inputHandle, [ref]$oldConsoleMode)
if ($haveConsoleMode) {
    [RunPower]::SetConsoleMode($inputHandle, [uint32](($oldConsoleMode -bor 128) -band (-bnot 64))) | Out-Null
}
$log = 'console_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.txt'
try {
    [RunPower]::SetThreadExecutionState([uint32]2147483649) | Out-Null
    $runnerArgs = @('-u', 'run_machine_suite.py')
    if ($CheckOnly) { $runnerArgs += '--check-only' }
    if ($SkipMisocp) { $runnerArgs += '--skip-misocp' }
    if ($RepairCheck) { $runnerArgs = @('-u', 'check_repair.py') }
    & '.\.venv\Scripts\python.exe' @runnerArgs 2>&1 | Tee-Object -FilePath $log
    if ($LASTEXITCODE -ne 0) { throw "Run stopped. Keep this folder and send $log." }
} finally {
    if ($haveConsoleMode) { [RunPower]::SetConsoleMode($inputHandle, $oldConsoleMode) | Out-Null }
    [RunPower]::SetThreadExecutionState([uint32]2147483648) | Out-Null
}
