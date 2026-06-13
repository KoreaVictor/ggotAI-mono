# ggotAIorder 자동시작 등록 스크립트 (관리자 PowerShell에서 실행)
# 출력 메시지는 인코딩 문제 회피를 위해 영문으로 둡니다.
$ErrorActionPreference = "Stop"
try {
    $exe = "C:\Program Files\Python313\pythonw.exe"
    $script = "C:\ggotAI\ggotAIorder\backend\run_dev.py"

    if (-not (Test-Path $exe))    { throw "pythonw.exe not found: $exe" }
    if (-not (Test-Path $script)) { throw "run_dev.py not found: $script" }

    $action   = New-ScheduledTaskAction -Execute $exe -Argument $script
    $trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
                  -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
                  -ExecutionTimeLimit ([TimeSpan]::Zero)

    Register-ScheduledTask -TaskName "ggotAIorder" -Action $action -Trigger $trigger `
        -Settings $settings -Description "ggotAIya auto order collector" -Force | Out-Null

    Start-ScheduledTask -TaskName "ggotAIorder"
    Start-Sleep -Seconds 2
    $t = Get-ScheduledTask -TaskName "ggotAIorder"

    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host " SUCCESS: scheduled task 'ggotAIorder' registered." -ForegroundColor Green
    Write-Host (" State: " + $t.State)
    Write-Host " It will auto-start on Windows logon (and restart on failure)." -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "FAILED:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}
