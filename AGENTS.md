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
node run_tests.js --with-net     # 36 套，任何一套失败就非零退出
```

**当前基线：36 套，35 通过。唯一失败的是 `test_report.py`** ——
它拿真实视频抽帧做快照，属**测试数据依赖**（`ValueError: Frame extraction failed`），
与代码质量无关，见 `docs/待办与后续.md`。

> 历史提示：`check_page.js` 曾长期失败（最多 79 条断言），
> 2026-10-16 已清理完毕（1005 条断言全过）。它失败的原因是**断言写的是已经不存在的旧 UI**
> （例如"左栏有独立的检测按钮"，那些按钮早已合并成 `Build tracks`）。
> **教训**：不要看到"既有失败"就跳过 —— 那 79 条一直在掩盖真实的界面回归。

`test_coverage*.py`（视场覆盖栅格 / 矢量化 / 接口层）**依赖 numpy**。
用系统 Python 跑时若没装 numpy，这三套会**明确打印 `[SKIP]` 并算通过**，不会误报失败。
想真正跑到它们，用带 numpy 的解释器：

```bash
PYTHON=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe node run_tests.js
```

**接口层的 HTTP 实测**（会通过接口自建夹具项目、测完删掉）**不在默认套件里**，
因为它需要开发服务在跑。要验的话单独跑：

```bash
python -B test_coverage_http.py      # 服务没在跑会明确 [SKIP]，不算失败
```

另外几件容易踩的：

- 前端是**单文件** `Code/project_geojson_preview.html`，后端是 `Code/project_manager.py`；
  页面 HTML 是**后端启动时读进内存**的 —— 改完必须**重启开发服务**，否则浏览器看不到新界面。
- **重启服务有个陷阱，踩过两次**：用 `Start-Process` 起服务时，
  若**没先确认老进程真的退出了**，新进程会因 8000 端口被占而失败，
  而**老进程继续服务** —— 于是你看到的、测到的全是**旧代码**的结果，
  会得出完全错误的结论（我就因此一度以为"接口过滤失效""页面改动没生效"）。

  **正确做法**（先杀干净 + `-PassThru` + 起来后验证新行为）：
  ```powershell
  Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep 4
  Start-Process -FilePath $py -ArgumentList '-B','project_manager.py' -PassThru `
      -WindowStyle Hidden -RedirectStandardError '<仓库根>\_srv.err'
  Start-Sleep 12
  (Get-Process python).Count          # 必须是 1
  ```
  判据不是"我执行过重启"，而是**"我验过新行为出现了"**。
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

## 双语（i18n）：前后端能力**不一样**，别混淆

| | 后端 `i18n.t()` | 前端 `t()` |
|---|---|---|
| 参数替换 | **支持** `t("{n} points", n=5)` → `'5 points'` | **不支持**，只有 `(key, fallback)` |
| `UI_ZH` 回落 | 有（`UI_ZH` 就在这里） | **没有**——中文表是后端 `all_messages()`
  把 `UI_ZH` 合并进 `messages` 一起下发的 |

所以前端带变量的文案要写成「变量 + `t('固定部分')`」拼接，**别写成 `t('{n} …', {n})`**
（那是后端 API 的形状）。

另外两点：

- **`t()` 的查表是大小写敏感的**。`t('segments')` 与 `t('Segments')` 是两个键。
  但**不要**为了省事在 `UI_ZH` 里加一对只差大小写的键 ——
  `test_i18n.py` 有一条断言明确禁止，理由是真的：JSON 里它们会被
  PowerShell `ConvertFrom-Json` 这类严格解析器当成同一个键而报错（踩过）。
  **正确做法是统一大小写。**
- 句首就是变量的整句（`${n} missing SRT files`）保留英文是**有意的取舍**：
  英文语序切不出干净的固定段，堆一次性数字键不划算。
- 动态渲染的内容要在 `onLangChanged()` 里给出重刷入口 ——
  `applyI18n()` 只替换**静态 DOM** 里带 `data-i18n` 的元素。
  重刷函数**需要数据参数时要先存一份**（例：`frameGalleryLastData`），
  否则切语言时拿不到数据会抛错、那一块就悄悄不换语言（踩过）。

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
