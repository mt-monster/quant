$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -match 'analyze_tabbit_parallel\.py' }
if (-not $procs) { Write-Output "NO_TABBIT_PROCS"; exit 0 }
foreach ($p in $procs) {
    Write-Output ("KILLING PID=" + $p.ProcessId + " CMD=" + $p.CommandLine)
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
Write-Output "TABBIT_KILL_DONE"
