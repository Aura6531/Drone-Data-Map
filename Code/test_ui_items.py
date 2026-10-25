# -*- coding: utf-8 -*-
"""P1b 验收测试：旧 ui 显隐在「在线 / 离线 / 重新接盘」三种状态下都不丢。

对应文档 §10.6.8 四条：
1) 在线迁移：旧 ui.videos/ortho/coverage -> ui.items[itemId]，状态不变；
2) 离线迁移：来源路径不存在但 project.json 里有 files[]，仍能映射，身份用 ip_ + pending；
3) 重新接盘：目录回来后 ip_ -> it_，状态不变；仍被其它来源引用时两个键都留；
4) 不误删：迁移只改 ui，不动磁盘文件。

全程在临时目录里跑，不碰真实项目。
"""
import json
import os
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import project_manager as pm

ROOT = _HERE.parent
TMP = ROOT / "_test_tmp_uiitems"
ok = True


def chk(cond, label, extra=""):
    global ok
    if not cond:
        ok = False
    print("  [%s] %s%s" % ("OK" if cond else "FAIL", label,
                           (" -> " + str(extra)) if extra else ""))


if TMP.exists():
    shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True, exist_ok=True)

real_project_dir = pm.PROJECT_DIR
pm.PROJECT_DIR = TMP / "Project"
pm.PROJECT_DIR.mkdir(parents=True, exist_ok=True)

NAME = "itemtest"


def write_project():
    pdir = pm.PROJECT_DIR / NAME
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "project.json").write_text(json.dumps({
        "name": NAME,
        "version": 1,
        "folders": [
            {
                "name": "A", "path": str(src_a),
                "files": [
                    {"name": "v1.geojson", "relative_path": "v1.geojson"},
                    {"name": "r1.tif", "relative_path": "sub/r1.tif"},
                ],
            },
            {
                "name": "B", "path": str(src_b),
                "files": [
                    # 与 A 共享同一真实文件（模拟父子来源重叠）
                    {"name": "v1.geojson", "relative_path": "v1.geojson"},
                ],
            },
        ],
        "ui": {
            "videos": {"v1.geojson": False},
            "ortho": {"r1.tif": True},
            "coverage": {"missing.srt": False},     # 映射不上 -> 应保留
        },
    }, ensure_ascii=False), encoding="utf-8")


try:
    src_a = TMP / "srcA"
    src_b = TMP / "srcB"
    (src_a / "sub").mkdir(parents=True)
    src_b.mkdir(parents=True)

    print("\n=== 1) 离线迁移：目录不存在，但 project.json 里有 files[] ===")
    write_project()          # src_a / src_b 里还没有文件
    p = pm.load_project(NAME)
    ids_offline = {}
    for folder in p["folders"]:
        for f in folder["files"]:
            ids_offline[(folder["name"], f["relative_path"])] = f.get("itemId")
    chk(all(str(v).startswith("ip_") for v in ids_offline.values()),
        "所有文件都拿到临时身份 ip_…", sorted(set(ids_offline.values())))
    chk(all(f.get("itemIdPending") for folder in p["folders"] for f in folder["files"]),
        "并标记 itemIdPending")

    v_ids = {ids_offline[("A", "v1.geojson")], ids_offline[("B", "v1.geojson")]}
    r_id = ids_offline[("A", "sub/r1.tif")]
    st = pm.migrate_ui_items(p)
    items = p["ui"]["items"]
    chk(len(items) == 2, "videos + ortho 都迁到了 ui.items（coverage 映射不上）", list(items))
    # 两个来源都有 v1.geojson（同相对路径、不同真实文件）-> 歧义：
    # 状态只落在其中一个 id 上（值必须是原来的 false），但不能丢。
    hit = [i for i in v_ids if i in items]
    chk(len(hit) == 1 and items[hit[0]] is False,
        "videos 的 false 状态落到了 v1.geojson 的 id 上（歧义时取一个）",
        f"{hit} -> {[items.get(i) for i in hit]}")
    chk(items.get(r_id) is True, "ortho 的 true 状态原样保留", str(items))
    chk("missing.srt" in (p["ui"].get("coverage") or {}), "映射不上的旧键保留（等来源恢复补迁）")
    chk(st["pending"] == 1, "pending 计数 = 1", str(st))

    print("\n=== 1b) 歧义：同一相对路径对应两个不同真实文件 ===")
    # 两个来源各有 v1.geojson（不同真实文件）-> 迁移时命中 2 个 itemId
    chk(p["ui"].get("videos") and "v1.geojson" in p["ui"]["videos"],
        "歧义时旧键保留（不因选了一个 id 就删）", str(p["ui"].get("videos")))
    legacy = p["ui"].get("legacy") or {}
    chk("videos:v1.geojson" in legacy,
        "旧键原值存进 ui.legacy（供人工核对）", str(legacy))
    chk(legacy.get("videos:v1.geojson") is False,
        "ui.legacy 里的值与旧键一致", str(legacy.get("videos:v1.geojson")))
    chk(st.get("legacy_saved", 0) >= 1, "统计里有 legacy_saved", str(st))

    # 幂等：再迁一次，legacy 不应重复累加
    st_again = pm.migrate_ui_items(p)
    chk(len(p["ui"].get("legacy") or {}) == len(legacy),
        "重复迁移不会重复写 ui.legacy", str(len(p["ui"].get("legacy") or {})))

    print("\n=== 2) 重新接盘：建出真实文件 -> ip_ 迁到 it_，状态不变 ===")
    (src_a / "v1.geojson").write_text("{}", encoding="utf-8")
    (src_a / "sub" / "r1.tif").write_text("x", encoding="utf-8")
    (src_b / "v1.geojson").write_text("{}", encoding="utf-8")

    p2 = pm.load_project(NAME)
    real_ids = {}
    for folder in p2["folders"]:
        for f in folder["files"]:
            real_ids[(folder["name"], f["relative_path"])] = f.get("itemId")
    chk(all(str(v).startswith("it_") for v in real_ids.values()),
        "在线后全部换成真实身份 it_…", sorted(set(real_ids.values())))
    chk(not any(f.get("itemIdPending") for folder in p2["folders"] for f in folder["files"]),
        "itemIdPending 被清掉")

    st2 = pm.migrate_ui_items(p2)
    items2 = p2["ui"]["items"]
    a_id = real_ids[("A", "v1.geojson")]
    b_id = real_ids[("B", "v1.geojson")]
    # A 与 B 是**不同真实文件**（只是相对路径同名）：状态落在其中一个即可，
    # 关键是不能丢。歧义在第一次迁移时已经记过一次（stats.ambiguous）。
    carried = [i for i in (a_id, b_id) if items2.get(i) is False]
    chk(len(carried) == 1,
        "重接盘后状态仍在（落在 primary 那个 id 上，没丢）", str(items2))
    # A 与 B 是不同目录下的两个文件 -> realpath 不同 -> 两个 id，互不影响
    chk(a_id != b_id, "A/B 各自真实文件不同 -> 两个 itemId", f"{a_id} / {b_id}")

    print("\n=== 3) 同一真实文件被两个来源引用（junction 场景）：旧键只在无人引用时删 ===")
    # 让 B 直接指向 A（用 junction/软链模拟同一真实文件被两个来源包含）
    try:
        shutil.rmtree(src_b)
        if hasattr(os, "symlink"):
            os.symlink(src_a, src_b, target_is_directory=True)
        else:
            raise OSError("no symlink")
        linked = True
    except (OSError, NotImplementedError):
        # 没有权限创建链接：用「同一路径登记两次」的等价场景（realpath 相同）
        src_b = src_a
        linked = True

    if linked:
        pdir = pm.PROJECT_DIR / NAME
        cfg = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
        cfg["folders"][1]["path"] = str(src_b)
        (pdir / "project.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

        p3 = pm.load_project(NAME)
        ids3 = {}
        for folder in p3["folders"]:
            for f in folder["files"]:
                ids3[(folder["name"], str(f.get("relative_path")))] = f.get("itemId")
        same = ids3[("A", "v1.geojson")] == ids3[("B", "v1.geojson")]
        chk(same, "两个来源指向同一真实文件 -> 同一个 itemId（天然去重）", str(same))

        # 先放一个旧键（模拟上一轮离线算的临时身份）再迁
        old_key = "ip_deadbeefcafe"
        p3["ui"].setdefault("items", {})[old_key] = True
        for folder in p3["folders"]:
            for f in folder["files"]:
                if str(f.get("relative_path")) == "v1.geojson":
                    f["itemIdPrev"] = old_key
        st3 = pm.migrate_ui_items(p3)
        chk(old_key not in p3["ui"]["items"] or st3["shared"] >= 1,
            "旧临时身份：被其它来源引用时保留（shared>=1）或已并入", str(st3))

    print("\n=== 4) 只改 ui，不动磁盘文件 ===")
    before = {p.name: p.stat().st_size for p in [src_a / "v1.geojson", src_a / "sub" / "r1.tif"]}
    pm.migrate_ui_items(p3)
    after = {p.name: p.stat().st_size for p in [src_a / "v1.geojson", src_a / "sub" / "r1.tif"]}
    chk(before == after and all(p.exists() for p in [src_a / "v1.geojson", src_a / "sub" / "r1.tif"]),
        "迁移前后磁盘文件原样（大小、存在性都不变）", str(after))

finally:
    pm.PROJECT_DIR = real_project_dir
    try:
        if src_b.is_symlink():
            src_b.unlink()
    except (OSError, AttributeError):
        pass
    shutil.rmtree(TMP, ignore_errors=True)

print("\n结果:", "全部通过" if ok else "有失败")
sys.exit(0 if ok else 1)
