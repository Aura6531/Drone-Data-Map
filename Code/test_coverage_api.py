# -*- coding: utf-8 -*-
"""coverage_api 的自测：清单 / 构建 / 查询 / 热力图 / 矢量化 / 导出 全链路。

**自建夹具**，不依赖仓库里有没有演示素材：
  1. 造一个临时项目 + 临时架次目录
  2. 写一份**合成的** DJI 风格 SRT（直飞航线、俯角固定、带经纬度与高度）
  3. 走完整条链路，最后把夹具删掉

为什么要合成而不是用真素材：这个测试要能进 run_tests.js，
在干净的 clone 上（没有 Data/、没有 Project/）也必须能跑。

    python -B test_coverage_api.py
"""
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import numpy as _np  # noqa: F401
except ImportError:
    # 覆盖功能依赖 numpy。没装时**明确跳过**而不是报失败 ——
    # 这样系统 Python（可能没有 numpy）跑 run_tests.js 也不会误判。
    print("=== 视场覆盖接口层测试 ===")
    print("  [SKIP] 这个解释器没有 numpy，跳过")
    print("\n结果: 全部通过（已跳过）")
    raise SystemExit(0)

import coverage_api as api  # noqa: E402

ok = True


def chk(cond, label, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"  {'[OK]' if cond else '[FAIL]'} {label}" + (f" -> {extra}" if extra else ""))


# ============================================================
# 夹具：合成一个 DJI 风格架次
# ============================================================

PROJ = "__cov_api_test__"
LAT0, LNG0 = 22.96, 113.77
ALT = 100.0
PITCH = -30.0


def synth_srt(path: Path, n=60, fps=30):
    """写一份 DJI 3D 风格的 SRT。

    必须严格照 DJI 的真实排版，否则后端解析不出来（踩过一次）：
        序号
        HH:MM:SS,mmm --> HH:MM:SS,mmm
        FrameCnt: N  YYYY-MM-DD HH:MM:SS.mmm
        [iso: ..] [shutter: ..] ... [dzoom_ratio: ..], [latitude: ..] ... [gb_roll: ..]

    注意那行参数末尾是**逗号**再接经纬度；参数之间是空格。
    """
    blocks = []
    for i in range(n):
        frac = i / max(1, n - 1)
        lat = LAT0 + frac * 0.0019
        lng = LNG0 + frac * 0.0019
        yaw = 45.0
        t0 = i / fps
        t1 = (i + 1) / fps

        def ts(t):
            ms = int(round((t - int(t)) * 1000))
            s = int(t) % 60
            m = (int(t) // 60) % 60
            h = int(t) // 3600
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        blocks.append(
            f"{i + 1}\n"
            f"{ts(t0)} --> {ts(t1)}\n"
            f"FrameCnt: {i} 2026-01-01 00:{i // (fps * 60):02d}:{(i // fps) % 60:02d}.{int((i % fps) * (1000 / fps)):03d}\n"
            f"[iso: 100] [shutter: 1/500.0] [fnum: 2.8] [ev: 0] [color_md: default] "
            f"[ae_meter_md: 1] [focal_len: 24.00] [dzoom_ratio: 1.00], "
            f"[latitude: {lat:.6f}] [longitude: {lng:.6f}] "
            f"[rel_alt: {ALT:.3f} abs_alt: {ALT + 20.0:.3f}] "
            f"[gb_yaw: {yaw:.1f} gb_pitch: {PITCH:.1f} gb_roll: 0.0] \n"
        )
    path.write_text("\n".join(blocks), encoding="utf-8")


def make_fixture(root: Path):
    import project_manager as pm

    proj_dir = pm.PROJECT_DIR / PROJ
    shutil.rmtree(proj_dir, ignore_errors=True)
    proj_dir.mkdir(parents=True, exist_ok=True)

    sortie = root / "DJI_TEST_0001"
    shutil.rmtree(sortie, ignore_errors=True)
    sortie.mkdir(parents=True, exist_ok=True)
    srt = sortie / "DJI_TEST_0001_V.srt"
    synth_srt(srt)

    (proj_dir / "project.json").write_text(json.dumps({
        "name": PROJ, "version": 1,
        "folders": [{"path": str(sortie)}],
        "videos": [], "photos": [], "tracks": [],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    return proj_dir, sortie, srt


def main():
    root = Path(__file__).resolve().parent.parent / "_cov_api_fixture"
    root.mkdir(parents=True, exist_ok=True)
    import project_manager as pm

    proj_dir, sortie, srt = make_fixture(root)
    try:
        print("=== 1) 清单 ===")
        lst = api.list_coverage(PROJ, [str(sortie)])
        chk(lst["has_numpy"], "numpy 可用（没它整个覆盖功能不可用）")
        chk(len(lst["items"]) == 1, "找到 1 个 SRT", f"{len(lst['items'])} 个")
        chk(lst["items"][0]["built"] is False, "还没建过")
        chk(lst["items"][0]["stale"] is True, "未建 = 需要重建")

        print("\n=== 2) 构建 ===")
        t0 = time.time()
        r = api.build_coverage(PROJ, srt, cell=1.0)
        dt = time.time() - t0
        chk(r.get("covered"), "构建成功", f"{dt:.1f}s")
        chk(r.get("reused") is False, "首次是新建")
        chk(r.get("frames_used", 0) > 0, "有帧被用上", f"{r.get('frames_used')} 帧")
        chk(r.get("area_ha", 0) > 0, "覆盖面积 > 0", f"{r.get('area_ha')} 公顷")
        npz = Path(r["npz"])
        chk(npz.is_file(), "npz 落盘", npz.name)
        chk(npz.with_suffix(".json").is_file(), "摘要 json 落盘")
        chk(npz.with_suffix(".meta.json").is_file(), "meta json 落盘")
        chk(npz.parent == (proj_dir / "coverage"), "网格落在项目目录下")

        print("\n=== 3) 再建一次应复用 ===")
        t0 = time.time()
        r2 = api.build_coverage(PROJ, srt, cell=1.0)
        chk(r2.get("reused") is True, "走了复用分支", f"{time.time() - t0:.2f}s")
        chk(r2.get("npz") == r.get("npz"), "同一个文件")

        print("\n=== 4) 源 SRT 变新后应判为过期 ===")
        synth_srt(srt, n=90)
        os.utime(srt, (time.time() + 5, time.time() + 5))
        chk(api.is_stale(npz, srt) is True, "mtime 变新 -> stale")

        print("\n=== 5) 点查询 ===")
        origin = r["origin"]
        # 注意：网格原点 (lat0,lng0) 是**西南角**，不是中心，
        # 所以 origin 本身不一定被覆盖。要取一个确实被覆盖的格子来测。
        # 坐标换算直接用网格自己的方法，别手工推（手工推容易沿用旧的中心语义）。
        import coverage as cov
        import numpy as np
        g = cov.CoverageGrid.load(npz)
        ys, xs = np.nonzero(g.count > 0)
        chk(len(xs) > 0, "网格里有被覆盖的格子", f"{len(xs)} 格")
        ix, iy = int(xs[0]), int(ys[0])
        clat, clng = g.cell_latlng(ix, iy)

        q = api.query_point(PROJ, npz, clat, clng)
        chk(q.get("covered") is True, "被覆盖的格子查得到", str(q.get("reason", "")))
        if q.get("covered"):
            print(f"      置信度 {q['confidence']} ({q['grade']})  帧 {q['basis']['frames']}"
                  f"  解像 {q['basis']['gsd_m_per_px']} m/px")
            chk(0.0 <= q["confidence"] <= 1.0, "置信度在 0~1")
            for k in ("r_space", "r_support", "r_clip", "sigma_m", "type",
                      "accuracy_note", "basis", "grid"):
                chk(k in q, f"含字段 {k}")
            chk(q["basis"]["frames"] >= 1, "至少 1 帧")
            chk(q["basis"]["gsd_m_per_px"] > 0, "解像度为正")
            chk(q["type"] in ("hard_boundary", "clipped"), "类型取值合法", q["type"])
            chk(0.0 <= q["r_clip"] <= 1.0, "r_clip 在 0~1")
        # 网格外
        far = api.query_point(PROJ, npz, origin[0] + 5.0, origin[1] + 5.0)
        chk(far.get("covered") is False, "网格外未覆盖", str(far.get("reason", ""))[:30])
        # 网格内但没被拍到：找一格 count==0 的
        zs = np.nonzero(g.count == 0)
        if len(zs[0]):
            zlat, zlng = g.cell_latlng(int(zs[1][0]), int(zs[0][0]))
            zq = api.query_point(PROJ, npz, zlat, zlng)
            chk(zq.get("covered") is False, "网格内空白格 -> 未覆盖",
                str(zq.get("reason", ""))[:30])

        print("\n=== 6) 热力图 ===")
        for metric, kw in (("count", {}), ("gsd", {"gsd_max": 0.30})):
            png = api.render_heatmap_png(npz, metric=metric, **kw)
            chk(png[:8] == b"\x89PNG\r\n\x1a\n", f"{metric} 是合法 PNG",
                f"{len(png) / 1024:.0f} KB")

        print("\n=== 7) 矢量导出 ===")
        geo = api.export_geojson(PROJ, npz, metric="count", threshold=1)
        st = geo["properties"]["stats"]
        chk(geo["type"] == "FeatureCollection", "是 FeatureCollection")
        chk(st["rings"] >= 1, "至少 1 个多边形",
            f"{st['rings']} 个 {st['area_ha']} 公顷")
        chk(st.get("project") == PROJ, "stats 带项目名")
        chk(len(geo["features"]) == st["rings"], "feature 数与 stats 一致")
        bad = 0
        for f in geo["features"]:
            for ring in f["geometry"]["coordinates"]:
                if len(ring) < 4 or ring[0] != ring[-1]:
                    bad += 1
        chk(bad == 0, "所有环闭合且 >= 4 点（RFC 7946）", f"问题 {bad}")
        f0 = geo["features"][0]["properties"]
        chk(abs(f0["area_m2"] - f0["cells"] * 1.0) < 1.0,
            "面积 = 格数 × 格宽²", f"{f0['area_m2']} vs {f0['cells']}")

        print("\n=== 8) 落盘导出 ===")
        out = api.write_geojson(PROJ, npz, metric="count", threshold=1)
        chk(out.is_file(), "geojson 落到覆盖目录", out.name)
        chk(out.parent == npz.parent, "与 npz 同目录")
        chk(json.loads(out.read_text(encoding="utf-8"))["type"] == "FeatureCollection",
            "文件内容是可解析的 GeoJSON")

        print("\n=== 9) gsd 指标导出也要能用 ===")
        geo2 = api.export_geojson(PROJ, npz, metric="gsd", gsd_max=0.30)
        chk(geo2["type"] == "FeatureCollection", "gsd 指标导出成功",
            f"{geo2['properties']['stats']['rings']} 个多边形")

        print("\n=== 10) 覆盖目录里没有意外文件 ===")
        kinds = {p.suffix.lower() for p in npz.parent.iterdir()}
        chk(kinds <= {".npz", ".json", ".geojson"}, "只有预期类型",
            ",".join(sorted(kinds)))

        print("\n=== 11) 导出的矢量产物不能混进航迹列表 ===")
        # 用户 2026-10-13：「这几个 coverage 的矢量图层没有存在的必要了，
        # 至少图上不要加载出来，也不要在搜索结果里面显示出来。
        # 我查看信息直接看热力图了，看它干嘛」。
        # 第 8 步刚写了一个真实的导出文件，正好用来验：
        #   · is_coverage_export 认得它
        #   · list_project_geojson 会把它滤掉
        #   · 真航迹（LineString + point_times）不能被误伤
        exported = json.loads(out.read_text(encoding="utf-8"))
        chk(pm.is_coverage_export(exported),
            "is_coverage_export 认得导出产物（顶层有 stats）")

        track_like = {
            "type": "FeatureCollection",
            "properties": {"record_count": 36542, "segment_count": 1},
            "features": [{
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[114.1, 23.0], [114.2, 23.1]]},
                "properties": {"point_times": [0, 1], "duration": 1},
            }],
        }
        chk(not pm.is_coverage_export(track_like),
            "真航迹不被误判为导出产物")
        chk(not pm.is_coverage_export({}),
            "空对象也不误判（按结构判、不抛异常）")

        # 把真航迹写进**被扫描的那个文件夹**（夹具项目的 folders[0]），
        # 看列表里只剩它。注意别写错目录 —— 写错会让断言"空列表"而假通过。
        fake_track = sortie / "DJI_TEST_0001_V.geojson"
        fake_track.write_text(json.dumps(track_like), encoding="utf-8")
        try:
            listing = pm.list_project_geojson(PROJ)
            names = [f["file_name"] for f in listing["files"]]
            chk(names, "列表非空（夹具写对了目录）", ",".join(names) or "(空)")
            chk(all("coverage" not in n.lower() and "resolvable" not in n.lower()
                    for n in names),
                "航迹列表里没有覆盖导出", ",".join(names) or "(空)")
            chk(fake_track.name in names,
                "真航迹仍然在列表里（没被误伤）", ",".join(names) or "(空)")
        finally:
            if fake_track.exists():
                fake_track.unlink()
    finally:
        shutil.rmtree(proj_dir, ignore_errors=True)
        shutil.rmtree(root, ignore_errors=True)
        _ = pm

    print("\n结果:", "全部通过" if ok else "有失败项")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
