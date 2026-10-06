"""直接排版生成《天地图 key 申请教程》PDF（Pillow 画好每页再存成多页 PDF）。

为什么不用 LibreOffice 转：这一版它对本文档的段落版面处理不可靠（正文会超出右边界），
而 Pillow 排版完全可控、并且能把同一批页面图留作自查。

代价（已如实写进文档）：PDF 是图像版，文字不可选中；要改文字请改
docs/make_tianditu_key_tutorial.py 生成的 DOCX（可编辑源文件）。

用法： <bundled-python> docs/make_tianditu_key_tutorial_pdf.py
"""

import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "key_tutorial_assets"
OUT_PDF = ROOT / "docs" / "天地图key申请教程.pdf"
PREVIEW = ROOT / "docs" / "_tutorial_preview"

FONT_REGULAR = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"

DPI = 150
PAGE_W, PAGE_H = int(8.27 * DPI), int(11.69 * DPI)      # A4
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = int(1.9 * DPI), int(1.8 * DPI), int(1.6 * DPI)

INK = (23, 32, 51)
BODY = (51, 51, 51)
GREY = (100, 116, 139)
ACCENT = (37, 99, 235)
GREEN = (19, 115, 51)
RED = (176, 0, 32)
CARD = (241, 245, 249)
WARN = (254, 249, 195)

_cache = {}


def font(size, bold=False):
    key = (size, bold)

    if key not in _cache:
        _cache[key] = ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)

    return _cache[key]


def text_w(draw, text, f):
    return draw.textbbox((0, 0), text, font=f)[2]


def wrap(draw, text, f, max_w):
    """按像素宽度折行；中文逐字、英文按单词。"""

    lines = []
    current = ""

    for char in text:

        if char == "\n":
            lines.append(current)
            current = ""
            continue

        if text_w(draw, current + char, f) <= max_w:
            current += char
            continue

        # 英文单词尽量不从中间断开
        if char.isascii() and char not in " " and " " in current:
            head, _, tail = current.rpartition(" ")
            lines.append(head)

            while tail and text_w(draw, tail + char, f) > max_w:
                lines.append(tail)
                tail = ""

            current = (tail + char).lstrip()
            continue

        lines.append(current)
        current = char

    if current:
        lines.append(current)

    return lines


class Page:
    def __init__(self):
        self.image = Image.new("RGB", (PAGE_W, PAGE_H), "white")
        self.draw = ImageDraw.Draw(self.image)
        self.y = MARGIN_TOP

    @property
    def max_w(self):
        return PAGE_W - 2 * MARGIN_X

    def space(self, pixels):
        self.y += pixels

    def paragraph(self, text, size=17, bold=False, color=BODY, line_gap=8, space_after=14):
        f = font(size, bold)

        for line in wrap(self.draw, text, f, self.max_w):
            self.draw.text((MARGIN_X, self.y), line, font=f, fill=color)
            self.y += size + line_gap

        self.y += space_after

    def heading(self, text, size=23):
        f = font(size, True)
        self.draw.text((MARGIN_X, self.y), text, font=f, fill=ACCENT)
        self.y += size + 12

        self.draw.line([(MARGIN_X, self.y), (PAGE_W - MARGIN_X, self.y)], fill=(226, 232, 240), width=2)
        self.y += 14

    def card(self, lines, fill=CARD, border=(203, 213, 225), pad=18, size=17):
        """一个浅色信息块。lines 是 (文本, 是否加粗, 颜色) 列表。"""

        f_bold = font(size, True)
        f_reg = font(size)
        wrapped = []

        for text, bold, color in lines:
            for line in wrap(self.draw, text, f_bold if bold else f_reg, self.max_w - 2 * pad):
                wrapped.append((line, bold, color))

        height = pad * 2 + sum(size + 10 for _ in wrapped)
        self.draw.rounded_rectangle(
            (MARGIN_X, self.y, PAGE_W - MARGIN_X, self.y + height), radius=14, fill=fill, outline=border, width=2
        )

        inner = self.y + pad

        for line, bold, color in wrapped:
            self.draw.text((MARGIN_X + pad, inner), line, font=f_bold if bold else f_reg, fill=color)
            inner += size + 10

        self.y += height + 16

    def image_fit(self, path, max_h, caption=None, border=True):
        source = Image.open(path).convert("RGB")
        scale = min(self.max_w / source.width, max_h / source.height)
        target = source.resize((int(source.width * scale), int(source.height * scale)), Image.LANCZOS)
        x = MARGIN_X + (self.max_w - target.width) // 2

        if border:
            self.draw.rectangle(
                (x - 2, self.y - 2, x + target.width + 2, self.y + target.height + 2),
                outline=(203, 213, 225), width=2
            )

        self.image.paste(target, (x, self.y))
        self.y += target.height + 10

        if caption:
            f = font(14)
            self.draw.text((MARGIN_X, self.y), caption, font=f, fill=GREY)
            self.y += 14 + 12

    def save(self, path):
        self.image.save(path)
        return self.image


def build_pages():
    flow = ASSETS / "fig1_flow.png"
    where = ASSETS / "fig4_where.png"
    shot_old = ASSETS / "shot_old_url.png"
    shot_installer = ASSETS / "shot_installer.png"

    pages = []

    # ---------------- 第 1 页 ----------------
    page = Page()
    f = font(40, True)
    page.draw.text((MARGIN_X, page.y), "天地图 key 申请教程", font=f, fill=INK)
    page.y += 52
    page.draw.line([(MARGIN_X, page.y), (PAGE_W - MARGIN_X, page.y)], fill=ACCENT, width=5)
    page.y += 26

    page.paragraph(
        "给「无人机巡查数据地图」的使用者：底图与地名搜索由天地图提供，"
        "需要一串属于你自己的 key（免费）。这份教程带你 5 分钟拿到它。"
    )
    page.paragraph(
        "实测时间：2026-10-06（Windows 11 + Edge）。天地图界面可能改版，以你实际看到的为准。"
        "本文图 1、图 4 是按官方流程画的示意图，不是官方截图。",
        size=14, color=GREY
    )

    page.heading("一、先看结论")
    page.card([
        ("申请地址（官方《应用开发许可申请说明》页）：", True, INK),
        ("https://lbs.tianditu.gov.cn/authorization/authorization.html", True, ACCENT),
        ("官网首页（登录后也能进「控制台」）：https://www.tianditu.gov.cn/", False, INK),
    ])
    page.paragraph(
        "拿到的是一串 32 位字符（叫 tk，或叫许可 Key）。填进安装向导，"
        "或者存成 <安装目录>\\tianditu_key.txt —— 存盘即生效，不用重启程序。"
    )
    page.heading("二、别用旧地址（这是个坑）")
    page.paragraph(
        "网上很多老教程还在给 console.tianditu.gov.cn/api/key。2026-10-06 实测："
        "https 连接被直接中断，http 返回 502 —— 它现在打不开，不是你的网络问题。"
    )
    page.image_fit(shot_old, max_h=int(2.6 * DPI), caption="图 2　实测：旧地址 console.tianditu.gov.cn 打不开")
    pages.append(page.save(PREVIEW / "page-0001.png"))

    # ---------------- 第 2 页 ----------------
    page = Page()
    page.heading("三、申请步骤")
    page.paragraph(
        "官方流程是：注册用户 → 申请成为开发者 → 从 API 网站进「控制台」→ "
        "在应用管理里创建应用并拿到许可 Key。"
    )
    page.image_fit(flow, max_h=int(5.6 * DPI), caption="图 1　申请流程（示意图）")
    page.paragraph("第 1 步　打开申请说明页", size=18, bold=True, color=INK, space_after=6)
    page.paragraph(
        "浏览器打开 https://lbs.tianditu.gov.cn/authorization/authorization.html 。"
        "这一页是官方的《天地图应用开发许可申请说明》，写明哪些服务需要许可。"
    )
    page.paragraph("第 2 步　注册 / 登录天地图账号", size=18, bold=True, color=INK, space_after=6)
    page.paragraph("用手机号或邮箱注册并登录。已有账号直接登录。")
    page.paragraph("第 3 步　申请成为「天地图开发者」", size=18, bold=True, color=INK, space_after=6)
    page.paragraph(
        "个人开发者即可满足本工具；调用量需求大的单位用户，可注册为单位用户并认证为企业开发者（配额更高）。"
    )
    pages.append(page.save(PREVIEW / "page-0002.png"))

    # ---------------- 第 3 页 ----------------
    page = Page()
    page.paragraph("第 4 步　进「控制台 → 应用管理」，创建应用", size=18, bold=True, color=INK, space_after=6)
    page.paragraph("从天地图 API 网站进入「控制台」，在「应用管理」里点创建应用，按提示填写应用名称与用途。")
    page.paragraph("第 5 步　应用类型选「浏览器端」", size=18, bold=True, color=INK, space_after=6)
    page.paragraph(
        "本工具是在浏览器里加载底图与瓦片，选「浏览器端」即可。类型选错会表现为底图加载失败或授权错误。"
    )
    page.paragraph("第 6 步　复制 32 位许可 Key（tk）", size=18, bold=True, color=INK, space_after=6)
    page.paragraph("应用创建成功后就能看到许可 Key，可以复制，也可以随时回控制台管理或重置它。")

    page.heading("四、key 放到哪里")
    page.image_fit(where, max_h=int(3.1 * DPI), caption="图 4　key 的三种放置位置（示意图）")
    page.paragraph("在安装向导里填（推荐）", size=18, bold=True, color=INK, space_after=6)
    page.paragraph(
        "安装过程第二步就是「天地图 key（可跳过）」，粘进去即可；留空也能装完，之后随时补。"
    )
    page.image_fit(shot_installer, max_h=int(3.0 * DPI),
                   caption="图 3　安装向导里的天地图 key 输入框（实测截图；图上印的旧网址已失效，请用本文的新地址）")
    pages.append(page.save(PREVIEW / "page-0003.png"))

    # ---------------- 第 4 页 ----------------
    page = Page()
    page.paragraph("已经装好了、想补填", size=18, bold=True, color=INK, space_after=6)
    page.paragraph(
        "把 32 位 tk 存成 <安装目录>\\tianditu_key.txt（一行，就是那串字符本身）。"
        "程序启动时和每次请求都会读它，存盘即生效 —— 不用重装，也不用重启。"
    )
    page.paragraph("直接跑源码（开发模式）", size=18, bold=True, color=INK, space_after=6)
    page.paragraph(
        "放 Code\\tianditu_key.txt。程序会把它当作数据目录里的 key 来读"
        "（首次启动时会自动把 Code 下的旧位置迁移过去）。"
    )

    page.heading("五、常见问题")
    faqs = [
        ("不填 key 会怎样？", "程序照常能用：底图自动退回 OpenStreetMap，只是地名搜索不可用。"),
        ("填完要重启程序吗？", "不用。key 是每次请求现读的，存盘就生效。"),
        ("底图空白 / 提示授权失败？",
         "依次检查：① tk 是否 32 位、没有多余空格；② 应用类型是否为「浏览器端」；"
         "③ 控制台里该应用的调用配额是否用完。"),
        ("能把这个 key 给同事用吗？", "技术上可以，但配额算在你账号上。建议每人各申请一个（免费，几分钟）。"),
        ("换电脑要重新填吗？", "要。key 文件不会跟着走 —— 把 tk 复制过去，或在新机器的安装向导里填一次。"),
        ("会不会不小心提交到代码仓库？",
         "本仓库的 .gitignore 已屏蔽 tianditu_key.txt，正常提交不会带上去。"
         "另外不要把 key 写进任何要公开的文件。"),
    ]

    for question, answer in faqs:
        page.paragraph(question, size=17, bold=True, color=INK, space_after=2)
        page.paragraph(answer, size=16, space_after=12)

    page.heading("六、说明")
    page.paragraph("· 图 1、图 4 是按官方流程画的示意图，不是官方界面截图；图 2、图 3 是 2026-10-06 的实测截图。",
                   size=15, color=GREY)
    page.paragraph("· 天地图可能调整界面与流程；若页面与本文不一致，以官方页面为准。", size=15, color=GREY)
    page.paragraph("· 本工具依赖的许可服务：底图瓦片、地名搜索、地理编码与逆地理编码。", size=15, color=GREY)
    page.paragraph("· 本 PDF 为图像版（文字不可选中）；要改文字请编辑随附的 "
                   "docs\\天地图key申请教程.docx 后重新导出。", size=15, color=GREY)
    pages.append(page.save(PREVIEW / "page-0004.png"))

    return pages


def main():
    PREVIEW.mkdir(parents=True, exist_ok=True)

    for old in PREVIEW.glob("page-*.png"):
        old.unlink()

    pages = build_pages()

    first, rest = pages[0], pages[1:]
    first.save(OUT_PDF, "PDF", resolution=DPI, save_all=True, append_images=rest)

    print(f"  已生成 {OUT_PDF}（{len(pages)} 页，{OUT_PDF.stat().st_size / 1024:.0f} KB）")
    print(f"  页面图留作自查：{PREVIEW}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
