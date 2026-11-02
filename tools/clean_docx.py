#!/usr/bin/env python3
"""清理 docx 中未被引用的冗余图片。

背景
----
用 `pandoc --reference-doc=<上一版成品.docx>` 反复生成时，reference 里的
`word/media/*` 会被一路继承下来：每轮 +4 张图（本文档的 4 张插图），
体积从 0.43 MB 涨到 2.0 MB，而 `inline_shapes` 始终只有 4。

只删 `word/media/` 下的文件是不够的——`word/_rels/document.xml.rels` 里仍留着
指向它们的 `<Relationship>` 条目，python-docx 会遍历所有关系项去读目标文件，
于是抛 `KeyError: There is no item named 'word/media/rId30.png'`。
因此必须**文件与关系项一起删**。

用法
----
    python tools/clean_docx.py docs/技术文档.docx          # 原地清理
    python tools/clean_docx.py docs/技术文档.docx --dry-run # 只看会删什么

退出码：0 成功（含"无需清理"），1 出错。
"""
import os
import re
import shutil
import sys
import tempfile
import zipfile


def clean(path: str, dry_run: bool = False) -> int:
    if not os.path.exists(path):
        print("找不到文件: %s" % path)
        return 1

    before = os.path.getsize(path)

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "word/document.xml" not in names:
            print("不是有效的 docx（缺 word/document.xml）")
            return 1

        doc = z.read("word/document.xml").decode("utf-8", "ignore")
        rels_name = "word/_rels/document.xml.rels"
        rels = z.read(rels_name).decode("utf-8", "ignore") if rels_name in names else ""

        used = set(re.findall(r'r:(?:embed|id|link)="(rId\d+)"', doc))
        pairs = re.findall(r'<Relationship[^>]*?Id="(rId\d+)"[^>]*?Target="([^"]+)"[^>]*?/>', rels)
        id2target = {i: t for i, t in pairs}

        all_media = {os.path.basename(t) for t in id2target.values() if t.startswith("media/")}
        keep = {os.path.basename(id2target[r]) for r in used
                if r in id2target and id2target[r].startswith("media/")}
        drop = all_media - keep
        drop_ids = [i for i, t in id2target.items()
                    if t.startswith("media/") and os.path.basename(t) in drop]

        if not drop:
            print("无需清理：%d 张图片全部被引用（%.2f MB）" % (len(keep), before / 1024 / 1024))
            return 0

        print("引用中 %d 张，冗余 %d 份（%d 条关系项）" % (len(keep), len(drop), len(drop_ids)))
        for n in sorted(drop):
            print("  - %s" % n)
        if dry_run:
            print("--dry-run：未写回")
            return 0

        for rid in drop_ids:
            rels = re.sub(r'<Relationship[^>]*?Id="%s"[^>]*?/>' % rid, "", rels)

        fd, tmp = tempfile.mkstemp(suffix=".docx")
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
                for n in names:
                    if n.startswith("word/media/") and os.path.basename(n) in drop:
                        continue
                    data = rels.encode("utf-8") if n == rels_name else z.read(n)
                    out.writestr(n, data)
            shutil.move(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    after = os.path.getsize(path)
    print("完成：%.2f MB → %.2f MB（省 %.2f MB）"
          % (before / 1024 / 1024, after / 1024 / 1024, (before - after) / 1024 / 1024))
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__)
        sys.exit(1)
    sys.exit(clean(args[0], dry_run="--dry-run" in sys.argv))
