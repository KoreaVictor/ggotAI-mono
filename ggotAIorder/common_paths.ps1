# common_paths.ps1
# 설치 PC마다 다른 값(설치 폴더·파이썬·크롬·로그인 사용자)을 실행 시점에 찾아낸다.
# install_autostart.ps1 / healthcheck.ps1 / launch_rpa_chrome.ps1 이 dot-source 로 불러 쓴다.
# 출력 메시지는 인코딩 문제 회피를 위해 영문으로 둔다.

# 이 파일은 <설치루트>\ggotAIorder\ 안에 있다. 따라서 설치루트는 그 부모.
$script:GgotOrderDir = $PSScriptRoot
$script:GgotRoot     = Split-Path $PSScriptRoot -Parent

function Get-GgotOrderDir { return $script:GgotOrderDir }
function Get-GgotRoot     { return $script:GgotRoot }

function Resolve-Pythonw {
    <#
      pythonw.exe 를 찾는다. 우선순위:
        1) py 런처가 알려주는 python.exe 의 형제 pythonw.exe
        2) PATH 의 python.exe 의 형제
        3) 표준 설치 위치(전체 사용자 / 사용자별) 글롭
      Microsoft Store 별칭(WindowsApps 아래 0바이트 스텁)은 제외한다.
    #>
    $candidates = @()

    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $out = & $py.Source -3 -c "import sys; print(sys.executable)"
            if ($LASTEXITCODE -eq 0 -and $out) { $candidates += ([string]$out).Trim() }
        } catch { }
    }

    $pyExe = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pyExe) { $candidates += $pyExe.Source }

    $globs = @(
        "$env:ProgramFiles\Python3*\python.exe",
        "${env:ProgramFiles(x86)}\Python3*\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe"
    )
    foreach ($g in $globs) {
        $hits = Get-ChildItem -Path $g -ErrorAction SilentlyContinue | Sort-Object FullName -Descending
        foreach ($h in $hits) { $candidates += $h.FullName }
    }

    foreach ($c in $candidates) {
        if ([string]::IsNullOrWhiteSpace($c)) { continue }
        if ($c -like '*\WindowsApps\*') { continue }   # Store alias stub
        $w = Join-Path (Split-Path $c -Parent) 'pythonw.exe'
        if (Test-Path $w) { return $w }
    }
    return $null
}

function Resolve-Chrome {
    <#
      chrome.exe 를 찾는다. App Paths 레지스트리 -> 표준 설치 위치 순.
    #>
    $regKeys = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe'
    )
    foreach ($k in $regKeys) {
        try {
            $v = (Get-ItemProperty -Path $k -ErrorAction Stop).'(default)'
            if ($v -and (Test-Path $v)) { return $v }
        } catch { }
    }

    $paths = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    foreach ($p in $paths) { if (Test-Path $p) { return $p } }
    return $null
}

function Resolve-InteractiveUser {
    <#
      "지금 콘솔에 로그인해 있는 사용자"를 DOMAIN\user 로 돌려준다.
      관리자 승격 시 $env:USERNAME 은 승격 계정이 되어버리므로 그걸 쓰면 안 된다.
      (표준 계정 사용자가 UAC 에서 별도 관리자 계정을 입력하는 경우 태스크가 엉뚱한
       계정 앞으로 등록되어, 정작 사장님이 로그인해도 안 뜬다.)
    #>
    try {
        $u = (Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop).UserName
        if ($u) { return $u }
    } catch { }

    # 폴백: explorer.exe 소유자
    try {
        $owner = Get-CimInstance -ClassName Win32_Process -Filter "Name='explorer.exe'" -ErrorAction Stop |
                 Select-Object -First 1 |
                 Invoke-CimMethod -MethodName GetOwner -ErrorAction Stop
        if ($owner -and $owner.User) {
            if ($owner.Domain) { return "$($owner.Domain)\$($owner.User)" }
            return $owner.User
        }
    } catch { }

    # 최후 폴백: 현재 프로세스 사용자
    return "$env:USERDOMAIN\$env:USERNAME"
}
