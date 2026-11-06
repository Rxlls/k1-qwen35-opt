#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""format_docx.py — 按赛题提交规范整理 Word 文档

1. 正文（含表格内文字）统一字体：宋体
2. 各级标题统一字体：黑体
3. 所有表格：自动调整方式 = 根据窗口调整表格（tblW=pct 5000 + tblLayout=autofit）
4. 代码块保留等宽字体（Consolas），避免代码变形

用法: python format_docx.py <in.docx> [out.docx]
"""
import sys
import docx
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.oxml import OxmlElement

BODY = "宋体"
HEAD = "黑体"
CODE = "Consolas"


def set_run_font(run, name):
    """同时设置西文与东亚字体（只设 font.name 不会作用于中文）"""
    if not run.text or not run.text.strip():
        return
    run.font.name = name
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rFonts.set(qn(attr), name)
    # pandoc 会带 w:hint="eastAsia"，导致 ASCII 走 eastAsia 字体；改回 default
    rFonts.set(qn("w:hint"), "default")


def set_style_font(doc, style_name, font):
    try:
        st = doc.styles[style_name]
    except KeyError:
        return False
    st.font.name = font
    rPr = st.element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rFonts.set(qn(attr), font)
    return True


def fit_table_to_window(table, total_twips=8845):
    """按内容长度分配列宽：pandoc 给出的 gridCol 有时把首列压到 1.7cm，
    正文会被挤成一字一行。这里按每列最长内容重算，并给最小宽度兜底。"""
    tbl = table._tbl
    tblPr = tbl.tblPr
    grid = tbl.find(qn("w:tblGrid"))
    if grid is None:
        return
    cols = grid.findall(qn("w:gridCol"))
    n = len(cols)
    if n == 0:
        return

    lens = [0] * n
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            if i >= n:
                break
            w = sum(2 if ord(ch) > 127 else 1 for ch in (cell.text or ""))
            lens[i] = max(lens[i], w)

    weights = [max(5, min(L, 42)) for L in lens]      # 单列权重封顶，避免长段落吃掉整表
    s = sum(weights)
    widths = [max(1300, int(total_twips * w / s)) for w in weights]
    s2 = sum(widths)
    widths = [int(w * total_twips / s2) for w in widths]

    for g, w in zip(cols, widths):
        g.set(qn("w:w"), str(w))
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            if i >= n:
                break
            tcPr = cell._tc.get_or_add_tcPr()
            tcW = tcPr.find(qn("w:tcW"))
            if tcW is None:
                tcW = OxmlElement("w:tcW")
                tcPr.append(tcW)
            tcW.set(qn("w:w"), str(widths[i]))
            tcW.set(qn("w:type"), "dxa")

    tblW = tblPr.find(qn("w:tblW"))
    if tblW is None:
        tblW = OxmlElement("w:tblW")
        ts = tblPr.find(qn("w:tblStyle"))
        if ts is not None:
            ts.addnext(tblW)
        else:
            tblPr.insert(0, tblW)
    tblW.set(qn("w:w"), "5000")
    tblW.set(qn("w:type"), "pct")

    layout = tblPr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tblW.addnext(layout)
    layout.set(qn("w:type"), "fixed")


def style_table(table):
    """细边框 + 表头浅底 + 跨页重复表头：pandoc 默认的表格几乎没有框线。"""
    tbl = table._tbl
    tblPr = tbl.tblPr

    old = tblPr.find(qn("w:tblBorders"))
    if old is not None:
        tblPr.remove(old)
    borders = OxmlElement("w:tblBorders")
    for edge, sz, color in (("top", 8, "7F7F7F"), ("left", 8, "7F7F7F"),
                            ("bottom", 8, "7F7F7F"), ("right", 8, "7F7F7F"),
                            ("insideH", 4, "BFBFBF"), ("insideV", 4, "BFBFBF")):
        el = OxmlElement("w:" + edge)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(sz))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        borders.append(el)
    layout = tblPr.find(qn("w:tblLayout"))
    if layout is not None:
        layout.addprevious(borders)
    else:
        tblPr.append(borders)

    if not table.rows:
        return
    hdr = table.rows[0]
    trPr = hdr._tr.get_or_add_trPr()
    if trPr.find(qn("w:tblHeader")) is None:
        trPr.append(OxmlElement("w:tblHeader"))      # 跨页时重复表头
    for cell in hdr.cells:
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), "F2F4F7")
        tcPr.append(shd)
        for par in cell.paragraphs:
            for r in par.runs:
                r.bold = True

    # 表内统一小五（9pt）、行距压紧：列多时避免“+25.0%”被拆成两行
    for row in table.rows:
        for cell in row.cells:
            for par in cell.paragraphs:
                par.paragraph_format.space_before = Pt(2)
                par.paragraph_format.space_after = Pt(2)
                par.paragraph_format.line_spacing = 1.05
                par.paragraph_format.first_line_indent = Pt(0)
                for r in par.runs:
                    r.font.size = Pt(9)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "docs/技术文档.docx"
    dst = sys.argv[2] if len(sys.argv) > 2 else src

    doc = docx.Document(src)

    # 1) 样式层面：Normal 设为宋体（兜底，未显式设置的文字也生效）
    set_style_font(doc, "Normal", BODY)

    # 2) 段落层面
    n_head = n_body = n_code = 0
    for p in doc.paragraphs:
        sname = p.style.name or ""
        if sname.startswith("Heading") or sname in ("Title", "Subtitle"):
            font, n_head = HEAD, n_head + 1
        elif sname in ("Source Code", "Verbatim Char"):
            font, n_code = CODE, n_code + 1
        else:
            font, n_body = BODY, n_body + 1
        for r in p.runs:
            set_run_font(r, font)
        if font == CODE:                      # 代码块：8pt + 浅底，减少长行折行
            pf = p.paragraph_format
            pf.space_before = Pt(2)
            pf.space_after = Pt(2)
            pf.line_spacing = 1.0
            pPr = p._p.get_or_add_pPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "F7F8FA")
            pPr.append(shd)
            for r in p.runs:
                r.font.size = Pt(8)
                r.font.color.rgb = RGBColor(0x1a, 0x1a, 0x1a)

    # 3) 表格内文字
    n_cell = 0
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for r in p.runs:
                        set_run_font(r, BODY)
                    n_cell += 1

    # 4) 表格自适应窗口
    n_tbl = 0
    for t in doc.tables:
        fit_table_to_window(t)
        style_table(t)
        n_tbl += 1

    doc.save(dst)

    print(f"保存: {dst}")
    print(f"  段落: 标题 {n_head} / 正文 {n_body} / 代码块 {n_code}")
    print(f"  表格: {n_tbl} 个（已设为根据窗口调整），单元格段落 {n_cell} 个")
    print(f"  字体: 正文={BODY}  标题={HEAD}  代码={CODE}")


if __name__ == "__main__":
    main()
