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

    # --- RPA dedicated Chrome (CDP) ---------------------------------------
    # FlowerNt3Automator connects over CDP (127.0.0.1:9222) to a dedicated
    # Chrome profile. Launch it on logon too, via launch_rpa_chrome.ps1.
    $chromeScript = "C:\ggotAI\ggotAIorder\launch_rpa_chrome.ps1"
    if (-not (Test-Path $chromeScript)) { throw "launch_rpa_chrome.ps1 not found: $chromeScript" }
    $psExe = (Get-Command powershell.exe).Source
    $chromeAction  = New-ScheduledTaskAction -Execute $psExe `
                       -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $chromeScript)
    $chromeTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $chromeSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

    Register-ScheduledTask -TaskName "ggotAIorder-RpaChrome" -Action $chromeAction `
        -Trigger $chromeTrigger -Settings $chromeSettings `
        -Description "ggotAIorder RPA dedicated Chrome (CDP 9222)" -Force | Out-Null

    Start-ScheduledTask -TaskName "ggotAIorder-RpaChrome"
    Start-Sleep -Seconds 2
    $t  = Get-ScheduledTask -TaskName "ggotAIorder"
    $tc = Get-ScheduledTask -TaskName "ggotAIorder-RpaChrome"

    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host " SUCCESS: scheduled tasks registered." -ForegroundColor Green
    Write-Host (" ggotAIorder          State: " + $t.State)
    Write-Host (" ggotAIorder-RpaChrome State: " + $tc.State)
    Write-Host " Both auto-start on Windows logon." -ForegroundColor Green
    Write-Host " First time only: log in to FlowerNT3 once in the RPA Chrome window." -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "FAILED:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}
