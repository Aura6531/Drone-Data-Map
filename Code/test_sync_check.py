# -*- coding: utf-8 -*-
"""验证同步校验真能抓到"视频被裁过"。

做法：建一个**临时项目**，里面放一条真视频 + 一份被人为改短时长的航迹，
看 check_project_sync 会不会报出来。测完删掉临时项目。

只读真实素材；不碰现有项目。
"""
import json
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import project_manager as pm

ROOT = _HERE.parent
TMP = ROOT / "Project" / "_synctest"
ok = True


def chk(cond, label, extra=""):
    global ok
    if not cond:
        ok = False
    print("  [%s] %s%s" % ("OK" if cond else "FAIL", label,
                           (" -> " + str(extra)) if extra else ""))


# ---- 准备：拿一条真视频 + 它的真 SRT ----
src_dir = ROOT / "Data" / "DJI_202609240950_001"
# **用参考路（_V）**：一次拍摄有 V/S/T 三路视频，合并航迹的坐标与时刻取自 _V
# （分辨率最高）。自检要拿参考路去比，否则是拿 A 路的视频比 B 路的航迹。
_vids = sorted(src_dir.glob("*.MP4"))
video = next((p for p in _vids if p.stem.upper().endswith("_V")), _vids[0])
srt = video.with_suffix(".srt")
# 航迹文件名现在是**合并后的公共名**（去掉 _V/_S/_T）—— 一次拍摄的多路已合成一份，
# 所以不再是 `video.with_suffix(".geojson")`。
# 用被测代码自己的 `flight_stem_of` 推，避免测试里再复制一份命名规则。
_stem = pm.flight_stem_of(video.name) or video.stem
geojson = video.with_name(_stem + ".geojson")
print("=== 借用素材 ===")
print("  视频 %s（%.1f MB）" % (video.name, video.stat().st_size / 1e6))
print("  SRT  %s  航迹 %s" % (srt.name, geojson.name))

data_dir = TMP / "data"
data_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(video, data_dir / video.name)
shutil.copy2(srt, data_dir / srt.name)

# 航迹：故意把时长改短 40 秒（模拟"视频被裁掉 40 s"）
#
# **必须同时改 point_times**：`_track_duration_of_geojson()` 的权威来源是
# `point_times` 数组的跨度（不是 `duration` 字段）。只改 duration 的话
# 自检照旧通过 —— 这个测试就变成了假通过。
gj = json.loads(geojson.read_text(encoding="utf-8"))
for f in gj.get("features") or []:
    pr = f.get("properties") or {}
    if isinstance(pr.get("duration"), (int, float)):
        pr["duration"] = float(pr["duration"]) - 40.0
    if isinstance(pr.get("video_end"), (int, float)):
        pr["video_end"] = float(pr["video_end"]) - 40.0
    pt = pr.get("point_times")
    if isinstance(pt, list) and pt:
        # 1 点 ≈ 1/30 s，所以 40 s ≈ 1200 点。
        # （一开始只截了 40 个点 = 1.3 s，小于 2 s 容差，测试就假通过了。）
        cut = max(1, int(round(40.0 * 30.0)))
        if len(pt) > cut + 10:
            pr["point_times"] = pt[:-cut]
(TMP / "data" / (_stem + ".geojson")).write_text(
    json.dumps(gj, ensure_ascii=False), encoding="utf-8")

(TMP / "project.json").write_text(json.dumps({
    "name": "_synctest",
    "folders": [{"path": str(data_dir)}],
}, ensure_ascii=False), encoding="utf-8")

try:
    print()
    print("=== 1) 航迹时长被改短 40 s，应当报 error ===")
    r = pm.check_project_sync("_synctest")
    print("  核对 %d 条   ok=%s   problems=%d" % (r["checked"], r["ok"], len(r["problems"])))
    errs = [p for p in r["problems"] if p["severity"] == "error"]
    chk(len(errs) == 1, "报出 1 条 error", len(errs))
    if errs:
        p = errs[0]
        chk(p["reference"] == "track", "参照物是**航迹**（不是 SRT）", p["reference"])
        chk(abs(p["delta"] + 40.0) < 1.0,
            "差 40 s 被算对（delta = 参照 − 视频，航迹改短所以是负的）", p["delta"])
        chk(p["kind"] == "track_shorter", "方向判定为 track_shorter", p["kind"])
        print("     message: %s" % p["message"])
    else:
        chk(False, "**没抓到 —— 校验逻辑有问题**")

    print()
    print("=== 2) 把航迹删掉，只有 SRT（360 那种情况）===")
    (TMP / "data" / (_stem + ".geojson")).unlink()
    r2 = pm.check_project_sync("_synctest")
    errs2 = [p for p in r2["problems"] if p["severity"] == "error"]
    chk(len(errs2) == 0, "只有 SRT 且 SRT 与视频一致 -> 不报错",
        "%d 条 error" % len(errs2))

    print()
    print("=== 3) 把 SRT 也改短 40 s，应当改用 SRT 参照并报错 ===")
    txt = srt.read_text(encoding="utf-8", errors="replace")
    import re
    # 把所有 00:MM:SS,mmm 时间戳减 0（简单做法：直接把整段 cue 删掉一部分更麻烦）
    # 这里改用"复制一份尾巴被截掉的 SRT"
    cues = re.split(r"\n\s*\n", txt.strip())
    keep = cues[: max(1, int(len(cues) * 0.9))]      # 砍掉最后 10% 的 cue
    (TMP / "data" / srt.name).write_text("\n\n".join(keep) + "\n", encoding="utf-8")
    r3 = pm.check_project_sync("_synctest")
    errs3 = [p for p in r3["problems"] if p["severity"] == "error"]
    chk(len(errs3) == 1, "SRT 被截短 -> 报 1 条 error", len(errs3))
    if errs3:
        chk(errs3[0]["reference"] == "srt", "参照物是 SRT", errs3[0]["reference"])
        print("     message: %s" % errs3[0]["message"])

    print()
    print("=== 4) 容差可调：把容差放大到 200 s，应当不再报 ===")
    r4 = pm.check_project_sync("_synctest", tolerance=200.0)
    chk(r4["ok"], "容差 200 s 时不报", "problems=%d" % len(r4["problems"]))
finally:
    shutil.rmtree(TMP, ignore_errors=True)
    print()
    print("  临时项目已删除: %s" % (not TMP.exists()))

print()
print("结果:", "全部通过" if ok else "有失败项")
raise SystemExit(0 if ok else 1)
