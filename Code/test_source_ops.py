# -*- coding: utf-8 -*-
"""P1c 后端验收：刷新索引（单/全）、重新定位（预检 + 确认）、移除来源。

对应文档 §10.1 / §10.2 / §10.6：
· 失败（目录不存在）时**保留旧索引**，只改状态；
· relocate 预检不写盘，confirm 才改，并按相对路径迁移 ui 状态；
· detach 默认只解除关联，磁盘文件不动；delete_generated=True 暂不支持。
"""
import json
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import project_manager as pm

ROOT = _HERE.parent
TMP = ROOT / "_test_tmp_sourceops"
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

real = pm.PROJECT_DIR
pm.PROJECT_DIR = TMP / "Project"
pm.PROJECT_DIR.mkdir(parents=True)
NAME = "opstest"
PDIR = pm.PROJECT_DIR / NAME
PDIR.mkdir()

old_dir = TMP / "旧目录"
new_dir = TMP / "新目录"
other_dir = TMP / "另一处"
old_dir.mkdir()
new_dir.mkdir()
other_dir.mkdir()

for p in ("a.mp4", "b.mp4", "c.jpg"):
    (old_dir / p).write_text("x", encoding="utf-8")
# 新目录：两个同名 + 一个额外
for p in ("a.mp4", "b.mp4", "d.mp4"):
    (new_dir / p).write_text("x", encoding="utf-8")
(old_dir / "a.srt").write_text("1", encoding="utf-8")


def write_project():
    cfg = {
        "name": NAME, "version": 1,
        "folders": [
            {"id": "src_A", "name": "旧目录", "path": str(old_dir),
             "file_count": 4, "mp4_count": 2, "srt_count": 1, "jpg_count": 1,
             "other_count": 0, "total_size": 6,
             "files": [
                 {"name": "a.mp4", "relative_path": "a.mp4", "itemId": "it_old_a"},
                 {"name": "b.mp4", "relative_path": "b.mp4", "itemId": "it_old_b"},
                 {"name": "c.jpg", "relative_path": "c.jpg", "itemId": "it_old_c"},
                 {"name": "a.srt", "relative_path": "a.srt", "itemId": "it_old_srt"},
             ]},
            {"id": "src_B", "name": "另一处", "path": str(other_dir),
             "file_count": 1, "files": [{"name": "z.mp4", "relative_path": "z.mp4",
                                          "itemId": "it_old_z"}]},
        ],
        "ui": {"items": {"it_old_a": False, "it_old_b": True, "it_old_c": True,
                          "it_old_srt": True, "it_old_z": False}},
    }
    (PDIR / "project.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")


try:
    print("\n=== 1) 刷新索引：成功时更新清单与 indexed_at ===")
    write_project()
    p = pm.load_project(NAME)
    r = pm.reindex_source(p, "src_A")
    chk(r["status"] == "ok", "状态 ok", r["status"])
    chk(r["counts"]["file_count"] == 4, "文件数 = 4", str(r["counts"]))
    chk(bool(r["indexed_at"]), "写了 indexed_at", r["indexed_at"])
    ids = [f.get("itemId") for f in p["folders"][0]["files"]]
    chk(all(str(i).startswith("it_") for i in ids), "重扫后文件都拿到真实身份", ids)

    print("\n=== 2) 刷新索引：目录不存在 -> 状态 missing，旧索引保留 ===")
    write_project()
    p = pm.load_project(NAME)
    gone = TMP / "已拔掉的盘"
    p["folders"][0]["path"] = str(gone)
    before_files = [f["relative_path"] for f in p["folders"][0]["files"]]
    r = pm.reindex_source(p, "src_A")
    chk(r["status"] == "missing", "状态 missing", r["status"])
    chk([f["relative_path"] for f in p["folders"][0]["files"]] == before_files,
        "旧索引原样保留（插错盘不会清空清单）")
    chk(p["folders"][0].get("index_status") == "missing", "来源上记了 index_status")

    print("\n=== 3) 全部刷新：一个坏一个正常，互不影响 ===")
    write_project()
    p = pm.load_project(NAME)
    p["folders"][1]["path"] = str(TMP / "不存在")
    results = pm.reindex_sources(p)
    by_id = {x["id"]: x for x in results}
    chk(by_id["src_A"]["status"] == "ok", "src_A 正常", by_id["src_A"]["status"])
    chk(by_id["src_B"]["status"] == "missing", "src_B 报 missing 但不影响别人",
        by_id["src_B"]["status"])

    print("\n=== 4) relocate 预检：不写盘，给出匹配报告 ===")
    write_project()
    p = pm.load_project(NAME)
    rep = pm.relocate_source(p, "src_A", str(new_dir), confirm=False)
    chk(rep["dry_run"] is True, "标记 dry_run")
    chk(rep["verdict"] in ("same", "likely"), "判定 same/likely", rep["verdict"])
    chk(rep["matched"] == 2, "相对路径命中 2 个（a.mp4/b.mp4）", str(rep["matched"]))
    chk("c.jpg" in rep["missing"] and "d.mp4" in rep["added"],
        "missing/added 列对", f"missing={rep['missing']} added={rep['added']}")
    chk(str(p["folders"][0]["path"]) == str(old_dir), "预检没有改来源路径")
    chk(round(rep["match_ratio"], 2) == 0.5, "匹配率 = 2/4 = 0.5", rep["match_ratio"])

    print("\n=== 5) relocate 确认：改路径 + 迁移 ui 状态（按相对路径） ===")
    p["ui"]["items"]["it_old_a"] = False
    rep2 = pm.relocate_source(p, "src_A", str(new_dir), confirm=True)
    chk(rep2["dry_run"] is False, "已生效")
    chk(str(p["folders"][0]["path"]) == str(new_dir), "路径已改")
    new_ids = {f["relative_path"]: f.get("itemId") for f in p["folders"][0]["files"]}
    chk(all(str(v).startswith("it_") for v in new_ids.values()), "新路径文件有真实身份", new_ids)
    a_new = new_ids.get("a.mp4")
    chk(p["ui"]["items"].get(a_new) is False, "a.mp4 的 false 状态迁到了新 id",
        f"{a_new} -> {p['ui']['items'].get(a_new)}")
    chk("it_old_a" not in p["ui"]["items"], "旧 id 无人引用 -> 已删除")
    chk(rep2["ui_keys_migrated"] >= 2, "迁移计数 >= 2", str(rep2["ui_keys_migrated"]))

    print("\n=== 6) detach：只解除关联，文件不动；删除生成物暂不支持 ===")
    write_project()
    p = pm.load_project(NAME)
    before = sorted(x.name for x in old_dir.iterdir())
    res = pm.detach_source(p, "src_A")
    chk(len(p["folders"]) == 1 and p["folders"][0]["id"] == "src_B",
        "来源已从项目移除", [f["id"] for f in p["folders"]])
    chk(res["removed"]["file_count"] == 4, "返回被移除来源的信息", str(res["removed"]))
    chk(res["ui_items_orphan"] >= 1, "ui.items 状态保留（orphan 计数）", str(res))
    after = sorted(x.name for x in old_dir.iterdir())
    chk(before == after, "磁盘文件一个没动", f"{before} == {after}")
    try:
        pm.detach_source(p, "src_B", delete_generated=True)
        chk(False, "delete_generated=True 应当暂不支持")
    except ValueError as e:
        chk("not enabled" in str(e).lower(), "delete_generated=True 明确拒绝", str(e))

finally:
    pm.PROJECT_DIR = real
    shutil.rmtree(TMP, ignore_errors=True)

print("\n结果:", "全部通过" if ok else "有失败")
sys.exit(0 if ok else 1)
