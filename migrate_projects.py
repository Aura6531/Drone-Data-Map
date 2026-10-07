# -*- coding: utf-8 -*-
"""把 Data 下所有架次并入「东莞3」，删除 东莞1/东莞2，并补齐缺失的 GeoJSON。

用法：
    python -B migrate_projects.py              # 只出计划，不改任何东西
    python -B migrate_projects.py --apply      # 真正改 Project\\ 与 Data\\
    python -B migrate_projects.py --apply --geojson   # 再补 SRT 与 GeoJSON

为什么 --apply 需要提权运行：
    仓库根下的 Code、Project、Data 三个目录在某些受管环境下缺少写权限，
    受限命令写入会被拒（诊断报告见根目录的 _acl_reports\\）。
    生成 3.4MB 的 GeoJSON 也没法走工具后端，所以这一步要一次提权执行。

安全措施：
    - 删除任何东西之前，先把 Project 下相关 project.json 备份到 _migration\\backup\\
    - 默认 dry-run；只有显式 --apply 才落盘
    - 不删除 Data 下任何原始数据
"""

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CODE = ROOT / "Code"
DATA = ROOT / "Data"
PROJECT = ROOT / "Project"
WORK = ROOT / "_migration"
WORK.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(CODE))
import project_manager as pm  # noqa: E402

TARGET = "东莞3"
DELETE = ["东莞1", "东莞2"]
FLIGHTS = [
    "DJI_202609230835_001",
    "DJI_202609240950_001",
    "DJI_202609241014_002",
]

APPLY = "--apply" in sys.argv
DO_GEO = "--geojson" in sys.argv
DO_FORCE_GEO = "--force-geojson" in sys.argv

LOG = []


def log(msg=""):
    print(msg)
    LOG.append(str(msg))


def fix_entry(entry, name):
    """把条目里的绝对路径改到工作区 Data 下。文件清单是相对路径，不用动。"""
    item = dict(entry)
    item["name"] = name
    item["path"] = str(DATA / name)
    return item


def build_merged():
    """算出合并后的 东莞3（不落盘）。

    每个架次都**重新扫描**：项目里存的清单是上一次扫描时的快照，
    例如 240950 那份还是提取 SRT 之前的（srt_count=0），照抄会漏掉文件，
    后面判断「哪些视频缺 GeoJSON」也会跟着漏。
    扫描只是一次目录遍历，很便宜。
    """
    return {
        "name": TARGET,
        "version": 1,
        "folders": [pm.scan_folder(DATA / name) for name in FLIGHTS],
        "videos": [],
        "photos": [],
        "tracks": [],
    }


def geojson_status(project):
    """每个视频对应的 GeoJSON / SRT 是否存在。"""
    rows = []

    for index, folder in enumerate(project["folders"]):
        base = Path(folder["path"])

        for item in folder.get("files", []):
            if item.get("extension") not in (".mp4", ".mov"):
                continue

            stem = Path(item["relative_path"]).stem

            rows.append({
                "index": index,
                "folder": folder["name"],
                "video": item["relative_path"],
                "video_ok": (base / item["relative_path"]).exists(),
                "srt_ok": (base / (stem + ".srt")).exists(),
                "geojson_ok": (base / (stem + ".geojson")).exists(),
            })

    return rows


def do_apply_structure(project):
    backup = WORK / "backup"
    backup.mkdir(parents=True, exist_ok=True)

    for name in [TARGET] + DELETE:
        src = PROJECT / name / "project.json"
        if src.exists():
            shutil.copy2(src, backup / (name + ".project.json"))
            log("  已备份 %s" % (backup / (name + ".project.json")))

    pm.save_project(TARGET, project)
    log("  已写入 %s" % (PROJECT / TARGET / "project.json"))

    for name in DELETE:
        target_dir = PROJECT / name
        if target_dir.exists():
            shutil.rmtree(target_dir)
            log("  已删除项目目录 %s" % target_dir)


def do_ensure_geojson(project, rows):
    pending = [r for r in rows if not r["geojson_ok"]]

    if not pending:
        log("  没有缺失的 GeoJSON")
        return

    failed = []

    for row in pending:
        folder = next(f for f in project["folders"] if f["name"] == row["folder"])
        started = time.time()

        # 单个视频失败不能中断整次迁移：Data 里还有「10 右岸-珠海市.mp4」这类
        # 非 DJI 命名的素材，没有遥测字幕流，本来就生成不出轨迹。
        try:
            if not row["srt_ok"]:
                log("  提取 SRT：%s" % row["video"])
                pm.extract_srt_for_video(TARGET, folder["path"], row["video"])

            log("  生成 GeoJSON：%s" % row["video"])
            result = pm.generate_geojson_for_video(TARGET, folder["path"], row["video"])

            log("    -> %s  %s 点 / %s 段  %.1f MB  %.1fs" % (
                result.get("geojson_name"),
                result.get("record_count"),
                result.get("segment_count"),
                (result.get("size") or 0) / 1048576.0,
                time.time() - started,
            ))
        except Exception as exc:
            failed.append(row)
            log("    !! 跳过：%s  —— %s: %s" % (
                row["video"], type(exc).__name__, exc))

    # 新生成的文件要重新扫进 project.json，否则清单与实际不符
    log("  重新扫描三个架次，刷新文件清单")
    project["folders"] = [pm.scan_folder(DATA / name) for name in FLIGHTS]
    pm.save_project(TARGET, project)

    if failed:
        log("")
        log("  以下 %d 个视频没能生成轨迹（已跳过，不影响其它数据）：" % len(failed))
        for row in failed:
            log("    - %s / %s" % (row["folder"], row["video"]))


def do_force_geojson(project):
    """用（已修好的）生成器重做所有 DJI V/S/T 的 GeoJSON，旧的先备份。

    为什么要重做：旧版 2D 生成器漏写了 feature 级 point_times，
    而「按此位置搜索飞行视频」和播放时箭头/视场定位全靠它 ——
    这类轨迹在页面上搜不到、地图也不跟着动。
    """
    import re
    dji = re.compile(r"^DJI_\d{8}\d{6}_\d+_[A-Za-z]+$")

    backup = WORK / "backup" / "geojson"
    backup.mkdir(parents=True, exist_ok=True)

    done = []

    for folder in project["folders"]:
        base = Path(folder["path"])

        for item in folder.get("files", []):
            if item.get("extension") not in (".mp4", ".mov"):
                continue

            stem = Path(item["relative_path"]).stem

            # 只处理 DJI 标准命名的 V/S/T，其它素材（例如「10 右岸-珠海市.mp4」）
            # 没有遥测字幕流，本来就生成不出轨迹
            if not dji.match(stem):
                continue

            geo = base / (stem + ".geojson")

            if geo.exists():
                shutil.copy2(geo, backup / (folder["name"] + "__" + geo.name))
                log("  已备份旧文件 %s" % (backup / (folder["name"] + "__" + geo.name)))

            started = time.time()
            result = pm.generate_geojson_for_video(TARGET, folder["path"], item["relative_path"])

            log("  重做 %-32s -> %d 点  用时 %.1fs" % (
                item["relative_path"], result.get("record_count") or 0, time.time() - started))
            done.append(result)

    log("  重新扫描三个架次，刷新文件清单")
    project["folders"] = [pm.scan_folder(DATA / name) for name in FLIGHTS]
    pm.save_project(TARGET, project)

    log("  共重做 %d 个 GeoJSON" % len(done))
    return done


def verify_point_times(project):
    """确认每个 GeoJSON 都带 point_times，且点数与坐标数一致。"""
    bad = []

    for folder in project["folders"]:
        base = Path(folder["path"])

        for geo in sorted(base.glob("*.geojson")):
            if geo.name.endswith(".3d.geojson"):
                continue

            try:
                data = json.loads(geo.read_text(encoding="utf-8"))
                feature = (data.get("features") or [{}])[0]
                coords = (feature.get("geometry") or {}).get("coordinates") or []
                times = (feature.get("properties") or {}).get("point_times") or []

                if len(times) != len(coords) or not times:
                    bad.append((geo.name, len(coords), len(times)))
                else:
                    log("  [OK] %-40s %5d 点 / %5d 个时间" % (geo.name, len(coords), len(times)))
            except Exception as exc:
                bad.append((geo.name, "读取失败", str(exc)))

    return bad


def main():
    log("=" * 68)
    log("合并计划：把 Data 下三个架次全部并入「%s」，删除 %s" % (TARGET, "、".join(DELETE)))
    log("模式：%s%s" % ("APPLY" if APPLY else "DRY-RUN",
                        " + 补齐 GeoJSON" if (APPLY and DO_GEO) else ""))
    log("=" * 68)

    project = build_merged()

    log("")
    log("目标项目 %s 将包含 %d 个数据文件夹：" % (TARGET, len(project["folders"])))
    for i, folder in enumerate(project["folders"]):
        log("  [%d] %-24s %4d 个文件  mp4=%d srt=%d" % (
            i, folder["name"], folder["file_count"],
            folder["mp4_count"], folder["srt_count"]))
        log("      path = %s" % folder["path"])

    rows = geojson_status(project)

    log("")
    log("视频 / SRT / GeoJSON 现状：")
    missing_geo = 0
    for row in rows:
        flag = "OK " if row["geojson_ok"] else "缺 "
        if not row["geojson_ok"]:
            missing_geo += 1
        log("  [%s] %-24s %-32s srt=%s geojson=%s" % (
            flag, row["folder"], row["video"],
            "有" if row["srt_ok"] else "缺",
            "有" if row["geojson_ok"] else "缺")) 

    log("")
    log("缺失 GeoJSON：%d 个（缺 SRT 的会先提取）" % missing_geo)

    plan = {
        "target": TARGET,
        "delete": DELETE,
        "folders": [
            {"name": f["name"], "path": f["path"], "file_count": f["file_count"]}
            for f in project["folders"]
        ],
        "videos": rows,
        "missing_geojson": missing_geo,
        "applied": APPLY,
        "with_geojson": DO_GEO,
    }
    (WORK / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (WORK / "last-run.txt").write_text("\n".join(LOG), encoding="utf-8")

    if not APPLY:
        log("")
        log("DRY-RUN 结束：没有改动任何文件。计划已写到 %s" % (WORK / "plan.json"))
        return 0

    log("")
    log("开始落盘……")

    if DO_FORCE_GEO:
        log("")
        log("重做全部 DJI V/S/T 的 GeoJSON（旧文件先备份）……")
        do_force_geojson(project)
    elif APPLY:
        do_apply_structure(project)

        if DO_GEO:
            log("")
            log("补齐 GeoJSON……")
            do_ensure_geojson(project, rows)

    log("")
    log("校验每个 GeoJSON 的 point_times（航迹检索依赖它）……")
    bad = verify_point_times(project)
    if bad:
        log("  以下文件仍然不可用于检索：")
        for name, a, b in bad:
            log("    - %s  坐标=%s 时间=%s" % (name, a, b))
    else:
        log("  全部通过：每个文件都有与坐标一一对应的 point_times")

    listing = pm.list_project_geojson(TARGET)
    log("")
    log("验证：%s 现有 %d 个 GeoJSON" % (TARGET, listing["count"]))
    for item in listing["files"]:
        log("  folder_index=%d  %-32s %8.2f MB  记录=%s 段=%s" % (
            item["folder_index"], item["relative_path"],
            item["size"] / 1048576.0, item["record_count"], item["segment_count"]))

    log("")
    log("剩余项目：%s" % ", ".join(sorted(
        p.name for p in PROJECT.iterdir() if p.is_dir())))

    (WORK / "last-run.txt").write_text("\n".join(LOG), encoding="utf-8")
    log("")
    log("完成。完整日志：%s" % (WORK / "last-run.txt"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
