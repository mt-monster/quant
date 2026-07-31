# 仅终止卡住的 scan_v53 python 进程
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*scan_v53*' } | ForEach-Object {
    Write-Host ("killing pid=" + $_.ProcessId + " cmd=" + $_.CommandLine)
    Stop-Process -Id $_.ProcessId -Force
}
Write-Host "DONE"
