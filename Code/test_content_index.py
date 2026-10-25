# -*- coding: utf-8 -*-
"""P3a 验收：内容目录（catalog）纯函数 + 只读接口契约。

夹具全部在临时目录里，**不碰真实 Project/Data**。
"""
import json
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import project_manager as pm

ROOT = _HERE.parent
TMP = ROOT / "_test_tmp_catalog"
ok = True


def chk(cond, label, extra=""):
    global ok
    if not cond:
        ok = False
    print("  [%s] %s%s" % ("OK" if cond else "FAIL", label,
                           (" -> " + str(extra)) if extra else ""))


if TMP.exists():
    shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)

real_project_dir = pm.PROJECT_DIR
pm.PROJECT_DIR = TMP / "Project"
pm.PROJECT_DIR.mkdir(parents=True)
NAME = "catalogtest"
( pm.PROJECT_DIR / NAME ).mkdir()


def entry(name, rel, item_id, size=10, mtime=None, uncertain=False, pending=False):
    e = {"name": name, "relative_path": rel, "extension": Path(name).suffix.lower(),
         "size": size}
    if item_id is not None:
        e["itemId"] = item_id
    if mtime is not None:
        e["mtime_ns"] = mtime
    if uncertain:
        e["uncertain"] = True
    if pending:
        e["itemIdPending"] = True
    return e


def write_project(folders, markers=None, labels=None):
    cfg = {"name": NAME, "version": 1, "folders": folders,
           "markers": markers or [], "labels": labels or [],
           "ui": {"items": {}}}
    (pm.PROJECT_DIR / NAME / "project.json").write_text(
        json.dumps(cfg, ensure_ascii=False), encoding="utf-8")


def folder(idx, files, exists=True, status="ok", indexed="2026-10-25T10:00:00"):
    return {
        "id": "src_%s" % chr(65 + idx),
        "name": "来源%d" % (idx + 1),
        "path": str(TMP / ("src%d" % idx)),
        "exists": exists,
        "index_status": status,
        "indexed_at": indexed,
        "file_count": len(files),
        "files": files,
    }


try:
    print("\n=== 1) 索引文件 1:1 进目录（含未识别类型）===")
    write_project([folder(0, [
        entry("DJI_0001_V.MP4", "DJI_0001_V.MP4", "it_v1"),
        entry("DJI_0001_V.srt", "DJI_0001_V.srt", "it_s1"),
        entry("DJI_0001.geojson", "DJI_0001.geojson", "it_g1"),
        entry("PANORAMA.JPG", "photos/PANORAMA.JPG", "it_p1"),
        entry("result.tif", "ortho/result.tif", "it_o1"),
        entry("roof.kml", "kml/roof.kml", "it_k1"),
        entry("weird.xyz", "misc/weird.xyz", "it_u1"),
        entry("notes.txt", "misc/notes.txt", "it_t1"),
    ])])
    data = pm.load_content_catalog(NAME)
    chk(data["success"] is True, "接口返回 success")
    chk(len(data["items"]) == 8, "8 个索引文件 -> 8 条目录项", len(data["items"]))
    chk(data["counts"]["index_files"] == 8, "index_files = 8", data["counts"])
    chk(data["counts"]["unique_files"] == 8, "unique_files = 8", data["counts"])
    by = {it["name"]: it for it in data["items"]}
    chk(by["DJI_0001_V.MP4"]["type"] == "video", "mp4 -> video")
    chk(by["DJI_0001_V.srt"]["type"] == "subtitle", "srt -> subtitle")
    chk(by["DJI_0001.geojson"]["type"] == "track", "普通 geojson -> track", by["DJI_0001.geojson"]["type"])
    chk(by["PANORAMA.JPG"]["type"] == "photo", "jpg -> photo")
    chk(by["result.tif"]["type"] == "ortho", "tif -> ortho")
    chk(by["roof.kml"]["type"] == "vector", "kml -> vector")
    chk(by["weird.xyz"]["type"] == "unknown" and by["notes.txt"]["type"] == "unknown",
        "未知扩展名 -> unknown（不静默丢弃）")
    chk(data["counts"]["unknown"] == 2, "unknown 计数 = 2", data["counts"]["unknown"])

    print("\n=== 2) 视频的生成物状态（只用索引判断）===")
    v = by["DJI_0001_V.MP4"]
    chk(v["artifacts"]["srt"] is True, "识别到配对 SRT", v["artifacts"])
    chk(v["artifacts"]["track"] is True, "识别到配对航迹", v["artifacts"])
    chk(v["status"]["text"] == "已生成", "状态：已生成", v["status"])
    chk(v["status"]["stale"] == "unknown", "指纹未实现 -> stale=unknown", v["status"])
    s = by["DJI_0001_V.srt"]
    chk(s["artifacts"]["srt"] is True, "srt 自身标 srt=true")

    print("\n=== 3) mtime：有就给，旧索引没有就是 unknown ===")
    write_project([folder(0, [
        entry("a.mp4", "a.mp4", "it_a", mtime=1690000000123456789),
        entry("b.mp4", "b.mp4", "it_b"),          # 旧索引：没有 mtime_ns
    ])])
    d = pm.load_content_catalog(NAME)
    m = {it["name"]: it for it in d["items"]}
    chk(m["a.mp4"]["mtime"] == 1690000000123456789, "有 mtime_ns -> 原样返回", m["a.mp4"]["mtime"])
    chk(m["a.mp4"]["mtime_source"] == "index", "mtime_source=index")
    chk(m["b.mp4"]["mtime"] is None and m["b.mp4"]["mtime_source"] == "unknown",
        "旧索引缺 mtime -> None + unknown（不猜）", (m["b.mp4"]["mtime"], m["b.mp4"]["mtime_source"]))

    print("\n=== 4) 重叠来源：同一 itemId 合一，来源引用齐全 ===")
    shared = entry("shared.mp4", "sub/shared.mp4", "it_shared")
    write_project([
        folder(0, [entry("shared.mp4", "sub/shared.mp4", "it_shared")]),
        folder(1, [entry("shared.mp4", "nested/shared.mp4", "it_shared")]),
    ])
    d = pm.load_content_catalog(NAME)
    chk(len(d["items"]) == 1, "两个来源同一个真实文件 -> 1 条", len(d["items"]))
    it = d["items"][0]
    chk(len(it["sources"]) == 2, "来源引用有 2 条", len(it["sources"]))
    chk({r["source_id"] for r in it["sources"]} == {"src_A", "src_B"}, "两个来源都记着",
        [r["source_id"] for r in it["sources"]])
    chk(d["counts"]["index_files"] == 2 and d["counts"]["unique_files"] == 1,
        "index_files=2 / unique_files=1（重复引用不算新成员）", d["counts"])

    print("\n=== 5) 同名不同文件不合并 ===")
    write_project([folder(0, [
        entry("same.mp4", "a/same.mp4", "it_same_1"),
        entry("same.mp4", "b/same.mp4", "it_same_2"),
    ])])
    d = pm.load_content_catalog(NAME)
    chk(len(d["items"]) == 2, "不同 itemId 即使同名也各自一条", len(d["items"]))
    chk({it["itemId"] for it in d["items"]} == {"it_same_1", "it_same_2"}, "两个 itemId 都在")

    print("\n=== 6) 离线来源：照索引返回，标 offline ===")
    write_project([folder(0, [entry("off.mp4", "off.mp4", "it_off")], exists=False)],
                  markers=[{"id": "m1", "name": "点1", "lat": 1, "lng": 2}],
                  labels=[{"id": "lb1", "text": "标注"}])
    d = pm.load_content_catalog(NAME)
    off = d["items"][0]
    chk(off["offline"] is True, "离线来源的条目 offline=true")
    chk(off["sources"][0]["available"] is False, "来源引用里 available=false")
    chk(off["status"]["level"] == "warn" and "离线" in off["status"]["text"],
        "状态里写明离线", off["status"])
    chk(d["project_items"] == {"markers": 1, "labels": 1, "vectors": 0},
        "项目对象单独统计（不当磁盘文件）", d["project_items"])
    chk(all(not it["itemId"].startswith("marker") for it in d["items"]),
        "目录里不出现伪文件")

    print("\n=== 7) partial / uncertain：保留并标记 ===")
    write_project([folder(0, [
        entry("ok.mp4", "ok.mp4", "it_ok"),
        entry("locked/inside.mp4", "locked/inside.mp4", "it_inside", uncertain=True),
    ], status="partial")])
    d = pm.load_content_catalog(NAME)
    m = {it["name"]: it for it in d["items"]}
    chk(m["locked/inside.mp4"]["uncertain"] is True, "uncertain 条目如实标记")
    chk("索引不确定" in m["locked/inside.mp4"]["status"]["text"],
        "状态文案带「索引不确定」", m["locked/inside.mp4"]["status"])
    chk(len(d["items"]) == 2, "partial 也不丢条目", len(d["items"]))

    print("\n=== 8) 覆盖导出 GeoJSON 不能当成航迹 ===")
    write_project([folder(0, [
        entry("DJI_0001_V.MP4", "DJI_0001_V.MP4", "it_v"),
        entry("DJI_0001.geojson", "DJI_0001.geojson", "it_track"),
        entry("DJI_0001_count1.geojson", "DJI_0001_count1.geojson", "it_cov_geo"),
        entry("DJI_0001.npz", "DJI_0001.npz", "it_npz"),
    ])])
    d = pm.load_content_catalog(NAME)
    m = {it["name"]: it for it in d["items"]}
    chk(m["DJI_0001.geojson"]["type"] == "track", "真航迹仍是 track")
    chk(m["DJI_0001_count1.geojson"]["type"] == "coverage_export",
        "count1.geojson -> coverage_export", m["DJI_0001_count1.geojson"]["type"])
    chk(m["DJI_0001_count1.geojson"]["displayable"] is False,
        "覆盖导出不可上图（它是产物）")
    chk("覆盖导出" in m["DJI_0001_count1.geojson"]["status"]["text"],
        "状态里标注覆盖导出", m["DJI_0001_count1.geojson"]["status"])
    chk(m["DJI_0001.npz"]["type"] == "coverage", "npz -> coverage")

    print("\n=== 9) 只读：调用前后 project.json 字节不变 ===")
    pf = pm.PROJECT_DIR / NAME / "project.json"
    before = pf.read_bytes()
    b_mtime = pf.stat().st_mtime_ns
    pm.load_content_catalog(NAME)
    pm.build_content_catalog(pm.load_project(NAME))
    chk(pf.read_bytes() == before, "目录构建不修改 project.json")
    chk(pf.stat().st_mtime_ns == b_mtime, "mtime 也没变")

    print("\n=== 10) 缺 itemId 的旧索引也有稳定键 ===")
    write_project([folder(0, [entry("legacy.mp4", "legacy.mp4", None)])])
    d = pm.load_content_catalog(NAME)
    chk(len(d["items"]) == 1, "条目仍在")
    # load_project 会给缺失 itemId 的条目补身份（真实路径可达 -> it_，否则 ip_）
    chk(d["items"][0]["itemId"].startswith(("it_", "ip_")),
        "没有 itemId 时由 P1b 规则补一个稳定身份", d["items"][0]["itemId"])
    d2 = pm.load_content_catalog(NAME)
    chk(d2["items"][0]["itemId"] == d["items"][0]["itemId"], "两次构建键一致（稳定）")

    print("\n=== 11) pending（临时身份）===")
    write_project([folder(0, [entry("p.mp4", "p.mp4", "ip_abc", pending=True)],
                          exists=False)])
    d = pm.load_content_catalog(NAME)
    chk(d["items"][0]["pending"] is True, "pending 标记透传")

    print("\n=== 12) 目录项字段齐全 ===")
    write_project([folder(0, [
        entry("DJI_9_V.MP4", "DJI_9_V.MP4", "it_x", size=123, mtime=1),
        entry("DJI_9_V.srt", "DJI_9_V.srt", "it_y"),
    ])])
    d = pm.load_content_catalog(NAME)
    need = {"itemId", "name", "relative_path", "extension", "size", "mtime",
            "mtime_source", "type", "type_label", "classification", "uncertain",
            "offline", "pending", "sources", "artifacts", "displayable", "processable",
            "status"}
    for it in d["items"]:
        missing = need - set(it.keys())
        chk(not missing, "字段齐全: " + it["name"], missing)
    chk(d["items"][0]["size"] == 123, "size 透传")

finally:
    pm.PROJECT_DIR = real_project_dir
    shutil.rmtree(TMP, ignore_errors=True)

print("\n结果:", "全部通过" if ok else "有失败")
sys.exit(0 if ok else 1)
