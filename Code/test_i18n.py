# -*- coding: utf-8 -*-
"""双语（i18n）自检。

覆盖这几件**真的出过错**的事：
  ① 字典有重复键（大小写不同也算）—— 生成的 JSON 严格解析器会直接报错
  ② zh / en 缺一边（半翻译）
  ③ 英文原串当键的查表与"未翻译退回英文"
  ④ 语言代码归一（认得 zh-CN / en-US / 乱输）
"""
import ast
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE))

import i18n
import i18n_ui

ok = True


def chk(cond, label, extra=""):
    global ok
    if not cond:
        ok = False
    print("  [%s] %s%s" % ("OK" if cond else "FAIL", label,
                           (" -> " + str(extra)) if extra else ""))


def dict_keys_of(path, var):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if var in [getattr(t, "id", "") for t in targets] \
                    and isinstance(node.value, ast.Dict):
                return [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
    return None


print("=== 1) 字典键必须唯一（含大小写冲突）===")
for name, var in (("i18n_ui.py", "UI_ZH"), ("i18n.py", "MESSAGES")):
    keys = dict_keys_of(CODE / name, var)
    chk(keys is not None, "%s 里找得到 %s" % (name, var))
    if keys is None:
        continue
    exact = sorted({k for k in keys if keys.count(k) > 1})
    chk(not exact, "%s 没有完全重复的键" % var, exact)
    lowered = {}
    case_dups = []
    for k in keys:
        low = k.lower()
        if low in lowered and lowered[low] != k:
            case_dups.append((lowered[low], k))
        lowered.setdefault(low, k)
    chk(not case_dups,
        "%s 没有大小写冲突（JSON 里是同一个键，严格解析器会报错）" % var,
        case_dups)

print("\n=== 2) 结构化文案 zh / en 必须成对 ===")
problems = i18n.self_check()
chk(not problems, "每条都有 zh 与 en", problems[:6])
chk(len(i18n.MESSAGES) > 50, "条目数合理", len(i18n.MESSAGES))
print("    界面文案 UI_ZH %d 条" % len(i18n_ui.UI_ZH))
_, empties = i18n_ui.self_check_ui()
chk(not empties, "UI_ZH 没有空译文", empties[:6])

print("\n=== 3) 英文原串当键：查得到 / 查不到退回英文 ===")
chk(i18n.t("Load all tracks", lang="zh") == "加载全部航迹",
    "中文环境查到译文", i18n.t("Load all tracks", lang="zh"))
chk(i18n.t("Load all tracks", lang="en") == "Load all tracks",
    "英文环境原样返回", i18n.t("Load all tracks", lang="en"))
untranslated = "A string that is definitely not translated yet 12345"
chk(i18n.t(untranslated, lang="zh") == untranslated,
    "**未翻译的串退回英文**（不出现空白/键名）",
    i18n.t(untranslated, lang="zh")[:40])
chk(i18n.t("brand.new.key", lang="zh") == "brand.new.key",
    "完全未知的键原样返回（便于排查）")

print("\n=== 4) 带参数的文案要真的替换 ===")
s_en = i18n.t("report.title", lang="en", project="Demo")
s_zh = i18n.t("report.title", lang="zh", project="Demo")
chk("Demo" in s_en and "Demo" in s_zh, "参数被替换", "%s | %s" % (s_en, s_zh))
# 参数给漏了也不能抛异常
try:
    bad = i18n.t("report.title", lang="zh")
    chk(True, "缺参数不抛异常（退化成含占位符的原文）", bad[:40])
except Exception as e:
    chk(False, "缺参数不抛异常", e)

print("\n=== 5) 语言代码归一 ===")
for raw, want in (("zh", "zh"), ("zh-CN", "zh"), ("zh_CN", "zh"),
                  ("ZH", "zh"), ("中文", "zh"),
                  ("en", "en"), ("en-US", "en"), ("English", "en"),
                  ("", "en"), (None, "en"), ("klingon", "en")):
    got = i18n.norm_lang(raw)
    chk(got == want, "norm_lang(%r) == %r" % (raw, want), got)

print("\n=== 6) all_messages 只给当前语言、且不含未翻译项 ===")
zh = i18n.all_messages("zh")
en = i18n.all_messages("en")
chk(len(zh) > len(en), "中文表比英文表大（多出英->中映射）",
    "zh %d / en %d" % (len(zh), len(en)))
chk(zh.get("Load all tracks") == "加载全部航迹", "中文表里带英->中映射")
chk("Load all tracks" not in en,
    "英文表里**不**放英->中映射（省冗余、避免英文键映射到英文值）")
chk(len(zh) == len(i18n.MESSAGES) + len(i18n_ui.UI_ZH),
    "中文表 = 结构化文案 + 界面文案",
    "%d + %d = %d" % (len(i18n.MESSAGES), len(i18n_ui.UI_ZH), len(zh)))

print("\n=== 7) 线程隔离：set_lang 只影响本线程 ===")
import threading

i18n.set_lang("en")
seen = {}


def worker():
    i18n.set_lang("zh")
    seen["worker"] = i18n.get_lang()


t = threading.Thread(target=worker)
t.start()
t.join()
chk(seen.get("worker") == "zh", "子线程里设成 zh", seen.get("worker"))
chk(i18n.get_lang() == "en", "主线程仍是 en（没被踩）", i18n.get_lang())

print("\n结果:", "全部通过" if ok else "有失败项")
raise SystemExit(0 if ok else 1)
