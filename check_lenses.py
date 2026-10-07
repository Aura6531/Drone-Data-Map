import re, sys, io
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

DATA   = Path(__file__).resolve().parent / "Data"
SERVED = DATA / "DJI_202609240950_001"     # 项目里记录的路径（服务实际读的）
LOCAL  = DATA / "DJI_202609240950_001"

print("=== 服务实际读取的目录里有什么 ===")
print(f"{SERVED}  存在={SERVED.exists()}")
if SERVED.exists():
    for f in sorted(SERVED.iterdir()):
        if f.suffix.lower() in (".srt", ".mp4", ".geojson"):
            print(f"   {f.name:<42} {f.stat().st_size/1048576:8.2f} MB")

RX = {
    "focal": re.compile(r"\[focal_len:\s*([-\d.]+)\]"),
    "dzoom": re.compile(r"\[dzoom_ratio:\s*([-\d.]+)\]"),
    "yaw":   re.compile(r"gb_yaw:\s*([-\d.]+)"),
    "pitch": re.compile(r"gb_pitch:\s*([-\d.]+)"),
    "alt":   re.compile(r"\[rel_alt:\s*([-\d.]+)"),
}

def load(path, limit=None):
    out = {k: [] for k in RX}
    n = 0
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if "latitude" not in line:
                continue
            n += 1
            for k, rx in RX.items():
                m = rx.search(line)
                out[k].append(float(m.group(1)) if m else None)
            if limit and n >= limit:
                break
    return out

files = {}
for tag in ("V", "S", "T"):
    p = SERVED / f"DJI_20260924095258_0001_{tag}.srt"
    if p.exists():
        files[tag] = load(p)
        print(f"\n{tag}: 读了 {len(files[tag]['focal'])} 帧")

if len(files) >= 2:
    print("\n=== 同一帧上三路的焦距/朝向/俯仰是否相同 ===")
    vs = [t for t in ("V", "S", "T") if t in files]
    n = min(len(files[t]["focal"]) for t in vs)
    steps = [0, 100, 5000, 12000, 20000, 30000]
    print(f"{'帧号':>7}  " + "  ".join(f"{t}:焦距/偏航/俯仰" for t in vs))
    for i in steps:
        if i >= n:
            continue
        row = f"{i:>7}  "
        for t in vs:
            d = files[t]
            row += f"  {d['focal'][i]:>7.1f} / {d['yaw'][i]:>7.1f} / {d['pitch'][i]:>6.1f}"
        print(row)

    print("\n=== V 与 S 的焦距数组是否逐帧相同 ===")
    if "V" in files and "S" in files:
        n2 = min(len(files["V"]["focal"]), len(files["S"]["focal"]))
        same = sum(1 for i in range(n2) if files["V"]["focal"][i] == files["S"]["focal"][i])
        print(f"   相同帧数 {same}/{n2}  ({100*same/n2:.1f}%)")
        diff = [i for i in range(n2) if files["V"]["focal"][i] != files["S"]["focal"][i]][:5]
        for i in diff:
            print(f"   第{i}帧  V={files['V']['focal'][i]}  S={files['S']['focal'][i]}")

    print("\n=== 各路的焦距取值集合（判断是定焦还是变焦）===")
    for t in vs:
        vals = sorted(set(files[t]["focal"]))
        print(f"   {t}: 共 {len(vals)} 种取值，范围 {vals[0]} ~ {vals[-1]}")

    print("\n=== dzoom（数码变焦）取值集合 ===")
    for t in vs:
        vals = sorted(set(files[t]["dzoom"]))
        print(f"   {t}: 共 {len(vals)} 种，范围 {vals[0]} ~ {vals[-1]}")
