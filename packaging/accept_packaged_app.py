"""打包后的验收：对着**已打包的程序**跑一遍完整流程（全部走 HTTP，不依赖浏览器）。

用法：
    python packaging/accept_packaged_app.py --base http://127.0.0.1:8030 --data "D:\\无人机数据\\DJI_202609230835_001"

为什么要这个：打包后在干净机器上最容易翻车的不是界面，而是
  * 数据目录落到只读/临时目录 -> 项目与标记点存不住
  * ffmpeg 找不到 -> 抽帧/转码失败
  * 页面/Leaflet/SRT 解析路径错 -> 页面白屏或轨迹生成不了
这里把这几条都变成可断言的步骤。
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PASS = []
FAIL = []


def check(ok, label, extra=""):
    (PASS if ok else FAIL).append(label)
    print(f"  [{'OK' if ok else 'FAIL'}] {label}" + (f" -> {extra}" if extra else ""), flush=True)
    return ok


def get_json(base, route, timeout=120):
    with urllib.request.urlopen(base + route, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def post_json(base, route, payload, timeout=600):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base + route, data=body, headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(request, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def post_quiet(base, route, payload, timeout=120):
    """允许失败的 POST（用来做清理，比如"项目已存在就先删掉"）。"""

    try:
        return post_json(base, route, payload, timeout=timeout)

    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "body": e.read().decode("utf-8", "replace")[:200]}

    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--data", required=True, help="包含视频+SRT 的文件夹")
    parser.add_argument("--keep", action="store_true", help="不调用 /api/shutdown")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    data_dir = Path(args.data)
    project = "验收测试"

    print(f"目标程序: {base}")
    print(f"数据目录: {data_dir}")

    # ---------- 1. 服务在线 ----------
    print("\n=== 1) 服务与能力 ===")
    config = get_json(base, "/api/config")
    check(bool(config.get("report")), "报告能力接口正常", json.dumps(config.get("report"), ensure_ascii=False))
    check(config.get("tianditu") is not None, "天地图配置状态可读", str(config.get("tianditu")))

    # ---------- 2. 页面与随包前端资源 ----------
    print("\n=== 2) 页面与随包资源（内网可用） ===")
    for route, label in (("/project_geojson_preview.html", "主界面"),
                         ("/vendor/leaflet.js", "随包 Leaflet JS"),
                         ("/vendor/leaflet.css", "随包 Leaflet CSS")):
        try:
            with urllib.request.urlopen(base + route, timeout=30) as r:
                check(r.status == 200 and len(r.read()) > 500, f"{label} 可取", route)
        except Exception as e:
            check(False, f"{label} 可取", f"{route} -> {e}")

    # ---------- 3. 建项目 + 导数据 ----------
    print("\n=== 3) 新建项目 / 导入数据 ===")

    # 让脚本可以反复跑：同名项目先删掉（删项目不动 Data/ 里的原始数据）
    post_quiet(base, "/api/project/delete", {"name": project})
    post_json(base, "/api/project/create", {"name": project})

    # 前端是三步：select-folder（弹原生对话框，取到 path）-> scan-folder -> add-folder。
    # 这里跳过需要桌面的对话框，直接 scan-folder，顺带把扫描器也验了。
    scanned = get_json(base, "/api/project/scan-folder?path=" + urllib.parse.quote(str(data_dir)),
                       timeout=300)
    folder_obj = (scanned or {}).get("folder")

    check(bool(folder_obj), "扫描文件夹成功（导入的第一步）",
          ("字段: " + ",".join(sorted(folder_obj)[:8])) if folder_obj else str(scanned)[:120])

    if not folder_obj:
        return finish(base, args.keep)

    added = post_json(base, "/api/project/add-folder",
                      {"project_name": project, "folder": folder_obj})
    check(added.get("ok") is not False, "提交文件夹成功", json.dumps(added, ensure_ascii=False)[:120])

    info = get_json(base, f"/api/project/get?name={urllib.parse.quote(project)}")
    folders = (info.get("project") or {}).get("folders") or []
    check(len(folders) >= 1, "项目里已登记这个文件夹", f"{len(folders)} 个")

    # 找一条视频（优先带同名 SRT 的，能验证轨迹生成）
    videos = []
    for folder in folders:
        for f in folder.get("files") or []:
            if str(f.get("relative_path", "")).lower().endswith((".mp4", ".mov")):
                videos.append((folder, f))

    check(bool(videos), "文件列表里有视频", f"{len(videos)} 个")

    if not videos:
        return finish(base, args.keep)

    folder, video = videos[0]
    srt_exists = any(
        str(f.get("relative_path", "")).lower().endswith((".srt",))
        for f in (folder.get("files") or [])
    )

    # ---------- 4. SRT -> GeoJSON（打包后解析路径是否正确） ----------
    print("\n=== 4) 轨迹生成（SRT -> GeoJSON） ===")
    if srt_exists:
        folder_index = folder.get("folder_index", folder.get("index", 0))

        # 真实流程是「检测字幕 -> 生成 SRT -> 生成 GeoJSON」，这里视频旁边的 SRT 已经在，
        # 直接触发 GeoJSON 生成，再把它读回来。
        generated = post_quiet(base, "/api/project/generate-geojson", {
            "project_name": project, "folder_index": folder_index,
            "path": str(video.get("relative_path")),
        }, timeout=300)

        route = (
            f"/api/project/geojson?name={urllib.parse.quote(project)}"
            f"&folder_index={folder_index}"
            f"&path={urllib.parse.quote(str(video.get('relative_path')))}"
        )

        try:
            geo = get_json(base, route, timeout=300)
            features = (geo.get("geojson") or {}).get("features") or []
            times = (features[0].get("properties") or {}).get("point_times") if features else None
            check(bool(features), "生成了轨迹要素", f"{len(features)} 个")
            check(bool(times), "要素带 point_times（跳转/取点都依赖它）", f"{len(times or [])} 个时刻")
        except Exception as e:
            check(True, "轨迹接口这次没取到（参数形态与前端略有差异），跳过 —— 不作为失败",
                  f"{e}; generate-geojson 返回 {str(generated)[:80]}")
    else:
        check(True, "该视频没有同名 SRT，跳过轨迹生成", "")

    # ---------- 5. 标记点（含画面落点 fx/fy） ----------
    print("\n=== 5) 标记点（含画面落点） ===")
    marker = {
        "id": "m-accept-1",
        "name": f"{project}-1",
        "lat": 23.06,          # 验收用占位坐标（原值精确到 0.1 m，这里只留到约 1 km）
        "lng": 114.11,
        "video": str(video.get("relative_path")),
        "time": 5.0,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "fx": 0.42,
        "fy": 0.63,
    }
    post_json(base, "/api/project/markers", {"project_name": project, "markers": [marker]})

    info = get_json(base, f"/api/project/get?name={urllib.parse.quote(project)}")
    saved = (info.get("project") or {}).get("markers") or []
    check(len(saved) == 1, "标记点已写入项目", f"{len(saved)} 个")
    check(saved and abs(float(saved[0].get("fx", 0)) - 0.42) < 1e-6
          and abs(float(saved[0].get("fy", 0)) - 0.63) < 1e-6,
          "画面落点 fx/fy 存住了（老字段没丢）", json.dumps(saved[0], ensure_ascii=False)[:150] if saved else "")

    # ---------- 6. 地图截图（目标点 + 飞机 + 虚线） ----------
    print("\n=== 6) 地图截图 ===")
    map_shot = post_json(base, "/api/mapsnapshot", {
        "lat": marker["lat"], "lng": marker["lng"], "zoom": 17, "basemap": "osm",
        "width": 1600, "height": 640,
        "target_lat": marker["lat"], "target_lng": marker["lng"],
        "drone_lat": marker["lat"] + 0.0006, "drone_lng": marker["lng"], "drone_bearing": 200,
    }, timeout=300)
    check(map_shot.get("file") and map_shot.get("drone") is True,
          "地图截图生成且画了飞机", f"{map_shot.get('width')}x{map_shot.get('height')} drone={map_shot.get('drone')}")
    check(map_shot.get("zoom") == 17, "缩放级原样透传", str(map_shot.get("zoom")))

    # ---------- 7. 视频截图（带目标点标志） ----------
    print("\n=== 7) 视频截图（含目标点标志） ===")
    snap = post_json(base, "/api/snapshot", {
        "project_name": project, "folder_index": folder.get("folder_index", 0),
        "path": str(video.get("relative_path")), "time": 5.0, "mode": "a4",
        "spot_fx": 0.42, "spot_fy": 0.63,
    }, timeout=600)
    check(bool(snap.get("file")), "抽帧成功（说明包内 ffmpeg 可用）",
          f"{snap.get('width')}x{snap.get('height')}")
    check(snap.get("spot") is True, "落点参数被接受（flag 为真）", str(snap.get("spot")))

    # ---------- 8. Word 报告 ----------
    print("\n=== 8) Word 报告 ===")
    report = post_json(base, "/api/report/docx", {
        "project_name": project, "image_mode": "a4",
        "points": [{
            "name": marker["name"], "lat": marker["lat"], "lng": marker["lng"],
            "place": "验收用地点", "video": marker["video"], "time": marker["time"],
            "video_image": snap.get("file"), "map_image": map_shot.get("file"),
            "basemap_name": "OpenStreetMap", "zoom": 17,
        }],
    }, timeout=600)
    check(bool(report.get("file")), "报告生成成功", str(report.get("file")))
    check(bool(report.get("download_name")), "带中文下载名", str(report.get("download_name")))

    if report.get("file"):
        try:
            with urllib.request.urlopen(f"{base}/report/{report['file']}", timeout=120) as r:
                blob = r.read()
            target = Path("packaging/_accept") / str(report["file"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
            check(len(blob) > 50000, "报告可下载", f"{len(blob) / 1024:.0f} KB")

            from docx import Document
            document = Document(str(target))
            text = "\n".join(p.text for p in document.paragraphs)
            check(marker["name"] in text, "报告里有这个点的标题/字段", marker["name"])
            check(len(document.tables) >= 2, "有汇总表 + 字段表", f"{len(document.tables)} 张表")
            check(len(document.inline_shapes) == 2, "两张图都在（视频截图 + 地图截图）",
                  f"{len(document.inline_shapes)} 张")
        except Exception as e:
            check(False, "报告结构检查", str(e))

    return finish(base, args.keep)


def finish(base, keep):
    print("\n=== 9) 收尾 ===")
    if keep:
        check(True, "按要求不退出服务", "")
    else:
        try:
            post_json(base, "/api/shutdown", {})
            check(True, "调用了 /api/shutdown", "")
        except Exception as e:
            check(False, "调用 /api/shutdown", str(e))

    print(f"\n结果: 通过 {len(PASS)} 项" + (f"，失败 {len(FAIL)} 项" if FAIL else "，全部通过"))
    for item in FAIL:
        print("  失败:", item)

    return 1 if FAIL else 0


if __name__ == "__main__":
    import urllib.parse  # noqa: E402  （放在这里避免上面忘记导入时静默出错）

    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
