# SRT 格式与机型字段对照（含可用性检查）

## 一、这份对照的用途

回答两个问题：

1. 别的机型能不能接进来（我们要解析哪种 SRT 方言）；
2. **接进来之后，我们需要的字段它到底有没有** —— 缺字段的机型，功能会降级，
   必须在界面上说清楚，而不是算出一个看着对、其实错的结果。

## 二、数据来源与许可

格式目录来自 [CallMarcus/dji-drone-metadata-embedder](https://github.com/CallMarcus/dji-drone-metadata-embedder) 的 [docs/SRT_FORMATS.md](https://github.com/CallMarcus/dji-drone-metadata-embedder/blob/master/docs/SRT_FORMATS.md)，
该仓库为 **MIT 许可**（LICENSE 已核对），允许在注明出处的前提下取用。
原始快照留在 `docs/_srt_formats_raw.md`（仅本次对照用，可不进仓库）。

> 我们**只取用它的格式说明当参考**，没有引入它的代码；解析仍由我们自己的 `Code/project_manager.py` 完成。

## 三、机型 → SRT 方言

| 机型 | 格式 | 说明 |
|---|---|---|
| DJI Mini 3 Pro | Format 1 | Bracketed key-value pairs |
| DJI Mini 4 Pro | Format 1 | Bracketed key-value pairs |
| DJI Mavic 3 | Format 3 | Comprehensive with HTML tags |
| DJI Air 2S | Format 3 | Comprehensive with HTML tags |
| DJI Air 3 | Format 3 | Comprehensive with HTML tags |
| DJI Mini 5 Pro | Format 3b | FrameCnt + decimal fnum/focal_len |
| DJI Avata 360 | Format 3b | FrameCnt + decimal units; `.OSV`/`.LRF` video, `pp_*` stabilization fields |
| DJI Neo 2 | Format 3b | FrameCnt + decimal units; `pp_*` stabilization fields; MP4 carries `djmd`/`dbgi` streams; audio recorded to a **separate same-basename `.m4a`** (see `--audio-sidecar`) |
| DJI Air 3S | Format 3b | FrameCnt + decimal units; `color_md: hlg`; MP4 carries `djmd`/`dbgi` streams |
| DJI Mavic 4 Pro | Format 3b | FrameCnt + decimal units; `[ct: N, tint: N]`; MP4 and `.LRF` carry `djmd`/`dbgi` streams (gimbal via bundled ExifTool config) |
| DJI Mavic Pro | Format 2 | GPS function format |
| DJI Phantom 4 | Format 2 | GPS function format |
| DJI Avata 2 | Format 2 | GPS function format with BAROMETER data |
| DJI Matrice 300 RTK | Format 2b | Legacy-with-unit (`0.0M` altitude) |
| DJI Phantom 4 RTK / P4P | Format 2c | P4 RTK compact single-line |
| DJI Mavic Air 2 | Format 1 | Bracketed key-value pairs |
| DJI FPV | Format 1 | May include additional flight data |

## 四、我们需要的字段 ← 哪些格式真的带

| 我们要的字段 | 用在哪 | 必要性 |
|---|---|---|
| 经纬度 | 轨迹、地图定位、画面取点的基准 | **必需** |
| 相对高度 rel_alt | 视场框大小、取点解算 | **必需** |
| 云台俯仰 gb_pitch / pitch | 视场框的远近、取点射线 | **必需** |
| 偏航/机头朝向 yaw | 视场框朝向、飞机箭头 | **必需**（缺了只能用航迹方向近似） |
| 焦距 focal_len / 变焦 zoom | 视场框的宽窄（FOV） | **必需**（缺了只能按默认广角估） |
| 光圈/快门/ISO | 报告里的相机参数表 | 可选 |

上游目录里明确列出的字段归属（原文口径）：

| 字段 | 哪些格式携带 | 作用 |
|---|---|---|
| `rel_alt` | Format 1, Format 3, Format 3b | Height above ground (AGL). Preferred over `abs_alt` subtraction. |
| `focal_len` | Format 3, Format 3b | 35mm-equivalent focal length. Determines field of view. Written as integer × 10 in Format 3 (`240` = 24 mm) or literal decimal in Format 3b (`24.00` = 24 mm). Overrides the `--model` table when present. |
| `gb_yaw`, `gb_pitch` | Format 3b — **Avata 360 variant only** | Gimbal yaw rotates the footprint rectangle to match where the lens points; gimbal pitch gates out strongly oblique frames (>~30° off nadir). Other Format 3b models and all earlier formats do not carry these fields — nadir is assumed and heading falls back to course over ground. |

## 五、结论：按机型看「够不够我们用」

| 机型（格式） | 经纬度 | 相对高度 | 云台俯仰 | 焦距/变焦 | 结论 |
|---|---|---|---|---|---|
| Matrice 4T（**我们现在用的**） | ✓ | ✓ | ✓ `gb_pitch` | ✓ `zoomfactor` | 齐 —— 视场框与取点都可用 |
| Mavic 3 / Air 2S / Air 3（Format 3） | ✓ | ✓ | ✓ | ✓ `focal_len` | 齐 |
| Mini 5 Pro / Air 3S / Mavic 4 Pro / Neo 2（Format 3b） | ✓ | ✓ | 部分（云台角度只有 Avata 360 变体明确列出） | ✓ | 取决于云台字段；**没有云台角度时视场框只能按航向近似** |
| Mini 3 Pro / Mini 4 Pro / Mavic Air 2 / FPV（Format 1） | ✓ | ✓ | ✗ 未列出 | **✗ 未列出 `focal_len`** | **会降级**：视场框宽窄只能按默认广角估，取点精度受影响 |
| Mavic Pro / Phantom 4 / Avata 2（Format 2） | ✓ | 部分（Avata 2 有 BAROMETER） | ✗ | ✗ | 只能做轨迹与跳转，视场/取点不可靠 |
| Matrice 300 RTK（Format 2b） | ✓ | ✓（带单位） | ✗ | ✗ | 同上 |
| Phantom 4 RTK / P4P（Format 2c） | ✓ | ✓ | 部分（F.PRY 里有姿态） | ✗ | 姿态可从 `F.PRY` 取，焦距仍缺 |

**最要紧的两条**：

1. `focal_len`（焦距）**只有 Format 3 / 3b 有** —— 也就是说 **Mini 3 Pro / Mini 4 Pro 这类
   Format 1 机型拿不到焦距**，视场框只能按默认广角估，画面取点也会有偏差。
2. 云台 yaw/pitch **只有 Format 3b 的 Avata 360 变体被明确列出**；其余机型要么写在
   别的字段里、要么根本没有 —— **必须先拿真实样片验证**，不能照文档假设。

> 注意：**上游目录里没有 Matrice 4T** —— 我们现在能跑，是因为我们自己按 M4T 的
> 实际 SRT 写了解析。所以这份目录对 M4T 没有参考价值，对**新机型**才有。

## 六、建议的落地方式

- **不照搬代码**：把这份目录当作「格式识别 + 能力清单」的参考；
- 给解析结果加**字段可用性标记**（例如 `has_focal / has_gimbal`），
  界面上直接说清「该机型缺焦距/云台角，视场框与取点为估算」；
- 新机型接入前，先要一段**原始 SRT 样片**做验证 —— 这也是上游仓库的同一做法：
  没有样片就不要声称支持。

