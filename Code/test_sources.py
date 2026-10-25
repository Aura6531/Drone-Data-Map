# -*- coding: utf-8 -*-
"""P1a 测试：来源 id 稳定 / 只在内存补 / 保存原子 / sources 接口。

不碰真实项目：把 PROJECT_DIR 指到临时目录里跑。
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import project_manager as pm

ROOT = _HERE.parent
TMP = ROOT / "_test_tmp_sources"
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

try:
    name = "idtest"
    pdir = pm.PROJECT_DIR / name
    pdir.mkdir(parents=True, exist_ok=True)
    data_a = TMP / "dataA"
    data_b = TMP / "dataB"
    data_a.mkdir()
    data_b.mkdir()

    # 旧格式：folders 里没有 id
    legacy = {
        "name": name,
        "version": 1,
        "folders": [
            {"name": "A", "path": str(data_a), "file_count": 3},
            {"name": "B", "path": str(data_b), "file_count": 0},
        ],
        "videos": [],
        "photos": [],
        "tracks": [],
    }
    cfg = pdir / "project.json"
    cfg.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
    before_mtime = cfg.stat().st_mtime

    print("\n=== 1) 读的时候只在内存补 id，不写盘 ===")
    p1 = pm.load_project(name)
    ids1 = [f.get("id") for f in p1["folders"]]
    chk(all(ids1), "两条来源都拿到了 id", ids1)
    chk(len(set(ids1)) == 2, "id 互不相同")
    time.sleep(0.05)
    chk(cfg.stat().st_mtime == before_mtime, "读取没有改动 project.json（mtime 不变）")
    on_disk = json.loads(cfg.read_text(encoding="utf-8"))
    chk("id" not in on_disk["folders"][0], "磁盘上仍然没有 id（只在内存）")

    print("\n=== 2) 同一路径每次读都是同一个 id（稳定） ===")
    p2 = pm.load_project(name)
    ids2 = [f.get("id") for f in p2["folders"]]
    chk(ids1 == ids2, "两次读取 id 完全一致", ids2)
    chk(pm.source_id_for_path(str(data_a)) == ids1[0], "直接算路径也得到同一个 id")

    print("\n=== 3) 保存是原子的，且把 id 写回 ===")
    pm.save_project(name, p1)
    saved = json.loads(cfg.read_text(encoding="utf-8"))
    chk([f.get("id") for f in saved["folders"]] == ids1, "保存后磁盘上有 id 且未变")
    leftovers = list(pdir.glob("*.tmp"))
    chk(not leftovers, "没有留下 .tmp 临时文件", [p.name for p in leftovers])

    print("\n=== 4) 已有 id 不会被覆盖；重复 id 会被重新推导 ===")
    saved["folders"][1]["id"] = saved["folders"][0]["id"]      # 人为制造重复
    cfg.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    p3 = pm.load_project(name)
    new_ids = [f.get("id") for f in p3["folders"]]
    chk(len(set(new_ids)) == 2, "重复 id 被改正，仍然互不相同", new_ids)
    chk(new_ids[0] == ids1[0], "第一条的合法 id 原样保留")

    print("\n=== 5) 目录不存在时 id 仍然稳定 ===")
    gone = TMP / "not-there"
    a1 = pm.source_id_for_path(str(gone))
    a2 = pm.source_id_for_path(str(gone))
    chk(a1 == a2 and a1.startswith("src_"), "不存在的路径也给出稳定 id", a1)

    print("\n=== 6) 大小写/分隔符不同的同一路径 -> 同一个 id ===")
    v1 = pm.source_id_for_path(str(data_a))
    v2 = pm.source_id_for_path(str(data_a).upper())
    chk(v1 == v2, "同路径不同大小写得到同一个 id", (v1, v2))

finally:
    pm.PROJECT_DIR = real_project_dir
    shutil.rmtree(TMP, ignore_errors=True)

print("\n结果:", "全部通过" if ok else "有失败")
sys.exit(0 if ok else 1)
