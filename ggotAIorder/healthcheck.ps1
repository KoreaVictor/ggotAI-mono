# healthcheck.ps1
# ggotAIorder 수집엔진/RPA 크롬 자동 점검·복구 스크립트.
# - 백엔드(127.0.0.1:8765)가 죽어 있으면 pythonw run_dev.py 로 재기동.
# - RPA 전용 Chrome(127.0.0.1:9222)은 launch_rpa_chrome.ps1(멱등)로 점검·기동.
# - 60분 주기 + 워크스테이션 잠금해제 시 트리거로 실행됨(install_autostart.ps1).
#   로그온 트리거가 안 걸리는 경우(절전/최대절전 복귀 등)에도 항상 살아 있게 한다.
# 출력 메시지는 인코딩 문제 회피를 위해 영문으로 둔다.
$ErrorActionPreference = "Stop"

$pythonw      = "C:\Program Files\Python313\pythonw.exe"
$backend      = "C:\ggotAI\ggotAIorder\backend\run_dev.py"
$chromeScript = "C:\ggotAI\ggotAIorder\launch_rpa_chrome.ps1"
$backendPort  = 8765

function Test-PortAlive([int]$port) {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    return [bool]$c
}

# --- Backend (collector engine) ---------------------------------------------
if (Test-PortAlive $backendPort) {
    Write-Host ("OK: backend already listening on 127.0.0.1:{0}." -f $backendPort) -ForegroundColor Yellow
} else {
    if (-not (Test-Path $pythonw)) { Write-Host ("FAILED: pythonw not found: {0}" -f $pythonw) -ForegroundColor Red; exit 1 }
    if (-not (Test-Path $backend)) { Write-Host ("FAILED: run_dev.py not found: {0}" -f $backend) -ForegroundColor Red; exit 1 }
    Start-Process -FilePath $pythonw -ArgumentList $backend -WindowStyle Hidden | Out-Null
    Write-Host ("RESTARTED: backend (pythonw run_dev.py) on port {0}." -f $backendPort) -ForegroundColor Green
}

# --- RPA dedicated Chrome (CDP 9222) ----------------------------------------
# launch_rpa_chrome.ps1 is idempotent: it skips if 9222 already responds.
if (Test-Path $chromeScript) {
    & $chromeScript
} else {
    Write-Host ("WARN: launch_rpa_chrome.ps1 not found: {0}" -f $chromeScript) -ForegroundColor Red
}
