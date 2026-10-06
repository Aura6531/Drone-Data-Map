"""抓取 dji-drone-metadata-embedder 的 SRT 格式目录，抽取「机型 x 字段」骨架。

只输出紧凑骨架（标题 / 表格行 / 关键字计数），避免把整份长文档塞进对话。
同时对照我们自己的解析器，列出我们已经提取的字段。
"""

import json
import pathlib
import re
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

RAW = "https://raw.githubusercontent.com/CallMarcus/dji-drone-metadata-embedder/master/docs/SRT_FORMATS.md"
LICENSE_URL = "https://raw.githubusercontent.com/CallMarcus/dji-drone-metadata-embedder/master/LICENSE"

FIELDS = {
    "经纬度": r"latitude|longitude|GPS\(",
    "高度": r"altitude|abs_alt|rel_alt|height",
    "偏航角": r"yaw|heading",
    "云台俯仰": r"pitch|gimbal",
    "云台横滚": r"roll",
    "缩放/焦距": r"zoom|focal|focal_len|zoomfactor",
    "光圈/快门/ISO": r"fnum|shutter|iso",
    "时间": r"datetime|timestamp|TIME",
}

text = urllib.request.urlopen(
    urllib.request.Request(RAW, headers={"User-Agent": "Mozilla/5.0"}), timeout=60
).read().decode("utf-8", "replace")

license_text = urllib.request.urlopen(
    urllib.request.Request(LICENSE_URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=60
).read().decode("utf-8", "replace")

out = pathlib.Path("docs/_srt_formats_raw.md")
out.write_text(text, encoding="utf-8")

print(f"  SRT_FORMATS.md {len(text)} 字符 / {len(text.splitlines())} 行 -> {out}")
print(f"  LICENSE 首行: {license_text.splitlines()[0][:80]}")
print(f"  LICENSE 是否 MIT: {'MIT' in license_text}")

print("\n=== 标题骨架 ===")
for line in text.splitlines():
    if re.match(r"^#{1,4}\s", line):
        print("  " + line.strip()[:110])

print("\n=== 表格（前 30 行） ===")
rows = [line for line in text.splitlines() if line.strip().startswith("|")]
for line in rows[:30]:
    print("  " + " | ".join(cell.strip() for cell in line.strip().strip("|").split("|"))[:150])
print(f"  （表格共 {len(rows)} 行）")

# 按小节切分，统计每个机型小节里出现了哪些关键字
print("\n=== 各机型小节 x 字段出现情况 ===")
sections = re.split(r"\n(?=#{2,3}\s)", text)
for section in sections:
    head = section.splitlines()[0].strip("# ").strip() if section.strip() else ""

    if not head or not re.search(r"DJI|Mini|Mavic|Air|Avata|Neo|Matrice|Phantom|Anafi", head, re.I):
        continue

    hits = [name for name, pattern in FIELDS.items() if re.search(pattern, section, re.I)]
    code = re.findall(r"\[[a-z_]+:", section)

    print(f"  {head[:58]:60} 字段: {'、'.join(hits) if hits else '（无）'}")
    if code:
        print(f"  {'':60} 样例键: {' '.join(sorted(set(code))[:8])}")

print("\n=== 我们自己的解析器提取哪些字段 ===")
pm = pathlib.Path("Code/project_manager.py").read_text(encoding="utf-8")
our = {
    "经纬度": r"latitude|longitude",
    "相对高度": r"rel_alt|relative_alt|altitude",
    "绝对高度": r"abs_alt",
    "偏航角": r"yaw|droneBearing|bearing",
    "云台俯仰": r"\bpitch\b",
    "云台横滚": r"\broll\b",
    "焦距/缩放": r"focal|zoom",
    "光圈/快门/ISO": r"fnum|shutter|\biso\b",
}
for name, pattern in our.items():
    print(f"  {name:10} {'有' if re.search(pattern, pm, re.I) else '【无】'}")

print(f"\n  原始文件留在 {out}（供后续逐步阅读，不进仓库也没关系）")
