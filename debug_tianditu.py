import json, sys, io, urllib.request, urllib.error, pathlib
from urllib.parse import urlencode

sys.stdout.reconfigure(encoding="utf-8")

KEY = ""
for line in pathlib.Path(r"<仓库根>\Code\tianditu_key.txt").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#"):
        KEY = line
        break

V2 = "https://api.tianditu.gov.cn/v2/search"
CHINA = "73,3,135,54"

def query(keyword, query_type, map_bound=CHINA, count=5):
    post = {"keyWord": keyword, "level": 12, "mapBound": map_bound,
            "queryType": query_type, "start": 0, "count": count}
    url = V2 + "?" + urlencode({"postStr": json.dumps(post, ensure_ascii=False),
                                "type": "query", "tk": KEY})
    req = urllib.request.Request(url, headers={"User-Agent": "test/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_body": e.read().decode("utf-8", "replace")[:200]}
    except Exception as e:
        return {"_err": f"{type(e).__name__}: {e}"}

KEYWORDS = ["肇庆市", "肇庆市端州区", "南岸街道", "肇庆市端州区南岸街道",
            "黄塘窦水闸", "东莞市", "西江大桥"]

for qt in (1, 2):
    print("=" * 78)
    print(f"queryType = {qt}")
    print("=" * 78)
    for kw in KEYWORDS:
        d = query(kw, qt)
        if "_http" in d or "_err" in d:
            print(f"  {kw:<20} 失败 {d}")
            continue
        st = (d.get("status") or {}).get("cndesc")
        info = (d.get("status") or {}).get("infocode")
        pois = d.get("pois") or []
        area = d.get("area") or {}
        line = f"  {kw:<20} resultType={d.get('resultType')} count={d.get('count')} pois={len(pois)} status={info}/{st}"
        print(line)
        if area:
            print(f"      area: name={area.get('name')} lonlat={area.get('lonlat')} level={area.get('level')}")
        for poi in pois[:4]:
            print(f"      poi: {poi.get('name')}  {poi.get('lonlat')}  {poi.get('address')}  type={poi.get('poiType')}")
        prompt = d.get("prompt") or []
        if prompt:
            print(f"      prompt: {[p.get('keyword') for p in prompt[:4]]}")
