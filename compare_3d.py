import json, sys, io
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"<仓库根>\Data\DJI_202609240950_001")


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


for tag in ("V", "S", "T"):
    plain = load(f"DJI_20260924095258_0001_{tag}.geojson")
    three = load(f"DJI_20260924095258_0001_{tag}.3d.geojson")

    print("=" * 78)
    print(f"### {tag} 路")

    def summarize(d, label):
        feats = d.get("features", [])
        props = d.get("properties", {})
        print(f"  [{label}] 顶层键 {sorted(d.keys())}")
        print(f"  [{label}] properties: {json.dumps(props, ensure_ascii=False)[:300]}")
        print(f"  [{label}] features 数 = {len(feats)}")
        if not feats:
            return None
        f0 = feats[0]
        print(f"  [{label}] feature[0] 键 {sorted(f0.keys())}")
        print(f"  [{label}] feature[0].properties 键 {sorted((f0.get('properties') or {}).keys())}")
        g = f0.get("geometry") or {}
        print(f"  [{label}] geometry.type = {g.get('type')}")
        c = g.get("coordinates")
        # LineString 的 coordinates 就是「点的数组」，不是「分段的数组」
        print(f"  [{label}] 点数 = {len(c) if c is not None else None}")
        if c:
            print(f"  [{label}] 首点 = {c[0]}   末点 = {c[-1]}")
            print(f"  [{label}] 单点分量数 = {len(c[0])}  （2=经纬度, 3=经纬度+高度）")
        return feats

    fp = summarize(plain, "2D")
    ft = summarize(three, "3D")

    if not fp or not ft:
        continue

    # 比较 properties
    pp = (fp[0].get("properties") or {})
    pt = (ft[0].get("properties") or {})
    print(f"  属性键是否相同: {sorted(pp.keys()) == sorted(pt.keys())}")
    if sorted(pp.keys()) != sorted(pt.keys()):
        print(f"    只在 2D: {sorted(set(pp) - set(pt))}")
        print(f"    只在 3D: {sorted(set(pt) - set(pp))}")

    # 比较坐标维度与数值（LineString：coordinates 就是点的数组）
    cp = (fp[0].get("geometry") or {}).get("coordinates") or []
    ct = (ft[0].get("geometry") or {}).get("coordinates") or []
    print(f"  点数: 2D={len(cp)}  3D={len(ct)}")

    if cp and ct:
        print(f"  单点分量数: 2D={len(cp[0])}  3D={len(ct[0])}")
        n = min(len(cp), len(ct))
        bad = next(
            (i for i in range(n)
             if abs(cp[i][0] - ct[i][0]) > 1e-12 or abs(cp[i][1] - ct[i][1]) > 1e-12),
            None
        )
        print(f"  经纬度逐点完全一致: {bad is None}")
        if bad is not None:
            print(f"    首个不一致点 #{bad}: 2D={cp[bad]}  3D={ct[bad]}")

        if len(ct[0]) == 3:
            alts = [p[2] for p in ct]
            print(f"  3D 坐标里的高度范围: {min(alts):.2f} ~ {max(alts):.2f} m")

        heights = (ft[0].get("properties") or {}).get("point_heights")
        if heights:
            print(f"  point_heights 长度 = {len(heights)}，范围 {min(heights):.2f} ~ {max(heights):.2f} m")
            if len(ct[0]) == 3:
                same = all(
                    abs(ct[i][2] - heights[i]) < 1e-6
                    for i in range(min(len(ct), len(heights)))
                )
                print(f"  point_heights 与坐标里的第三维完全相同: {same}")

        pt = (ft[0].get("properties") or {})
        print(f"  3D 的 max_height/min_height = {pt.get('max_height')} / {pt.get('min_height')}")
        print(f"  2D 的 properties 里有没有高度相关字段: "
              f"{[k for k in (fp[0].get('properties') or {}) if 'height' in k.lower()] or '没有'}")
    print()
