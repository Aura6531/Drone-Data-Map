"""DJI 照片元数据读取 + 「镜头中心点对应地面位置」解算。

为什么单独一个模块：照片这条路和视频那条路的数据来源不同（视频靠 SRT/内嵌轨，
照片靠 JPEG 的 EXIF + XMP），先把它独立出来，方便单独验证和复用。

关键点（用户需求）：地图上要标的是**镜头光轴打到地面的那个点**（照片中心对应的地物目标），
不是飞机自己的位置。做法与视频视场同一套「平地假设」：
    水平距离 d = 离地高度 h / tan(俯角)
    目标点   = 从飞机位置沿云台偏航方向走 d 米
俯角 = |GimbalPitchDegree|（DJI 约定：0 水平，负值向下）。

XMP 直接从 JPEG 字节里取，不需要 ExifTool。
"""

import math
import pathlib
import re
import sys

EARTH_R = 6378137.0          # WGS-84 长半轴（米）


# ------------------------------------------------------------
# 读取
# ------------------------------------------------------------

def _dms_to_deg(value):
    try:
        parts = [float(x) for x in value]

    except (TypeError, ValueError):
        return None

    if len(parts) == 3:
        return parts[0] + parts[1] / 60 + parts[2] / 3600

    return None


def read_jpeg_meta(path):
    """读一张 DJI JPEG：EXIF 的 GPS + XMP 里 drone-dji 的那一堆。

    返回 dict；缺的字段为 None。读不动就抛异常，由调用方决定怎么处理。
    """

    from PIL import ExifTags, Image

    path = pathlib.Path(path)
    raw = path.read_bytes()

    meta = {
        "path": str(path),
        "name": path.name,
        "lat": None, "lon": None,
        "alt_relative": None, "alt_absolute": None,
        "gimbal_pitch": None, "gimbal_yaw": None, "gimbal_roll": None,
        "flight_yaw": None, "flight_pitch": None,
        "lens_position": None, "lens_infinite": None,
        "model": None, "serial": None, "camera": None,
        # 像素尺寸与"是不是全景"。
        #
        # 为什么要记：DJI 的全景照片是 **2:1 等距柱状**（实测 15520×7760）。
        # 以前它们被当成普通照片塞进照片图层，缩略图就是一张**被拉扁的球面展开图**，
        # 完全看不懂。知道它是全景之后，前端可以改用 360 播放器那条路去看
        # （等距柱状 -> 透视取景的代码已经写好了）。
        "width": None, "height": None,
        "panorama": False,
        "lrf": {},
        "source": "",
    }

    # ---- EXIF：GPS（度分秒）与机型 ----
    image = Image.open(path)
    # 尺寸从同一个 PIL 句柄顺手拿，不额外读一次文件。
    # 全景判定：宽高比接近 2:1 且足够大（普通照片是 16:9 / 4:3，不会命中）。
    try:
        meta["width"], meta["height"] = image.size
        w, h = image.size
        meta["panorama"] = bool(
            h > 0 and w >= 4000 and 1.90 <= (w / float(h)) <= 2.10)
    except Exception:
        pass
    exif = image.getexif()
    gps = exif.get_ifd(ExifTags.IFD.GPSInfo)

    lat = lon = None
    lat_ref = lon_ref = ""

    for tag, value in gps.items():
        name = ExifTags.GPSTAGS.get(tag, tag)

        if name == "GPSLatitude":
            lat = _dms_to_deg(value)

        elif name == "GPSLongitude":
            lon = _dms_to_deg(value)

        elif name == "GPSAltitude":
            meta["alt_absolute"] = float(value)

        elif name == "GPSLatitudeRef":
            lat_ref = str(value)

        elif name == "GPSLongitudeRef":
            lon_ref = str(value)

    if lat is not None:
        meta["lat"] = -lat if lat_ref.upper().startswith("S") else lat

    if lon is not None:
        meta["lon"] = -lon if lon_ref.upper().startswith("W") else lon

    for tag, value in exif.items():
        name = ExifTags.TAGS.get(tag, tag)

        if name == "Model":
            meta["model"] = str(value)

    # ---- XMP：云台角、相对高度、激光目标 ----
    marker = raw.find(b"http://ns.adobe.com/xap/1.0/")

    if marker >= 0:
        start = raw.find(b"<x:xmpmeta", marker)
        end = raw.find(b"</x:xmpmeta>", start)

        if start >= 0 and end > start:
            xmp = raw[start:end + len(b"</x:xmpmeta>")].decode("utf-8", "replace")
            fields = dict(re.findall(r'drone-dji:([A-Za-z]+)="([^"]*)"', xmp))
            meta["source"] = "xmp"

            def number(key):
                text = (fields.get(key) or "").strip().lstrip("+")

                try:
                    return float(text)

                except ValueError:
                    return None

            meta["lat"] = number("GpsLatitude") or meta["lat"]
            meta["lon"] = number("GpsLongitude") or meta["lon"]
            meta["alt_relative"] = number("RelativeAltitude")
            meta["alt_absolute"] = number("AbsoluteAltitude") or meta["alt_absolute"]
            meta["gimbal_pitch"] = number("GimbalPitchDegree")
            meta["gimbal_yaw"] = number("GimbalYawDegree")
            meta["gimbal_roll"] = number("GimbalRollDegree")
            meta["flight_yaw"] = number("FlightYawDegree")
            meta["flight_pitch"] = number("FlightPitchDegree")
            meta["lens_position"] = number("LensPosition")
            meta["lens_infinite"] = number("LensInfinitePosition")
            meta["model"] = fields.get("DroneModel") or meta["model"]
            meta["serial"] = fields.get("DroneSerialNumber")
            meta["camera"] = fields.get("ImageSource")

            meta["lrf"] = {
                "status": fields.get("LRFStatus"),
                "distance": number("LRFTargetDistance"),
                "lat": number("LRFTargetLat"),
                "lon": number("LRFTargetLon"),
                "abs_alt": number("LRFTargetAbsAlt"),
                "rel_alt": number("LRFTargetAlt"),
            }

    return meta


# ------------------------------------------------------------
# 解算：镜头中心点对应的地面位置
# ------------------------------------------------------------

def destination(lat, lon, bearing_deg, distance_m):
    """从 (lat, lon) 沿 bearing（正北顺时针，度）走 distance 米后的坐标。"""

    angular = distance_m / EARTH_R
    bearing = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular)
        + math.cos(lat1) * math.sin(angular) * math.cos(bearing)
    )

    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )

    return math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180


def ground_target(meta, ground_elevation=None, prefer_lrf=True):
    """算「照片中心对应的地面点」。

    平地假设：h = |相对高度|（相对起飞点，视频那边也是这个假设，保持一致），
    俯角 = |云台俯仰|。

    距离优先用激光（用户要求：有激光就用激光；水面/无激光的照片会缺）：
      1) 有激光斜距      -> d = 斜距 × cos(俯角)        直接用实测射线，不依赖"落差"假设
      2) 有激光目标高程  -> h = 飞机绝对高 - 目标绝对高，d = h / tan(俯角)
                           等价于拿到了当地真实地面高程
      3) 都没有          -> d = 相对高度 / tan(俯角)     平地假设（原来的算法）
    将来接 DEM 或手工指定平均高程时，就是第 2 级：把 ground_elevation 传进来即可
    （此时 h = 绝对高度 - ground_elevation）。

    返回 dict（含 distance / lat / lon / method），算不出来返回 None。
    """

    lat, lon = meta.get("lat"), meta.get("lon")
    pitch = meta.get("gimbal_pitch")
    yaw = meta.get("gimbal_yaw")

    if lat is None or lon is None or pitch is None or yaw is None:
        return None

    depression = abs(float(pitch))

    # 平视或朝上：光轴不落地，没有"中心点对应的地面位置"
    if depression < 1.0:
        return None

    lrf = meta.get("lrf") or {}

    # 只有测距状态正常才算"有激光数据"。
    # 实测发现 LRFStatus 取值只有 Normal / TooFar 两种：
    #   Normal = 有效回波（此时一定有斜距与目标点）
    #   TooFar = 超出量程（没有斜距、没有目标点，但其它字段可能残留数值）
    # 残留值不是一次有效测量，拿它当"当地地面高程"会算出错误的中心点，所以必须挡住。
    lrf_status = (lrf.get("status") or "").strip()
    lrf_valid = (lrf_status == "Normal") if lrf_status else bool(lrf.get("distance"))

    slant = lrf.get("distance") if (prefer_lrf and lrf_valid) else None
    target_abs = lrf.get("abs_alt") if (prefer_lrf and lrf_valid) else None
    drone_abs = meta.get("alt_absolute")
    relative = meta.get("alt_relative")

    method = ""
    detail = ""
    distance = None

    if slant and float(slant) > 0:
        # 1) 激光斜距：直接就是这条射线的实测长度
        distance = float(slant) * math.cos(math.radians(depression))
        method = "lrf-slant"
        detail = f"激光斜距 {float(slant):.1f} m"

    elif target_abs is not None and drone_abs is not None:
        # 2) 激光目标绝对高程：拿到当地地面高程，落差不再靠"相对起飞点"猜
        height = float(drone_abs) - float(target_abs)

        if height > 0.5:
            distance = height / math.tan(math.radians(depression))
            method = "lrf-target-alt"
            detail = f"落差 {height:.1f} m（飞机绝对高 - 激光目标高）"

    if distance is None:
        # 将来这里可以换成 DEM 查询或用户指定的平均高程
        height = ground_elevation is not None and drone_abs is not None \
            and (float(drone_abs) - float(ground_elevation)) or relative

        if height is None:
            return None

        height = abs(float(height))

        if height <= 0.5:
            return None

        distance = height / math.tan(math.radians(depression))
        method = "flat-ground"
        detail = f"平地假设，落差 {height:.1f} m（相对起飞点）"

    target_lat, target_lon = destination(lat, lon, float(yaw), distance)

    # 数据质量标签。前端按 === 'measured' 判定，所以这里必须用英文标识符
    # （历史坑：前端已改成 'measured'，后端还在发「实测」，导致每一组都被
    #   当成「位置不准」并显示中文原值）。
    if method == "flat-ground":
        accuracy = "inaccurate"
        accuracy_note = (
            "Laser rangefinder failed (LRFStatus=" + (lrf_status or "none") + ")"
            if lrf_status and lrf_status != "Normal"
            else "No laser data for this photo"
        ) + "; ground position estimated on a flat-earth assumption"
    else:
        accuracy = "measured"
        accuracy_note = "Ground position derived from the laser rangefinder"

    return {
        "lat": target_lat,
        "lon": target_lon,
        "distance": distance,
        "bearing": float(yaw),
        "depression": depression,
        "method": method,
        "detail": detail,
        "accuracy": accuracy,
        "accuracy_note": accuracy_note,
        "lrf_point": (lrf.get("lat"), lrf.get("lon")) if lrf.get("lat") else None,
    }


_META_CACHE = {}


def build_photo_payload(folders):
    """给前端用的照片数据：按目标点分好组 + 统计。folders 是项目里的文件夹路径。"""

    photos = collect_photos(folders, cache=_META_CACHE)
    groups = group_photos(photos)

    with_target = sum(1 for _ in photos if ground_target(_))

    return {
        "photos": len(photos),
        "scanned": len(photos),
        "groups": groups,
        "counts": {
            "groups": len(groups),
            "photos": len(photos),
            "with_target": with_target,
            "inaccurate": sum(1 for g in groups if g["accuracy"] != "实测"),
            "merged": sum(1 for g in groups if g["count"] > 1),
        },
    }


def photo_stamp(meta):
    """照片的时刻（秒级）。文件名里那串时间就是拍摄时刻，优先用它。"""

    match = re.search(r"DJI_(\d{8})(\d{6})_", meta.get("name") or "")

    if match:
        return f"{match.group(1)}_{match.group(2)}"

    return ""


def photo_seq(meta):
    """文件名里的**序号**（`DJI_20260924100146_0020_T` 里的 0020）。

    这是「同一次按快门」的标识：一次快门会同时出一张 V（可见光）与一张 T（热成像），
    两张的序号相同。**但两者的文件名时刻可能差 1 秒** —— 热成像文件小、先写完，
    可见光文件大、后写完（用户 2026-10-07 说明的现象）。
    所以配对必须用序号，不能用「同一秒」。
    """

    match = re.search(r"DJI_\d{8}\d{6}_(\d+)_", meta.get("name") or "")

    return match.group(1) if match else ""


# 相机优先序：用户要求「优先展示变焦，用大图」，然后广角可见光，最后热成像
CAMERA_ORDER = {"ZoomCamera": 0, "WideCamera": 1, "InfraredCamera": 2}


def group_photos(metas, max_gap_m=8.0):
    """把「同一目标点」的多张照片合并成一组（用户要求：地图上合并成一个点）。

    分组规则（2026-10-07 改）：**同一架次文件夹里、文件名序号相同**的算一组。
    一次按快门会同时出 V（可见光，文件大）与 T（热成像，文件小），两张序号一样；
    但文件名里的**时刻**可能差 1 秒 —— 大文件后写完。所以原来的「同一秒」键
    既会把一对拆成两个点（实测 26 个序号），也会把不同目标在同一秒拍的并到一起
    （实测 1 组）。序号 + 文件夹才是「同一次按快门」。

    max_gap_m 只用来**记录**两张解算点的距离（写进 group 的 spread_m 供诊断），
    **不再拿它拆组** —— 同一目标的 T/V 虽然同一次拍，但两支镜头的解算点实测能差
    9~19 m（激光落点/视场不同），拿 8 m 卡会把真的一对拆开。

    组内排序：变焦优先 -> 广角 -> 热成像（前端按这个顺序展示，第一张用大图）。
    """

    groups = []

    for meta in metas:
        target = ground_target(meta)

        if not target:
            continue

        stamp = photo_stamp(meta)
        seq = photo_seq(meta)
        folder = str(pathlib.Path(meta["path"]).parent)

        # 认不出序号的（文件名不合规范）退回「同一秒」，至少不比以前差
        key = (folder, seq) if seq else (folder, stamp + "#stamp")

        placed = False

        for group in groups:
            if group["key"] != key:
                continue

            group["members"].append((meta, target))
            group["accuracy"] = group["accuracy"] if group["accuracy"] == target["accuracy"] else "混合"
            group["lat"] = (group["lat"] * (len(group["members"]) - 1) + target["lat"]) / len(group["members"])
            group["lon"] = (group["lon"] * (len(group["members"]) - 1) + target["lon"]) / len(group["members"])

            # 组时刻取组内最早的那张（T 先写完时仍然是它，V 先写时也一样）
            if stamp and stamp < group["stamp"]:
                group["stamp"] = stamp

            placed = True
            break

        if not placed:
            groups.append({
                "key": key,
                "folder": folder,
                "stamp": stamp,
                "lat": target["lat"],
                "lon": target["lon"],
                "accuracy": target["accuracy"],
                "members": [(meta, target)],
            })

    result = []

    for group in groups:
        members = sorted(
            group["members"],
            key=lambda item: CAMERA_ORDER.get(item[0].get("camera"), 9),
        )

        # 组内两张（或更多）解算点相距多远 —— 只作诊断信息，不参与拆组
        spread = 0.0

        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                spread = max(spread, haversine(
                    members[i][1]["lat"], members[i][1]["lon"],
                    members[j][1]["lat"], members[j][1]["lon"],
                ))

        result.append({
            "stamp": group["stamp"],
            "folder": group["folder"],
            "lat": group["lat"],
            "lon": group["lon"],
            "accuracy": group["accuracy"],
            "count": len(members),
            "lead": members[0][0].get("camera"),          # 前端用这张当大图
            "spread_m": round(spread, 1),                 # 组内解算点最大间距（诊断用）
            "members": [
                {
                    "name": meta["name"],
                    "folder": str(pathlib.Path(meta["path"]).parent),
                    "camera": meta.get("camera"),
                    "accuracy": target["accuracy"],
                    "accuracy_note": target["accuracy_note"],
                    "lat": target["lat"],
                    "lon": target["lon"],
                    "distance": round(target["distance"], 1),
                    "depression": round(target["depression"], 1),
                    "gimbal_yaw": meta.get("gimbal_yaw"),
                    "relative_alt": meta.get("alt_relative"),
                    "drone_lat": meta["lat"],
                    "drone_lon": meta["lon"],
                    # 全景照片（2:1 等距柱状）要单独标出来 —— 前端拿去开 360 播放器，
                    # 而不是当普通照片显示一张被拉扁的展开图。
                    "panorama": bool(meta.get("panorama")),
                    "width": meta.get("width"),
                    "height": meta.get("height"),
                }
                for meta, target in members
            ],
        })

    return result


def collect_photos(folders, cache=None):
    """扫这些文件夹里的 JPG，逐张读元数据（带内存缓存，按 路径+大小+mtime 失效）。"""

    cache = cache if cache is not None else {}
    metas = []

    for folder in folders:
        root = pathlib.Path(folder)

        if not root.is_dir():
            continue

        paths = sorted({
            p.resolve()
            for p in list(root.glob("**/*.JPG")) + list(root.glob("**/*.jpg"))
        })

        for path in paths:
            try:
                stat = path.stat()
            except OSError:
                continue

            key = (str(path), stat.st_size, int(stat.st_mtime))
            meta = cache.get(key)

            if meta is None:
                try:
                    meta = read_jpeg_meta(path)

                except Exception:
                    continue

                cache[key] = meta

            metas.append(meta)

    return metas


def haversine(a_lat, a_lon, b_lat, b_lon):
    """两点间地面距离（米）—— 用来和激光测距交叉验证。"""

    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = p2 - p1
    dl = math.radians(b_lon - a_lon)

    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2

    return 2 * EARTH_R * math.asin(math.sqrt(h))


# ------------------------------------------------------------
# 自检：拿真实照片跑，并与激光测距对比
# ------------------------------------------------------------

def main():
    root = pathlib.Path(__file__).resolve().parent.parent

    # 注意：Windows 上 glob 不区分大小写，"*.JPG" 与 "*.jpg" 会匹配同一批文件，
    # 两个模式相加会重复计算（这里曾经把 244 张算成 488 张）。用集合按绝对路径去重。
    photos = sorted({
        p.resolve()
        for p in list((root / "Data").glob("**/*.JPG")) + list((root / "Data").glob("**/*.jpg"))
    })

    if not photos:
        raise SystemExit("Data/ 下没有 JPG 可读")

    print(f"  Data/ 下照片 {len(photos)} 张 —— 逐张自检（有激光就用激光）\n")

    stats = {"lrf-slant": 0, "lrf-target-alt": 0, "flat-ground": 0, "no-target": 0, "error": 0}
    no_lrf = 0
    max_diff = 0.0
    diffs = []

    for path in photos:
        try:
            meta = read_jpeg_meta(path)

        except Exception:
            stats["error"] += 1
            continue

        target = ground_target(meta)
        lrf = meta.get("lrf") or {}

        if not (lrf.get("distance") or lrf.get("abs_alt")):
            no_lrf += 1

        if not target:
            stats["no-target"] += 1
            continue

        stats[target["method"]] = stats.get(target["method"], 0) + 1

        if target.get("lrf_point") and target["lrf_point"][0]:
            diff = haversine(target["lat"], target["lon"],
                             target["lrf_point"][0], target["lrf_point"][1])
            diffs.append(diff)
            max_diff = max(max_diff, diff)

    print("  解算方式分布：")
    labels = {
        "lrf-slant": "① 激光斜距（最准）",
        "lrf-target-alt": "② 激光目标高程（相当于当地真实地面高程）",
        "flat-ground": "③ 平地假设（相对起飞点，无激光时）",
        "no-target": "   算不出（俯角太平 / 坐标或高度缺失）",
        "error": "   读元数据失败",
    }

    for key, label in labels.items():
        print(f"    {label:44} {stats.get(key, 0):4} 张")

    print(f"\n  没有激光数据的照片：{no_lrf} 张（水面反射/超出量程等）")
    print(f"  其中标为「位置不准」的：{stats.get('flat-ground', 0)} 张"
          f"（走平地假设 -> 交付时必须带这个标签）")

    if diffs:
        average = sum(diffs) / len(diffs)
        print(f"  解算点与激光实测点：平均相距 {average:.1f} m，最大 {max_diff:.1f} m"
              f"（共 {len(diffs)} 张可比）")

    print("\n  前 5 张明细：")

    for path in photos[:5]:
        meta = read_jpeg_meta(path)
        target = ground_target(meta)
        lrf = meta.get("lrf") or {}

        print(f"\n  {path.name}")
        print(f"    飞机 {meta['lat']:.6f}, {meta['lon']:.6f}   相对高 {meta['alt_relative']} m"
              f"   绝对高 {meta['alt_absolute']} m")
        print(f"    云台 俯仰 {meta['gimbal_pitch']}°  偏航 {meta['gimbal_yaw']}°   {meta['camera']}")

        if target:
            print(f"    中心点 {target['lat']:.6f}, {target['lon']:.6f}"
                  f"   水平 {target['distance']:.1f} m   [{target['method']}]"
                  f"   质量标签：{target['accuracy']}")
            print(f"           依据：{target['detail']}")
            print(f"           说明：{target['accuracy_note']}")

        if lrf.get("lat"):
            print(f"    激光点 {lrf['lat']:.6f}, {lrf['lon']:.6f}   斜距 {lrf.get('distance')} m")

    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
