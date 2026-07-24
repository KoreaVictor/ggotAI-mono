# launch_rpa_chrome.ps1
# RPA 전용 Chrome 기동 스크립트 (CDP 디버그 포트 + 전용 프로필).
# - FlowerNt3Automator 가 http://127.0.0.1:9222 (CDP) 로 붙어서 주문폼을 조작합니다.
# - 전용 user-data-dir 에 로그인 세션이 유지되므로, 최초 1회만 수동 로그인하면 됩니다.
# - 이미 9222 가 응답하면(=Chrome 기동 중) 중복 실행하지 않습니다(idempotent).
# 출력 메시지는 인코딩 문제 회피를 위해 영문으로 둡니다.
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot 'common_paths.ps1')

$chrome      = Resolve-Chrome
$profileDir  = Join-Path (Get-GgotRoot) 'rpa_profile'
$debugPort   = 9222
# 사전기동 시 열 랜딩 URL(FlowerNT3). 실제 주문 시엔 백엔드가 DB의 rpa_program_url로 구동한다.
$landingUrl  = "https://www.flowernt.com/main.asp?checkintro=Y"

try {
    # This Chrome exists only for FlowerNT (CDP automation). Shops on RoseWeb or
    # any other program do not need it - launching it there just puts a stray
    # window on the owner's screen every logon. Ask the backend which program
    # this shop uses; "unknown" (DB unreachable AND no cached answer) launches
    # anyway, keeping the behaviour existing installs already have.
    $programType = 'unknown'
    $typeScript  = Join-Path $PSScriptRoot 'backend\scripts\rpa_program_type.py'
    $python      = Resolve-Python
    if ($python -and (Test-Path $typeScript)) {
        try {
            $out = & $python $typeScript
            if ($LASTEXITCODE -eq 0 -and $out) { $programType = ([string]$out).Trim() }
        } catch {
            Write-Host ("WARN: program type lookup failed - assuming unknown. {0}" -f $_.Exception.Message) -ForegroundColor Yellow
        }
    }

    if ($programType -ne 'flowernt' -and $programType -ne 'unknown') {
        Write-Host ("Shop program is '{0}' - FlowerNT Chrome not needed, skip launch." -f $programType) -ForegroundColor Yellow
        exit 0
    }

    if (-not $chrome) { throw "chrome.exe not found (App Paths / Program Files / LocalAppData)." }
    if (-not (Test-Path $profileDir)) { New-Item -ItemType Directory -Force -Path $profileDir | Out-Null }

    # Already up? CDP endpoint responds on 127.0.0.1 (localhost->::1 is refused).
    $alive = $false
    try {
        $resp = Invoke-WebRequest -Uri ("http://127.0.0.1:{0}/json/version" -f $debugPort) `
                    -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) { $alive = $true }
    } catch { $alive = $false }

    if ($alive) {
        Write-Host ("RPA Chrome already running on 127.0.0.1:{0} - skip launch." -f $debugPort) -ForegroundColor Yellow
        exit 0
    }

    $chromeArgs = @(
        ("--remote-debugging-port={0}" -f $debugPort),
        ('--user-data-dir="{0}"' -f $profileDir),
        "--no-first-run",
        "--no-default-browser-check",
        $landingUrl
    )
    Start-Process -FilePath $chrome -ArgumentList $chromeArgs | Out-Null

    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host (" SUCCESS: RPA Chrome launched (CDP 127.0.0.1:{0})." -f $debugPort) -ForegroundColor Green
    Write-Host (" Profile: {0}" -f $profileDir)
    Write-Host " First time only: log in to FlowerNT3 once; the session persists." -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "FAILED:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
