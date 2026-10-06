"""生成《天地图 key 申请教程》DOCX（随后用 LibreOffice 转 PDF）。

素材：
  * 用户提供的两张实拍截图（旧地址报错页、安装向导填 key 页）
  * 自绘流程图/示意图（Pillow）—— 特意画成示意图而不是伪造官方界面截图，
    文档里也写明「示意图，非官方截图」

用法：
  <bundled-python> docs/make_tianditu_key_tutorial.py
"""

import pathlib
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "key_tutorial_assets"
OUT_DOCX = ROOT / "docs" / "天地图key申请教程.docx"

ATTACHMENTS = pathlib.Path.home() / ".dsh" / "attachments" / "v1" / "objects"

SHOT_OLD_URL = "9398f3d334557e2e7c7debf00e133f24c5294de2852aa7047e4b5c1824fdd554"
SHOT_INSTALLER = "02f51a76fd90db178fb426ae3f9bcfe15829b0b51d55939e4ae73d96535ccd37"

FONT_REGULAR = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"

ACCENT = (37, 99, 235)
DARK = (23, 32, 51)
GREY = (100, 116, 139)
GREEN = (19, 115, 51)
RED = (176, 0, 32)
BOX_BG = (241, 245, 249)
WARN_BG = (254, 249, 195)

ASSETS.mkdir(parents=True, exist_ok=True)


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)


def rounded(draw, box, radius, fill, outline=None, width=2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def center_text(draw, box, text, text_font, fill):
    left, top, right, bottom = box
    l, t, r, b = draw.textbbox((0, 0), text, font=text_font)
    draw.text((left + (right - left - (r - l)) / 2 - l,
               top + (bottom - top - (b - t)) / 2 - t), text, font=text_font, fill=fill)


def arrow(draw, start, end, fill=ACCENT, width=4):
    draw.line([start, end], fill=fill, width=width)
    (x1, y1), (x2, y2) = start, end

    if abs(x2 - x1) >= abs(y2 - y1):
        direction = 1 if x2 > x1 else -1
        tip = [(x2, y2), (x2 - 12 * direction, y2 - 7), (x2 - 12 * direction, y2 + 7)]
    else:
        direction = 1 if y2 > y1 else -1
        tip = [(x2, y2), (x2 - 7, y2 - 12 * direction), (x2 + 7, y2 - 12 * direction)]

    draw.polygon(tip, fill=fill)


def figure_flow():
    """图 1：申请流程（横向两步、纵向五步）。"""

    width, height = 1500, 1010
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    title_font = font(40, True)
    step_font = font(30, True)
    body_font = font(24)
    small_font = font(21)

    draw.text((50, 34), "图 1  天地图 key 申请流程（示意图）", font=title_font, fill=DARK)

    steps = [
        ("① 打开官方申请说明页", "lbs.tianditu.gov.cn/authorization/authorization.html", ACCENT),
        ("② 注册 / 登录天地图账号", "手机号或邮箱注册，完成后登录", ACCENT),
        ("③ 申请成为「天地图开发者」", "个人开发者即可；调用量大可认证为单位/企业", ACCENT),
        ("④ 进「控制台 → 应用管理」", "点「创建应用」新建一个应用", ACCENT),
        ("⑤ 应用类型选「浏览器端」", "创建成功后会得到许可 Key", GREEN),
        ("⑥ 复制 32 位 tk", "粘进安装向导，或存成 tianditu_key.txt", GREEN),
    ]

    top = 130
    box_h = 100
    gap = 22

    for index, (headline, detail, color) in enumerate(steps):
        y = top + index * (box_h + gap)
        rounded(draw, (50, y, width - 50, y + box_h), 16, BOX_BG, outline=(203, 213, 225))

        number_box = (50, y, 160, y + box_h)
        rounded(draw, number_box, 16, color)
        center_text(draw, number_box, headline.split()[0], step_font, "white")

        draw.text((185, y + 16), " ".join(headline.split()[1:]), font=step_font, fill=DARK)
        draw.text((185, y + 58), detail, font=body_font, fill=GREY)

        if index < len(steps) - 1:
            arrow(draw, (105, y + box_h + 3), (105, y + box_h + gap - 3))

    note = "注意：旧地址 console.tianditu.gov.cn 目前打不开（实测 HTTP 502），不要再试它。"
    draw.rectangle((50, height - 78, width - 50, height - 24), fill=WARN_BG)
    draw.text((70, height - 66), note, font=small_font, fill=(146, 64, 14))

    path = ASSETS / "fig1_flow.png"
    image.save(path)

    return path


def figure_where_to_put_key():
    """图 4：key 放哪里（三种位置 + 存盘即生效）。"""

    width, height = 1500, 660
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    title_font = font(40, True)
    label_font = font(28, True)
    body_font = font(23)

    draw.text((50, 34), "图 4  填好之后放在哪里（示意图）", font=title_font, fill=DARK)

    boxes = [
        ("安装向导里直接填", "可选。留空也能装；之后补填一样有效。", ACCENT),
        ("<安装目录>\\tianditu_key.txt", "推荐。程序启动时会读它，存盘即生效、不用重启。", GREEN),
        ("Code\\tianditu_key.txt", "开发模式（直接跑 python 时）用这个位置。", GREY),
    ]

    top = 140

    for index, (headline, detail, color) in enumerate(boxes):
        y = top + index * 155
        rounded(draw, (50, y, width - 50, y + 120), 16, BOX_BG, outline=(203, 213, 225))
        draw.rectangle((50, y, 62, y + 120), fill=color)
        draw.text((95, y + 22), headline, font=label_font, fill=DARK)
        draw.text((95, y + 68), detail, font=body_font, fill=GREY)

    draw.text((50, height - 70), "文件内容就是那串 32 位字符本身，一行即可。", font=body_font, fill=GREY)

    path = ASSETS / "fig4_where.png"
    image.save(path)

    return path


def copy_screenshot(sha, target_name):
    source = ATTACHMENTS / sha[:2] / sha

    if not source.is_file():
        raise SystemExit(f"找不到截图：{source}")

    target = ASSETS / target_name
    shutil.copyfile(source, target)

    return target


def set_cjk_font(run, name="Microsoft YaHei", size=None, bold=None, color=None):
    """中文字体必须同时设 w:eastAsia，否则可能回退成方框。"""

    run.font.name = name

    if size is not None:
        run.font.size = Pt(size)

    if bold is not None:
        run.font.bold = bold

    if color is not None:
        run.font.color.rgb = color

    rpr = run._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))

    if fonts is None:
        fonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(fonts)

    fonts.set(qn("w:eastAsia"), name)
    fonts.set(qn("w:ascii"), name)
    fonts.set(qn("w:hAnsi"), name)


def paragraph(document, text, size=10.5, bold=False, color=None, style=None, space_after=6):
    para = document.add_paragraph(style=style)
    run = para.add_run(text)
    set_cjk_font(run, size=size, bold=bold, color=color)
    para.paragraph_format.space_after = Pt(space_after)

    return para


def add_figure(document, path, caption, width_cm=15.0):
    document.add_picture(str(path), width=Cm(width_cm))
    document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    caption_para = document.add_paragraph()
    caption_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = caption_para.add_run(caption)
    set_cjk_font(run, size=9, color=RGBColor(0x64, 0x74, 0x8B))
    caption_para.paragraph_format.space_after = Pt(12)


def build():
    flow = figure_flow()
    where = figure_where_to_put_key()
    shot_old = copy_screenshot(SHOT_OLD_URL, "shot_old_url.png")
    shot_installer = copy_screenshot(SHOT_INSTALLER, "shot_installer.png")

    document = Document()

    for section in document.sections:
        # 明确用 A4 + 固定页边距：默认模板是 Letter，渲染出来正文容易顶到页边
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.left_margin = Cm(2.4)
        section.right_margin = Cm(2.4)
        section.top_margin = Cm(2.2)
        section.bottom_margin = Cm(2.2)

    title = document.add_heading("", level=0)
    run = title.add_run("天地图 key 申请教程")
    set_cjk_font(run, size=26, bold=True, color=RGBColor(0x17, 0x20, 0x33))

    paragraph(document, "给「无人机巡查数据地图」的使用者：底图与地名搜索由天地图提供，"
                        "需要一串属于你自己的 key（免费）。这份教程带你 5 分钟拿到它。",
              size=11, color=RGBColor(0x33, 0x33, 0x33))

    paragraph(document, "实测时间：2026-10-06（Windows 11 + Edge）。天地图界面可能改版，"
                        "以你实际看到的为准；文中图 1、图 4 是示意图，不是官方截图。",
              size=9.5, color=RGBColor(0x64, 0x74, 0x8B), space_after=14)

    # ---- 先看结论 ----
    document.add_heading("一、先看结论", level=1)
    paragraph(document, "申请地址（官方「应用开发许可申请说明」页）：", bold=True)
    paragraph(document, "https://lbs.tianditu.gov.cn/authorization/authorization.html",
              size=11, bold=True, color=RGBColor(0x25, 0x63, 0xEB))
    paragraph(document, "官网首页（登录后也能进「控制台」）：https://www.tianditu.gov.cn/")
    paragraph(document, "拿到的是一串 32 位字符（叫 tk 或许可 Key）。填进安装向导，"
                        "或者存成 <安装目录>\\tianditu_key.txt —— 存盘即生效，不用重启程序。",
              space_after=12)

    # ---- 不要用旧地址 ----
    document.add_heading("二、别用旧地址（这是个坑）", level=1)
    paragraph(document, "网上很多老教程还在给 console.tianditu.gov.cn/api/key。"
                        "2026-10-06 实测：https 连接被直接中断，http 返回 502 —— 它现在打不开，"
                        "不是你的网络问题。")
    add_figure(document, shot_old, "图 2  实测：旧地址 console.tianditu.gov.cn 打不开（HTTP 502）")

    # ---- 步骤 ----
    document.add_heading("三、申请步骤", level=1)
    paragraph(document, "官方流程是：注册用户 → 申请成为开发者 → 从 API 网站进「控制台」→ "
                        "在应用管理里创建应用并拿到许可 Key。")
    add_figure(document, flow, "图 1  申请流程（示意图）")

    steps = [
        ("第 1 步　打开申请说明页",
         "浏览器打开 https://lbs.tianditu.gov.cn/authorization/authorization.html 。"
         "这一页是官方的《天地图应用开发许可申请说明》，写明哪些服务需要许可。"),
        ("第 2 步　注册 / 登录天地图账号",
         "点页面上的注册入口，用手机号或邮箱注册并登录。已有账号直接登录。"),
        ("第 3 步　申请成为「天地图开发者」",
         "登录后在账号/开发者相关入口申请成为开发者。个人开发者即可满足本工具；"
         "调用量需求大的单位用户，可以注册为单位用户并认证为企业开发者（配额更高）。"),
        ("第 4 步　进「控制台 → 应用管理」，创建应用",
         "从天地图 API 网站进入「控制台」，在「应用管理」里点创建应用，按提示填写应用名称与用途。"),
        ("第 5 步　应用类型选「浏览器端」",
         "本工具是在浏览器里加载底图与瓦片，选「浏览器端」即可。"
         "类型选错会表现为底图加载失败或返回授权错误。"),
        ("第 6 步　复制 32 位许可 Key（tk）",
         "应用创建成功后就能看到许可 Key，可以复制，也可以随时回到控制台管理/重置它。"),
    ]

    for headline, detail in steps:
        document.add_heading(headline, level=2)
        paragraph(document, detail)

    # ---- 放到哪里 ----
    document.add_heading("四、key 放到哪里", level=1)
    add_figure(document, where, "图 4  key 的三种放置位置（示意图）")

    document.add_heading("在安装向导里填（推荐）", level=2)
    paragraph(document, "安装过程第二步就是「天地图 key（可跳过）」，粘进去即可；"
                        "下面这张图就是那一步的样子。留空也能装完，之后随时补。")
    add_figure(document, shot_installer,
               "图 3  安装向导里的天地图 key 输入框（实测截图；图上印的旧网址已失效，请用本文的新地址）",
               width_cm=14.0)

    document.add_heading("已经装好了、想补填", level=2)
    paragraph(document, "把 32 位 tk 存成 <安装目录>\\tianditu_key.txt（一行，就是那串字符本身）。"
                        "程序启动时和每次请求都会读它，存盘即生效、不用重装也不用重启。")

    document.add_heading("直接跑源码（开发模式）", level=2)
    paragraph(document, "放 Code\\tianditu_key.txt。程序会把它当作数据目录里的 key 来读"
                        "（首次启动时会自动把 Code 下的旧位置迁移过去）。")

    # ---- 常见问题 ----
    document.add_heading("五、常见问题", level=1)

    faqs = [
        ("不填 key 会怎样？",
         "程序照常能用：底图自动退回 OpenStreetMap，只是地名搜索不可用。"),
        ("填完要重启程序吗？",
         "不用。key 是每次请求现读的，存盘就生效。"),
        ("底图空白 / 提示授权失败？",
         "依次检查：① tk 是否 32 位、没有多余空格；② 应用类型是否为「浏览器端」；"
         "③ 控制台里该应用的调用配额是否用完。"),
        ("能把这个 key 给同事用吗？",
         "技术上可以，但配额是算在你账号上的。建议每人各申请一个（免费、几分钟）。"),
        ("换电脑要重新填吗？",
         "要。key 文件不会跟着走 —— 把 tk 复制过去，或在新机器的安装向导里填一次。"),
        ("会不会不小心提交到代码仓库？",
         "本仓库的 .gitignore 已经屏蔽了 tianditu_key.txt，正常提交不会带上去。"
         "另外建议不要把 key 写进任何要公开的文件。"),
    ]

    for question, answer in faqs:
        paragraph(document, question, bold=True, space_after=2)
        paragraph(document, answer, space_after=10)

    document.add_heading("六、说明", level=1)
    paragraph(document, "· 图 1、图 4 是按官方流程画的示意图，不是官方界面截图；"
                        "图 2、图 3 是 2026-10-06 的实测截图。")
    paragraph(document, "· 天地图可能调整界面与流程；若页面与本文不一致，以官方页面为准。")
    paragraph(document, "· 用到许可的服务里，本工具依赖的是底图瓦片、地名搜索、"
                        "地理编码与逆地理编码。")

    document.save(OUT_DOCX)

    print(f"  已生成 {OUT_DOCX}")

    for path in (flow, where):
        print(f"  图：{path.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    build()
