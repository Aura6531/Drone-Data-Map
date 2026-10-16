# -*- coding: utf-8 -*-
"""360 全景预览器：后端。

## 做什么

`Data/360视频/` 下的 Avata 360 素材（`.OSV` 双鱼眼）在浏览器里是**没法直接播**的
（14.5 GB，而且是两路半球鱼眼）。这个服务把它按需转成**等距柱状全景图**，
前端再拖拽看任意方向。

## 为什么按需渲染 + 磁盘缓存

14.5 GB / 10 分钟 / 35976 帧：不可能全部转换。
所以按"用户拖动时间轴时请求哪个时刻"来渲染一张，并**按 (视频, 时刻, 宽度) 缓存** ——
同一个时刻第二次看就是秒开。

## 几何

见 `pano360.py`；北向见 `pano360_north.py`。
默认视场 200°（见那里的说明；这个值还有 ±15% 的不确定，不影响北向）。
"""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pano360

# 渲染缓存（放工作区内的临时目录，避免 %TEMP% 不可写）
_CACHE_DIR_NAME = ".pano_cache"
_MAX_CACHE_FILES = 400

_render_lock = threading.Lock()

# 手工覆盖北向（**正常留空**）。北向由 `north_for()` 用太阳位置自动算 + 缓存。
# 留这个表只用于"自动算失败时人工钉住一个值" —— 别当主路径：
# 写死的值换了素材会静默错下去（画面转错方向却不报错）。
NORTH_YAW: dict[str, float] = {}


def cache_dir(base: Path) -> Path:
    d = base / _CACHE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _trim_cache(d: Path, keep: int = _MAX_CACHE_FILES) -> None:
    try:
        files = sorted(d.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[keep:]:
            p.unlink(missing_ok=True)
    except OSError:
        pass


def _ffmpeg() -> str:
    import project_manager as pm
    return pm.find_ffmpeg()


def find_360_videos(folders) -> list[dict]:
    """列出项目文件夹里的 360 素材（.OSV + 同名 SRT）。"""
    out = []
    for fi, folder in enumerate(folders or []):
        f = Path(str(folder)).expanduser()
        if not f.is_dir():
            continue
        for osv in sorted(f.rglob("*.OSV")):
            srt = osv.with_suffix(".SRT")
            if not srt.is_file():
                srt = osv.with_suffix(".srt")
            out.append({
                "folder_index": fi,
                "relative_path": str(osv.relative_to(f)),
                "name": osv.name,
                "size_mb": round(osv.stat().st_size / 1024 / 1024, 1),
                "srt": str(srt) if srt.is_file() else "",
                "srt_name": srt.name if srt.is_file() else "",
                "lrf": str(osv.with_suffix(".LRF")) if osv.with_suffix(".LRF").is_file() else "",
            })
    return out


def _duration(video: Path) -> float:
    probe = str(Path(_ffmpeg()).with_name("ffprobe.exe"))
    r = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(video)],
                       capture_output=True, text=True, timeout=300)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def grab_lens(video: Path, idx: int, t_sec: float, size: int) -> np.ndarray:
    """抽某一时刻、某一路鱼眼帧。"""
    p = subprocess.run(
        [_ffmpeg(), "-y", "-loglevel", "error", "-ss", "%.3f" % t_sec, "-i", str(video),
         "-map", "0:v:%d" % idx, "-frames:v", "1",
         "-vf", "scale=%d:%d" % (size, size), "-f", "image2pipe",
         "-vcodec", "png", "-"],
        capture_output=True, timeout=1800)
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError("抽帧失败（流 %d）: %s" % (idx, (p.stderr or b"")[:200]))
    return np.asarray(Image.open(io.BytesIO(p.stdout)).convert("RGB"))


def render_equirect(video: Path, t_sec: float, ew: int = 2048,
                    fov_deg: float = pano360.DEFAULT_FOV, quality: int = 88) -> bytes:
    """渲染一张等距柱状 JPEG，返回字节。"""
    size = max(1024, min(2160, ew // 2))       # 单路抽帧尺寸：跟着输出走，别浪费
    up = grab_lens(video, 0, t_sec, size)
    dn = grab_lens(video, 1, t_sec, size)
    g = pano360.Fisheye360(fov_deg=fov_deg)
    equi = g.stitch(up, dn, ew=ew)
    buf = io.BytesIO()
    Image.fromarray(equi).save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def render_cached(video: Path, cache: Path, t_sec: float, ew: int = 2048,
                  fov_deg: float = pano360.DEFAULT_FOV) -> tuple[bytes, bool]:
    """带磁盘缓存的渲染。返回 (jpeg 字节, 是否命中缓存)。"""
    key = hashlib.sha1(
        ("%s|%.2f|%d|%.1f" % (str(video), t_sec, ew, fov_deg)).encode("utf-8")
    ).hexdigest()[:16]
    dst = cache / ("%s.jpg" % key)
    if dst.is_file():
        try:
            return dst.read_bytes(), True
        except OSError:
            pass
    with _render_lock:
        # 双检：等锁的时候别人可能已经渲好了
        if dst.is_file():
            try:
                return dst.read_bytes(), True
            except OSError:
                pass
        data = render_equirect(video, t_sec, ew=ew, fov_deg=fov_deg)
        try:
            tmp = dst.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(dst)
        except OSError:
            pass
        _trim_cache(cache)
    return data, False


def _north_cached(video: Path, srt: Path | None) -> dict | None:
    """只读北向缓存；没有就返回 None（**不现算**）。"""
    if not srt or not Path(srt).is_file():
        return None
    try:
        key = hashlib.sha1(
            ("%s|%d|%d" % (str(video), video.stat().st_size,
                           Path(srt).stat().st_size)).encode("utf-8")).hexdigest()[:16]
        dst = cache_dir(video.parent) / ("north_%s.json" % key)
        if dst.is_file():
            j = json.loads(dst.read_text(encoding="utf-8"))
            j["cached"] = True
            return j
    except (OSError, ValueError):
        pass
    return None


def north_for(video: Path, srt: Path | None, t_guess: float = 30.0) -> dict:
    """算并**缓存**这段素材的 north_yaw。

    为什么自动算而不是写死一张表：素材会换（用户录了新的一段），
    写死的表迟早对不上，而且错误会静默传下去（画面转错方向却不报错）。

    缓存落在 `<视频目录>/.pano_cache/north_<sha1>.json`，键里带视频大小与
    SRT 大小 —— 换了素材自然失效。
    """
    if not srt or not Path(srt).is_file():
        return {"ok": False, "why": "这个架次没有 SRT，无法用太阳定北向"}
    try:
        import pano360_north as pn
    except Exception as e:
        return {"ok": False, "why": "无法导入 pano360_north: %s" % e}

    key = hashlib.sha1(
        ("%s|%d|%d" % (str(video), video.stat().st_size, Path(srt).stat().st_size)
         ).encode("utf-8")).hexdigest()[:16]
    d = cache_dir(video.parent)
    dst = d / ("north_%s.json" % key)
    if dst.is_file():
        try:
            j = json.loads(dst.read_text(encoding="utf-8"))
            j["cached"] = True
            return j
        except (OSError, ValueError):
            pass

    try:
        # 采样时刻：太阳较高、日面清晰的时刻。**每个时刻都要过"可信度检查"**，
        # 不过就不接受 —— 宁可返回 unknown，也不给一个错的方向。
        #
        # 为什么这么严：这个场景（高原河谷 + 河面反光 + 建筑反光）里有**多个亮源**，
        # "找最亮点当太阳"实测会抓到水面反光。某段素材在 t=30/120/300 三个时刻
        # 测出三个完全不同的方向（r/R 0.573 / 0.579 / 0.659，phi +72° / +69° / −98°），
        # 说明它根本没找到日面。**错的方向比没有方向更危险**（画面会指错南）。
        good = None
        tried = []
        for t in (t_guess, max(5.0, t_guess / 2), 5.0, 60.0, 120.0, 300.0):
            try:
                north, diag = pn.north_yaw_for(video, Path(srt), t)
            except Exception as e:
                tried.append({"t": t, "why": str(e)})
                continue
            # 可信度有三道：
            #   a) 日面必须落在**由太阳高度角预测的半径**附近（水面反光不会落这儿）
            #   b) 过曝块必须**像个盘**：够大，但**也不能太大**。
            #      实测真日面在这个尺度上是 1700~3000 px；见过 305 px 的碎片
            #      （给出 +71° 的错方向），也见过 **17509 px 的地平线晨昏光带**
            #      （贡嘎那批清晨素材，太阳高度角只有 +0.07°）。
            #      "过大"这一侧就是被它钻过去的。
            #   c) 太阳本身得升得够高（在 `pano360_north` 里判，
            #      见 MIN_SUN_ELEVATION_DEG —— 那是最根本的一道）
            delta = abs(diag.get("r_delta") or 9.9)
            blob = int(diag.get("sun_blob_px") or 0)
            diag["trusted"] = bool(delta <= 0.06 and 800 <= blob <= 8000)
            diag["north_yaw"] = round(north, 2)
            tried.append(diag)
            if diag["trusted"]:
                good = {"ok": True, **diag, "cached": False}
                break
        if good is None:
            # 把**真实的**失败原因说出来，别一律怪"反光"。
            # 踩过：贡嘎那批是"太阳太低"（+0.07°），但这里的文案写的是
            # "多半是水面/建筑反光"，把用户往错方向引。
            reasons = [str(x.get("why")) for x in tried if x.get("why")]
            raised = [str(x.get("why")) for x in tried
                      if "太阳高度角" in str(x.get("why"))]
            if raised:
                why = raised[0]
            elif reasons:
                why = ("太阳位置不可信（找到的亮点对不上理论日面位置）—— "
                       "北向留空，不猜。试过的时刻：%s" % reasons[0])
            else:
                why = ("试过的时刻都量不出日面（多半是太阳被山/云挡住，"
                       "或素材太短）—— 北向留空，不猜")
            return {"ok": False, "cached": False, "why": why, "tried": tried}
        last = good
        try:
            tmp = dst.with_suffix(".tmp")
            tmp.write_text(json.dumps(last, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(dst)
        except OSError:
            pass
        return last
    except Exception as e:
        return {"ok": False, "why": str(e)}


def render_perspective(video: Path, cache: Path, t_sec: float,
                       yaw_deg: float, pitch_deg: float,
                       fov_deg: float = 75.0, out_w: int = 480,
                       quality: int = 86) -> tuple[bytes, bool]:
    """渲染一张**透视小图**（从 360 全景按某方向裁），返回 (jpeg, 命中缓存)。

    用途：检索结果卡片的缩略图。360 的整张全景当缩略图没法看（2:1 展开图），
    必须按"看哪个方向"投影成正常透视才有判读价值。

    **注意锁**：底下调的 `render_cached` 自己会拿 `_render_lock`，而那是一把
    **不可重入**的 `threading.Lock` —— 如果本函数也拿它就会**死锁**
    （实测：进程挂住、缓存目录毫无动静）。所以这里**不拿锁**：
    拼接那一步由 `render_cached` 保护，透视裁剪是纯 CPU、无共享状态。
    """
    key = hashlib.sha1(
        ("P|%s|%.2f|%.1f|%.1f|%.1f|%d" % (str(video), t_sec, yaw_deg, pitch_deg,
                                          fov_deg, out_w)).encode("utf-8")
    ).hexdigest()[:16]
    dst = cache / ("p%s.jpg" % key)
    if dst.is_file():
        try:
            return dst.read_bytes(), True
        except OSError:
            pass
    # 先从全景（它的渲染本身有缓存）拿底，再裁 —— 同一时刻的不同方向共用一次拼接
    eq_jpg, _ = render_cached(video, cache, t_sec, ew=2048)
    equi = np.asarray(Image.open(io.BytesIO(eq_jpg)).convert("RGB"))
    crop = pano360.perspectives_from_equirect(
        equi, yaw_deg, pitch_deg, fov_deg=fov_deg, out_w=out_w)
    buf = io.BytesIO()
    Image.fromarray(crop).save(buf, format="JPEG", quality=quality)
    data = buf.getvalue()
    try:
        tmp = dst.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(dst)
    except OSError:
        pass
    _trim_cache(cache)
    return data, False


def find_360_frames(project_name: str, lat: float, lng: float, limit: int = 60,
                    mode: str = "passes") -> dict:
    """在项目的 360 素材里检索"哪些时刻拍到了这一点"。

    与 `coverage_api.find_frames` 分开：那条依赖相机姿态（把点投到画面检验
    |xi|,|yi| <= 1），而 360 的 SRT 里没有 `gb_yaw`/`gb_pitch` —— 也**不需要**，
    全景的覆盖是圆环、判据只是"地面距离落在内外半径之间"。
    见 `pano360_coverage.find_frames_360`。
    """
    import project_manager as pm
    import pano360_coverage as pc

    project = pm.load_project(project_name)
    folders = [item.get("path") for item in (project.get("folders") or [])
               if item.get("path")]
    items = find_360_videos(folders)
    if not items:
        return {"ok": True, "total": 0, "hits": [], "note": "这个项目里没有 360 素材。"}

    all_hits = []
    skipped = []
    for it in items:
        if not it.get("srt"):
            skipped.append({"name": it["name"], "why": "没有同名 SRT，无法定位"})
            continue
        srt = Path(it["srt"])
        try:
            recs = pm.parse_dji_srt(srt)
            tele = pm.load_srt_telemetry(srt)
        except Exception as e:
            skipped.append({"name": it["name"], "why": "读 SRT 失败: %s" % e})
            continue
        step = 3
        try:
            import coverage as cov
            step = cov.TELEMETRY_STEP
        except Exception:
            pass
        n = int(tele.get("count") or 0)
        times = tele.get("times") or []
        alts = tele.get("alt") or []
        samples = []
        for i in range(n):
            j = i * step
            if j >= len(recs):
                break
            r = recs[j]
            if not r.get("latitude") or not r.get("longitude"):
                continue
            samples.append((float(times[i]) if i < len(times) else 0.0,
                            float(r["latitude"]), float(r["longitude"]),
                            float(alts[i]) if i < len(alts) and alts[i] else 0.0))
        res = pc.find_frames_360(samples, float(lat), float(lng),
                                 limit=limit, mode=mode)
        # 北向：缩略图要朝向目标点，需要它把"地理方位"换算成"相机系经度"
        north = north_for(Path(it["srt"]).with_suffix(".OSV"), srt)
        north_yaw = north.get("north_yaw") if north.get("ok") else None
        for h in res["hits"]:
            h = dict(h)
            # 相机系经度：图上的 lon=0 对应"相机前方"。
            #   地理方位 = north_yaw + lon_cam  =>  lon_cam = bearing - north_yaw
            # （north_yaw = az_theory − phi，见 pano360_north 的推导）
            lon_cam = None
            if north_yaw is not None:
                lon_cam = ((h["bearing_deg"] - north_yaw) + 180.0) % 360.0 - 180.0
            h.update({
                "srt": str(srt), "srt_name": srt.name,
                "video_path": str(Path(it["srt"]).with_suffix(".OSV")),
                "video_name": Path(it["srt"]).with_suffix(".OSV").name,
                "folder_index": it["folder_index"],
                "relative_path": str(Path(it["relative_path"]).with_suffix(".OSV")),
                "stream": "360",
                # 前端"跳视频"要这三个；360 用同一套
                "target_seconds": round(h["t"], 3),
                "player_seek_seconds": round(h["t"], 3),
                "start_seconds": round(max(0.0, h["t"] - 3.0), 3),
                # 360 没有云台姿态，这两个字段明确给 None（不是 0）
                "pitch_deg": None, "yaw_deg": None, "focal_mm": None,
                "zoomed": False,
                "category": "sphere",
                "recommended": True,
                # 缩略图/预览器用：把镜头转向这一点所需的方向
                "north_yaw": north_yaw,
                "look_yaw_deg": (round(lon_cam, 2) if lon_cam is not None else None),
                # 目标在画面里的仰角（负数=在下方）。俯仰要看向它
                "look_pitch_deg": round(h["elev_deg"], 2),
            })
            all_hits.append(h)
    all_hits.sort(key=lambda h: h["ground_m_per_px"])
    return {"ok": True, "total": len(all_hits), "mode": mode,
            "hits": all_hits[:limit], "skipped": skipped,
            "note": ("全景素材：覆盖是圆环，判据是地面距离而不是画面位置；"
                     "没有云台姿态可报，所以 pitch/yaw 为 null。")}


def video_info(video: Path, srt: Path | None, want_north: bool = True) -> dict:
    """给前端的元信息：时长、时长内的定位范围（方便画时间轴）。"""
    info = {
        "name": video.name,
        "size_mb": round(video.stat().st_size / 1024 / 1024, 1),
        "duration": _duration(video),
        "north_yaw": NORTH_YAW.get(video.name),
    }
    if want_north and info["north_yaw"] is None:
        # **只读缓存，绝不在这里现算** —— 现算要给每段抽帧（几秒/段），
        # 而这个接口是 UI 进页面就调的，会把界面卡住（我第一版就是这样）。
        # 现算发生在真正需要的时候：检索命中出卡片（见 find_360_frames）。
        cached = _north_cached(video, srt)
        if cached is not None:
            info["north"] = cached
            info["north_yaw"] = cached["north_yaw"]
    if srt and srt.is_file():
        try:
            import project_manager as pm
            tele = pm.load_srt_telemetry(srt)
            t = tele.get("times") or []
            recs = pm.parse_dji_srt(srt)
            nz = [r for r in recs if r.get("latitude") and r.get("longitude")]
            if t:
                info["srt_span"] = [round(t[0], 2), round(t[-1], 2)]
            if nz:
                info["bbox"] = [
                    min(r["latitude"] for r in nz), min(r["longitude"] for r in nz),
                    max(r["latitude"] for r in nz), max(r["longitude"] for r in nz),
                ]
                info["gps_points"] = len(nz)
            info["samples"] = len(recs)

            # 飞行剖面：这趟是**悬停延时**还是**真实航线**。
            #
            # 为什么要机器判、还要给用户看（2026-10-15 的教训）：
            # 我把贡嘎那趟真航线（漂移 1110 m）当成了悬停，依据还是一个
            # 采样错了的数字。用户对素材的判断（"这两个是悬停延时"）是对的，
            # 但**不该靠人去认** —— 当场量出来、标在界面上。
            try:
                import coverage as _cov
                import pano360_coverage as _pc
                step = _cov.TELEMETRY_STEP
                samples = []
                for i in range(int(tele.get("count") or 0)):
                    j = i * step
                    if j >= len(recs):
                        break
                    samples.append((
                        float(t[i]) if i < len(t) else 0.0,
                        recs[j]["latitude"], recs[j]["longitude"],
                        (tele["alt"][i] if i < len(tele.get("alt") or []) else 0.0),
                    ))
                info["profile"] = _pc.flight_profile(samples)
            except Exception as e:
                info["profile_error"] = str(e)
        except Exception as e:
            info["srt_error"] = str(e)
    return info
