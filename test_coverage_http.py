# -*- coding: utf-8 -*-
"""对**正在运行的开发服务**实测覆盖接口（走 HTTP，不是直接调函数）。

界面能不能用，最终取决于这几条接口对不对，所以单独测一层。
夹具**通过接口自己建**（新建项目 -> 加文件夹 -> 写合成 SRT -> Build），
测完删掉，所以在任何机器上都能跑。

服务没在跑时**明确跳过**（返回 0）而不算失败 —— 这样它也能进 run_tests.js，
不需要谁记得先起服务。

    python -B test_coverage_http.py
"""
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# 这个脚本在仓库根，而 project_manager 在 Code/ 下 —— 末尾清理夹具要用到它，
# 所以必须先把 Code/ 挂上 sys.path（之前漏了，导致清理**静默失败**、
# 夹具项目留在 Project/ 里没人发现）。
sys.path.insert(0, str(Path(__file__).resolve().parent / "Code"))

BASE = os.environ.get("COVERAGE_BASE", "http://127.0.0.1:8000")
PROJ = "__cov_http_test__"
ok = True

try:
    with urllib.request.urlopen(BASE + "/api/config", timeout=5):
        pass
except Exception as e:
    print("=== 视场覆盖 HTTP 接口测试 ===")
    print(f"  [SKIP] 开发服务没在跑（{BASE}）")
    print(f"         原因: {type(e).__name__}")
    print("\n结果: 全部通过（已跳过）")
    raise SystemExit(0)


def chk(cond, label, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"  {'[OK]' if cond else '[FAIL]'} {label}" + (f" -> {extra}" if extra else ""))


def get(path, **params):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    try:
        with urllib.request.urlopen(url, timeout=300) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        # 400 是**预期结果**（参数校验），不能让它打断测试
        return e.code, e.read(), dict(e.headers)


def get_json(path, **params):
    st, body, _ = get(path, **params)
    try:
        return st, json.loads(body.decode("utf-8"))
    except Exception:
        return st, {"_raw": body[:200].decode("utf-8", "replace")}


def post(path, payload):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


# ============================================================
# 夹具：合成 SRT。
# 格式必须照 DJI 的真实排版（序号 / 时间轴 / FrameCnt 行 / 参数字段用空格分隔、
# 末尾逗号再接经纬度），否则 load_srt_telemetry 解析不出来。
# ============================================================

def synth_srt(path: Path, n=60, fps=30):
    lat0, lng0, alt, pitch = 22.96, 113.77, 100.0, -30.0
    blocks = []
    for i in range(n):
        frac = i / max(1, n - 1)
        t0, t1 = i / fps, (i + 1) / fps

        def ts(t):
            return "%02d:%02d:%02d,%03d" % (
                int(t) // 3600, (int(t) // 60) % 60, int(t) % 60,
                int(round((t - int(t)) * 1000)))

        blocks.append(
            f"{i + 1}\n{ts(t0)} --> {ts(t1)}\n"
            f"FrameCnt: {i} 2026-01-01 00:00:{i // fps:02d}.{int((i % fps) * (1000 / fps)):03d}\n"
            f"[iso: 100] [shutter: 1/500.0] [fnum: 2.8] [ev: 0] [color_md: default] "
            f"[ae_meter_md: 1] [focal_len: 24.00] [dzoom_ratio: 1.00], "
            f"[latitude: {lat0 + frac * 0.0019:.6f}] [longitude: {lng0 + frac * 0.0019:.6f}] "
            f"[rel_alt: {alt:.3f} abs_alt: {alt + 20:.3f}] "
            f"[gb_yaw: 45.0 gb_pitch: {pitch:.1f} gb_roll: 0.0] \n"
        )
    path.write_text("\n".join(blocks), encoding="utf-8")


def main():
    root = Path(__file__).resolve().parent / "_cov_http_fixture"
    sortie = root / "DJI_HTTP_0001"
    shutil.rmtree(root, ignore_errors=True)
    sortie.mkdir(parents=True, exist_ok=True)
    srt = sortie / "DJI_HTTP_0001_V.srt"
    synth_srt(srt)

    try:
        print("=== 0) 通过接口建夹具项目 ===")
        st, j = post("/api/project/create", {"name": PROJ})
        chk(st == 200, "新建项目", str(j.get("error", ""))[:50])
        st, j = post("/api/project/add-folder",
                     {"project_name": PROJ, "folder": {"path": str(sortie)}})
        chk(st == 200, "加文件夹", str(j.get("error", ""))[:50])

        print("\n=== 1) GET /coverage/list ===")
        st, j = get_json("/api/project/coverage/list", name=PROJ)
        chk(st == 200 and j.get("ok"), "HTTP 200 + ok")
        chk(j.get("has_numpy") is True, "后端有 numpy")
        items = j.get("items") or []
        chk(len(items) == 1, "列出 1 个 SRT", f"{len(items)} 个")
        chk(bool(items) and items[0]["built"] is False, "还没建过")

        print("\n=== 2) 参数校验：缺参数要 400 而不是崩 ===")
        st, j = get_json("/api/project/coverage/list")
        chk(st == 400 and "error" in j, "缺 name -> 400", str(j.get("error"))[:40])
        st, j = get_json("/api/project/coverage/query", name=PROJ, lat="1", lng="")
        chk(st == 400 and "error" in j, "缺 lng -> 400", str(j.get("error"))[:40])

        print("\n=== 3) POST /coverage/build ===")
        t0 = time.time()
        st, j = post("/api/project/coverage/build",
                     {"project_name": PROJ, "srt": str(srt), "cell": 1.0})
        chk(st == 200 and j.get("success"), "构建成功", f"{time.time() - t0:.1f}s")
        res = j.get("result") or {}
        npz = res.get("npz")
        chk(bool(npz), "返回 npz 路径")
        chk(res.get("area_ha", 0) > 0, "有覆盖面积", f"{res.get('area_ha')} 公顷")
        chk(res.get("reused") is False, "首次是新建")
        st, j2 = post("/api/project/coverage/build",
                      {"project_name": PROJ, "srt": str(srt), "cell": 1.0})
        chk((j2.get("result") or {}).get("reused") is True, "再建一次走复用")

        print("\n=== 4) 越权：项目外的 SRT 必须被拒 ===")
        st, j = post("/api/project/coverage/build",
                     {"project_name": PROJ, "srt": r"A:\Windows\notepad.exe"})
        chk(st == 400, "拒绝非 .srt", str(j.get("error"))[:50])
        outside = Path(__file__).resolve().parent / "run_tests.js"
        st, j = post("/api/project/coverage/build",
                     {"project_name": PROJ, "srt": str(outside)})
        chk(st == 400, "拒绝项目外路径", str(j.get("error"))[:50])

        print("\n=== 5) GET /coverage/query ===")
        # 网格原点 (lat0,lng0) 是**西南角**，且它不一定被覆盖，
        # 所以从中心沿对角线找一个确实被覆盖的点。
        origin = res.get("origin") or [0, 0]
        q = None
        for d in (0.0, 0.002, 0.004, 0.006, 0.008, 0.010, 0.012,
                  -0.002, -0.004, -0.006):
            st, cand = get_json("/api/project/coverage/query", name=PROJ, npz=npz,
                                lat=origin[0] + d, lng=origin[1] + d)
            if st == 200 and cand.get("covered"):
                q = cand
                break
        chk(q is not None, "找到一个被覆盖的点并查到结果")
        if q:
            print(f"      置信度 {q['confidence']} ({q['grade']})  "
                  f"帧 {q['basis']['frames']}  解像 {q['basis']['gsd_m_per_px']} m/px")
            for k in ("confidence", "grade", "r_space", "r_support", "r_clip",
                      "sigma_m", "type", "accuracy_note", "basis"):
                chk(k in q, f"含字段 {k}")
            chk(0.0 <= q["confidence"] <= 1.0, "置信度在 0~1")
        st, j = get_json("/api/project/coverage/query", name=PROJ, npz=npz,
                         lat=origin[0] + 5, lng=origin[1] + 5)
        chk(j.get("covered") is False, "网格外未覆盖", str(j.get("reason"))[:30])

        print("\n=== 6) 路径穿越：npz 参数只认项目 coverage/ 下的 .npz ===")
        for bad in (r"..\..\project.json", r"A:\Windows\win.ini",
                    "x.geojson", "..%5C..%5Cproject.json"):
            st, j = get_json("/api/project/coverage/query", name=PROJ, npz=bad,
                             lat="22", lng="113")
            chk(st == 400, f"拒绝 npz={bad[:26]}", str(j.get("error"))[:40])

        print("\n=== 7) GET /coverage/heatmap ===")
        for label, params in (("count", {"metric": "count"}),
                              ("gsd", {"metric": "gsd", "gsd_max": "0.30"}),
                              ("count+overlay", {"metric": "count", "overlay": "1",
                                                 "threshold": "1"})):
            st, body, _ = get("/api/project/coverage/heatmap", name=PROJ, npz=npz,
                              **params)
            chk(st == 200 and body[:8] == b"\x89PNG\r\n\x1a\n",
                f"{label} 是合法 PNG", f"{len(body) / 1024:.0f} KB")

        print("\n=== 8) POST /coverage/export ===")
        st, j = post("/api/project/coverage/export",
                     {"project_name": PROJ, "npz": npz, "metric": "count",
                      "threshold": 1, "inline": True})
        chk(st == 200 and j.get("success"), "导出成功",
            f"{j.get('file_name')} {j.get('size_kb')} KB")
        geo = j.get("geojson") or {}
        chk(geo.get("type") == "FeatureCollection", "返回 FeatureCollection")
        stt = (geo.get("properties") or {}).get("stats") or {}
        chk(stt.get("rings", 0) >= 1, "环数 >= 1",
            f"{stt.get('rings')} 个 {stt.get('area_ha')} 公顷")
        chk(stt.get("project") == PROJ, "stats 带项目名")
        fn = j.get("file_name")

        print("\n=== 9) GET /coverage/file ===")
        st, body, h = get("/api/project/coverage/file", name=PROJ, file=fn)
        chk(st == 200, "取回导出文件", str(st))
        chk("geo+json" in (h.get("Content-Type") or ""), "Content-Type 正确",
            h.get("Content-Type"))
        chk(json.loads(body.decode("utf-8"))["type"] == "FeatureCollection",
            "内容是可解析 GeoJSON")
        for bad in ("..\\..\\project.json", "A:\\Windows\\win.ini", "x.exe"):
            st, _, _ = get("/api/project/coverage/file", name=PROJ, file=bad)
            chk(st == 400, f"拒绝 file={bad[:24]}")
        st, _, _ = get("/api/project/coverage/file", name=PROJ, file="nope.geojson")
        chk(st == 400, "不存在的文件 -> 400")
    finally:
        shutil.rmtree(root, ignore_errors=True)
        # 项目的删除：**不能用 ignore_errors=True 糊过去** ——
        # 之前就是因为静默失败，夹具项目留在 Project/ 里没人发现。
        try:
            import project_manager as pm
            victim = pm.PROJECT_DIR / PROJ
            if victim.exists():
                for attempt in range(3):
                    shutil.rmtree(victim, ignore_errors=True)
                    if not victim.exists():
                        break
                    time.sleep(0.4)          # 服务端可能还开着文件句柄
                if victim.exists():
                    print(f"  [WARN] 夹具项目没能删掉，请手动删除：{victim}")
        except Exception as e:
            print(f"  [WARN] 清理夹具出错：{type(e).__name__}: {e}")

    print("\n结果:", "全部通过" if ok else "有失败项")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
