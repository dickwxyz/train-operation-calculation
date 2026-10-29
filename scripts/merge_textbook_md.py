# -*- coding: utf-8 -*-
"""把逐页 MinerU 产物合并成《铁路行车组织（第 2 版）》前 3 篇的单个 Markdown。

输入
----
* `--pages-dir`：`scripts/mineru_pdf_to_md.py` 的输出根目录。每个 PDF 一个子目录，
  目录名形如 `铁路行车组织第2版_123`，内含 `full.md` 与 `images/`。
* 两份章节原文 md（第四章、第十一章），用来补原扫描件整章缺失的部分。

输出
----
* 一个 md 文件（默认 `knowledge_base/铁路行车组织第2版-前3篇.md`）；
* 一个图片目录（默认 `knowledge_base/前3篇-images/`），**全部图片都放这里**：
  扫描页图 `p{页码}_原名`、第四章图 `ch4_原名`、第十一章图 `ch11_原名`。

页序规则（唯一依据，改之前先核对教材）
--------------------------------------
    11–45   单页 OCR
    46–67   第四章 md（L1–595；L597 起是习题尾巴，不用）
    68      合订本第 68 页（本章小结/思考题，第四章 md 未收）
    69–134  单页 OCR
    135–136 合订本第 135–136 页（本篇习题；不用 md 的习题尾巴，避免重叠）
    137–159 单页 OCR
    160–179 第十一章 md（L1–708；L709 起是「略」与习题，不用）
    180     合订本第 180 页，只取「第四节」起（前半是例 11.6，与 md 重复）
    181–200 单页 OCR
    201     合订本第 201 页（简答题+综合计算题）
    202–279 单页 OCR

用法
----
    /opt/anaconda3/bin/python3 scripts/merge_textbook_md.py --dry-run
    /opt/anaconda3/bin/python3 scripts/merge_textbook_md.py

脚本幂等：每次清空并重建输出图片目录，再重写 md。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_PAGES_DIR = ROOT / "过程" / "mineru-前3篇" / "md"
DEFAULT_OUT = ROOT / "knowledge_base" / "铁路行车组织第2版-前3篇.md"
DEFAULT_IMAGES_DIR = ROOT / "knowledge_base" / "前3篇-images"
DEFAULT_CH4 = ROOT / "knowledge_base" / "调车工作" / "铁路行车组织第2版-调车工作.md"
DEFAULT_CH11 = (ROOT / "knowledge_base" / "技术站列车编组计划的编制"
                / "铁路行车组织第2版-技术站列车编组计划的编制.md")

START_PAGE = 11
END_PAGE = 279
PAGE_OFFSET = 10                     # 印刷页 = PDF 页 − 10

# 章节 md 的正文行号（1-based，闭区间）；尾部习题不用
CH4_BODY = (1, 595)      # L596 为空行，L597 起是习题
CH11_BODY = (1, 708)     # L709 起是「第四节（略）」

# 章节 md 的图片源目录与前缀
CH4_IMG_DIR = ROOT / "knowledge_base" / "调车工作" / "images"
CH11_IMG_DIR = ROOT / "knowledge_base" / "技术站列车编组计划的编制" / "images"

# 从合订本补入、按普通页整页并入的页
WHOLE_EXTRA_PAGES = {68, 135, 136, 201}
# 只保留「第四节」起内容的页
TRUNCATE_PAGE = 180

# 已对照教材原页人工核实的 OCR 漏行：页号 -> [(锚点原文, 追加文本)]
# 第 134 页（印刷页 124）MinerU 漏识别了简答题第 6、8 题，按原页补回。
PAGE_FIXES: dict[int, list[tuple[str, str]]] = {
    134: [
        ("5. 简述技术站办理到达解体列车的技术作业过程。",
         "6. 简述调车工作的基本要求。"),
        ("7. 简述调车工作的意义，调车作业按其目的可分为哪几类？",
         "8. 解体和编组调车的目的是什么？"),
    ],
}

PAGE_DIR_RE = re.compile(r"_(\d+)$")
MD_IMG_RE = re.compile(r"(!\[[^\]]*\]\()\s*(<)?([^)\s>]+)(>)?(\s*\))")
HTML_IMG_RE = re.compile(r"(<img\b[^>]*?\bsrc\s*=\s*)(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
SECTION4_RE = re.compile(r"^\s*(?:#{1,6}\s*)?第四节[^\n]*分组列车[^\n]*$", re.M)
SECTION4_LOOSE_RE = re.compile(r"^\s*(?:#{1,6}\s*)?第四节[^\n]*$", re.M)


def log(msg: str) -> None:
    print(msg, flush=True)


def printed(p: int) -> str:
    return "%03d" % (p - PAGE_OFFSET)


def parse_pages(pages_dir: Path) -> dict[int, Path]:
    """扫描输出目录，返回 {PDF 页号: 子目录}；只收 11..279。"""
    if not pages_dir.is_dir():
        sys.exit("转换目录不存在：%s" % pages_dir)
    pages: dict[int, Path] = {}
    for d in pages_dir.iterdir():
        if not d.is_dir():
            continue
        m = PAGE_DIR_RE.search(d.name)
        if not m:
            continue
        n = int(m.group(1))
        if START_PAGE <= n <= END_PAGE and (d / "full.md").is_file():
            pages[n] = d
    return pages


def read_lines(path: Path, span: tuple[int, int], head: str,
               boundary_line: int, boundary_text: str) -> str:
    """按行号取章节正文，并校验首行与切分边界，防止 md 改版后静默错切。"""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    a, b = span
    if b > len(lines) or boundary_line > len(lines):
        sys.exit("%s 只有 %d 行，取不到 L%d–L%d / L%d"
                 % (path.name, len(lines), a, b, boundary_line))
    first = lines[a - 1]
    if head not in first:
        sys.exit("%s L%d 应以「%s」开头，实际是：%s" % (path.name, a, head, first[:60]))
    nxt = lines[boundary_line - 1]
    if boundary_text not in nxt:
        sys.exit("%s L%d 应含「%s」（切分边界），实际是：%s"
                 % (path.name, boundary_line, boundary_text, nxt[:60]))
    return "\n".join(lines[a - 1:b]).strip()


def copy_image(src: Path, dest_dir: Path, name: str, copied: dict[str, str]) -> str:
    """复制图片（同名只复制一次），返回 md 里的相对链接。"""
    if name not in copied:
        if not src.is_file():
            sys.exit("图片不存在：%s" % src)
        dest = dest_dir / name
        if dest.exists():
            sys.exit("图片重名：%s" % dest)
        shutil.copy2(src, dest)
        copied[name] = name
    return copied[name]


def rewrite_page_images(text: str, page_dir: Path, page: int,
                        dest_dir: Path, copied: dict[str, str],
                        link_prefix: str) -> str:
    """把一页 full.md 里的 images/xxx 复制并改写成统一图片目录下的 pNNN_xxx。"""
    img_root = page_dir / "images"

    def new_name(raw: str) -> str:
        raw = unquote(raw.strip())
        if raw.startswith(("http://", "https://", "data:")):
            return raw
        rel = raw[2:] if raw.startswith("./") else raw
        if not rel.startswith("images/"):
            return raw
        src = page_dir / rel
        return link_prefix + copy_image(src, dest_dir, "p%03d_%s" % (page, src.name), copied)

    def md_sub(m: re.Match) -> str:
        head, lt, path, gt, tail = m.groups()
        new = new_name(path)
        if new == path:
            return m.group(0)
        return "%s%s%s%s%s" % (head, lt or "", new, gt or "", tail)

    def html_sub(m: re.Match) -> str:
        head, val = m.groups()
        quote = ""
        raw = val
        if val[:1] in "\"'":
            quote, raw = val[0], val[1:-1]
        new = new_name(raw)
        if new == raw:
            return m.group(0)
        return "%s%s%s%s" % (head, quote, new, quote)

    return HTML_IMG_RE.sub(html_sub, MD_IMG_RE.sub(md_sub, text))


def rewrite_chapter_images(text: str, src_dir: Path, prefix: str,
                           dest_dir: Path, copied: dict[str, str],
                           link_prefix: str) -> str:
    """把章节 md 里的 images/xxx 复制为统一目录下的 chN_xxx 并改写链接。"""
    def new_name(raw: str) -> str:
        raw = unquote(raw.strip())
        if raw.startswith(("http://", "https://", "data:")):
            return raw
        rel = raw[2:] if raw.startswith("./") else raw
        if not rel.startswith("images/"):
            return raw
        src = src_dir / Path(rel).name
        return link_prefix + copy_image(src, dest_dir, prefix + src.name, copied)

    def md_sub(m: re.Match) -> str:
        head, lt, path, gt, tail = m.groups()
        new = new_name(path)
        if new == path:
            return m.group(0)
        return "%s%s%s%s%s" % (head, lt or "", new, gt or "", tail)

    def html_sub(m: re.Match) -> str:
        head, val = m.groups()
        quote = ""
        raw = val
        if val[:1] in "\"'":
            quote, raw = val[0], val[1:-1]
        new = new_name(raw)
        if new == raw:
            return m.group(0)
        return "%s%s%s%s" % (head, quote, new, quote)

    return HTML_IMG_RE.sub(html_sub, MD_IMG_RE.sub(md_sub, text))


def apply_page_fixes(text: str, page: int) -> str:
    """补回已核实的 OCR 漏行；锚点缺失就报错，避免静默失效。"""
    for anchor, add in PAGE_FIXES.get(page, []):
        if add in text:
            continue
        if anchor not in text:
            sys.exit("第 %d 页校正锚点不存在：%s" % (page, anchor))
        text = text.replace(anchor, anchor + "\n\n" + add, 1)
    return text


def truncate_at_section4(text: str, page: int) -> str:
    """第 180 页只保留「第四节」起的内容；找不到就报错。"""
    m = SECTION4_RE.search(text) or SECTION4_LOOSE_RE.search(text)
    if not m:
        sys.exit("第 %d 页（印刷页 %s）找不到「第四节」标题，拒绝静默拼接"
                 % (page, printed(page)))
    head = text[m.start():].lstrip()
    first, _, rest = head.partition("\n")
    if not first.lstrip().startswith("#"):
        first = "## " + first.strip()
    return first + ("\n" + rest if rest else "")


def build_plan(pages: dict[int, Path]) -> list[tuple[str, object]]:
    """返回 [(kind, payload)]，kind = page / md4 / md11。并校验页序无空洞。"""
    overlap = sorted(set(pages) & (set(range(46, 68)) | set(range(160, 180))))
    if overlap:
        sys.exit("以下页既在 md 覆盖范围内、又有逐页 OCR，会重复：%s" % _ranges(overlap))

    plan: list[tuple[str, object]] = []
    covered: set[int] = set()
    for p in range(START_PAGE, END_PAGE + 1):
        if p == 46:
            plan.append(("md4", None))
            covered.update(range(46, 68))
        if p == 160:
            plan.append(("md11", None))
            covered.update(range(160, 180))
        if p in pages:
            plan.append(("page", p))
            covered.add(p)

    expect = set(range(START_PAGE, END_PAGE + 1))
    missing = sorted(expect - covered)
    if missing:
        sys.exit("页序有空洞：%s（缺 %d 页）" % (_ranges(missing), len(missing)))
    return plan


def _ranges(nums: list[int]) -> str:
    if not nums:
        return ""
    out, start, prev = [], nums[0], nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        out.append("%d" % start if start == prev else "%d–%d" % (start, prev))
        start = prev = n
    out.append("%d" % start if start == prev else "%d–%d" % (start, prev))
    return "、".join(out)


def resolve_link_prefix(out: Path, images_dir: Path) -> str:
    rel = Path(os.path.relpath(images_dir, out.parent))
    return rel.as_posix().rstrip("/") + "/"


def check_output(text: str, out: Path, images_dir: Path, n_pages: int) -> dict:
    problems: list[str] = []

    # 1) 图片链接：全部指向统一目录且文件存在
    refs: list[str] = []
    for m in MD_IMG_RE.finditer(text):
        refs.append(m.group(3))
    for m in HTML_IMG_RE.finditer(text):
        val = m.group(2)
        refs.append(val[1:-1] if val[:1] in "\"'" else val)
    for ref in refs:
        if ref.startswith(("http://", "https://", "data:")):
            continue
        p = (out.parent / unquote(ref)).resolve()
        if not p.is_file():
            problems.append("图片断链：%s" % ref)
        try:
            p.relative_to(images_dir.resolve())
        except ValueError:
            problems.append("图片不在统一目录：%s" % ref)

    # 2) 两章标题各出现一次
    for pat, label in ((r"(?m)^#\s*第四章\s*调车工作\s*$", "第四章"),
                       (r"(?m)^#\s*第十一章[^\n]*$", "第十一章")):
        n = len(re.findall(pat, text))
        if n != 1:
            problems.append("%s 章标题出现 %d 次" % (label, n))

    # 3) 页标记数量
    marks = re.findall(r"<!-- ===== PDF 第 (\d+) 页", text)
    if len(marks) != n_pages:
        problems.append("页标记 %d 个，应为 %d" % (len(marks), n_pages))
    nums = [int(x) for x in marks]
    if nums != sorted(nums):
        problems.append("页标记未按升序排列")

    if problems:
        for p in problems:
            log("  ✗ " + p)
        sys.exit("完整性检查未通过（%d 项）" % len(problems))

    return {
        "pages": len(marks),
        "images": len(set(refs)),
        "chars": len(text),
        "lines": text.count("\n") + 1,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="合并教材逐页 Markdown 为单个文件")
    ap.add_argument("--pages-dir", type=Path, default=DEFAULT_PAGES_DIR)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--images-dir", type=Path, default=DEFAULT_IMAGES_DIR)
    ap.add_argument("--ch4", type=Path, default=DEFAULT_CH4)
    ap.add_argument("--ch11", type=Path, default=DEFAULT_CH11)
    ap.add_argument("--dry-run", action="store_true", help="只打印合并计划，不写文件")
    args = ap.parse_args()

    pages = parse_pages(args.pages_dir)
    plan = build_plan(pages)
    n_page = sum(1 for k, _ in plan if k == "page")

    if args.dry_run:
        log("转换目录：%s（%d 页）" % (args.pages_dir, len(pages)))
        log("合并计划：%d 段页面 + 2 段章节 md" % n_page)
        for kind, payload in plan:
            if kind == "md4":
                log("  [md] 第四章正文 L%d–L%d（覆盖 PDF 46–67）" % CH4_BODY)
            elif kind == "md11":
                log("  [md] 第十一章正文 L%d–L%d（覆盖 PDF 160–179）" % CH11_BODY)
            elif payload == TRUNCATE_PAGE:
                log("  [page] PDF %d（只取「第四节」起）" % payload)
            elif payload in WHOLE_EXTRA_PAGES:
                log("  [page] PDF %d（合订本补页）" % payload)
        return 0

    link_prefix = resolve_link_prefix(args.out, args.images_dir)

    # 幂等：清空并重建图片目录
    if args.images_dir.exists():
        shutil.rmtree(args.images_dir)
    args.images_dir.mkdir(parents=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    copied: dict[str, str] = {}
    chunks: list[str] = []
    segments: list[str] = []

    chunks.append(
        "# 铁路行车组织（第 2 版）· 前 3 篇\n\n"
        "> 覆盖范围：PDF 第 %d–%d 页（印刷页 %s–%s）。\n"
        "> 数据来源：MinerU 精准解析逐页 OCR；第四、十一章正文及若干零散页取自 "
        "`knowledge_base/` 已有原文与教材合订本。\n"
        "> 人工校正：第 134 页（印刷页 124）简答题第 6、8 题 OCR 漏行，已按原页补回。\n"
        "> 生成时间：%s。图片统一存放于 `%s`。\n"
        % (START_PAGE, END_PAGE, printed(START_PAGE), printed(END_PAGE),
           datetime.now().strftime("%Y-%m-%d %H:%M"), link_prefix.rstrip("/"))
    )
    segments.append("文首说明")

    for kind, payload in plan:
        if kind == "md4":
            body = read_lines(args.ch4, CH4_BODY, "# 第四章", 597, "11. 简述")
            body = rewrite_chapter_images(body, CH4_IMG_DIR, "ch4_",
                                          args.images_dir, copied, link_prefix)
            chunks.append("<!-- ===== 印刷页 036–057：第四章正文，补自 "
                          "knowledge_base/调车工作/铁路行车组织第2版-调车工作.md ===== -->\n\n"
                          + body.strip())
            segments.append("第四章正文（md L%d–L%d）" % CH4_BODY)
            continue
        if kind == "md11":
            body = read_lines(args.ch11, CH11_BODY, "# 第十一章", 709, "第四节")
            body = rewrite_chapter_images(body, CH11_IMG_DIR, "ch11_",
                                          args.images_dir, copied, link_prefix)
            chunks.append("<!-- ===== 印刷页 150–169：第十一章正文，补自 "
                          "knowledge_base/技术站列车编组计划的编制/"
                          "铁路行车组织第2版-技术站列车编组计划的编制.md ===== -->\n\n"
                          + body.strip())
            segments.append("第十一章正文（md L%d–L%d）" % CH11_BODY)
            continue

        page = int(payload)
        page_dir = pages[page]
        text = (page_dir / "full.md").read_text(encoding="utf-8", errors="replace").strip()
        text = apply_page_fixes(text, page)
        note = ""
        if page == TRUNCATE_PAGE:
            text = truncate_at_section4(text, page)
            note = "，只取「第四节」起"
        elif page in WHOLE_EXTRA_PAGES:
            note = "，合订本补页"
        text = rewrite_page_images(text, page_dir, page, args.images_dir,
                                   copied, link_prefix)
        chunks.append("<!-- ===== PDF 第 %d 页 / 印刷页 %s%s ===== -->\n\n%s"
                      % (page, printed(page), note, text.strip()))

    text = "\n\n".join(chunks).rstrip() + "\n"
    args.out.write_text(text, encoding="utf-8")

    stats = check_output(text, args.out, args.images_dir, n_page)
    log("输出：%s" % args.out)
    log("图片：%s（%d 个）" % (args.images_dir, len(list(args.images_dir.iterdir()))))
    log("统计：%d 页、%d 行、%.1f KB、%d 张图片引用"
        % (stats["pages"], stats["lines"], stats["chars"] / 1024, stats["images"]))
    log("插入段：" + "；".join(segments[1:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
