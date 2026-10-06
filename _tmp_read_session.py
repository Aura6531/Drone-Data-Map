import json, sys, pathlib

sys.stdout.reconfigure(encoding="utf-8")

src = pathlib.Path(r"<用户目录>\.dsh\sessions\--A-DeepSeek~0020Test--\session-b5988015-86da-4e8f-b089-604fd6434179\session.v4.jsonl.zstd")
from compression import zstd
raw = zstd.decompress(src.read_bytes()).decode("utf-8", "replace")

rows = []
for l in raw.splitlines():
    if not l.strip():
        continue
    try:
        o = json.loads(l)
    except Exception:
        continue
    rows.append(o)

def texts(content):
    out = []
    if isinstance(content, list):
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                out.append(c.get("text", ""))
    return "\n".join(out)

# 最后几轮助手说了什么 + 最后调用了哪些工具
asst, tools, todos = [], [], []
for o in rows:
    t = o.get("type")
    d = o.get("data") or {}
    if t == "assistant/message":
        txt = texts((d.get("message") or {}).get("content"))
        if txt.strip():
            asst.append((o.get("seq"), txt))
    elif t == "tool/call":
        tools.append((o.get("seq"), d.get("name"), str(d.get("arguments"))[:160]))
    elif t == "todo/write":
        todos.append((o.get("seq"), d.get("todos")))

print("=== 最后的 todo/write ===")
for seq, td in todos[-2:]:
    print("seq", seq)
    for x in td or []:
        print(f"   [{x.get('status')}] {x.get('content')}")

print("\n=== 最后 5 条助手发言 ===")
for seq, txt in asst[-5:]:
    print(f"\n--- seq {seq} ---")
    print(txt[:1500])

print("\n=== 最后 30 次工具调用 ===")
for seq, name, args in tools[-30:]:
    print(f"[{seq}] {name}  {args}")
