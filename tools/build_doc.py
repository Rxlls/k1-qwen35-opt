#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_doc.py —— 把 markdown 生成带封面/页眉页脚/目录的交付版 docx。

流程：pandoc → format_docx（字体/表格）→ clean_docx（清冗余图片）→ 本脚本（封面、页码、目录）
      → Word COM 更新目录域并导出 PDF 供校验。

用法：
    python tools/build_doc.py td          # 技术文档
    python tools/build_doc.py fa          # 方案书
    python tools/build_doc.py td --pdf    # 同时导出 PDF 到临时目录
"""
import argparse
import os
import subprocess
import sys

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANDOC = r"C:\Program Files\Pandoc\pandoc.exe"

TEAM = "panpan最努力"
MEMBERS = "潘荣轩　王一鸣　陶心如　王恩惠"
CONTEST = "全国 RISC-V 高水平创新及应用大赛（第二届）"
TRACK = "CIE · 进迭时空赛道"
TOPIC = "赛题：基于 K1 AI CPU 的 Qwen3.5 本地部署与性能优化"
PROJECT = "把权重压进 IME：K1 上的 Qwen3.5 加速"
REPO = "代码仓库：https://github.com/Rxlls/k1-qwen35-opt"
DATE = "2026 年 11 月"

PRESETS = {
    "td": {"md": "docs/技术文档.md", "docx": "docs/技术文档.docx", "subtitle": "技 术 文 档",
           "header": "%s · 技术文档" % PROJECT},
    "fa": {"md": "docs/方案书.md", "docx": "docs/方案书.docx", "subtitle": "方 案 书",
           "header": "%s · 方案书" % PROJECT},
}


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write("失败: %s\n%s\n" % (" ".join(cmd), r.stderr[-600:]))
        raise SystemExit(1)
    return r


def set_font(run, name="宋体", size=None, bold=None, color=None):
    run.font.name = name
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rFonts.set(qn(a), name)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color:
        run.font.color.rgb = color


def para_before(anchor, text="", *, name="宋体", size=12, bold=False,
                align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0, color=None,
                border_bottom=False):
    p = docx.text.paragraph.Paragraph(OxmlElement("w:p"), anchor._parent)
    anchor._p.addprevious(p._p)
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = 1.15
    if text:
        set_font(p.add_run(text), name, size, bold, color)
    if border_bottom:
        pPr = p._p.get_or_add_pPr()
        pbdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "6")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "999999")
        pbdr.append(bottom)
        pPr.append(pbdr)
    return p


def add_field(par, instr, placeholder="1"):
    r1 = par.add_run(); fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), "begin"); r1._r.append(fc)
    r2 = par.add_run(); it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve")
    it.text = " %s " % instr; r2._r.append(it)
    r3 = par.add_run(); fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), "separate"); r3._r.append(fc)
    set_font(par.add_run(placeholder), size=9)
    r5 = par.add_run(); fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), "end"); r5._r.append(fc)


def tune_body(doc):
    """中文正文常规排版：首行缩进 2 字符、行距 1.3。"""
    for name in ("Body Text", "First Paragraph"):
        try:
            st = doc.styles[name]
        except KeyError:
            continue
        st.paragraph_format.first_line_indent = Pt(21)     # 10.5pt × 2 字
        st.paragraph_format.line_spacing = 1.3
        st.paragraph_format.space_after = Pt(3)


def build_cover(doc, subtitle):
    first = doc.paragraphs[0]
    G = WD_ALIGN_PARAGRAPH.CENTER
    para_before(first, "", size=10, before=54)
    para_before(first, "把权重压进 IME：", name="黑体", size=26, bold=True, before=0, after=6)
    para_before(first, "K1 上的 Qwen3.5 加速", name="黑体", size=26, bold=True, after=10)
    para_before(first, subtitle, name="宋体", size=18, after=30, color=RGBColor(0x44, 0x44, 0x44))
    para_before(first, "", border_bottom=True, after=26)
    for line in (CONTEST, TRACK, TOPIC):
        para_before(first, line, size=12, after=6)
    para_before(first, "", size=10, before=54)
    para_before(first, "团队名称：%s" % TEAM, size=14, after=8)
    para_before(first, "团队成员：%s" % MEMBERS, size=14, after=6)
    para_before(first, REPO, size=10, before=10, after=6, color=RGBColor(0x55, 0x55, 0x55))
    para_before(first, "", size=10, before=84)
    para_before(first, DATE, size=14)

    brk = para_before(first, "", size=10)
    brk.add_run().add_break(docx.enum.text.WD_BREAK.PAGE)


def build_header_footer(doc, header_text):
    s = doc.sections[0]
    s.page_width, s.page_height = Cm(21.0), Cm(29.7)
    s.top_margin, s.bottom_margin = Cm(2.54), Cm(2.4)
    s.left_margin, s.right_margin = Cm(2.8), Cm(2.6)
    s.header_distance, s.footer_distance = Cm(1.4), Cm(1.3)
    s.different_first_page_header_footer = True    # 封面不显示页眉页脚

    # 参考文档若已带页眉页脚，pandoc 会一起继承下来；先清空再写，避免叠字
    def clean(part):
        ps = part.paragraphs
        for extra in ps[1:]:
            extra._p.getparent().remove(extra._p)
        first = ps[0]
        for r in list(first.runs):
            r._r.getparent().remove(r._r)
        return first

    hp = clean(s.header)
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    set_font(hp.add_run(header_text), size=9, color=RGBColor(0x77, 0x77, 0x77))

    fp = clean(s.footer)
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(fp.add_run("— "), size=9)
    add_field(fp, "PAGE")
    set_font(fp.add_run(" —"), size=9)

    # 页码从 0 起：封面计 0 且不显示，正文首页为 1
    sectPr = s._sectPr
    pgNum = sectPr.find(qn("w:pgNumType"))
    if pgNum is None:
        pgNum = OxmlElement("w:pgNumType")
        sectPr.append(pgNum)
    pgNum.set(qn("w:start"), "0")


def remap_headings(doc):
    """pandoc 的 ## 是 Heading 2；文档没有 H1（标题已移入封面）。
    整体上提一级，Word 的 \\o "1-2" 才能正常识别大纲。"""
    h2 = [p for p in doc.paragraphs if p.style.name == "Heading 2"]
    h3 = [p for p in doc.paragraphs if p.style.name == "Heading 3"]
    h4 = [p for p in doc.paragraphs if p.style.name == "Heading 4"]
    for p in h2:
        p.style = doc.styles["Heading 1"]
    for p in h3:
        p.style = doc.styles["Heading 2"]
    for p in h4:
        p.style = doc.styles["Heading 3"]
    # 字号随层级收紧：章 16pt / 节 14pt / 目 12pt
    for name, size in (("Heading 1", 16), ("Heading 2", 14), ("Heading 3", 12)):
        try:
            doc.styles[name].font.size = Pt(size)
        except KeyError:
            pass
    return len(h2), len(h3)


def chapter_page_break(doc):
    """每章（Heading 1）另起一页"""
    n = 0
    for p in doc.paragraphs:
        if p.style.name == "Heading 1":
            p.paragraph_format.page_break_before = True
            n += 1
    return n


def build_toc(doc):
    """把占位段替换成“目　录”标题 + TOC 域"""
    target = None
    for p in doc.paragraphs:
        if p.text.strip() == "【目录】":
            target = p
            break
    if target is None:
        print("  警告：未找到【目录】占位")
        return False

    for r in list(target.runs):
        r._r.getparent().remove(r._r)
    target.alignment = WD_ALIGN_PARAGRAPH.LEFT
    target.paragraph_format.page_break_before = True
    target.paragraph_format.space_before = Pt(0)
    target.paragraph_format.space_after = Pt(18)
    set_font(target.add_run("目　录"), name="黑体", size=18, bold=True)

    toc_p = docx.text.paragraph.Paragraph(OxmlElement("w:p"), target._parent)
    target._p.addnext(toc_p._p)
    # \t 把 Heading 2 映射成 TOC 一级、Heading 3 映射成二级（章节用 H2，避免整篇改层级）
    add_field(toc_p, 'TOC \\o "1-2" \\h \\z \\u',
              placeholder="（目录将在用 Word 打开时自动生成）")

    # Word 内置目录样式在 styles.xml 里叫 "toc 1"/"toc 2"（styleId TOC1/TOC2），
    # 用 doc.styles[name] 取不到，必须按 styleId 找；顺手清掉早先误建的 TOC11/TOC21。
    for junk in ("TOC11", "TOC21"):
        for st in [x for x in doc.styles if x.style_id == junk]:
            st.element.getparent().remove(st.element)
    for sid, indent in (("TOC1", 0), ("TOC2", 18)):
        st = next((x for x in doc.styles if x.style_id == sid), None)
        if st is None:
            print("      警告：未找到目录样式 %s" % sid)
            continue
        st.font.size = Pt(10.5)
        pf = st.paragraph_format
        pf.space_before = Pt(4 if sid == "TOC1" else 0)
        pf.space_after = Pt(0)
        pf.line_spacing = 1.1
        pf.left_indent = Pt(indent)
    return True


def word_update_and_pdf(path, pdf_path=None):
    import win32com.client as win32
    word = win32.Dispatch("Word.Application")
    word.Visible = False
    doc = None
    try:
        doc = word.Documents.Open(os.path.abspath(path), ReadOnly=False)
        if doc.TablesOfContents.Count:
            doc.TablesOfContents(1).Update()
        doc.Fields.Update()
        cp = doc.BuiltInDocumentProperties
        cp("Title").Value = PROJECT
        cp("Author").Value = "%s（%s）" % (MEMBERS.replace("　", "、"), TEAM)
        cp("Subject").Value = TOPIC.replace("赛题：", "")
        doc.Repaginate()
        doc.Repaginate()
        pages = doc.ComputeStatistics(2)     # wdStatisticPages
        doc.Save()
        if pdf_path:
            doc.ExportAsFixedFormat(os.path.abspath(pdf_path), 17)   # wdExportFormatPDF
        return pages
    finally:
        if doc is not None:
            doc.Close(SaveChanges=0)
        word.Quit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("preset", choices=sorted(PRESETS))
    ap.add_argument("--pdf", action="store_true")
    args = ap.parse_args()
    cfg = PRESETS[args.preset]
    md = os.path.join(ROOT, cfg["md"])
    out = os.path.join(ROOT, cfg["docx"])
    tmp = os.path.join(os.environ.get("TEMP", "/tmp"), "build_%s.docx" % args.preset)

    print("[1/5] pandoc")
    r = sh([PANDOC, md, "-o", tmp, "--reference-doc", out,
            "--resource-path=%s" % os.path.dirname(md)])
    if r.stderr.strip():
        print("      pandoc 告警：")
        for line in r.stderr.strip().splitlines()[:6]:
            print("        " + line)
    print("[2/5] 字体与表格")
    sh([sys.executable, os.path.join(ROOT, "tools/format_docx.py"), tmp,
        os.path.join(os.environ.get("TEMP", "/tmp"), "build_%s_f.docx" % args.preset)])
    fmt = os.path.join(os.environ.get("TEMP", "/tmp"), "build_%s_f.docx" % args.preset)
    print("[3/5] 清理冗余图片")
    sh([sys.executable, os.path.join(ROOT, "tools/clean_docx.py"), fmt])

    print("[4/5] 封面 / 页眉页脚 / 目录")
    doc = docx.Document(fmt)
    build_header_footer(doc, cfg["header"])
    tune_body(doc)
    build_cover(doc, cfg["subtitle"])
    n1, n2 = remap_headings(doc)
    n = chapter_page_break(doc)
    build_toc(doc)
    print("      章 %d / 节 %d；章节另起一页 %d 处" % (n1, n2, n))
    doc.save(out)

    print("[5/5] Word 更新目录域")
    pdf = None
    if args.pdf:
        pdf = os.path.join(os.environ.get("TEMP", "/tmp"), "preview_%s.pdf" % args.preset)
    pages = word_update_and_pdf(out, pdf)
    print("完成：%s  共 %d 页%s" % (os.path.relpath(out, ROOT), pages,
                                 ("，PDF: %s" % pdf) if pdf else ""))


if __name__ == "__main__":
    main()
