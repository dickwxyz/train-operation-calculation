# -*- coding: utf-8 -*-
"""教材 Markdown -> 结构化 chunk。

设计要点
--------
* 不依赖 Markdown 标题级别：OCR 把章、节、正文列表混成了 #/##，这里按
  「第X篇 / 第X章 / 第X节 / 一、 / （一）」的文本模式识别。
* 表格、公式、例题、习题题号是原子块，不按行切。
* 页标记注释转成页码元数据；第四、十一章的「补自」块只能给印刷页范围。
* 跨页断句：页标记两侧的空行先压掉，段落累积时若上一行没有句末标点就直接拼接。
"""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from . import config

# ---------------------------------------------------------------------------
# 文本归一化
# ---------------------------------------------------------------------------

_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_PAGE_STD_RE = re.compile(
    r"<!--\s*=====\s*PDF 第\s*(\d+)\s*页\s*/\s*印刷页\s*(\d+)([^>]*)-->")
_PAGE_RANGE_RE = re.compile(
    r"<!--\s*=====\s*印刷页\s*(\d+)\s*[–\-]\s*(\d+)\s*[：:]([^>]*)-->")
_TERMINAL = "。！？!?；;：:"
_HEADING_SPECIALS = (
    "本章小结", "思考题", "本篇习题", "单项选择题", "多项选择题", "单选题",
    "多选题", "名词解释题", "简答题", "判断分析题", "综合计算题", "计算题",
)


def fullwidth_to_halfwidth(text: str) -> str:
    """全角转半角（仅 ASCII 区），保留中文标点原样。"""
    out = []
    for ch in text:
        code = ord(ch)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


def latex_to_text(text: str) -> str:
    """把本教材 OCR 产生的 LaTeX 片段改成可读文本（不追求完整 LaTeX 解析）。"""
    s = text
    is_math = ("\\" in s) or ("$" in s) or ("Σ" in s) or ("∈" in s)
    # 先处理 \mathop{\sum}\limits_{{i \in Z}} 这类求和
    s = re.sub(
        r"\\mathop\s*\{\s*\\sum\s*\}\s*\\limits_\s*\{\s*\{([^{}]*)\}\s*\}",
        lambda m: "Σ(" + m.group(1) + ")", s)
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\\,", "").replace("\\;", "").replace("\\ ", "")
    s = s.replace("\\mathrm", "").replace("\\mathbf", "").replace("\\text", "")
    s = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"\1/\2", s)
    s = re.sub(r"\\(?:mathop|limits)\s*", "", s)
    symbols = {
        "\\sum": "Σ", "\\Delta": "Δ", "\\triangle": "△", "\\bigtriangleup": "△",
        "\\circ": "○", "\\bigcirc": "○", "\\bullet": "●", "\\times": "×",
        "\\sim": "~", "\\leq": "≤", "\\geq": "≥", "\\le": "≤", "\\ge": "≥",
        "\\approx": "≈", "\\cdot": "·", "\\in": "∈", "\\langle": "⟨",
        "\\rangle": "⟩", "\\prime": "′", "\\tau": "τ", "\\varepsilon": "ε",
        "\\overline": "", "\\tag": " 式",
    }
    for k, v in symbols.items():
        s = s.replace(k, v)
    s = s.replace("$", "")
    s = s.replace("{", "").replace("}", "")
    s = re.sub(r"\\([A-Za-z]+)", r"\1", s)
    # 下标/上标：F_{耗} -> F耗，x^{2} -> x^2
    s = re.sub(r"_\s*", "", s)
    s = re.sub(r"\^\s*", "^", s)
    if is_math:
        s = re.sub(r"\s*([∈=+×/<>≤≥^()])\s*", r"\1", s)
        s = re.sub(r"(?<=[A-Za-z0-9)⟩])\s+(?=[A-Za-z0-9(⟨])", "", s)
    s = re.sub(r"(?<=[A-Za-z0-9])\s+(?=[一-鿿])", "", s)
    s = re.sub(r"(?<=[一-鿿])\s+(?=[A-Za-z0-9])", "", s)
    s = re.sub(r"(?<=\d)\s+(?=\d)", "", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


def normalize_for_index(text: str) -> str:
    """检索用归一化：全半角、数字空格、LaTeX、空白。"""
    s = latex_to_text(html.unescape(text))
    s = fullwidth_to_halfwidth(s)
    s = re.sub(r"(?<=\d)\s+(?=\d)", "", s)
    s = re.sub(r"[ \t\u3000]+", " ", s)
    s = re.sub(r"\n+", "\n", s)
    return s.strip().lower()


def readable(text: str) -> str:
    """回答/出处展示用：去图片、去 HTML、LaTeX 可读化、压缩空白。"""
    s = _IMG_RE.sub("", text)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = _HTML_TAG_RE.sub(" ", s)
    s = latex_to_text(html.unescape(s))
    s = re.sub(r"[ \t\u3000]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def table_to_text(table_html: str) -> str:
    """HTML 表 -> 线性文本：每行用「列: 值；…」或「值 | 值」。"""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.S | re.I)
    out = []
    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.S | re.I)
        vals = [readable(c) for c in cells]
        vals = [v for v in vals if v]
        if vals:
            out.append(" | ".join(vals))
    return "\n".join(out)


def display_text(text: str) -> str:
    """回答/出处用：表格先线性化，再去 HTML/图片/LaTeX。"""
    def _table(m: re.Match) -> str:
        return "\n" + table_to_text(m.group(0)) + "\n"

    s = re.sub(r"<table\b.*?</table>", _table, text, flags=re.S | re.I)
    return readable(s)


def split_sentences(text: str) -> list[str]:
    """中文句级切分，保留标点；编号列表项也作为独立句。"""
    text = text.strip()
    if not text:
        return []
    parts = re.split(r"(?<=[。！？!?；;])", text)
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # 长段再按换行拆开，避免把一整块列表塞成一句
        if "\n" in p:
            out.extend(x.strip() for x in p.split("\n") if x.strip())
        else:
            out.append(p)
    return out


def _bigrams(text: str) -> set[str]:
    s = re.sub(r"\s+", "", normalize_for_index(text))
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class Block:
    kind: str                       # prose / table / formula / example / exercise
    text: str
    heading_path: list[str] = field(default_factory=list)
    chapter: str = ""
    section: str = ""
    block_type: str = ""
    example_id: str | None = None
    question_no: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    page_conf: str = "none"         # exact / range / none
    continuation: bool = False


@dataclass
class Parent:
    """按完整 heading_path 聚合的章节块（检索单元）。"""
    key: str
    chapter: str
    section: str
    heading_path: list[str]
    chunk_ids: list[str]
    text: str


@dataclass
class Chunk:
    id: str
    text: str
    index_text: str
    chapter: str
    section: str
    heading_path: list[str]
    block_type: str
    page_start: int | None
    page_end: int | None
    page_conf: str
    example_id: str | None = None
    question_no: str | None = None
    parent_key: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "text": self.text, "chapter": self.chapter,
            "section": self.section, "heading_path": self.heading_path,
            "block_type": self.block_type, "page_start": self.page_start,
            "page_end": self.page_end, "page_conf": self.page_conf,
            "example_id": self.example_id, "question_no": self.question_no,
            "parent_key": self.parent_key,
        }


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------

_CHAPTER_RE = re.compile(r"^第([一二三四五六七八九十百零〇\d]+)章\s*(.*)$")
_SECTION_RE = re.compile(r"^第([一二三四五六七八九十百零〇\d]+)节\s*(.*)$")
_PART_RE = re.compile(r"^第([一二三四五六七八九十]+)篇\s*(.*)$")
_SUB_RE = re.compile(r"^([一二三四五六七八九十]+)、\s*(.*)$")
_SUBSUB_RE = re.compile(r"^[（(]([一二三四五六七八九十]+)[）)]\s*(.*)$")
_LIST_HEAD_RE = re.compile(r"^[（(]\d+[）)]|^\d+[.、]|^[①-⑳]")
_QUESTION_RE = re.compile(r"^\s*(\d{1,3})[.、]\s*")
_EXAMPLE_RE = re.compile(r"【\s*例\s*(\d+\.\d+)\s*】")


def _classify_heading(text: str) -> tuple[str, str]:
    """返回 (类型, 规范化标题)。类型：part/chapter/section/sub/subsub/special/other。"""
    t = text.strip()
    if re.match(r"^第[一二三四五六七八九十]+篇\b", t):
        return "part", t
    # 「一、单项选择题」「五、综合计算题」这类带序号的习题小节
    t2 = re.sub(r"^[一二三四五六七八九十]+、\s*", "", t)
    if any(t2.startswith(s) for s in _HEADING_SPECIALS):
        return "special", t2
    m = _CHAPTER_RE.match(t)
    if m:
        return "chapter", "第%s章 %s" % (m.group(1), m.group(2).strip())
    m = _SECTION_RE.match(t)
    if m:
        return "section", "第%s节 %s" % (m.group(1), m.group(2).strip())
    m = _SUB_RE.match(t)
    if m:
        return "sub", "%s、%s" % (m.group(1), m.group(2).strip())
    m = _SUBSUB_RE.match(t)
    if m:
        return "subsub", "（%s）%s" % (m.group(1), m.group(2).strip())
    return "other", t


def _heading_text(line: str) -> str | None:
    """Markdown 标题行 -> 标题文本；普通行返回 None。"""
    m = re.match(r"^\s*#{1,6}\s+(.*?)\s*$", line)
    return m.group(1).strip() if m else None


def _is_structural_heading(text: str) -> bool:
    """# 标题里哪些是真的结构标题；`## （1）…` 是正文列表，不是标题。"""
    if not text or len(text) > 80:
        return False
    if _LIST_HEAD_RE.match(text):
        return False
    kind, _ = _classify_heading(text)
    if kind in ("part", "chapter", "section", "sub", "subsub", "special"):
        return True
    # 形如「本章主要知识点回顾：」的短标题算小节标题
    return len(text) <= 40 and not text.endswith("。")


def _page_from_marker(line: str):
    m = _PAGE_STD_RE.search(line)
    if m:
        p = int(m.group(2))
        return (p, p, "exact")
    m = _PAGE_RANGE_RE.search(line)
    if m:
        return (int(m.group(1)), int(m.group(2)), "range")
    return None


def _merge_pages(pages: list[tuple[int, int, str]]):
    pages = [p for p in pages if p and p[0] is not None]
    if not pages:
        return None, None, "none"
    starts = [p[0] for p in pages]
    ends = [p[1] for p in pages]
    conf = "range" if any(p[2] == "range" for p in pages) else (
        "exact" if all(p[2] == "exact" for p in pages) else "none")
    return min(starts), max(ends), conf


class _Parser:
    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self.part = "第一篇"
        self.chapter = "绪论"
        self.section = ""
        self.sub = ""
        self.subsub = ""
        self.in_exercises = False
        self.exercise_qtype: str | None = None
        self.in_summary = False
        self.page = (None, None, "none")

        self._para: list[str] = []
        self._para_pages: list[tuple[int, int, str]] = []
        self._pending_break = False
        self._exercise: list[str] = []
        self._exercise_pages: list[tuple[int, int, str]] = []
        self._exercise_no: str | None = None
        self._exercise_type: str | None = None
        self._example: list[str] = []
        self._example_pages: list[tuple[int, int, str]] = []
        self._example_id: str | None = None
        self._table_continuation = False

    # ---- 标题状态 ----
    def _heading_path(self) -> list[str]:
        path = [self.chapter]
        if self.section:
            path.append(self.section)
        if self.sub:
            path.append(self.sub)
        if self.subsub:
            path.append(self.subsub)
        return [p for p in path if p]

    def _flush_para(self) -> None:
        if not self._para:
            return
        text = "\n".join(self._para).strip()
        if text:
            ps, pe, pc = _merge_pages(self._para_pages)
            kind = "summary" if self.in_summary else "prose"
            self.blocks.append(Block(
                kind="prose", text=text, heading_path=self._heading_path(),
                chapter=self.chapter, section=self.section, block_type=kind,
                page_start=ps, page_end=pe, page_conf=pc,
            ))
        self._para = []
        self._para_pages = []

    def _flush_exercise(self) -> None:
        if not self._exercise:
            return
        text = "\n".join(self._exercise).strip()
        if text:
            ps, pe, pc = _merge_pages(self._exercise_pages)
            self.blocks.append(Block(
                kind="exercise", text=text, heading_path=self._heading_path(),
                chapter=self.chapter, section=self.section,
                block_type="exercise_%s" % (self._exercise_type or "short"),
                question_no=self._exercise_no,
                page_start=ps, page_end=pe, page_conf=pc,
            ))
        self._exercise = []
        self._exercise_pages = []
        self._exercise_no = None
        self._exercise_type = None

    def _flush_example(self) -> None:
        if not self._example:
            return
        text = "\n".join(self._example).strip()
        if text:
            ps, pe, pc = _merge_pages(self._example_pages)
            self.blocks.append(Block(
                kind="example", text=text, heading_path=self._heading_path(),
                chapter=self.chapter, section=self.section, block_type="example",
                example_id=self._example_id,
                page_start=ps, page_end=pe, page_conf=pc,
            ))
        self._example = []
        self._example_pages = []
        self._example_id = None

    def _flush_all(self) -> None:
        self._flush_para()
        self._flush_exercise()
        self._flush_example()

    # ---- 主循环 ----
    def feed(self, lines: Iterable[str], finalize: bool = True) -> None:
        for raw in lines:
            line = raw.rstrip("\n")
            page = _page_from_marker(line)
            if page:
                self.page = page
                self._pending_break = True
                continue

            if not line.strip():
                # 空行结束段落，但页标记之后的续写由 _pending_break 处理
                self._flush_para()
                continue

            htext = _heading_text(line)
            if htext is not None and _is_structural_heading(htext):
                self._flush_all()
                self._on_heading(htext)
                self._pending_break = False
                continue

            if htext is not None:
                line = htext  # `## （1）…` 这类伪标题还原成正文

            if _IMG_RE.fullmatch(line.strip()):
                continue

            if line.lstrip().startswith("<table"):
                # 例题/习题里的资料表要留在同一块里
                if self._example:
                    self._example.append(line)
                    self._example_pages.append(self.page)
                elif self._exercise:
                    self._exercise.append(line)
                    self._exercise_pages.append(self.page)
                else:
                    self._flush_all()
                    self._collect_table(line)
                self._pending_break = False
                continue

            if line.strip().startswith("$$"):
                if self._example:
                    self._example.append(line)
                    self._example_pages.append(self.page)
                elif self._exercise:
                    self._exercise.append(line)
                    self._exercise_pages.append(self.page)
                else:
                    self._flush_para()
                    self._collect_formula(line)
                self._pending_break = False
                continue

            if line.strip() in ("续表", "续 表"):
                self._table_continuation = True
                continue

            m = _EXAMPLE_RE.search(line)
            if m:
                self._flush_all()
                self._example_id = m.group(1)
                self._example = [line]
                self._example_pages = [self.page]
                self._pending_break = False
                continue

            if self.in_exercises:
                qm = _QUESTION_RE.match(line)
                if qm:
                    self._flush_para()
                    self._flush_exercise()
                    self._exercise_no = qm.group(1)
                    self._exercise_type = self.exercise_qtype or "short"
                    self._exercise = [line]
                    self._exercise_pages = [self.page]
                    self._pending_break = False
                    continue

            # 普通正文行
            if self._example:
                if self._pending_break and self._example and not self._example[-1].endswith(tuple(_TERMINAL)):
                    self._example[-1] += line.strip()
                else:
                    self._example.append(line)
                self._example_pages.append(self.page)
            elif self._exercise:
                if self._pending_break and self._exercise and not self._exercise[-1].endswith(tuple(_TERMINAL)):
                    self._exercise[-1] += line.strip()
                else:
                    self._exercise.append(line)
                self._exercise_pages.append(self.page)
            else:
                if self._pending_break and self._para and not self._para[-1].endswith(tuple(_TERMINAL)) \
                        and not _LIST_HEAD_RE.match(line.strip()):
                    self._para[-1] += line.strip()
                else:
                    self._para.append(line)
                self._para_pages.append(self.page)
            self._pending_break = False
        if finalize:
            self._flush_all()

    def _on_heading(self, text: str) -> None:
        kind, norm = _classify_heading(text)
        if kind == "part":
            self.part = norm
            self.chapter = norm
            self.section = self.sub = self.subsub = ""
            self.in_exercises = False
            self.exercise_qtype = None
            self.in_summary = False
            return
        if kind == "chapter":
            self.chapter = norm
            self.section = self.sub = self.subsub = ""
            self.in_exercises = False
            self.exercise_qtype = None
            self.in_summary = False
            return
        if kind == "section":
            self.section = norm
            self.sub = self.subsub = ""
            self.in_exercises = False
            self.exercise_qtype = None
            self.in_summary = False
            return
        if kind == "sub":
            self.sub = norm
            self.subsub = ""
            return
        if kind == "subsub":
            self.subsub = norm
            return
        if kind == "special":
            self.sub = self.subsub = ""
            if norm.startswith("本章小结"):
                self.section = "本章小结"
                self.in_summary = True
                self.in_exercises = False
                self.exercise_qtype = None
            elif norm.startswith("思考题"):
                self.section = "思考题"
                self.in_summary = False
                self.in_exercises = True
                self.exercise_qtype = "thinking"
            elif norm.startswith("本篇习题"):
                self.chapter = "%s 本篇习题" % self.part
                self.section = ""
                self.in_summary = False
                self.in_exercises = True
                self.exercise_qtype = "short"
            else:
                self.section = norm
                self.in_summary = False
                self.in_exercises = True
                self.exercise_qtype = {
                    "单项选择题": "mc", "单选题": "mc", "多项选择题": "multi",
                    "多选题": "multi", "名词解释题": "term", "简答题": "short",
                    "判断分析题": "judge", "综合计算题": "calc", "计算题": "calc",
                }.get(norm.split()[0], "short")
            return
        # other: 视作小节标题（如「本章主要知识点回顾」）
        self.sub = norm
        self.subsub = ""

    def _collect_table(self, first: str) -> None:
        """单行表格；跨行表格由 feed_stream 的 pending_table 处理。"""
        self._append_table(first)

    def _append_table(self, html_text: str) -> None:
        ps, pe, pc = self.page
        full = html_text
        if self._table_continuation and self.blocks and self.blocks[-1].kind == "table":
            self.blocks[-1].text += "\n" + full
            self.blocks[-1].page_end = pe
            if pc == "range":
                self.blocks[-1].page_conf = "range"
        else:
            self.blocks.append(Block(
                kind="table", text=full, heading_path=self._heading_path(),
                chapter=self.chapter, section=self.section, block_type="table",
                page_start=ps, page_end=pe, page_conf=pc,
            ))
        self._table_continuation = False

    def _collect_formula(self, first: str) -> None:
        """单行公式；跨行公式由 feed_stream 的 pending_formula 处理。"""
        self._append_formula(first)

    def _append_formula(self, text: str) -> None:
        ps, pe, pc = self.page
        self.blocks.append(Block(
            kind="formula", text=text, heading_path=self._heading_path(),
            chapter=self.chapter, section=self.section, block_type="formula",
            page_start=ps, page_end=pe, page_conf=pc,
        ))

    # 供 feed_stream 使用：表格/公式跨行时把行塞回来
    def feed_stream(self, lines: Iterable[str]) -> None:
        it = iter(lines)
        pending_table: list[str] | None = None
        pending_formula: list[str] | None = None
        for raw in it:
            line = raw.rstrip("\n")
            if pending_table is not None:
                page = _page_from_marker(line)
                if page:
                    self.page = page
                pending_table.append(line)
                if "</table>" in line:
                    text = "\n".join(pending_table)
                    if self._example:
                        self._example.append(text)
                        self._example_pages.append(self.page)
                    elif self._exercise:
                        self._exercise.append(text)
                        self._exercise_pages.append(self.page)
                    else:
                        self._append_table(text)
                    pending_table = None
                    self._pending_break = False
                continue
            if pending_formula is not None:
                page = _page_from_marker(line)
                if page:
                    self.page = page
                    continue
                pending_formula.append(line)
                if line.strip().startswith("$$") and len(pending_formula) > 1:
                    text = "\n".join(pending_formula)
                    if self._example:
                        self._example.append(text)
                        self._example_pages.append(self.page)
                    elif self._exercise:
                        self._exercise.append(text)
                        self._exercise_pages.append(self.page)
                    else:
                        self._append_formula(text)
                    pending_formula = None
                    self._pending_break = False
                continue
            if line.lstrip().startswith("<table") and "</table>" not in line:
                page = _page_from_marker(line)
                if page:
                    self.page = page
                    continue
                if not (self._example or self._exercise):
                    self._flush_all()
                pending_table = [line]
                continue
            if line.strip().startswith("$$") and line.strip().count("$$") < 2:
                if not (self._example or self._exercise):
                    self._flush_para()
                pending_formula = [line]
                continue
            self.feed([line], finalize=False)
        if pending_table is not None:
            text = "\n".join(pending_table)
            if self._example:
                self._example.append(text)
                self._example_pages.append(self.page)
            elif self._exercise:
                self._exercise.append(text)
                self._exercise_pages.append(self.page)
            else:
                self._append_table(text)
        if pending_formula is not None:
            text = "\n".join(pending_formula)
            if self._example:
                self._example.append(text)
                self._example_pages.append(self.page)
            elif self._exercise:
                self._exercise.append(text)
                self._exercise_pages.append(self.page)
            else:
                self._append_formula(text)
        self._flush_all()


# ---------------------------------------------------------------------------
# 分块
# ---------------------------------------------------------------------------

def _split_text(text: str, target: int, hard_max: int, overlap: int) -> list[str]:
    """按句子累积到 target；超长句硬切；相邻块保留最后一句作为重叠。"""
    sents = split_sentences(text)
    if not sents:
        return []
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for s in sents:
        if len(s) > hard_max:
            if cur:
                chunks.append("".join(cur).strip())
                cur, cur_len = [], 0
            for i in range(0, len(s), hard_max):
                chunks.append(s[i:i + hard_max])
            continue
        if cur_len + len(s) > target and cur:
            chunks.append("".join(cur).strip())
            tail = cur[-1] if len(cur[-1]) <= overlap * 2 else ""
            cur = [tail] if tail else []
            cur_len = len(tail)
        cur.append(s)
        cur_len += len(s)
    if cur:
        chunks.append("".join(cur).strip())
    return [c for c in chunks if c]


def _split_example(text: str, example_id: str | None) -> list[str]:
    if len(text) <= config.EXAMPLE_MAX:
        return [text]
    parts = re.split(r"(?=第[一二三四五六七八九十\d]+步)", text)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(p) > config.EXAMPLE_MAX:
            out.extend(_split_text(p, 1200, config.EXAMPLE_MAX, 0))
        else:
            out.append(p)
    return out or [text]


def _make_chunks(blocks: list[Block]) -> list[Chunk]:
    chunks: list[Chunk] = []
    seq = 0

    def add(text: str, block: Block, block_type: str, *, example_id=None, question_no=None):
        nonlocal seq
        text = text.strip()
        if not text:
            return
        path = block.heading_path
        heading = " | ".join(path)
        index_text = "\n".join([heading, heading, heading, text])
        chunks.append(Chunk(
            id="c%04d" % seq, text=text, index_text=index_text,
            chapter=block.chapter, section=block.section, heading_path=path,
            block_type=block_type, page_start=block.page_start,
            page_end=block.page_end, page_conf=block.page_conf,
            example_id=example_id or block.example_id,
            question_no=question_no or block.question_no,
            parent_key=heading,
        ))
        seq += 1

    for block in blocks:
        if block.kind == "prose":
            btype = "summary" if block.block_type == "summary" else "prose"
            for part in _split_text(block.text, config.CHILD_TARGET,
                                    config.CHILD_MAX, config.CHILD_OVERLAP):
                add(part, block, btype)
        elif block.kind == "formula":
            if chunks and chunks[-1].parent_key == " | ".join(block.heading_path) \
                    and chunks[-1].block_type == "prose" \
                    and len(chunks[-1].text) + len(block.text) <= config.CHILD_MAX:
                chunks[-1].text += "\n\n" + block.text
                chunks[-1].index_text += "\n" + normalize_for_index(block.text)
            else:
                add(block.text, block, "formula")
        elif block.kind == "table":
            linear = table_to_text(block.text)
            if linear:
                add(linear, block, "table")
        elif block.kind == "example":
            for part in _split_example(block.text, block.example_id):
                add(part, block, "example", example_id=block.example_id)
        elif block.kind == "exercise":
            add(block.text, block, block.block_type, question_no=block.question_no)

    # 过短的块并入同 parent 的前一块
    merged: list[Chunk] = []
    for c in chunks:
        if merged and len(c.text) < config.MIN_CHUNK_CHARS \
                and merged[-1].parent_key == c.parent_key \
                and merged[-1].block_type == c.block_type \
                and not c.block_type.startswith("exercise"):
            merged[-1].text += "\n" + c.text
            merged[-1].index_text += "\n" + c.text
            if c.page_end:
                merged[-1].page_end = c.page_end
            continue
        merged.append(c)
    return merged


def _dedupe(chunks: list[Chunk]) -> tuple[list[Chunk], int]:
    """完全重复 + 同一例题的近重复只保留一份。"""
    seen: set[str] = set()
    exact: list[Chunk] = []
    dropped = 0
    for c in chunks:
        h = hashlib.sha1(normalize_for_index(c.text).encode("utf-8")).hexdigest()
        if h in seen:
            dropped += 1
            continue
        seen.add(h)
        exact.append(c)

    # 例题近重复：同 example_id 且二元组 Jaccard > 0.85
    by_example: dict[str, list[Chunk]] = {}
    for c in exact:
        if c.example_id:
            by_example.setdefault(c.example_id, []).append(c)
    drop_ids: set[str] = set()
    for eid, group in by_example.items():
        if len(group) < 2:
            continue
        # 例 8.1 在教材里出现了两遍：按「【例…】」起始块分段，保留 LaTeX 更规范的一段
        starts = [i for i, c in enumerate(group) if c.text.lstrip().startswith("【例")]
        if len(starts) >= 2:
            def start_score(i: int):
                head = group[i].text[:800]
                return (head.count("$") + head.count("\\tag"), len(head))
            keep_start = max(starts, key=start_score)
            keep_from = keep_start
            keep_to = starts[starts.index(keep_start) + 1] if keep_start != starts[-1] else len(group)
            for i, c in enumerate(group):
                if keep_from <= i < keep_to:
                    continue
                drop_ids.add(c.id)
                dropped += 1
            continue
        keep = max(group, key=lambda c: (c.text.count("$") + c.text.count("\\tag"), len(c.text)))
        keep_grams = _bigrams(keep.text)
        for c in group:
            if c is keep:
                continue
            grams = _bigrams(c.text)
            inter = len(keep_grams & grams)
            union = len(keep_grams | grams) or 1
            if inter / union > 0.85:
                drop_ids.add(c.id)
                dropped += 1
    return [c for c in exact if c.id not in drop_ids], dropped


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------

def load_blocks(path: Path | None = None) -> list[Block]:
    path = path or config.CORPUS_PATH
    text = path.read_text(encoding="utf-8")
    # 压掉页标记两侧的空行，让跨页续写进入同一段落
    text = re.sub(
        r"\n(?:[ \t]*\n)+(<!--\s*=====\s*(?:PDF 第|印刷页)[^\n]*-->)(?:[ \t]*\n)+",
        r"\n\1\n", text)
    parser = _Parser()
    parser.feed_stream(text.splitlines())
    return parser.blocks


def build_parents(chunks: list[Chunk]) -> list[Parent]:
    """把 child chunks 按 parent_key 聚合成 section 级检索单元。"""
    groups: dict[str, list[Chunk]] = {}
    for c in chunks:
        groups.setdefault(c.parent_key, []).append(c)
    parents: list[Parent] = []
    for key, group in groups.items():
        first = group[0]
        header = " | ".join(first.heading_path)
        body = "\n".join(c.text for c in group)
        parents.append(Parent(
            key=key, chapter=first.chapter, section=first.section,
            heading_path=first.heading_path,
            chunk_ids=[c.id for c in group],
            text=header + "\n" + body,
        ))
    return parents


def load_chunks(path: Path | None = None) -> tuple[list[Chunk], dict]:
    blocks = load_blocks(path)
    chunks = _make_chunks(blocks)
    chunks, dropped = _dedupe(chunks)
    for i, c in enumerate(chunks):
        c.id = "c%04d" % i
    stats = {
        "blocks": len(blocks),
        "chunks": len(chunks),
        "dropped_duplicates": dropped,
        "by_type": _count(chunks, lambda c: c.block_type),
        "by_chapter": _count(chunks, lambda c: c.chapter),
    }
    return chunks, stats


def _count(items: list[Chunk], key) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items:
        k = key(it)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))
