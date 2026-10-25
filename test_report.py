# 标记点报告（Word）后端：逆地理编码 / 地图截图 / 视频抽帧 / docx 结构
#
# 这四块都容易「看起来对但结果是坏的」，所以尽量跑真东西：
#   - 逆地理编码：替掉 urlopen 喂真实返回结构（不发真请求，结果确定）
#   - 地图截图：替掉瓦片获取，喂真 PNG 瓦片，检查尺寸 / 底图跟随 / 标点
#   - 视频抽帧：真跑 ffmpeg 抽真原片（Data 下没有 MP4 就跳过这一段）
#   - docx：真生成再读回来，检查书签、超链接目录、表格、图片
import io
import json
import pathlib
import re
import socket
import subprocess
import sys
import threading
import urllib.request
import zipfile

sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "Code"))

import project_manager as pm  # noqa: E402

ok = True


def chk(cond, label, extra=""):
    global ok
    ok &= bool(cond)
    print(f"  {'[OK]' if cond else '[FAIL]'} {label}{(' -> ' + str(extra)) if extra else ''}")


def raises(callable_obj, *args, **kwargs):
    """调用应当抛异常；返回异常消息（没抛就返回 None）。"""
    try:
        callable_obj(*args, **kwargs)
        return None
    except Exception as e:
        return str(e) or type(e).__name__


# ---------------------------------------------------------------
# 1) 逆地理编码
# ---------------------------------------------------------------

print("=== 1) 逆地理编码：地址拼装 ===")


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


real_urlopen = urllib.request.urlopen
sent_urls = []


def install_fake_response(payload):
    def fake_urlopen(request, timeout=None):
        sent_urls.append(getattr(request, "full_url", str(request)))
        return FakeResponse(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    urllib.request.urlopen = fake_urlopen


try:
    pm.TIANDITU_KEY = "f" * 32
    pm.TIANDITU_KEY_FILE = ROOT / "__no_such_key_file__.txt"
    pm.REVERSE_GEOCODE_MEMORY.clear()

    install_fake_response({
        "status": "0",
        "msg": "ok",
        "result": {
            "formatted_address": "广东省肇庆市高要区南岸街道新江村附近",
            "addressComponent": {
                "province": "广东省", "city": "肇庆市",
                "county": "高要区", "town": "南岸街道", "village": "新江村",
            },
        },
    })

    first = pm.reverse_geocode_place(23.03441, 112.466997)
    chk(first["place"] == "广东省肇庆市高要区南岸街道新江村",
        "拼成 省+市+区+镇+村", first["place"])
    chk(first["detail"] == "广东省肇庆市高要区南岸街道新江村附近",
        "detail 原样带回 formatted_address", first["detail"])
    chk(len(sent_urls) == 1 and "type=geocode" in sent_urls[0] and "postStr" in sent_urls[0],
        "请求里带 type=geocode 与 postStr")

    pm.reverse_geocode_place(23.03441, 112.466997)
    chk(len(sent_urls) == 1, "同一个点第二次调用命中缓存，不再发请求")

    install_fake_response({
        "status": "0",
        "result": {
            "formatted_address": "广东省肇庆市高要区南岸街道公厕西北约178米",
            "addressComponent": {
                "province": "广东省", "city": "肇庆市",
                "county": "高要区", "town": "南岸街道",
            },
        },
    })
    no_village = pm.reverse_geocode_place(23.035, 112.468)
    chk(no_village["place"] == "广东省肇庆市高要区南岸街道",
        "没有 village 字段时就到街道级，不编造", no_village["place"])

    install_fake_response({
        "status": "0",
        "result": {"formatted_address": "某某坐标附近", "addressComponent": {}},
    })
    fallback = pm.reverse_geocode_place(23.036, 112.469)
    chk(fallback["place"] == "某某坐标附近", "字段全空时退回 formatted_address", fallback["place"])

    install_fake_response({"status": "1", "msg": "无效的 tk 参数"})
    message = raises(pm.reverse_geocode_place, 23.04, 112.47)
    chk(message is not None and "无效的 tk 参数" in message, "天地图报错时把原因透传", message)

    chk(raises(pm.reverse_geocode_place, 12345, 112.4) is not None, "纬度超范围要报错")
    chk(raises(pm.reverse_geocode_place, "abc", 112.4) is not None, "经纬度不是数字要报错")

    pm.TIANDITU_KEY = ""
    import os
    os.environ.pop("TIANDITU_KEY", None)
    message = raises(pm.reverse_geocode_place, 23.04, 112.47)
    chk(message is not None and "key" in message, "没有 tk 时明确报「未配置天地图 key」", message)

finally:
    urllib.request.urlopen = real_urlopen
    pm.TIANDITU_KEY = "f" * 32


# ---------------------------------------------------------------
# 2) 地图截图
# ---------------------------------------------------------------

print("\n=== 2) 地图截图：底图跟随 + 标点 ===")

from PIL import Image  # noqa: E402

TILE_COLORS = {
    "tdt_img": (12, 40, 80, 255),
    "tdt_cia": (255, 255, 255, 210),
    "tdt_vec": (238, 232, 214, 255),
    "tdt_cva": (0, 0, 0, 255),
    "osm": (205, 225, 205, 255),
}
tile_requests = []


def fake_tile_bytes(source, z, x, y):
    tile_requests.append((source, z, x, y))
    buffer = io.BytesIO()
    Image.new("RGBA", (256, 256), TILE_COLORS[source]).save(buffer, "PNG")
    return buffer.getvalue()


real_tile_bytes = pm.cached_map_tile_bytes
pm.cached_map_tile_bytes = fake_tile_bytes

try:
    osm = pm.compose_map_snapshot(23.03441, 112.466997, 16, "osm", 640, 480)
    chk(osm.size == (640, 480), "尺寸按请求来", f"{osm.size[0]}x{osm.size[1]}")
    chk(osm.getpixel((2, 2)) == TILE_COLORS["osm"][:3],
        "角落是底图本身的颜色", str(osm.getpixel((2, 2))))
    chk(osm.getpixel((320, 240)) == (220, 38, 38),
        "正中间画了红十字（目标点）", str(osm.getpixel((320, 240))))

    satellite = pm.compose_map_snapshot(23.03441, 112.466997, 16, "satellite", 640, 480)
    chk(satellite.getpixel((2, 2)) != TILE_COLORS["osm"][:3],
        "换底图（卫星）后同一位置像素不同 —— 底图确实跟参数走")

    sources = {item[0] for item in tile_requests}
    chk("tdt_img" in sources and "tdt_cia" in sources,
        "卫星底图取的是 影像 + 影像注记 两层", str(sorted(sources)))

    message = raises(pm.compose_map_snapshot, 23.03441, 112.466997, 19, "osm", 2560, 1920)
    chk(message is not None and "范围太大" in message, "瓦片数超上限时拒绝（不把缓存打爆）", message)

    snap = pm.make_map_snapshot({
        "lat": 23.03441, "lng": 112.466997, "zoom": 16,
        "basemap": "street", "width": 800, "height": 600,
    })
    saved = ROOT / "report_cache" / snap["file"]
    chk(saved.is_file() and saved.stat().st_size > 2000, "截图落盘且不是空文件",
        f"{saved.stat().st_size} 字节")
    chk((saved.read_bytes()[:2] == b"\xff\xd8"), "存的是 JPEG")
    chk(snap["basemap"] == "street" and snap["zoom"] == 16,
        "返回里带上用了哪种底图、多少级")
    chk(pm.make_map_snapshot({"lat": 23.0344, "lng": 112.467, "basemap": "不存在"})["basemap"] == "street",
        "底图类型不认识时退回街道图，不报错")

    # ---------- 地图截图上要画飞机与注视虚线 ----------
    target_lat, target_lng = 23.03441, 112.466997

    plain = pm.make_map_snapshot({
        "lat": target_lat, "lng": target_lng, "zoom": 16,
        "basemap": "osm", "width": 640, "height": 480,
    })

    # 飞机放在目标点正北 200m，机头朝正南（就是「看向目标点」）
    drone_lat = target_lat + 200 / 111320.0

    with_drone = pm.make_map_snapshot({
        "lat": target_lat, "lng": target_lng, "zoom": 16,
        "basemap": "osm", "width": 640, "height": 480,
        "drone_lat": drone_lat, "drone_lng": target_lng, "drone_bearing": 180,
    })

    chk(with_drone["drone"] is True and plain["drone"] is False,
        "带飞机参数时如实回报 drone=true")

    plain_img = Image.open(ROOT / "report_cache" / plain["file"]).convert("RGB")
    drone_img = Image.open(ROOT / "report_cache" / with_drone["file"]).convert("RGB")

    world_x, world_y = pm.mercator_world_pixel(target_lat, target_lng, 16)
    drone_world_x, drone_world_y = pm.mercator_world_pixel(drone_lat, target_lng, 16)

    left = world_x - 640 / 2.0
    top = world_y - 480 / 2.0
    drone_px = (int(round(drone_world_x - left)), int(round(drone_world_y - top)))

    chk(0 <= drone_px[0] < 640 and 0 <= drone_px[1] < 480,
        "飞机落在截图范围内", str(drone_px))
    chk(drone_px[1] < 240, "飞机在目标点北边（y 更小）", str(drone_px[1]))

    center_pixel = drone_img.getpixel(drone_px)
    chk(max(abs(a - b) for a, b in zip(center_pixel, pm.DRONE_ARROW_FILL)) < 40,
        "飞机位置上确实是箭头那个蓝色", str(center_pixel))

    line_hits = 0
    for y in range(drone_px[1], 240):
        for x in range(drone_px[0] - 6, drone_px[0] + 7):
            r, g, b = drone_img.getpixel((x, y))
            if (abs(r - pm.LOOK_LINE_COLOR[0]) < 26
                    and abs(g - pm.LOOK_LINE_COLOR[1]) < 26
                    and abs(b - pm.LOOK_LINE_COLOR[2]) < 26):
                line_hits += 1

    chk(line_hits > 10, "飞机到目标点之间画了注视虚线", f"{line_hits} 个灰色像素")
    chk(drone_img.tobytes() != plain_img.tobytes(), "带飞机的那张和纯地图那张不一样")

    # 飞机箭头不能比网页版「压扁」：量蓝色像素的外接框
    # 网页 SVG：翼展 28/40、机长 31/40（40 的 viewBox）-> 外接框比例约 0.90
    blue_pixels = [
        (x, y)
        for x in range(640) for y in range(480)
        if max(abs(a - b) for a, b in zip(drone_img.getpixel((x, y)), pm.DRONE_ARROW_FILL)) < 45
    ]
    chk(len(blue_pixels) > 50, "截图上找得到飞机箭头的蓝色像素", str(len(blue_pixels)))

    xs = [p[0] for p in blue_pixels]
    ys = [p[1] for p in blue_pixels]
    arrow_w = max(xs) - min(xs) + 1
    arrow_h = max(ys) - min(ys) + 1

    chk(0.85 <= arrow_w / arrow_h <= 1.0,
        "飞机箭头比例与网页版一致（宽/高约 0.90，不是被压扁的窄条）",
        f"{arrow_w}×{arrow_h}px，比值 {arrow_w / arrow_h:.2f}")

    chk(pm.make_map_snapshot({
        "lat": target_lat, "lng": target_lng, "width": 400, "height": 300,
        "drone_lat": "坏值", "drone_lng": target_lng,
    })["drone"] is False, "飞机参数坏掉时当作没给，图照出")

    # ---------- 取景中心 ≠ 目标点：红十字必须落在目标点上 ----------
    def is_crosshair(pixel):
        r, g, b = pixel
        return r > 150 and r - g > 60 and r - b > 60

    drone_lat3 = target_lat + 120 / 111320.0        # 飞机在目标点正北 120m
    center_lat3 = (target_lat + drone_lat3) / 2     # 取景取「中点」

    shifted = pm.make_map_snapshot({
        "lat": center_lat3, "lng": target_lng, "zoom": 18,
        "basemap": "osm", "width": 640, "height": 640,
        "target_lat": target_lat, "target_lng": target_lng,
        "drone_lat": drone_lat3, "drone_lng": target_lng, "drone_bearing": 180,
    })

    chk(shifted["zoom"] == 18, "缩放级原样透传（18 级，字看得清）", str(shifted["zoom"]))
    chk(shifted["drone"] is True, "18 级时飞机照样画")

    img3 = Image.open(ROOT / "report_cache" / shifted["file"]).convert("RGB")

    center_world = pm.mercator_world_pixel(center_lat3, target_lng, 18)
    target_world = pm.mercator_world_pixel(target_lat, target_lng, 18)
    drone_world3 = pm.mercator_world_pixel(drone_lat3, target_lng, 18)

    left3 = center_world[0] - 640 / 2.0
    top3 = center_world[1] - 640 / 2.0

    target_px3 = (int(round(target_world[0] - left3)), int(round(target_world[1] - top3)))
    drone_px3 = (int(round(drone_world3[0] - left3)), int(round(drone_world3[1] - top3)))

    chk(abs(target_px3[1] - 320) > 10,
        "这个用例里目标点确实不在图片中心（否则测不出问题）",
        f"目标点 y={target_px3[1]}，图片中心 y=320")
    chk(is_crosshair(img3.getpixel(target_px3)),
        "红十字画在目标点上", str(img3.getpixel(target_px3)))
    chk(not is_crosshair(img3.getpixel((320, 320))),
        "图片正中不再有红十字（取景中心≠目标点时不写死中心）",
        str(img3.getpixel((320, 320))))
    chk(max(abs(a - b) for a, b in zip(img3.getpixel(drone_px3), pm.DRONE_ARROW_FILL)) < 40,
        "飞机画在飞机位置上", str(img3.getpixel(drone_px3)))

finally:
    pm.cached_map_tile_bytes = real_tile_bytes


# ---------------------------------------------------------------
# 3) 视频抽帧（真跑 ffmpeg）
# ---------------------------------------------------------------

print("\n=== 3) 视频抽帧：原分辨率 / 压缩 ===")

videos = sorted((ROOT / "Data").glob("**/*.MP4")) + sorted((ROOT / "Data").glob("**/*.mp4"))

if not videos:
    print("  （跳过：Data/ 下没有 MP4 可抽）")
else:
    # 2026-10-25：不能直接拿 videos[0]——Data/ 里现在还有 360 全景转码
    # （2048x1024 等距柱状），字母序会排在无人机视频前面，
    # 让「原分辨率 ≥1080p / A4 会缩小」这些断言全部误报。
    # 选一支有代表性的：优先 *_V.MP4（3840x2160 主流），否则体积最大的。
    _vs = [v for v in videos if v.name.upper().endswith("_V.MP4")]
    video = _vs[0] if _vs else max(videos, key=lambda v: v.stat().st_size)
    print(f"  （抽帧样本：{video.name}）")
    real_resolve = pm.resolve_project_video
    pm.resolve_project_video = lambda *args, **kwargs: video

    try:
        full = pm.make_video_snapshot({
            "project_name": "测试", "folder_index": 0,
            "path": video.name, "time": 60, "mode": "full",
        })
        full_path = ROOT / "report_cache" / full["file"]
        chk(full_path.is_file() and full_path.stat().st_size > 10000,
            "抽到一帧真图", f"{full_path.stat().st_size} 字节")
        chk(full["width"] >= 1920 and full["height"] >= 1080,
            "原分辨率档不缩小", f"{full['width']}x{full['height']}")

        head = full_path.read_bytes()[:4]
        chk(head[:3] == b"\xff\xd8\xff" and head[3] == 0xE0,
            "JPEG 必须是 JFIF 头（SOI+APP0）—— ffmpeg 直接写的 COM 头 docx 不认",
            head.hex())

        from docx.image.image import Image as DocxImage
        message = raises(DocxImage.from_file, str(full_path))
        chk(message is None, "python-docx 认这张图（否则报告生成时才炸，报错还是空的）",
            message or "ok")

        small = pm.make_video_snapshot({
            "project_name": "测试", "folder_index": 0,
            "path": video.name, "time": 60, "mode": "a4",
        })
        chk(small["width"] == pm.REPORT_IMAGE_WIDTH_A4,
            f"压缩档宽度是 {pm.REPORT_IMAGE_WIDTH_A4}px（A4 正文宽 @320ppi）",
            f"{small['width']}x{small['height']}")
        _expect_h = max(2, round(full["height"] * pm.REPORT_IMAGE_WIDTH_A4 / full["width"]))
        chk(small["height"] == _expect_h,
            "压缩档高度按同一比例换算（等比，不是拉伸/裁切）",
            f"{small['width']}x{small['height']}，期望高 {_expect_h}")

        leftovers = list((ROOT / "report_cache").glob("frame_*.png"))
        chk(not leftovers, "中间的 PNG 没有留在 report_cache 里", str([p.name for p in leftovers]))

        chk(raises(pm.make_video_snapshot, {"project_name": "", "path": "x.MP4"}) is not None,
            "缺项目名要报错")

        # ---- 画面落点：视频截图上叠一个目标点标志 ----
        def is_mark(pixel):
            r, g, b = pixel
            return r > 150 and r - g > 60 and r - b > 60

        def mark_bbox(path_a, path_b):
            """同一帧、一张带标志一张不带：求差异外接框（只有标志那一小块不同）。

            不用颜色找红色 —— 真实画面里本来就有红色物体（船、土、屋顶），会误判。
            """
            from PIL import ImageChops

            with Image.open(path_a) as a, Image.open(path_b) as b:
                diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L")

            return diff.point(lambda v: 255 if v > 40 else 0).getbbox()

        plain_of = {"a4": small, "full": full}

        for label, mode, fx, fy in (("压缩档", "a4", 0.25, 0.75),
                                    ("原分辨率档", "full", 0.8, 0.2)):
            spotted = pm.make_video_snapshot({
                "project_name": "测试", "folder_index": 0,
                "path": video.name, "time": 60, "mode": mode,
                "spot_fx": fx, "spot_fy": fy,
            })
            spot_path = ROOT / "report_cache" / spotted["file"]

            chk(spotted["spot"] is True, f"{label}：落点参数被接受", str(spotted.get("spot")))

            with Image.open(spot_path) as opened:
                mark = opened.convert("RGB")
                cx = int(round(fx * mark.width))
                cy = int(round(fy * mark.height))

                chk(any(is_mark(mark.getpixel((x, y)))
                        for x in range(max(0, cx - 3), min(mark.width, cx + 4))
                        for y in range(max(0, cy - 3), min(mark.height, cy + 4))),
                    f"{label}：标志中心是那个红（{fx:.0%}, {fy:.0%}）",
                    str(mark.getpixel((cx, cy))))

            box = mark_bbox(spot_path, ROOT / "report_cache" / plain_of[mode]["file"])
            chk(box is not None, f"{label}：带标志的图和同帧原图有差异")

            if box:
                box_cx = (box[0] + box[2]) / 2
                box_cy = (box[1] + box[3]) / 2
                side = max(box[2] - box[0], box[3] - box[1])

                chk(abs(box_cx - fx * spotted["width"]) <= 12
                    and abs(box_cy - fy * spotted["height"]) <= 12,
                    f"{label}：差异就只有那一小块标志，且落在鼠标点的位置",
                    f"差异中心 ({box_cx:.0f}, {box_cy:.0f}) vs 落点 "
                    f"({fx * spotted['width']:.0f}, {fy * spotted['height']:.0f})，{side}px 见方")

                globals()[f"spot_side_{mode}"] = side
                globals()[f"spot_area_{mode}"] = (spotted["width"], spotted["height"])

        # 标志大小按图宽等比。理论比值 = full 宽 / A4 宽
        # （原断言把它写死成 4K 的 1.55 倍；素材换成别的分辨率就会误报，
        #  所以改成对理论值取 10% 误差 —— 判定更准，也没有放宽）
        ratio = (spot_side_full / spot_side_a4) if spot_side_a4 else 0
        _expect_ratio = full["width"] / pm.REPORT_IMAGE_WIDTH_A4
        chk(abs(ratio - _expect_ratio) <= 0.1,
            "标志随输出分辨率等比缩放（比值 = full 宽 / A4 宽，不是固定像素）",
            f"{spot_side_full}px / {spot_side_a4}px = {ratio:.2f}，期望 {_expect_ratio:.2f}")

        # 产品规则（2026-10-25 明确写进测试）：a4 档**总是**缩放到 2480 宽，
        # 原片比 2480 窄时会有意放大 —— 目的是让报告里那张图正好铺满 A4 正文宽。
        # 以前这条规则靠「素材一定是 4K」隐含成立，现在显式断言。
        # 窄素材必须**按实测宽度**挑（不能用「第一支不同的视频」想当然）。
        def _probe_width(p):
            """用 ffprobe 量视频宽度；量不出来返回 None。"""
            import shutil as _shutil
            ffmpeg = pm.find_ffmpeg()
            if not ffmpeg:
                return None
            probe = _shutil.which("ffprobe") or str(pathlib.Path(ffmpeg).with_name("ffprobe.exe"))
            if not pathlib.Path(probe).exists():
                probe = _shutil.which("ffprobe")
            if not probe:
                return None
            try:
                out = subprocess.run(
                    [probe, "-v", "error", "-select_streams", "v:0",
                     "-show_entries", "stream=width", "-of", "csv=p=0", str(p)],
                    capture_output=True, text=True, timeout=60,
                )
                return int((out.stdout or "").strip().splitlines()[0])
            except (OSError, ValueError, IndexError, subprocess.SubprocessError):
                return None

        _narrow_ok = False
        _tried = []
        # 逐个候选（窄的、体积从小到大）试着抽一帧：抽不出来就换下一个。
        # 只看宽度不够 —— Data/ 里有几支极短的样本视频，抽帧会失败。
        for _cand in sorted((v for v in videos if v.name != video.name),
                            key=lambda v: v.stat().st_size):
            _w = _probe_width(_cand)
            if _w is None or _w >= pm.REPORT_IMAGE_WIDTH_A4:
                continue
            _tried.append(f"{_cand.name}({_w}px)")
            _sample_resolve = pm.resolve_project_video
            pm.resolve_project_video = lambda *a, **k: _cand
            try:
                tiny = pm.make_video_snapshot({
                    "project_name": "测试", "folder_index": 0,
                    "path": _cand.name, "time": 60, "mode": "a4",
                })
            except ValueError as e:
                # 只吞「这支样本抽不出帧」这一类（短样本/坏样本），换下一支；
                # 其它 ValueError（参数、Pillow 转换…）与所有非 ValueError 异常
                # 都必须抛出来，否则真 bug 会被静默变成 [SKIP]。
                if "Frame extraction failed" not in str(e):
                    raise
                print(f"  （跳过 {_cand.name}：抽帧失败，换下一个候选）")
                continue
            finally:
                pm.resolve_project_video = _sample_resolve

            print(f"  （窄素材：{_cand.name} = {_w}px < {pm.REPORT_IMAGE_WIDTH_A4}px）")
            chk(_w < pm.REPORT_IMAGE_WIDTH_A4,
                '窄素材确实比 A4 正文宽更窄（否则这条断言没意义）', f"{_w}px")
            chk(tiny["width"] == pm.REPORT_IMAGE_WIDTH_A4,
                "窄素材进 a4 档同样铺满 A4 正文宽（允许放大，这是有意的）",
                f"{_cand.name}: {tiny['width']}x{tiny['height']}")
            _narrow_ok = True
            break

        if not _narrow_ok:
            print("  [SKIP] 没有可用的窄素材（宽度 <%dpx 且能抽帧），跳过这条规则断言"
                  % pm.REPORT_IMAGE_WIDTH_A4)
            if _tried:
                print("         试过：", ", ".join(_tried[:6]))

        # 不给落点就不叠标志（老标记点没有这个字段）
        plain = pm.make_video_snapshot({
            "project_name": "测试", "folder_index": 0,
            "path": video.name, "time": 60, "mode": "a4",
        })
        chk(plain["spot"] is False, "没给落点时如实回报 spot=false")

        for bad in ({"spot_fx": "abc", "spot_fy": 0.5}, {"spot_fx": 1.4, "spot_fy": 0.5},
                    {"spot_fx": -0.1, "spot_fy": 0.5}, {"spot_fx": 0.5}):
            chk(pm.parse_image_spot(bad) is None,
                f"坏落点当作没给：{bad}", str(pm.parse_image_spot(bad)))

        chk(pm.parse_image_spot({"spot_fx": 0.25, "spot_fy": 0.75}) == (0.25, 0.75),
            "正常落点原样返回")

    finally:
        pm.resolve_project_video = real_resolve

    # 上面把解析函数替换成了「永远返回这个视频」，所以这条要在还原之后再断言
    message = raises(pm.make_video_snapshot, {
        "project_name": "这个项目不存在", "folder_index": 0, "path": video.name, "time": 1,
    })
    chk(message is not None, "项目/视频解析不到时如实报错", message)


# ---------------------------------------------------------------
# 4) docx 结构
# ---------------------------------------------------------------

print("\n=== 4) docx：目录可点 / 总表 / 章节 / 图片 ===")

shots = sorted((ROOT / "report_cache").glob("shot_*.jpg"))
maps = sorted((ROOT / "report_cache").glob("map_*.jpg"))

if not (shots and maps):
    print("  （跳过：没有可用的截图，先跑上面第 2/3 段）")
else:
    from docx import Document  # noqa: E402

    payload = {
        "project_name": "东莞2",
        "image_mode": "a4",
        "points": [
            {
                "name": "1 号排水口", "lat": 23.03441, "lng": 112.466997,
                "place": "广东省肇庆市高要区南岸街道",
                "video": "DJI_20260924101516_0001_V.MP4", "time": 608.274,
                "video_image": shots[-1].name, "map_image": maps[-1].name,
                "basemap_name": "卫星图（天地图影像）", "zoom": 16,
            },
            {
                "name": '2 号 <桥下> & "涵洞"', "lat": 23.0346, "lng": 112.4671,
                "place": "unresolved",
                "video": "DJI_20260924101516_0001_V.MP4", "time": 90,
                "video_image": "不存在的图.jpg", "map_image": maps[-1].name,
                "basemap_name": "街道图（天地图）", "zoom": 16,
            },
        ],
    }

    result = pm.build_docx_report(payload)
    docx_path = ROOT / "report_cache" / result["file"]
    chk(docx_path.is_file() and docx_path.stat().st_size > 20000,
        "docx 落盘", f"{docx_path.stat().st_size} 字节")

    document = Document(str(docx_path))
    xml = document.element.xml

    chk(xml.count("bookmarkStart") == 2, "两个点各有一个书签", str(xml.count("bookmarkStart")))
    chk(xml.count("<w:hyperlink ") == 2, "目录里两条可点链接",
        str(xml.count("<w:hyperlink ")))
    chk('w:anchor="mark1"' in xml and 'w:anchor="mark2"' in xml,
        "超链接锚点指到对应章节书签")
    chk("fldSimple" not in xml and "TOC \\o" not in xml,
        "没用需要按 F9 刷新的域代码目录")

    chk(len(document.tables) == 3,
        "一张汇总表 + 每个点一张字段表", str(len(document.tables)))
    chk(len(document.tables[0].columns) == 7 and len(document.tables[0].rows) == 3,
        "汇总表 7 列（序号/名称/纬度/经度/位置/视频/时间）+ 表头 + 2 行",
        f"{len(document.tables[0].columns)} 列 {len(document.tables[0].rows)} 行")
    chk(document.tables[0].rows[1].cells[4].text == "广东省肇庆市高要区南岸街道",
        "汇总表里带所在位置")
    chk("zoom 16" in xml,
        "图注里的「zoom N」跟着传进来的级别走（这一份是 16 级）")

    zoomed_payload = dict(payload)
    zoomed_payload["points"] = [dict(payload["points"][0], zoom=17)]
    zoomed = pm.build_docx_report(zoomed_payload)
    with zipfile.ZipFile(ROOT / "report_cache" / zoomed["file"]) as package:
        zoomed_xml = package.read("word/document.xml").decode("utf-8")
    chk("zoom 17" in zoomed_xml and "zoom 16" not in zoomed_xml,
        "换个级别，图注跟着变（不是写死的）")
    chk(document.tables[0].rows[2].cells[4].text == "unresolved",
        "解析不到就写「unresolved」，不编造")
    chk(document.tables[0].rows[1].cells[6].text == "00:10:08",
        "视频时间格式化成 时:分:秒", document.tables[0].rows[1].cells[6].text)

    chk(len(document.inline_shapes) == 3,
        "图片 3 张（第 1 点两张 + 第 2 点缺图只贴一张）", str(len(document.inline_shapes)))

    # 插图尺寸：两张图 + 字段表 + 两行图注要能排在同一页 A4 里
    extents = re.findall(r'<wp:extent cx="(\d+)" cy="(\d+)"/>', xml)
    chk(len(extents) == 3, "三张图各自写了尺寸", str(len(extents)))

    heights_cm = [int(cy) / 360000 for _, cy in extents]
    widths_cm = [int(cx) / 360000 for cx, _ in extents]

    chk(max(heights_cm) <= pm.REPORT_VIDEO_IMAGE_MAX_HEIGHT_CM + 0.01,
        f"视频截图高度不超过 {pm.REPORT_VIDEO_IMAGE_MAX_HEIGHT_CM}cm",
        f"最高 {max(heights_cm):.2f}cm")
    chk(min(heights_cm) <= pm.REPORT_MAP_IMAGE_MAX_HEIGHT_CM + 0.01,
        f"地图截图更矮（按 {pm.REPORT_MAP_IMAGE_MAX_HEIGHT_CM}cm 封顶）",
        f"最矮 {min(heights_cm):.2f}cm")
    chk(max(widths_cm) == pm.REPORT_IMAGE_MAX_WIDTH_CM,
        f"16:9 的图横向铺满正文宽（{pm.REPORT_IMAGE_MAX_WIDTH_CM}cm）",
        f"最宽 {max(widths_cm):.2f}cm")
    chk(max(widths_cm) <= pm.REPORT_IMAGE_MAX_WIDTH_CM + 0.01,
        f"任何图都不会超过正文宽 {pm.REPORT_IMAGE_MAX_WIDTH_CM}cm",
        f"最宽 {max(widths_cm):.2f}cm")

    # 表格边界要和插图边界对齐（用户明确要求）：两者都等于正文宽
    table_widths = []
    for table_block in re.findall(r"<w:tbl>.*?</w:tblGrid>", xml, re.S):
        grid = re.search(r"<w:tblGrid>.*?</w:tblGrid>", table_block, re.S)
        table_widths.append(sum(int(v) for v in re.findall(r'w:w="(\d+)"', grid.group(0))) / 567)

    chk(max(table_widths) - min(table_widths) < 0.01,
        "三张表宽度一致", " / ".join(f"{w:.3f}cm" for w in table_widths))
    chk(abs(max(table_widths) - max(widths_cm)) < 0.01,
        "表格宽度 = 插图宽度（边界对齐）",
        f"表 {max(table_widths):.4f}cm vs 图 {max(widths_cm):.4f}cm")
    chk(abs(max(table_widths) - pm.REPORT_IMAGE_MAX_WIDTH_CM) < 0.01,
        f"表格与插图都用 {pm.REPORT_IMAGE_MAX_WIDTH_CM}cm",
        f"{max(table_widths):.4f}cm")
    chk(max(table_widths) < 16.0 - 0.005,
        "留了约 1mm 余量，不会被 Word 缩放后再居中（那正是左边缘差 1~2mm 的原因）",
        f"{max(table_widths):.4f}cm < 16.0cm")
    chk(xml.count('<w:tblInd w:type="dxa" w:w="0"/>') >= 3,
        "三张表都显式写了缩进 0（挡掉默认的 -0.19cm 负缩进）",
        str(xml.count('<w:tblInd w:type="dxa" w:w="0"/>')))

    # 单元格边距必须全 0：Word 按「单元格里文字的起点」定位表格，
    # 左右边距非 0（默认 0.08 英寸 ≈ 2.03mm）时表格边框会被推到正文边距左边那么多，
    # 于是边框和插图差出约 2mm（用户实测就是这个数）。
    margin_blocks = re.findall(r"<w:tblCellMar>.*?</w:tblCellMar>", xml, re.S)
    chk(len(margin_blocks) >= 3, "三张表都写了 tblCellMar",
        str(len(margin_blocks)) + " 处")
    chk(all(block.count('w:w="0"') == 4 for block in margin_blocks),
        "上下左右单元格边距都是 0（文字起点＝表格边框＝插图左边缘）",
        str([block.count('w:w="0"') for block in margin_blocks]))

    first_tblPr = re.search(r"<w:tblPr>.*?</w:tblPr>", xml, re.S)
    order = first_tblPr.group(0) if first_tblPr else ""
    positions = [
        order.find(f"<w:{name}")
        for name in ("tblW", "tblInd", "tblLayout", "tblCellMar", "tblLook")
    ]
    chk(all(positions) and positions == sorted(positions),
        "tblPr 子元素顺序合 schema（tblW → tblInd → tblLayout → tblCellMar → tblLook）",
        str(dict(zip(("tblW", "tblInd", "tblLayout", "tblCellMar", "tblLook"), positions))))
    chk(xml.count('<w:jc w:val="center"/>') == 3,
        "只有三行图注是段落居中；插图段落是左对齐（左边缘与表格同一条线）",
        str(xml.count('<w:jc w:val="center"/>')) + " 处段落居中")

    # 图与图注：图左对齐（与表格同一条线），图注居中 —— 见上面的 jc 断言

    # 方形图（热成像 5:4）也按高度封顶，不会横向顶破页面
    square_width = pm.report_picture_width_cm(shots[-1].name) if shots else None
    chk(pm.report_picture_width_cm(ROOT / "report_cache" / shots[-1].name) <= pm.REPORT_IMAGE_MAX_WIDTH_CM,
        "按高度封顶算出来的宽度不会超过正文宽",
        f"{pm.report_picture_width_cm(ROOT / 'report_cache' / shots[-1].name)}cm")
    chk(pm.report_picture_width_cm(ROOT / "report_cache" / "不存在的图.jpg") == pm.REPORT_IMAGE_MAX_WIDTH_CM,
        "图读不出来时退回正文宽，不抛异常", str(square_width))

    # 插图写上「诚实的 DPI」：像素宽 / 目标显示宽 —— 按固有尺寸排的阅读器也算得对
    expected_dpi = round(2480 / (pm.REPORT_IMAGE_MAX_WIDTH_CM / 2.54))
    chk(pm.report_image_dpi(2480, 1395, pm.REPORT_VIDEO_IMAGE_MAX_HEIGHT_CM) == (expected_dpi, expected_dpi),
        f"2480x1395 的截图写成 {expected_dpi}dpi（铺满 {pm.REPORT_IMAGE_MAX_WIDTH_CM}cm 宽）",
        str(pm.report_image_dpi(2480, 1395, pm.REPORT_VIDEO_IMAGE_MAX_HEIGHT_CM)))
    chk(pm.report_image_dpi(0, 0, 8.0) == (300, 300), "尺寸无效时给个安全默认值")

    saved_shot = Image.open(ROOT / "report_cache" / shots[-1].name)
    chk(saved_shot.info.get("dpi") is not None,
        "落盘的截图确实带了 DPI 元数据", str(saved_shot.info.get("dpi")))

    # ---------- 字体统一：中文 微软雅黑、西文数字 Arial ----------
    with zipfile.ZipFile(docx_path) as package:
        styles_xml = package.read("word/styles.xml").decode("utf-8")

    chk(styles_xml.count(f'w:eastAsia="{pm.REPORT_FONT_CJK}"') >= 3,
        "Normal / Title / Heading 1 都写了中文字体（各一份）",
        str(styles_xml.count(f'w:eastAsia="{pm.REPORT_FONT_CJK}"')) + " 处")
    chk(f'w:ascii="{pm.REPORT_FONT_LATIN}"' in styles_xml
        and f'w:hAnsi="{pm.REPORT_FONT_LATIN}"' in styles_xml,
        "西文与数字走 Arial（w:ascii / w:hAnsi）")
    chk('w:rFonts' in xml and f'w:eastAsia="{pm.REPORT_FONT_CJK}"' in xml,
        "目录里手写的超链接 run 也显式带上了字体")

    # ---------- 经纬度：数字带符号，半球写在表头里 ----------
    chk(pm.format_latitude(23.03441) == "23.034410", "北纬是正数", pm.format_latitude(23.03441))
    chk(pm.format_longitude(112.466997) == "112.466997", "东经是正数",
        pm.format_longitude(112.466997))
    chk(pm.format_latitude(-12.3456789) == "-12.345679", "南纬是负数（不取绝对值）",
        pm.format_latitude(-12.3456789))
    chk(pm.format_longitude(-70.5) == "-70.500000", "西经是负数", pm.format_longitude(-70.5))

    chk(document.tables[1].rows[1].cells[0].text == "Latitude (°N)",
        "字段表把半球写在表头里", document.tables[1].rows[1].cells[0].text)
    chk(document.tables[1].rows[2].cells[0].text == "Longitude (°E)",
        "经度表头同样", document.tables[1].rows[2].cells[0].text)
    chk(" N" not in document.tables[1].rows[1].cells[1].text
        and " E" not in document.tables[1].rows[2].cells[1].text,
        "数字里不再带 N/E（复制时最碍事）",
        document.tables[1].rows[1].cells[1].text + " / " + document.tables[1].rows[2].cells[1].text)
    chk(document.tables[0].rows[0].cells[2].text == "Lat (°N)"
        and document.tables[0].rows[0].cells[3].text == "Lng (°E)",
        "汇总表表头也写明半球",
        document.tables[0].rows[0].cells[2].text + " / " + document.tables[0].rows[0].cells[3].text)

    # ---------- 主题字体引用必须删掉 ----------
    heading_block = re.search(r'<w:style [^>]*w:styleId="Heading1".*?</w:style>', styles_xml, re.S)
    chk(heading_block is not None, "styles.xml 里找得到 Heading1 样式")

    block = heading_block.group(0) if heading_block else ""
    chk("asciiTheme" not in block and "eastAsiaTheme" not in block,
        "Heading1 里已无主题字体引用（这正是标题中文落 MS Gothic、数字落 Calibri 的原因）",
        str(re.findall(r'w:(?:ascii|hAnsi|eastAsia|cstheme)Theme="[^"]*"', block)[:3]))
    chk('w:ascii="Arial"' in block and f'w:eastAsia="{pm.REPORT_FONT_CJK}"' in block,
        "Heading1 明确写了 Arial + 微软雅黑")

    # ---------- 表格内容：中部左对齐 ----------
    chk(xml.count('w:vAlign w:val="center"') >= 20,
        "单元格垂直居中（中部）", str(xml.count('w:vAlign w:val="center"')) + " 个单元格")
    chk(xml.count('w:jc w:val="left"') >= 20,
        "单元格内容水平靠左", str(xml.count('w:jc w:val="left"')) + " 处")

    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading 1")]
    chk("1. 1 号排水口" in headings and '2. 2 号 <桥下> & "涵洞"' in headings,
        "章节标题是「数字序号. 空格 点名」（不用汉字数字）", str(headings)[:80])
    chk(not any(re.match(r"^[一二三四五六七八九十]+、", h) for h in headings),
        "标题里已经没有任何汉字序号", str(headings)[:80])

    chk("东莞2" in result["download_name"] and result["download_name"].endswith(".docx"),
        "下载文件名带项目名与日期", result["download_name"])

    chk(raises(pm.build_docx_report, {"project_name": "x", "points": []}) is not None,
        "一个点都没有时要报错（不生成空报告）")
    chk(raises(pm.build_docx_report, {"project_name": "x", "points": [{"name": "没有经纬度"}]}) is not None,
        "经纬度缺失的点会被剔除，全无效就报错")


# ---------------------------------------------------------------
# 5) 小工具与安全
# ---------------------------------------------------------------

print("\n=== 5) 小工具 / 路径穿越防护 ===")

chk(pm.format_seconds_text(608.274) == "00:10:08", "秒 -> 00:10:08", pm.format_seconds_text(608.274))
chk(pm.format_seconds_text("abc") == "-", "坏值给 '-'，不抛异常")
chk(pm.safe_file_stem('东莞2/非法:*名') == "东莞2_非法_名",
    "文件名里的非法字符被替换（连续的合成一个 _）", pm.safe_file_stem('东莞2/非法:*名'))

chk(pm.report_file("a.jpg") == pm.REPORT_DIR / "a.jpg", "普通文件名可用")
chk(raises(pm.report_file, "../secret.txt") is not None, "挡掉 ../")
chk(raises(pm.report_file, "sub/a.jpg") is not None, "挡掉子目录")
chk(raises(pm.report_file, "a\\b.jpg") is not None, "挡掉反斜杠")
chk(pm.resolve_report_image("../x.jpg") is None, "报告里的图名也走同一道校验")
chk(pm.resolve_report_image("不存在.jpg") is None, "图不存在就返回 None")

caps = pm.report_capabilities()
chk(set(caps) == {"docx", "pillow", "ffmpeg"}, "/api/config 里如实报告依赖", str(caps))

print("\n=== 6) 启动自检：端口上已有旧服务时要能提醒 ===")

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402


class StubConfigHandler(BaseHTTPRequestHandler):
    """只回旧版 /api/config 的桩服务，冒充「上一次没关掉的进程」。"""

    def do_GET(self):
        body = b'{"tianditu": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


# 空端口：不该打扰
probe = socket.socket()
probe.bind(("127.0.0.1", 0))
free_port = probe.getsockname()[1]
probe.close()

chk(pm.existing_server_hint("127.0.0.1", free_port, timeout=0.5) is None,
    "端口上没东西就不出声（返回 None）")

stub = ThreadingHTTPServer(("127.0.0.1", 0), StubConfigHandler)
stub_port = stub.server_address[1]
threading.Thread(target=stub.serve_forever, daemon=True).start()

try:
    hint = pm.existing_server_hint("127.0.0.1", stub_port, timeout=2)
finally:
    stub.shutdown()
    stub.server_close()

chk(isinstance(hint, str) and str(stub_port) in hint,
    "有旧服务时给出提示，并点明是哪个端口",
    (hint or "").splitlines()[0] if hint else None)
chk(bool(hint) and "随机抢答" in hint and "taskkill" in hint,
    "提示里讲清原因 + 给出可照做的命令")

print()
if ok:
    print("结果: 全部通过")
else:
    print("结果: 有失败")
sys.exit(0 if ok else 1)
