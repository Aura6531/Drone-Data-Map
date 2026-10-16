# -*- coding: utf-8 -*-
"""核实「相对高度 / 海拔」的关系，以及它对覆盖几何的含义。

用户 2026-10-15 指出：
> 贡嘎的第三个视频是来回飞行录制的，因为是山顶起飞，起飞点高度 0m（非海拔），
> 然后有些片段是飞到了山顶的侧下方，高度为负值。这个是正常情况，
> 换算成海拔就没问题了。

所以负的 `rel_alt` **不是错误**。这个测试把这件事钉成不变量：
  ① `abs_alt − rel_alt` 是常数（起飞点海拔），标准差 ≈ 0
  ② 负的 `rel_alt` 对应的 `abs_alt` 仍是合理的正值
  ③ `load_srt_telemetry` 现在给出 `takeoff_elev` 与 `alt_abs`
  ④ **并暴露真正的局限**：覆盖几何把 rel_alt 当"离地高度"用，
     在山地会偏 —— 正确处理需要 DEM
"""
import statistics
import sys
from pathlib import Path

sys.path.insert(0, r"<仓库根>\Code")
import coverage as cov
import project_manager as pm

ROOT = Path(r"<仓库根>\Data\360视频")
ok = True


def chk(cond, label, extra=""):
    global ok
    if not cond:
        ok = False
    print("  [%s] %s%s" % ("OK" if cond else "FAIL", label,
                           (" -> " + str(extra)) if extra else ""))


osvs = sorted(ROOT.rglob("*.OSV"))
chk(len(osvs) >= 4, "素材够测", "%d 段" % len(osvs))

print()
print("=== ① abs_alt − rel_alt 是常数（起飞点海拔）===")
worst_std = 0.0
rows = []
for osv in osvs:
    srt = osv.with_suffix(".SRT")
    if not srt.is_file():
        continue
    t = pm.load_srt_telemetry(srt)
    rel = t.get("alt") or []
    ab = t.get("alt_abs") or []
    offs = [a - r for a, r in zip(ab, rel) if a is not None and r is not None]
    if len(offs) < 3:
        continue
    std = statistics.pstdev(offs)
    worst_std = max(worst_std, std)
    rows.append((osv.name, t.get("takeoff_elev"), min(rel), min(ab), std))

chk(worst_std < 0.01,
    "所有素材的偏移标准差都 ≈ 0（说明只是**基准不同**）",
    "最大 std %.4f" % worst_std)
for name, elev, rmin, amin, std in rows[:4]:
    print("     %-34s 起飞点 %7.1f m   rel最小 %8.1f   abs最小 %8.1f   std %.4f"
          % (name, elev, rmin, amin, std))

print()
print("=== ② 负的 rel_alt 对应的 abs_alt 仍是合理正值 ===")
neg_cases = [(n, e, r, a) for (n, e, r, a, _s) in rows if r < 0]
chk(len(neg_cases) > 0, "确实有素材出现负的相对高度（山顶起飞飞到侧下方）",
    "%d 段" % len(neg_cases))
for name, elev, rmin, amin in neg_cases:
    chk(amin > 0 and amin > 1000,
        "%s：rel 最低 %.1f m 但海拔 %.1f m（正常）" % (name[:26], rmin, amin))

print()
print("=== ③ load_srt_telemetry 现在给出这两个量 ===")
one = next((o for o in osvs if "075758_0001" in o.name), None)
if one is None:
    one = osvs[0]
t = pm.load_srt_telemetry(one.with_suffix(".SRT"))
chk("takeoff_elev" in t, "有 takeoff_elev", t.get("takeoff_elev"))
chk("alt_abs" in t and len(t["alt_abs"]) == t["count"],
    "有 alt_abs 且与逐点对齐", "%d 个" % len(t.get("alt_abs") or []))
chk(isinstance(t.get("takeoff_elev"), float), "takeoff_elev 是数值")

print()
print("=== ④ 真正的局限：覆盖几何把 rel_alt 当离地高度 ===")
# 这段素材 rel 最低 -108.7 m —— 也就是有相当比例的帧因为 alt<=0 被跳过，
# 而其中一部分其实是"飞到山顶侧下方"，离地高度可能仍是正的。
if one is not None:
    rel = [a for a in (t.get("alt") or []) if a is not None]
    skipped = sum(1 for a in rel if a <= 0)
    print("     %s" % one.name)
    print("       采样 %d，其中 rel_alt <= 0 的 %d 帧（%.0f%%）会被覆盖跳过"
          % (len(rel), skipped, 100.0 * skipped / max(1, len(rel))))
    print("       这些帧里有些是**飞到山顶侧下方**，离地高度可能仍是正的。")
    print("       要正确处理需要 DEM（地形高程）—— 目前没有，所以这里是保守跳过。")
    chk(skipped > 0, "这个局限真的会出现（不是理论问题）")

# 覆盖代码里确实是 alt <= 0 就跳过
src = (Path(r"<仓库根>\Code") / "coverage.py").read_text(encoding="utf-8")
chk("alt <= 0" in src, "coverage.py 里确实是 alt <= 0 就跳过（记录在案）")

print()
print("结果:", "全部通过" if ok else "有失败项")
raise SystemExit(0 if ok else 1)
