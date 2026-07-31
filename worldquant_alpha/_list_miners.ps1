$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'"
if (-not $procs) { Write-Output "NO_PYTHON_PROCS"; exit 0 }
foreach ($p in $procs) {
    Write-Output ("PID=" + $p.ProcessId + " CMD=" + $p.CommandLine)
}
