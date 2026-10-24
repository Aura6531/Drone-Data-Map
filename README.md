# 无人机巡查数据 · 轨迹视频地图

把 DJI 无人机的一次次飞行，变成**地图上可点、可播的视频**：点地图上的任意位置，
就能跳到那一刻、那个位置拍的画面。

本机运行，不依赖云服务；天地图底图走本地服务端代理并带磁盘缓存。

> 界面为**英文**（主页面标题 `Fly Data Map`）。选它是因为术语（可见光/热成像、
> 俯仰角、视场框）在英文里更短、更少歧义，截图贴进报告和文档也更通用。

---

## ▶ 讲解视频

15 分钟完整演示（从导入数据到出 Word 报告）：

**▶ [YouTube](https://youtu.be/7mKu2h0WP0g)**　　**▶ [b 站（Bilibili）](https://www.bilibili.com/video/BV1nhpu6pE3j/)**

- YouTube：<https://youtu.be/7mKu2h0WP0g>
- b 站：<https://www.bilibili.com/video/BV1nhpu6pE3j/>

---

## 它解决什么问题

巡查录像的痛点是"**找到了地点，找不到画面对应的那一秒**"。

这个工具把无人机的遥测（GPS / 高度 / 云台朝向）与视频对齐：

- 地图上画出每一段航迹，并实时投影出**相机视场框**（画面在地面上的覆盖范围）
- 点地图任意位置 → 播放**那一刻**对应位置的视频
- 地图上点轨迹 → 视频跳到该点；视频播放 → 地图上的飞机箭头同步移动
- 视频画面上右键 → 算出该像素对应的**地面坐标**，命名后在地图上留一个标记点
- 标记点可批量**导出 KML**、复制经纬度、**生成 Word 报告**（每点一张视频截图 + 一张地图截图）
- 视频上还能**导出当前时刻前后各 5 秒**（共 10 秒、1080p）的片段，方便转发
- **照片也能上图**：可见光 / 热成像成对的一组照片只画一个点，带「位置是否实测」角标，
  点照片可跳到对应视频时刻

---

## 目录结构

```
Code/
  project_geojson_preview.html   主页面（单文件，含全部界面与逻辑）—— Fly Data Map
  project_manager.py             后端（HTTP 服务 + 遥测解析 + ffmpeg 调用）
  project_import.html            导入数据页（Import Data）
  project_media.html             媒体检查页（Media Inspector）
  project_video_inspector.html   视频结构检查页（Video Inspector）
  project_geo3d_preview.html     三维轨迹预览页（3D Track Preview）
  project_manager.html           早期版本页面（保留，不再是主入口）
tests（仓库根目录）
  test_*.js + check_page.js      Node 测试（12 套）
  check_py.py / test_geocode.py / test_report.py   Python 测试（3 套）
vendor/                           Leaflet 本地副本（离线时用，见「已知限制」）
packaging/                        打包脚本（PyInstaller + 自带向导的安装程序）
AGENTS.md                         项目约定 —— 装了 DSH 的人在此目录开会话会自动读到
Data/                            原始视频与派生的 SRT / GeoJSON（不进仓库）
Project/                         项目定义 project.json（本地状态，不进仓库）
```

---

## 运行

```bash
# 1. 启动后端（工作目录必须是 Code/，绑定 127.0.0.1:8000）
cd Code
python -B project_manager.py

# 2. 浏览器打开
http://127.0.0.1:8000/project_geojson_preview.html
```

### 依赖

| 依赖 | 用途 | 必需 |
|---|---|---|
| Python 3.10+ | 后端 | ✓ |
| FFmpeg | 从 MP4 抽取遥测字幕流、转码代理片段 | ✓ |
| 天地图 API Key | 底图瓦片（写在 `Code/tianditu_key.txt`，**不进仓库**）| 可选，缺省可切 OpenStreetMap |

---

## 使用流程（左栏从上到下）

1. **New project** → 填项目名 → 在弹出的文件夹框里选一个数据文件夹
2. 之后**自动跑完整流程**（也可以随时点 **Build tracks** 手动重跑）：
   检测字幕流 → 生成 SRT → 生成 GeoJSON → 加载到地图

   > 这三步**合并成了一个按钮**，因为 GeoJSON 必须读同名 `.srt`（后端找不到就直接报错），
   > 中间没有"只生成 SRT"这种可跳过的状态。进度写在按钮下方的小字里：
   > 先给检测结果（几个视频、几个带字幕流），再逐条报 `Creating SRT files (1/5)`、
   > `Creating GeoJSON tracks (1/5)`，最后汇总。

3. **Import data** → 往当前项目继续加文件夹（同一个文件夹重复导入 = 就地更新）
4. 在「Tracks」卡片里点 **Load all tracks** → 地图出现多条航迹
5. 地图上点轨迹 → 气泡里点 **Play from here** → 右侧视频从那一刻开始播

文件列表每行有 **Load / Delete** 两个动作：
**Delete 只删该视频对应的 GeoJSON（含 3D 版）与 SRT，视频源文件不会被删除。**
删掉之后点 **Build tracks** 即可重新生成。

---

## 标记点

在视频画面上右键 → 命名 → 地图上留一个点；这些点**随项目保存**，关掉重开仍在。
右栏下半是标记点列表（Markers）：

- 每行 `[✓] 名称 纬度 经度 [×]`，表头 **Select all** 带半选态，标题旁写着「已选 n / 共 m」
- 点一行 → 地图定位到该点（16 级）+ 视频跳到那一帧
- 勾选后批量：**Delete** / **Export KML** / **Copy lat/lng**（制表符表格，直接粘进 Excel）
  / **Make Word report**（先选截图尺寸，报告含可点击目录、汇总表，每点一张视频截图 + 一张地图截图，
  地图截图的底图跟随你当前选的底图）
- 一个都没勾就点批量按钮 → 页面上直接提示先勾选

---

## 测试

```bash
node run_tests.js              # 一次跑完 15 套（12 Node + 3 Python），任何一套失败就非零退出
node run_tests.js --with-net   # 额外跑需要联网的天地图瓦片检查
node run_tests.js --list       # 只列清单
```

逐套跑（与上面等价）：

```bash
node check_page.js      # 页面静态断言（最全的一套）
node test_boot.js       # 页面启动执行
node test_sync.js       # 地图 / 视频同步路径
node test_telemetry.js  # 遥测换算
node test_footprint.js  # 相机视场几何
node test_filelist.js   # 文件列表
node test_drone.js      # 飞机箭头朝向
node test_follow.js     # 地图跟随
node test_nearest.js    # 按位置检索飞行视频（用真实 GeoJSON）
node test_ab.js         # A+B 检索的数学基础（正/反投影互逆）
node test_markers.js    # 标记点列表（排序/勾选/删除/KML/复制/跳转）
node test_photos.js     # 照片图层（一组一点 / ⚠ 角标 / 展示区 / 点照片跳视频）
python -B check_py.py   # 后端静态断言
python -B test_geocode.py
python -B test_report.py # 报告后端（逆地理编码/地图截图/抽帧/docx 结构）
```

共 15 套（另有 1 套需联网的 `test_tdt_tiles.py`，用 `node run_tests.js --with-net` 跑）。
测试路径按脚本所在目录推导，换机器不用改；
**注意 `node a.js b.js` 里 b.js 会被静默忽略**（只有第一个会执行），别那么写。

### 当前的失败项（已知，非代码缺陷）

跑 `run_tests.js` 会看到 **13/15 通过**，两套失败都**不是功能问题**：

| 套件 | 失败原因 |
|---|---|
| `check_page.js` | 约 40 条断言的**判据里还写着旧中文标签**（界面改英文后过期）。页面本身正常，其余 11 套也不依赖这些中文 |
| `test_report.py` | 2 条 A4 断言把输出宽度写死成 2480 px（测试数据是 1080p 素材）。见 `docs/待办与后续.md` |

`--with-net` 的 `test_tdt_tiles.py` 需要有效的天地图 key，没有 key 时会失败，属预期。

---

## 开发与交接

**换个人（或换台机器）继续做，需要的东西在这里：**

| 要什么 | 在哪 |
|---|---|
| 项目约定（DSH 会话会自动读取） | **`AGENTS.md`** |
| 实现细节、踩过的坑、验证记录 | `docs/交接说明.md`（最全的一份） |
| 左栏（三段化 / 「已加载」面板）的现状与坑 | docs/左栏三段化_已加载面板.md |
| 只想知道怎么用 | 本文档 + `docs/使用说明.md` |
| 打安装包 | `packaging\build_installer.ps1`（首次先跑 `fetch_build_libs.py` / `fetch_deps.py`） |

**关于 DSH**：装了 DeepSeek Harness 的人，只要在这个目录里开一个会话，
DSH 就会自动加载 `AGENTS.md`（它加载「用户全局 `~/.dsh/AGENTS.md`」+「从项目根到工作目录
这一路上的 `AGENTS.md`」）。所以约定要写在文件里，而不是只留在某次对话里。
注意它只在**会话第一次请求**时加载 —— 把仓库给对方之后，让他**新开一个会话**。

**不进仓库的东西**（接手的人要自己准备）：

- `Code/tianditu_key.txt` —— 天地图密钥，申请办法见 `docs/天地图key申请说明.md`；
  不填也能用，底图会退回 OpenStreetMap。
- `Data/`（原始视频）、`Project/`（项目状态）、`packaging/` 下的打包产物。
- **ffmpeg** 需要另备：装到 PATH，或跑 `python packaging/fetch_deps.py` 下到 `packaging/payload/ffmpeg/`。
- 跑测试需要 Node；没装可以用 DSH 自带的：
  `%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe`

---

## 数据约定（重要）

- 只处理 **DJI 标准命名的素材**：`DJI_YYYYMMDDHHMMSS_NNNN_X`
  （`_V` 可见光 / `_S` 可见光小画幅 / `_T` 热成像）
- **请始终导入原片，不要用剪辑软件重新导出**：重编码会丢掉内嵌的遥测字幕流，
  文件也可能被改名，导致遥测、SRT、GeoJSON 全部对不上。
- 若必须剪辑：先备份 `.srt`，剪完保持原文件名，并让 `.srt` 与视频同名放在同一目录 ——
  生成 GeoJSON 读的是这个同名 `.srt` 文件，**不依赖 MP4 里是否还有字幕流**。

---

## 已知限制

- 相机视场框与「画面取点」都基于**平地假设**：俯角大（近处）很准，
  接近平视时会明显偏（实测 1° 俯仰误差 ≈ 112 m）
- 高度是**相对起飞点**的相对高度
- 全屏反复切换后地图小窗尺寸需要重算（当前加了硬上限兜底）
- **视场框的远端是"模糊边界"**：低俯角时画面上边缘的真实落点会非常远
  （实测 97 m 高、俯仰 −18.7°、24 mm 广角时上边缘约 1079 m，而画面中心才 287 m），
  所以按「每米高度 12 倍」截断、低空保底 600 m。被截的地方不是"镜头只看到那么远"
- **视频编码**：素材是 HEVC 时浏览器放不了，会走 ffmpeg 转码代理（`video_proxy/`，有缓存）；
  素材是 H.264 时直接原片播放，不用转码

### 离线 / 内网

Leaflet 已在仓库里带了一份本地副本（`vendor/`，含 5 个 marker / layers 图标），
页面会优先加载它，所以**底图和 Leaflet 都不依赖 CDN**。
真正的离线瓶颈是**地图瓦片**：默认走天地图（需要 key 和外网），
内网部署要另配可访问的瓦片源。

---

## 许可

**个人使用许可 —— 禁止商业使用**（全文见 [LICENSE](LICENSE)，中英对照）。

**可以用**：个人学习、研究、业余项目、自用工具；也可以自己改。
**不可以**：任何商业用途 —— 在营利性公司/机构内部使用、为客户交付或提供有偿服务、
做成在线/托管服务、与硬件或服务捆绑销售、转售或再分发；也不得去掉版权声明。

> 这不是 OSI 认可的开源许可（GitHub 会把本仓库标为 *proprietary*），
> 需商业授权请先联系作者取得书面许可。

第三方组件遵循各自的许可，与本许可无关：**FFmpeg**（运行期调用，GPL 构建）、
**Leaflet**（地图库，BSD-2-Clause）、**天地图**（底图瓦片，遵循天地图服务条款，需自备 key）。
