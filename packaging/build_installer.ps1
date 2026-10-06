# ============================================================
#  一键打包：PyInstaller 目录版 -> Inno Setup 安装包
#
#  在仓库根目录执行：  powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1
#
#  前置（脚本会自己检查并给出提示）：
#    * packaging\build_libs   —— PyInstaller/pystray（用 python packaging\fetch_build_libs.py 准备）
#    * packaging\payload      —— ffmpeg + Leaflet（用 python packaging\fetch_deps.py 准备）
#    * Inno Setup 6（ISCC.exe）—— 编译安装包用；只打 exe 不需要它
#
#  产物：
#    packaging\dist\UAVMap\              目录版程序（拷走即可运行）
#    packaging\installer\*安装程序.exe    安装包
# ============================================================

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

function Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }

# ---------- 前置检查 ----------
Step "检查打包依赖"

if (-not (Test-Path 'packaging\build_libs\PyInstaller')) {
    Write-Host "缺 packaging\build_libs，先跑：python packaging\fetch_build_libs.py" -ForegroundColor Yellow
    python -B packaging\fetch_build_libs.py
}

if (-not (Test-Path 'packaging\payload\ffmpeg\ffmpeg.exe')) {
    Write-Host "缺 packaging\payload\ffmpeg，先跑：python packaging\fetch_deps.py" -ForegroundColor Yellow
    python -B packaging\fetch_deps.py
}

# ---------- 1) 打 exe ----------
Step "PyInstaller：生成目录版程序"

$env:PYTHONPATH = Join-Path $root 'packaging\build_libs'
Remove-Item Env:\UAVMAP_CONSOLE -ErrorAction SilentlyContinue

python -B -m PyInstaller packaging\UAVMap.spec --noconfirm --clean `
    --distpath packaging\dist --workpath packaging\build

$exe = 'packaging\dist\UAVMap\UAVMap.exe'
if (-not (Test-Path $exe)) { throw "没生成 $exe，打包失败" }
Write-Host ("  生成 {0}（{1:N1} MB）" -f $exe, ((Get-Item $exe).Length / 1MB)) -ForegroundColor Green

# ---------- 2) 编译安装包 ----------
Step "Inno Setup：编译安装包"

$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Host "没找到 Inno Setup 6（ISCC.exe）。" -ForegroundColor Yellow
    Write-Host "  * 目录版程序已经好了，可以直接拷走用：packaging\dist\UAVMap\"
    Write-Host "  * 想生成安装包：装一个 Inno Setup 6（https://jrsoftware.org/isdl.php），再重跑本脚本"
    exit 0
}

& $iscc 'packaging\UAVMap.iss'

Step "完成"
Get-ChildItem packaging\installer -Filter *.exe -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host ("  {0}  {1:N1} MB" -f $_.Name, ($_.Length / 1MB)) -ForegroundColor Green }
