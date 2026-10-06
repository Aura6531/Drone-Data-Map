import urllib.request, urllib.error, sys, io, pathlib
sys.stdout.reconfigure(encoding="utf-8")

# 路径按脚本所在目录推导（换机器/换盘符都不用改）
ROOT = pathlib.Path(__file__).resolve().parent

# 天地图对部分 UA 直接回 403（实测 Mozilla/5.0 取 img 瓦片会被拒），统一用这个
UA = "LianheZhihui-UAV-Inspection-Map/1.0"

key_file = ROOT / "Code" / "tianditu_key.txt"
if not key_file.exists():
    print(f"找不到 {key_file} —— 这套需要天地图 tk（只有 node run_tests.js --with-net 会跑到它）")
    sys.exit(1)

KEY = ""
# utf-8-sig：记事本另存 UTF-8 会带 BOM，strip() 去不掉，会把 tk 弄脏
for line in key_file.read_text(encoding="utf-8-sig").splitlines():
    line = line.strip()
    if line and not line.startswith("#"):
        KEY = line
        break
print("tk =", KEY[:8] + "..." + KEY[-4:] if KEY else "(空)")
if not KEY:
    print("tk 是空的 —— 先在天地图控制台申请，再粘进 Code/tianditu_key.txt")
    sys.exit(1)
print()

LAYERS = [
    ("矢量底图  vec", "vec", "vec_w"),
    ("影像底图  img", "img", "img_w"),
    ("矢量注记  cva", "cva", "cva_w"),
    ("影像注记  cia", "cia", "cia_w"),
]

# 东莞附近 z=10 x=836 y=444
failed = []
for name, layer, service in LAYERS:
    url = (f"https://t0.tianditu.gov.cn/{service}/wmts"
           f"?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER={layer}"
           f"&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles"
           f"&TILEMATRIX=10&TILEROW=444&TILECOL=836&tk={KEY}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read()
            ctype = r.headers.get("Content-Type", "")
            head = data[:4].hex()
            kind = "PNG" if data[:4] == b"\x89PNG" else ("JPEG" if data[:2] == b"\xff\xd8" else "其他")
            print(f"  {name}  HTTP 200  类型={ctype:<12} {len(data):>7} 字节  文件头={head}  -> {kind}")
    except urllib.error.HTTPError as e:
        body = e.read()[:200].decode("utf-8", "replace")
        failed.append(f"{name} HTTP {e.code}")
        print(f"  {name}  HTTP {e.code}  {body}")
    except Exception as e:
        failed.append(f"{name} {type(e).__name__}")
        print(f"  {name}  失败 {type(e).__name__}: {e}")

# 把影像那块存下来，确认是一张真图（只是留个样图，判定看上面的 HTTP 状态）
url = (f"https://t0.tianditu.gov.cn/img_w/wmts"
       f"?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=img"
       f"&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles"
       f"&TILEMATRIX=10&TILEROW=444&TILECOL=836&tk={KEY}")
out = ROOT / "lens_probe" / "tdt_img_test.png"
out.parent.mkdir(parents=True, exist_ok=True)
try:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        out.write_bytes(r.read())
    print(f"\n影像瓦片已存 {out}  {out.stat().st_size} 字节")
except Exception as e:
    print(f"\n影像存档失败（只是留样图，不算上面的判定）：{type(e).__name__}: {e}")

print()
if failed:
    print("失败：" + "、".join(failed))
    sys.exit(1)
print("结果: 全部通过（4 个图层都是 HTTP 200）")
