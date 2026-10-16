import sys, json, io, pathlib, shutil

sys.stdout.reconfigure(encoding="utf-8")
# 路径按脚本所在目录推导（换机器/换盘符都不用改）
ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "Code"))

import project_manager as pm

# 测试期间不要碰真实的磁盘缓存：geocode_place 会先查 Code/geocode_cache/（30 天），
# 只要「肇庆市」被页面搜索框缓存过一次，下面第 3 段就永远走缓存、假 urlopen 不被调用，
# 断言会莫名其妙全空。所以换到测试自己的缓存目录（已 gitignore），并且每次先清空 ——
# 否则上一次跑留下的缓存会同样把第 3 段弄成假绿/假红。
_TEST_CACHE = ROOT / "_test_geocode_cache"

pm.GEOCODE_CACHE_DIR = _TEST_CACHE


def clear_geocode_cache():
    """内存缓存 + 磁盘缓存一起清。

    只清内存是不够的：前面几段一旦把关键词写进磁盘缓存（30 天有效），
    后面「这段应该发请求 / 应该报错」的断言就会全部落空 ——
    这个文件以前就踩过：第 3 段缓存了「肇庆市」，第 6 段就不再发请求、也不报错了。
    """

    pm.GEOCODE_MEMORY.clear()
    shutil.rmtree(pm.GEOCODE_CACHE_DIR, ignore_errors=True)


clear_geocode_cache()

# 让测试确定化：不要读真实的 tianditu_key.txt
NO_SUCH = ROOT / "__no_such_key_file__.txt"
TMP_KEY = ROOT / "_test_key.txt"

ok = True
def chk(cond, label, extra=""):
    global ok
    ok &= bool(cond)
    print(f"  {'[OK]' if cond else '[FAIL]'} {label}{(' -> ' + str(extra)) if extra else ''}")

print("=== 0) get_tianditu_key() 取值优先级 ===")
pm.TIANDITU_KEY_FILE = NO_SUCH
if TMP_KEY.exists(): TMP_KEY.unlink()
for v in ("TIANDITU_KEY", "TIANDITU_KEY_FILE"):
    pass

pm.TIANDITU_KEY = ""
import os
os.environ.pop("TIANDITU_KEY", None)
chk(pm.get_tianditu_key() == "", "文件不存在 + 无环境变量 + 常量为空 -> 空")

pm.TIANDITU_KEY = "CONST_KEY"
chk(pm.get_tianditu_key() == "CONST_KEY", "回退到源码常量", pm.get_tianditu_key())

pm.TIANDITU_KEY_FILE = TMP_KEY
TMP_KEY.write_text("# 只有注释\n\n# 还是注释\n", encoding="utf-8")
chk(pm.get_tianditu_key() == "CONST_KEY", "文件里只有注释 -> 继续回退到常量")

TMP_KEY.write_text("# 注释\nabcd1234abcd1234abcd1234abcd1234\n", encoding="utf-8")
chk(pm.get_tianditu_key() == "abcd1234abcd1234abcd1234abcd1234",
    "文件里的 key 生效（优先级高于常量）", pm.get_tianditu_key())

os.environ["TIANDITU_KEY"] = "ENV_KEY"
chk(pm.get_tianditu_key() == "ENV_KEY", "环境变量优先级最高", pm.get_tianditu_key())
os.environ.pop("TIANDITU_KEY", None)

pm.TIANDITU_KEY = ""
pm.TIANDITU_KEY_FILE = NO_SUCH
chk(pm.get_tianditu_key() == "", "全部为空 -> 空（会被拦下并给出提示）")

print("\n=== 0b) key 文件带 BOM（Windows 记事本另存 UTF-8 会加）===")
BOM_KEY = ROOT / "_test_bom_key.txt"
BOM_KEY.write_bytes(b"\xef\xbb\xbf" + b"feedfacefeedfacefeedfacefeedface\n")
pm.TIANDITU_KEY = ""
pm.TIANDITU_KEY_FILE = BOM_KEY
got = pm.get_tianditu_key()
chk(got == "feedfacefeedfacefeedfacefeedface",
    "BOM 被吃掉，tk 前后没有脏字符", repr(got[:6]) + "..." + repr(got[-6:]))
try:
    BOM_KEY.unlink()
except OSError:
    pass

print("\n=== 1) parse_lonlat 兼容性 ===")
cases = [
    ("116.420888 39.609496", (116.420888, 39.609496), "v1 空格分隔"),
    ("116.397,39.909",       (116.397, 39.909),       "v2 逗号分隔"),
    ("112.466997,23.034410", (112.466997, 23.034410), "真实水印坐标"),
    ("  112.4 ,  23.0  ",    (112.4, 23.0),           "带多余空格"),
    ("",                     (None, None),            "空串"),
    (None,                   (None, None),            "None"),
    ("abc",                  (None, None),            "非数字"),
    ("116.4",                (None, None),            "只有一个数"),
]
for value, expected, label in cases:
    got = pm.parse_lonlat(value)
    chk(got == expected, label, f"{value!r} -> {got}")

print("\n=== 2) 无 key 时的报错（应指向配置文件名）===")
EMPTY_KEY = ROOT / "_test_empty_key.txt"
EMPTY_KEY.write_text("# 只有注释，没有 key\n", encoding="utf-8")
pm.TIANDITU_KEY = ""
pm.TIANDITU_KEY_FILE = EMPTY_KEY
try:
    pm.geocode_place("肇庆市")
    chk(False, "应抛出 ValueError")
except ValueError as e:
    chk("No Tianditu key configured" in str(e) and EMPTY_KEY.name in str(e),
        "提示里给出了配置文件名", str(e))

print("\n=== 2b) 真实 tianditu_key.txt 能被正确读取 ===")
REAL_KEY = ROOT / "Code" / "tianditu_key.txt"
pm.TIANDITU_KEY_FILE = REAL_KEY
real = pm.get_tianditu_key()
chk(len(real) == 32 and all(c in "0123456789abcdefABCDEF" for c in real),
    "读到 32 位十六进制 tk", f"{real[:8]}...{real[-4:]}（长度 {len(real)}）")
pm.TIANDITU_KEY = ""
pm.TIANDITU_KEY_FILE = NO_SUCH

print("\n=== 3) v2 返回结构（status.code + 逗号 lonlat）===")
captured = {}

class FakeResp:
    def __init__(self, payload): self._b = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    def read(self): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False

v2 = {
    "status": {"code": 0, "cndesc": "成功"},
    "count": 2,
    "pois": [
        {"name": "肇庆市", "address": "广东省肇庆市", "lonlat": "112.472246,23.031779", "phone": ""},
        {"name": "南岸街道", "address": "广东省肇庆市高要区", "lonlat": "112.4 , 23.0"},
        {"name": "坏数据", "address": "", "lonlat": ""},
    ],
}
def fake_urlopen(request, timeout=None):
    captured["url"] = request.full_url if hasattr(request, "full_url") else str(request)
    return FakeResp(v2)

pm.urllib.request.urlopen = fake_urlopen
pm.TIANDITU_KEY = "TESTKEY"
clear_geocode_cache()
data = pm.geocode_place("肇庆市")

chk(data["keyword"] == "肇庆市", "回显关键词")
chk(data["count"] == 2, "坏数据被丢弃，剩 2 条", data["count"])
chk(data["results"][0] == {"name": "肇庆市", "address": "广东省肇庆市",
                           "lon": 112.472246, "lat": 23.031779, "kind": "poi"},
    "第一条解析正确（含 kind）", data["results"][0])
chk(data["results"][1]["lon"] == 112.4 and data["results"][1]["lat"] == 23.0, "空格分隔也能解析")

u = captured.get("url", "")
chk("api.tianditu.gov.cn/v2/search" in u, "打到天地图 v2 接口")
chk("type=query" in u, "带 type=query")
chk("tk=TESTKEY" in u, "带 tk")
chk("postStr=" in u, "带 postStr")
from urllib.parse import urlparse, parse_qs
qs = parse_qs(urlparse(u).query)
post = json.loads(qs["postStr"][0])
chk(post.get("keyWord") == "肇庆市", "postStr.keyWord", post)
chk(post.get("queryType") == 1 and post.get("level") == 12, "postStr 其余参数", post)

print("\n=== 4) 内存缓存命中（不应再发请求）===")
captured.clear()
data2 = pm.geocode_place("肇庆市")
chk("url" not in captured, "第二次未发起网络请求")
chk(data2["count"] == 2, "命中缓存且内容一致")

print("\n=== 5) v1 返回结构（ret_code + 空格 lonlat）===")
v1 = {"ret_code": 0, "remark": "请求成功", "count": "1",
      "pois": [{"name": "绿茵超市", "lonlat": "116.420888 39.609496", "address": "北京市大兴区"}]}
pm.urllib.request.urlopen = lambda request, timeout=None: FakeResp(v1)
clear_geocode_cache()
d1 = pm.geocode_place("超市")
chk(d1["count"] == 1 and d1["results"][0]["lat"] == 39.609496, "v1 结构可解析", d1["results"])

print("\n=== 6) 天地图报错时的提示 ===")
pm.urllib.request.urlopen = lambda request, timeout=None: FakeResp(
    {"status": {"code": -1, "cndesc": "无效的 tk 参数"}})
clear_geocode_cache()
try:
    pm.geocode_place("肇庆市")
    chk(False, "应抛出 ValueError")
except ValueError as e:
    chk("无效的 tk" in str(e), "status.code 变体：把原因透传给用户", str(e))

pm.urllib.request.urlopen = lambda request, timeout=None: FakeResp(
    {"count": 0, "resultType": 1, "status": {"cndesc": "缺少参数：mapBound", "infocode": 2003}})
clear_geocode_cache()
try:
    pm.geocode_place("东莞市")
    chk(False, "应抛出 ValueError")
except ValueError as e:
    chk("缺少参数" in str(e), "真实 v2 形态（infocode）也能报错", str(e))

pm.urllib.request.urlopen = lambda request, timeout=None: FakeResp(
    {"msg": "该tk已限流", "code": 302010, "resolve": "请求已限流，请稍后重试!"})
clear_geocode_cache()
try:
    pm.geocode_place("西江大桥")
    chk(False, "应抛出 ValueError")
except ValueError as e:
    chk("限流" in str(e) or "302010" in str(e) or "该tk已限流" in str(e),
        "顶层 code 形态（限流）也能报错", str(e))

print("\n=== 7) 参数校验 ===")
pm.urllib.request.urlopen = lambda request, timeout=None: FakeResp(v2)
clear_geocode_cache()
for bad in ("", "   "):
    try:
        pm.geocode_place(bad); chk(False, f"空关键词应报错 {bad!r}")
    except ValueError as e:
        chk("请输入" in str(e), f"空关键词报错 {bad!r}")
try:
    pm.geocode_place("x" * 61); chk(False, "超长应报错")
except ValueError as e:
    chk("过长" in str(e), "超长关键词被拦截")

if TMP_KEY.exists(): TMP_KEY.unlink()
if EMPTY_KEY.exists(): EMPTY_KEY.unlink()
print("\n=== 2c) 老位置的 key 会自动迁移到数据目录 ===")

# 用工作区里的目录做沙箱：沙箱环境里 %TEMP% 不一定可写
MIGRATE_SANDBOX = ROOT / "_test_geocode_cache" / "migrate"
shutil.rmtree(MIGRATE_SANDBOX, ignore_errors=True)
LEGACY_DIR = MIGRATE_SANDBOX / "Code"
LEGACY_DIR.mkdir(parents=True)
(LEGACY_DIR / "tianditu_key.txt").write_text("f" * 32 + "\n", encoding="utf-8")
MIGRATE_TARGET = MIGRATE_SANDBOX / "data" / "tianditu_key.txt"

_real_code_dir, _real_key_file = pm.CODE_DIR, pm.TIANDITU_KEY_FILE
pm.CODE_DIR, pm.TIANDITU_KEY_FILE = LEGACY_DIR, MIGRATE_TARGET

try:
    chk(pm.migrate_legacy_key_file() is True, "老位置有 key -> 搬一份到数据目录")
    chk(MIGRATE_TARGET.is_file()
        and MIGRATE_TARGET.read_text(encoding="utf-8").strip() == "f" * 32,
        "搬过去的内容与原来一致")
    chk(pm.migrate_legacy_key_file() is False, "已经搬过就不再重复搬（不覆盖新位置）")

finally:
    pm.CODE_DIR, pm.TIANDITU_KEY_FILE = _real_code_dir, _real_key_file
    shutil.rmtree(MIGRATE_SANDBOX, ignore_errors=True)

print("\n结果:", "全部通过" if ok else "有失败项")
sys.exit(0 if ok else 1)
