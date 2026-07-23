# ggotAIorder 자동시작 등록 스크립트 (관리자 PowerShell에서 실행)
# 경로(설치폴더·파이썬·크롬)와 대상 사용자는 common_paths.ps1 이 이 PC에서 찾아낸다.
# 출력 메시지는 인코딩 문제 회피를 위해 영문으로 둡니다.
$ErrorActionPreference = "Stop"
try {
    . (Join-Path $PSScriptRoot 'common_paths.ps1')

    $exe = Resolve-Pythonw
    if (-not $exe) { throw "pythonw.exe not found (py launcher / PATH / standard install dirs)." }

    $script = Join-Path $PSScriptRoot 'backend\run_dev.py'
    if (-not (Test-Path $script)) { throw "run_dev.py not found: $script" }

    # 승격하면 $env:USERNAME 은 관리자 계정이 된다. 태스크는 "평소 로그인하는 사용자"
    # 앞으로 등록해야 그 사람이 로그인할 때 뜬다.
    $targetUser = Resolve-InteractiveUser
    Write-Host ("Registering tasks for logon user: {0}" -f $targetUser) -ForegroundColor Cyan
    Write-Host ("Install root: {0}" -f (Get-GgotRoot))
    Write-Host ("Pythonw     : {0}" -f $exe)

    $action   = New-ScheduledTaskAction -Execute $exe -Argument ('"{0}"' -f $script)
    $trigger  = New-ScheduledTaskTrigger -AtLogOn -User $targetUser
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
                  -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
                  -ExecutionTimeLimit ([TimeSpan]::Zero)

    Register-ScheduledTask -TaskName "ggotAIorder" -Action $action -Trigger $trigger `
        -Settings $settings -User $targetUser `
        -Description "ggotAIya auto order collector" -Force | Out-Null

    Start-ScheduledTask -TaskName "ggotAIorder"

    # --- RPA dedicated Chrome (CDP) ---------------------------------------
    # FlowerNt3Automator connects over CDP (127.0.0.1:9222) to a dedicated
    # Chrome profile. Launch it on logon too, via launch_rpa_chrome.ps1.
    $chromeScript = Join-Path $PSScriptRoot 'launch_rpa_chrome.ps1'
    if (-not (Test-Path $chromeScript)) { throw "launch_rpa_chrome.ps1 not found: $chromeScript" }
    if (-not (Resolve-Chrome)) { throw "chrome.exe not found (App Paths / Program Files / LocalAppData)." }
    $psExe = (Get-Command powershell.exe).Source
    $chromeAction  = New-ScheduledTaskAction -Execute $psExe `
                       -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $chromeScript)
    $chromeTrigger = New-ScheduledTaskTrigger -AtLogOn -User $targetUser
    $chromeSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

    Register-ScheduledTask -TaskName "ggotAIorder-RpaChrome" -Action $chromeAction `
        -Trigger $chromeTrigger -Settings $chromeSettings -User $targetUser `
        -Description "ggotAIorder RPA dedicated Chrome (CDP 9222)" -Force | Out-Null

    Start-ScheduledTask -TaskName "ggotAIorder-RpaChrome"

    # --- Health check (60min + on workstation unlock) ---------------------
    # The logon trigger does NOT fire when resuming from sleep/hibernate, so
    # the engine can stay down silently. This task re-runs healthcheck.ps1
    # every 60 minutes AND whenever the workstation is unlocked, restarting
    # the backend(8765)/RPA Chrome(9222) if either is down (idempotent).
    $hcScript = Join-Path $PSScriptRoot 'healthcheck.ps1'
    if (-not (Test-Path $hcScript)) { throw "healthcheck.ps1 not found: $hcScript" }
    $hcAction = New-ScheduledTaskAction -Execute $psExe `
                  -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $hcScript)
    $hcRepeat = New-ScheduledTaskTrigger -Once -At (Get-Date) `
                  -RepetitionInterval (New-TimeSpan -Minutes 60)
    $hcCls = Get-CimClass -ClassName MSFT_TaskSessionStateChangeTrigger `
               -Namespace Root/Microsoft/Windows/TaskScheduler
    $hcUnlock = New-CimInstance -CimClass $hcCls -ClientOnly
    $hcUnlock.StateChange = 8          # 8 = TASK_SESSION_UNLOCK
    $hcUnlock.Enabled = $true
    $hcUnlock.UserId = $targetUser
    $hcSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
                    -MultipleInstances IgnoreNew `
                    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
    Register-ScheduledTask -TaskName "ggotAIorder-HealthCheck" -Action $hcAction `
        -Trigger @($hcRepeat, $hcUnlock) -Settings $hcSettings -User $targetUser `
        -Description "ggotAIorder health check: restart backend(8765)/RPA Chrome(9222) if down. 60min + on unlock." `
        -Force | Out-Null

    Start-Sleep -Seconds 2
    $t  = Get-ScheduledTask -TaskName "ggotAIorder"
    $tc = Get-ScheduledTask -TaskName "ggotAIorder-RpaChrome"
    $th = Get-ScheduledTask -TaskName "ggotAIorder-HealthCheck"

    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host " SUCCESS: scheduled tasks registered." -ForegroundColor Green
    Write-Host (" Logon user            : " + $t.Principal.UserId)
    Write-Host (" ggotAIorder           State: " + $t.State)
    Write-Host (" ggotAIorder-RpaChrome State: " + $tc.State)
    Write-Host (" ggotAIorder-HealthCheck State: " + $th.State)
    Write-Host " Both auto-start on Windows logon." -ForegroundColor Green
    Write-Host " HealthCheck re-runs every 60 min and on unlock (survives sleep/hibernate)." -ForegroundColor Green
    Write-Host " First time only: log in to FlowerNT3 once in the RPA Chrome window." -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "FAILED:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}
