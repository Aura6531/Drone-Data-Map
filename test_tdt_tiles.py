import urllib.request, urllib.error, sys, io, pathlib
sys.stdout.reconfigure(encoding="utf-8")

KEY = ""
for line in pathlib.Path(r"<仓库根>\Code\tianditu_key.txt").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#"):
        KEY = line
        break
print("tk =", KEY[:8] + "..." + KEY[-4:] if KEY else "(空)")
print()

LAYERS = [
    ("矢量底图  vec", "vec", "vec_w"),
    ("影像底图  img", "img", "img_w"),
    ("矢量注记  cva", "cva", "cva_w"),
    ("影像注记  cia", "cia", "cia_w"),
]

# 东莞附近 z=10 x=836 y=444
for name, layer, service in LAYERS:
    url = (f"https://t0.tianditu.gov.cn/{service}/wmts"
           f"?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER={layer}"
           f"&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles"
           f"&TILEMATRIX=10&TILEROW=444&TILECOL=836&tk={KEY}")
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "LianheZhihui-UAV-Inspection-Map/1.0"}
        )
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read()
            ctype = r.headers.get("Content-Type", "")
            head = data[:4].hex()
            kind = "PNG" if data[:4] == b"\x89PNG" else ("JPEG" if data[:2] == b"\xff\xd8" else "其他")
            print(f"  {name}  HTTP 200  类型={ctype:<12} {len(data):>7} 字节  文件头={head}  -> {kind}")
    except urllib.error.HTTPError as e:
        body = e.read()[:200].decode("utf-8", "replace")
        print(f"  {name}  HTTP {e.code}  {body}")
    except Exception as e:
        print(f"  {name}  失败 {type(e).__name__}: {e}")

# 把影像那块存下来，确认是一张真图
url = (f"https://t0.tianditu.gov.cn/img_w/wmts"
       f"?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=img"
       f"&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles"
       f"&TILEMATRIX=10&TILEROW=444&TILECOL=836&tk={KEY}")
out = pathlib.Path(r"<仓库根>\lens_probe\tdt_img_test.png")
try:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        out.write_bytes(r.read())
    print(f"\n影像瓦片已存 {out}  {out.stat().st_size} 字节")
except Exception as e:
    print("\n保存影像瓦片失败:", e)
