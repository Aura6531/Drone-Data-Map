# 项目约定（给 DSH 会话 / 接手的开发者）

**无人机巡查数据地图** —— 把 DJI 无人机的遥测与视频对齐的本地小工具。
功能与用法看 `README.md`；实现细节、踩过的坑、验证记录看 `docs/交接说明.md`（那份最全）。

---

## 跑起来

```bash
cd Code
python -B project_manager.py          # 后端，绑定 127.0.0.1:8000
# 浏览器打开 http://127.0.0.1:8000/project_geojson_preview.html
```

依赖：**Python 3.10+**、**ffmpeg**（抽帧/转码）、可选 **Node**（跑测试）。
Node 没装也不要紧 —— DSH 自带一个运行时，可以直接用它跑测试：

```
%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe
```

ffmpeg 没有时，仓库里这条命令会连它一起下下来（约 100MB）：

```bash
python packaging/fetch_deps.py
```

---

## 验一遍（改完必须做）

```bash
node run_tests.js          # 15 套，任何一套失败就非零退出
```

**任何改动都要让它保持 15/15** —— 其中 `test_report.py` 那套里 3 条失败是
测试数据依赖（见 `docs/待办与后续.md`），换了 `Data/` 之后数会变。

另外几件容易踩的：

- 前端是**单文件** `Code/project_geojson_preview.html`，后端是 `Code/project_manager.py`；
  页面 HTML 是**后端启动时读进内存**的 —— 改完必须**重启开发服务**，否则浏览器看不到新界面。
- `node a.js b.js` 里第二个文件会被静默忽略（只跑第一个），别那样写。
- `check_page.js` 里 `html` 是整页、`body` 只是 `<script>` 段：断言 HTML 元素要用 `html`。

---

## 干活规矩

1. **不要顺手重打安装包** —— 用户明确要求「等他喊了再打」。日常改动只做三件事：
   改代码 → 跑测试 → **重启开发服务**（用户 Ctrl+F5 就能验）。重打一次要 3~4 分钟，
   而且会让他手上那份 zip 作废。
2. 回复用**中文**；结论要有证据（测试输出、实测数值、文件时间戳），
   没验证过的就说「没验证」，不确定就说不确定。
3. 一次改动一次提交；提交信息写**为什么**，不只写改了什么。

---

## 提交与密钥

- `.gitignore` 用**白名单**：`packaging/` 下只跟踪脚本/配置/图标，
  `dist`、`build`、`payload`、`installer`、运行期缓存（`geocode_cache` 等）一律不进仓库。
- **天地图 key 是密钥**：`Code/tianditu_key.txt` 与根目录 `tianditu_key.txt` 都不能提交
  （已在 `.gitignore` 里，别去动这两条规则）。
- `Data/`（原始视频）、`Project/`（项目状态）也不进仓库。

---

## 打包（只在用户要求时做）

```powershell
python packaging/fetch_build_libs.py     # 首次：下 PyInstaller（绕开 pip，见下）
python packaging/fetch_deps.py           # 首次：下 ffmpeg + Leaflet
powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1
# 产物：packaging\installer\无人机巡查数据地图_安装程序.zip
```

- 为什么不用 pip：这台机器上 `pip install` 写 `.whl.metadata` 会稳定报 `PermissionError`
  （实时扫描锁文件），所以 `fetch_build_libs.py` 直接下 wheel 当 zip 解。
- 载荷用 LZMA 压（150MB → 46.6MB），并且**先写临时文件再 `os.replace` 原子替换** ——
  构建与测试并行时，读的一方曾拿到写了一半的 zip。
- `packaging/UAVMap.iss` 是 Inno Setup 备选方案；没装 ISCC 时脚本会跳过它。

---

## 本机环境的坑（Windows + DSH）

- **PowerShell 5.1 按 GBK 读无 BOM 的 UTF-8 `.ps1`** → 中文会被读坏、脚本解析失败。
  `build_installer.ps1` 必须存成 **UTF-8 with BOM**；`.bat` 里干脆只写 ASCII。
- 用**裸 Python 进程写 `Code/` 下的文件偶尔报 PermissionError**（实时扫描锁文件）——
  改用编辑工具写，或退避重试。
- 这个 DSH 会话**没有交互桌面**：Chrome、托盘窗口、GUI 安装程序都起不来。
  GUI 相关只能用无头脚本验证（例：`python smoke_installer_wizard.py` 程序化点击安装向导），
  其余交给用户在桌面上确认。
- `%TEMP%` 可能不可写：临时目录一律放**工作区内**。
- 窗口版（`console=False`）打包后 **`sys.stdout` / `sys.stderr` 是 `None`** ——
  任何 `.reconfigure()`、`.write()` 之前都要判空。
