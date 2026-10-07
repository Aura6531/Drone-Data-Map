import subprocess, sys, io, re, os, shutil
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent
# ffmpeg：先看环境变量 FFMPEG，再找 PATH，最后用打包目录里那份
FF = (os.environ.get("FFMPEG") or shutil.which("ffmpeg")
      or str(ROOT_DIR / "packaging" / "payload" / "ffmpeg" / "ffmpeg.exe"))
SRC = str(ROOT_DIR / "Data" / "DJI_202609240950_001" / "DJI_20260924095258_0001_V.MP4")
OUT = ROOT_DIR / "lens_probe"
OUT.mkdir(parents=True, exist_ok=True)

for idx in (1, 2):
    dst = OUT / f"stream{idx}.bin"
    cmd = [FF, "-hide_banner", "-loglevel", "error", "-t", "8", "-i", SRC,
           "-map", f"0:{idx}", "-c", "copy", "-f", "data", "-y", str(dst)]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    size = dst.stat().st_size if dst.exists() else 0
    print(f"流 0:{idx} 提取 {size} 字节  (ffmpeg rc={r.returncode})")
    if r.returncode != 0:
        print("   stderr:", r.stderr.decode("utf-8", "replace")[:200])
    if not size:
        continue

    blob = dst.read_bytes()
    # 抽出可打印字符串
    strings = re.findall(rb"[\x20-\x7e]{4,}", blob)
    text = [s.decode("latin1") for s in strings]

    print(f"   可打印字符串 {len(text)} 段，前 12 段示例:")
    for s in text[:12]:
        print("     ", s[:100])

    print("   含测距/激光类关键词的字符串:")
    hits = [s for s in text if re.search(r"laser|range|dist|\blr\b|target|alt", s, re.I)]
    for s in hits[:15]:
        print("     ", s[:120])
    if not hits:
        print("      无")

    # protobuf 风格的字段名候选（短小写单词）
    words = sorted({w for s in text for w in re.findall(r"[a-z_]{3,20}", s)})
    print(f"   字段名候选（{len(words)} 个）: {', '.join(words[:40])}")
    print()
