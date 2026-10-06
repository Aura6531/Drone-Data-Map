# ============================================================
#  一键打包：目录版程序 -> 安装程序 -> 分发 zip
#
#  在仓库根目录执行：  powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1
#
#  前置（脚本会自己检查并给出提示）：
#    * packaging\build_libs  —— PyInstaller（python packaging\fetch_build_libs.py）
#    * packaging\payload     —— ffmpeg + Leaflet（python packaging\fetch_deps.py）
#
#  产物：
#    packaging\dist\UAVMap\                                  目录版程序（拷走即可运行）
#    packaging\dist-installer-release\...安装程序\             安装程序（exe + payload.zip）
#    packaging\installer\无人机巡查数据地图_安装程序.zip        发给别人的那一个文件
#    packaging\installer\无人机巡查数据地图_安装程序.exe        （装了 Inno Setup 时的备选方案）
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

$env:PYTHONPATH = Join-Path $root 'packaging\build_libs'
Remove-Item Env:\UAVMAP_CONSOLE -ErrorAction SilentlyContinue
Remove-Item Env:\UAVMAP_PAYLOAD_SOURCE -ErrorAction SilentlyContinue

# ---------- 1) 打应用（目录版） ----------
Step "1/4 PyInstaller：目录版程序"
python -B -m PyInstaller packaging\UAVMap.spec --noconfirm --clean `
    --distpath packaging\dist --workpath packaging\build

$exe = 'packaging\dist\UAVMap\UAVMap.exe'
if (-not (Test-Path $exe)) { throw "没生成 $exe，打包失败" }
Write-Host ("  生成 {0}（{1:N1} MB）" -f $exe, ((Get-Item $exe).Length / 1MB)) -ForegroundColor Green

# ---------- 2) 做 LZMA 载荷 ----------
Step "2/4 压缩载荷（LZMA）"
python -B packaging\make_payload_zip.py

# ---------- 3) 打安装程序 ----------
Step "3/4 PyInstaller：安装程序"
$env:UAVMAP_INSTALLER_ONEFOLDER = '1'
python -B -m PyInstaller packaging\UAVMapInstaller.spec --noconfirm --clean `
    --distpath packaging\dist-installer-release --workpath packaging\build-installer-release
Remove-Item Env:\UAVMAP_INSTALLER_ONEFOLDER -ErrorAction SilentlyContinue

$installerDir = 'packaging\dist-installer-release\无人机巡查数据地图_安装程序'
if (-not (Test-Path $installerDir)) { throw "没生成安装程序目录 $installerDir" }

# ---------- 4) 打成分发 zip（发给别人的就是这一个文件） ----------
Step "4/4 分发 zip"
New-Item -ItemType Directory -Force -Path packaging\installer | Out-Null
$zip = 'packaging\installer\无人机巡查数据地图_安装程序.zip'
Remove-Item $zip -ErrorAction SilentlyContinue
Compress-Archive -Path "$installerDir\*" -DestinationPath $zip -CompressionLevel Optimal

Write-Host ("  {0}  {1:N1} MB" -f $zip, ((Get-Item $zip).Length / 1MB)) -ForegroundColor Green

# ---------- 可选：Inno Setup 版本 ----------
Step "可选：Inno Setup 安装包"

$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($iscc) {
    & $iscc 'packaging\UAVMap.iss'
    Get-ChildItem packaging\installer -Filter *.exe -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Host ("  {0}  {1:N1} MB" -f $_.Name, ($_.Length / 1MB)) -ForegroundColor Green }
} else {
    Write-Host "  没装 Inno Setup 6，跳过（默认的安装程序已经好了，见上面的 zip）" -ForegroundColor Yellow
}

Step "完成"
Get-ChildItem packaging\installer -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host ("  {0}  {1:N1} MB" -f $_.Name, ($_.Length / 1MB)) -ForegroundColor Green }
