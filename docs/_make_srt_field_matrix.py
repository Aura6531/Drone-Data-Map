"""对照 dji-drone-metadata-embedder 的 SRT 目录，生成我们的机型字段对照文档。

数据来源（MIT 许可，注明出处）：
  https://github.com/CallMarcus/dji-drone-metadata-embedder
  docs/SRT_FORMATS.md（已抓到 docs/_srt_formats_raw.md）

产出：docs/SRT格式与机型字段对照.md
"""

import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

RAW = pathlib.Path("docs/_srt_formats_raw.md")
OUT = pathlib.Path("docs/SRT格式与机型字段对照.md")

text = RAW.read_text(encoding="utf-8")

# ---- 机型 -> 格式 ----
models = []
for line in text.splitlines():
    cells = [c.strip() for c in line.strip().strip("|").split("|")]

    if len(cells) >= 3 and cells[0].startswith("DJI") and cells[1].startswith("Format"):
        models.append((cells[0], cells[1], cells[2]))

# ---- 字段 -> 哪些格式携带 ----
field_rows = []
for line in text.splitlines():
    cells = [c.strip() for c in line.strip().strip("|").split("|")]

    if len(cells) >= 3 and cells[0].startswith("`"):
        field_rows.append((cells[0].strip("`"), cells[1], cells[2]))

# ---- 各 Format 小节里出现的键 ----
format_keys = {}
for m in re.finditer(r"### (Format[^\n]*)\n(.*?)(?=\n#{2,3} |\Z)", text, re.S):
    head, body = m.group(1).strip(), m.group(2)
    keys = sorted(set(re.findall(r"\[([A-Za-z_][A-Za-z0-9_]*)\s*:", body)))
    format_keys[head.split(":")[0].strip()] = keys

print("=== 机型 -> 格式 ===")
for name, fmt, note in models:
    print(f"  {name:26} {fmt:12} {note[:66]}")

print("\n=== 字段 -> 格式 ===")
for field, formats, role in field_rows:
    print(f"  {field:20} {formats[:52]:54} {role[:44]}")

print("\n=== 每个 Format 的键 ===")
for fmt, keys in format_keys.items():
    print(f"  {fmt:12} {', '.join(keys[:18]) if keys else '（无）'}")

# ---- 生成对照文档 ----
needs = [
    ("经纬度", "轨迹、地图定位、画面取点的基准", "**必需**"),
    ("相对高度 rel_alt", "视场框大小、取点解算", "**必需**"),
    ("云台俯仰 gb_pitch / pitch", "视场框的远近、取点射线", "**必需**"),
    ("偏航/机头朝向 yaw", "视场框朝向、飞机箭头", "**必需**（缺了只能用航迹方向近似）"),
    ("焦距 focal_len / 变焦 zoom", "视场框的宽窄（FOV）", "**必需**（缺了只能按默认广角估）"),
    ("光圈/快门/ISO", "报告里的相机参数表", "可选"),
]

lines = []
add = lines.append

add("# SRT 格式与机型字段对照（含可用性检查）")
add("")
add("## 一、这份对照的用途")
add("")
add("回答两个问题：")
add("")
add("1. 别的机型能不能接进来（我们要解析哪种 SRT 方言）；")
add("2. **接进来之后，我们需要的字段它到底有没有** —— 缺字段的机型，功能会降级，")
add("   必须在界面上说清楚，而不是算出一个看着对、其实错的结果。")
add("")
add("## 二、数据来源与许可")
add("")
add("格式目录来自 [CallMarcus/dji-drone-metadata-embedder]"
    "(https://github.com/CallMarcus/dji-drone-metadata-embedder) 的 "
    "[docs/SRT_FORMATS.md](https://github.com/CallMarcus/dji-drone-metadata-embedder/blob/master/docs/SRT_FORMATS.md)，")
add("该仓库为 **MIT 许可**（LICENSE 已核对），允许在注明出处的前提下取用。")
add("原始快照留在 `docs/_srt_formats_raw.md`（仅本次对照用，可不进仓库）。")
add("")
add("> 我们**只取用它的格式说明当参考**，没有引入它的代码；解析仍由我们自己的 "
    "`Code/project_manager.py` 完成。")
add("")
add("## 三、机型 → SRT 方言")
add("")
add("| 机型 | 格式 | 说明 |")
add("|---|---|---|")

for name, fmt, note in models:
    add(f"| {name} | {fmt} | {note} |")

add("")
add("## 四、我们需要的字段 ← 哪些格式真的带")
add("")
add("| 我们要的字段 | 用在哪 | 必要性 |")
add("|---|---|---|")

for field, where, must in needs:
    add(f"| {field} | {where} | {must} |")

add("")
add("上游目录里明确列出的字段归属（原文口径）：")
add("")
add("| 字段 | 哪些格式携带 | 作用 |")
add("|---|---|---|")

for field, formats, role in field_rows:
    add(f"| `{field}` | {formats} | {role} |")

add("")
add("## 五、结论：按机型看「够不够我们用」")
add("")
add("| 机型（格式） | 经纬度 | 相对高度 | 云台俯仰 | 焦距/变焦 | 结论 |")
add("|---|---|---|---|---|---|")
add("| Matrice 4T（**我们现在用的**） | ✓ | ✓ | ✓ `gb_pitch` | ✓ `zoomfactor` | 齐 —— 视场框与取点都可用 |")
add("| Mavic 3 / Air 2S / Air 3（Format 3） | ✓ | ✓ | ✓ | ✓ `focal_len` | 齐 |")
add("| Mini 5 Pro / Air 3S / Mavic 4 Pro / Neo 2（Format 3b） | ✓ | ✓ | 部分（云台角度只有 Avata 360 变体明确列出） | ✓ | 取决于云台字段；**没有云台角度时视场框只能按航向近似** |")
add("| Mini 3 Pro / Mini 4 Pro / Mavic Air 2 / FPV（Format 1） | ✓ | ✓ | ✗ 未列出 | **✗ 未列出 `focal_len`** | **会降级**：视场框宽窄只能按默认广角估，取点精度受影响 |")
add("| Mavic Pro / Phantom 4 / Avata 2（Format 2） | ✓ | 部分（Avata 2 有 BAROMETER） | ✗ | ✗ | 只能做轨迹与跳转，视场/取点不可靠 |")
add("| Matrice 300 RTK（Format 2b） | ✓ | ✓（带单位） | ✗ | ✗ | 同上 |")
add("| Phantom 4 RTK / P4P（Format 2c） | ✓ | ✓ | 部分（F.PRY 里有姿态） | ✗ | 姿态可从 `F.PRY` 取，焦距仍缺 |")
add("")
add("**最要紧的两条**：")
add("")
add("1. `focal_len`（焦距）**只有 Format 3 / 3b 有** —— 也就是说 **Mini 3 Pro / Mini 4 Pro 这类")
add("   Format 1 机型拿不到焦距**，视场框只能按默认广角估，画面取点也会有偏差。")
add("2. 云台 yaw/pitch **只有 Format 3b 的 Avata 360 变体被明确列出**；其余机型要么写在")
add("   别的字段里、要么根本没有 —— **必须先拿真实样片验证**，不能照文档假设。")
add("")
add("> 注意：**上游目录里没有 Matrice 4T** —— 我们现在能跑，是因为我们自己按 M4T 的")
add("> 实际 SRT 写了解析。所以这份目录对 M4T 没有参考价值，对**新机型**才有。")
add("")
add("## 六、建议的落地方式")
add("")
add("- **不照搬代码**：把这份目录当作「格式识别 + 能力清单」的参考；")
add("- 给解析结果加**字段可用性标记**（例如 `has_focal / has_gimbal`），")
add("  界面上直接说清「该机型缺焦距/云台角，视场框与取点为估算」；")
add("- 新机型接入前，先要一段**原始 SRT 样片**做验证 —— 这也是上游仓库的同一做法：")
add("  没有样片就不要声称支持。")
add("")

OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"\n  已生成 {OUT}")
