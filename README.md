# 无人机巡查数据 · 轨迹视频地图

把 DJI 无人机的一次次飞行，变成**地图上可点、可播的视频**：点地图上的任意位置，
就能跳到那一刻、那个位置拍的画面。

本机运行，不依赖云服务；天地图底图走本地服务端代理并带磁盘缓存。

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

---

## 目录结构

```
Code/
  project_geojson_preview.html   前端主页面（单文件，含全部界面与逻辑）
  project_manager.py             后端（HTTP 服务 + 遥测解析 + ffmpeg 调用）
  project_manager.html           早期版本页面（保留，不再是主入口）
tests（仓库根目录）
  test_*.js / check_page.js      Node 测试（11 个）
  check_py.py / test_geocode.py / test_report.py   Python 测试（3 个）
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

1. **新建项目** → 填项目名 → 在弹出的文件夹框里选一个数据文件夹
2. 之后**自动跑完整流程**：检测字幕流 → 生成 SRT → 生成 GeoJSON → 加载到地图
   （三个按钮会依次变绿打钩；也可以单独点某一步）
3. **导入数据** → 往当前项目继续加文件夹（同一个文件夹重复导入 = 就地更新）
4. 在「轨迹文件」卡片里点 **加载全部轨迹** → 地图出现多条航迹
5. 地图上点轨迹 → 气泡里点「从点击位置播放」→ 右侧视频从那一刻开始播

文件列表每行有 **加载 / 删除** 两个动作：
**删除只删该视频对应的 GeoJSON（含 3D 版）与 SRT，视频源文件不会被删除。**
删掉之后点「生成 GeoJSON」即可重新生成。

---

## 标记点

在视频画面上右键 → 命名 → 地图上留一个点；这些点**随项目保存**，关掉重开仍在。
右栏下半是标记点列表：

- 每行 `[✓] 名称 纬度 经度 [×]`，表头「全选」带半选态，标题旁写着「已选 n / 共 m」
- 点一行 → 地图定位到该点（16 级）+ 视频跳到那一帧
- 勾选后批量：**删除** / **导出 KML** / **复制经纬度**（制表符表格，直接粘进 Excel）
  / **生成 Word 报告**（先选截图尺寸，报告含可点击目录、汇总表，每点一张视频截图 + 一张地图截图，
  地图截图的底图跟随你当前选的底图）
- 一个都没勾就点批量按钮 → 页面上直接提示先勾选

---

## 测试

```bash
node run_tests.js              # 一次跑完 14 套，任何一套失败就非零退出
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
python -B check_py.py   # 后端静态断言
python -B test_geocode.py
python -B test_report.py # 报告后端（逆地理编码/地图截图/抽帧/docx 结构）
```

共 14 套（另有 1 套需联网的 `test_tdt_tiles.py`，用 `node run_tests.js --with-net` 跑）。
测试路径按脚本所在目录推导，换机器不用改；
**注意 `node a.js b.js` 里 b.js 会被静默忽略**（只有第一个会执行），别那么写。

---

## 开发与交接

**换个人（或换台机器）继续做，需要的东西在这里：**

| 要什么 | 在哪 |
|---|---|
| 项目约定（DSH 会话会自动读取） | **`AGENTS.md`** |
| 实现细节、踩过的坑、验证记录 | `docs/交接说明.md`（最全的一份） |
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
- 断网时 Leaflet 只能走 CDN 兜底：仓库里没有 `vendor/` 副本，
  要离线可把 `leaflet.js` / `leaflet.css` 放进仓库根目录的 `vendor/`

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
