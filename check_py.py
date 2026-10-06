import ast, io, sys, pathlib
sys.stdout.reconfigure(encoding="utf-8")
# 路径按脚本所在目录推导（换机器/换盘符都不用改）
ROOT = pathlib.Path(__file__).resolve().parent
PY = ROOT / "Code" / "project_manager.py"
src = io.open(PY, encoding="utf-8").read()
ok = True
def chk(c, label, extra=""):
    global ok
    ok &= bool(c)
    print(f"  {'[OK]' if c else '[FAIL]'} {label}{(' -> ' + str(extra)) if extra else ''}")

print("=== Python 语法 ===")
try:
    tree = ast.parse(src)
    chk(True, "project_manager.py 语法通过")
except SyntaxError as e:
    chk(False, f"语法错误 line {e.lineno}: {e.msg}")
    sys.exit(1)

names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
print("\n=== 函数齐备 ===")
for need in ("find_ffmpeg", "find_ffprobe", "probe_video_stream", "build_proxy_segment",
             "prune_proxy_cache", "resolve_project_video", "resolve_project_file",
             "send_file_range", "stream_project_video", "load_srt_telemetry",
             "guess_image_type", "tile_source_url", "prune_tile_cache", "proxy_map_tile",
             "geocode_place", "get_tianditu_key", "parse_lonlat",
             "shorter_keyword", "request_tianditu_search", "parse_tianditu_payload",
             # 导出「前后 10 秒」片段
             "build_clip", "send_clip_download"):
    chk(need in names, f"def {need}")

consts = set()
for n in tree.body:
    if isinstance(n, ast.Assign):
        for t in n.targets:
            if isinstance(t, ast.Name):
                consts.add(t.id)
print("\n=== 常量齐备 ===")
for need in ("PROXY_DIR", "PROXY_SECONDS", "PROXY_BUCKET_SECONDS", "PROXY_HEIGHT",
             "PROXY_CRF", "PROXY_CACHE_MAX_MB", "PROXY_LOCK", "VIDEO_PROBE_CACHE",
             # 导出片段：前 5 + 后 5 秒、1080p、单独缓存目录
             "CLIP_BEFORE_SECONDS", "CLIP_AFTER_SECONDS", "CLIP_HEIGHT", "CLIP_CRF",
             "CLIP_MAXRATE", "CLIP_BUFSIZE", "CLIP_CACHE_MAX_MB", "CLIP_DIR"):
    chk(need in consts, need)

print("\n=== 导出「前后 10 秒」的实现要点 ===")
chk("CLIP_BEFORE_SECONDS = 5" in src and "CLIP_AFTER_SECONDS = 5" in src,
    "默认前 5 秒 + 后 5 秒（一共 10 秒）")
chk("CLIP_HEIGHT = 1080" in src, "导出高度 1080p")
# 画质：原来 crf28 + 2200k 实测 SSIM 0.894、用户说糊；
# 现在 crf18 + 8000k（用户定档：每次约 10 MB 可以接受）
chk("CLIP_CRF = 18" in src, "CRF 18（比原来的 28 清晰一大截）")
chk('CLIP_MAXRATE = "8000k"' in src, "限码率 8000k（和 CRF 18 配套；原来 2200k 太狠）")
chk('"-maxrate", CLIP_MAXRATE' in src and '"-bufsize", CLIP_BUFSIZE' in src,
    "限码率与缓冲都走常量")
chk('f"scale=-2:{CLIP_HEIGHT}"' in src, "按 1080p 等比缩放（宽度自动偶数）")
chk('"attachment; filename=' in src, "按下载发出去（Content-Disposition: attachment）")
chk("url_quote(download_name)" in src, "中文文件名转义后再放进响应头")
chk("CLIP_DIR" in src and "clip_path, start, seconds = build_clip" in src,
    "片段缓存在独立目录（不会被播放缓存清理掉）")
chk("prune_clip_cache" in names and "prune_clip_cache()" in src,
    "导出目录有自己的清理（超过 CLIP_CACHE_MAX_MB 按最旧的删）")
chk("CLIP_MAXRATE}|{CLIP_BUFSIZE}" in src.replace("f\"|{", "f\"|{")
    or "|{CLIP_MAXRATE}|{CLIP_BUFSIZE}" in src,
    "缓存指纹带上码率参数（改压制档位会重新生成，不会复用旧文件）")
chk('"/api/project/clip"' in src, "注册了 /api/project/clip 路由")

print("\n=== 路由与关键行为 ===")
for need in ('/api/project/proxy', '/api/project/video', '/api/geocode',
             '/api/project/telemetry', 'movflags'):
    chk(need in src, f"包含 {need}")
chk('TELEMETRY_STEP' in consts and 'SRT_FIELD_RES' in consts, "遥测常量已定义")
chk('TIANDITU_TILE_LAYERS' in consts and 'MAP_TILE_CACHE_MAX_MB' in consts, "瓦片图层与缓存上限常量已定义")
chk('/api/config' in src, "包含 /api/config（前端询问有没有天地图 key）")
chk('send_error(502, "Tile upstream error")' in src, "瓦片失败用 ASCII 状态行（避免 latin-1 编码崩溃）")
chk('guess_image_type' in src and 'data[:2] == b"\\xff\\xd8"' in src, "能按文件头识别 JPEG（天地图影像是 JPEG）")
# 只匹配真正的代码写法；注释里提到这个字段名不算问题
chk('"point_heights": [' not in src,
    "生成端不再写冗余的 point_heights（与坐标第三维重复，占 13.5% 体积）")
chk('record["height"]' in src or 'r["height"]' in src,
    "坐标第三维仍然带着高度（删的是重复那份，不是信息本身）")
chk('VENDOR_DIR' in consts, "已定义本地第三方资源目录")
chk('VENDOR_CONTENT_TYPES' in consts, "已定义 vendor 资源的 MIME 表")
chk('if path.startswith("/vendor/")' in src, "有 /vendor/ 路由（页面可离线加载 Leaflet）")
chk('".." in name' in src and '"\\\\" in name' in src,
    "vendor 路由挡掉了路径穿越（只允许单层文件名）")
chk('Cache-Control", "public, max-age=604800"' in src, "vendor 资源带缓存头")
chk('gb_yaw' in src and 'gb_pitch' in src and 'focal_len' in src and 'dzoom_ratio' in src,
    "解析了云台朝向/俯仰、焦距、数码变焦")
chk('resolve_project_file' in src and 'resolve_project_video' in src,
    "文件解析已抽出复用（视频 + SRT）")
chk('"-movflags", "+faststart"' in src, "转码带 +faststart（moov 前置，秒开）")
chk('"-map", "0:a?"' in src, "可选音轨（无音轨的文件不会失败）")
chk('"-map", "0:v:0"' in src, "只取一路视频轨（避开 DJI 的 mjpeg/字幕轨）")
chk('handler.send_header("Content-Length", "0")' in src, "416 响应补了 Content-Length")
chk('hashlib.sha1' in src, "片段缓存以内容指纹命名")

# 确认 stream_project_video 已被重构为复用 send_file_range，没有残留重复逻辑
i = src.find("def stream_project_video")
j = src.find("def ", i + 10)
body = src[i:j]
chk("send_file_range(handler, video_path, content_type)" in body, "stream_project_video 复用 send_file_range")
chk("range_header" not in body, "原函数里不再有重复的 Range 解析")

# 关键参数范围校验
chk("max(5.0, min(seconds, 600.0))" in src, "片段长度被限幅在 5~600 秒")
chk("duration - seconds" in src, "起播点越界时回退，避免转出空片段")

print("\n=== 删除项目接口 ===")
chk('/api/project/delete' in src, "注册了 /api/project/delete 路由")
chk('def delete_project(self)' in src, "有 delete_project()")
chk('shutil.rmtree(target)' in src, "用 rmtree 删项目目录")
chk('target.parent != root' in src,
    "只允许删 Project 的直接子目录（去掉空白后比对，挡住 ../ 路径穿越）")
# 删项目绝不碰 Data：这个语义写进了注释，也写了显式防护
chk('删除项目不会动数据文件' in src, "注释写明「删除项目不会动数据文件」")
chk('data_rootintarget.parents' in src.replace(' ', ''),
    "显式挡住 Data 目录（万一 PROJECT_DIR 定义被改动也拦得住）")

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
