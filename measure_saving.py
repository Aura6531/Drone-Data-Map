import json, sys, io, re
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"<仓库根>\Data\DJI_202609240950_001")

print("=== 从现有 3D 文件里精确量出 point_heights 占多少字节 ===")
for tag in ("V", "S", "T"):
    p = ROOT / f"DJI_20260924095258_0001_{tag}.3d.geojson"
    text = p.read_text(encoding="utf-8")
    size = p.stat().st_size

    # 定位 "point_heights": [ ... ] 这一段（含前后缩进与逗号）
    m = re.search(r'\n\s*"point_heights": \[.*?\n\s*\],?', text, re.S)
    if not m:
        print(f"  {tag}: 没找到 point_heights?")
        continue

    seg = m.group(0)
    seg_bytes = len(seg.encode("utf-8"))
    print(f"  {tag}: 文件 {size/1024/1024:.2f} MB   该字段 {seg_bytes/1024:.0f} KB "
          f"({100*seg_bytes/size:.1f}%)   删后约 {(size-seg_bytes)/1024/1024:.2f} MB")

    # 确认同一份数据确实在坐标里
    d = json.loads(text)
    coords = d["features"][0]["geometry"]["coordinates"]
    heights = d["features"][0]["properties"]["point_heights"]
    same = all(abs(coords[i][2] - heights[i]) < 1e-9 for i in range(len(coords)))
    print(f"       坐标第三维与 point_heights 完全一致: {same}"
          f"   (共 {len(heights)} 个值)")
