# -*- coding: utf-8 -*-
"""
把 paper/origin/ 下的文献 PDF 批量转成 Markdown（走 MinerU 精准解析 API）。

为什么需要这一步
----------------
文献综述与讨论节的依据是 paper/origin/ 下的论文 PDF。PDF 形态没法 grep、
也没法直接喂给模型做综合，写作时要反复翻页。转成 Markdown 后即可全文检索、逐段引用，
同时保留图片便于核对原文图表。

做法
----
调 MinerU「精准解析 API」的**本地文件批量上传**链路（本地文件不能走 /extract/task，
那个接口只收公网 URL）：

    ① POST /api/v4/file-urls/batch      申请预签名上传链接，拿 batch_id + file_urls[]
    ② PUT  <file_urls[i]>               逐篇上传二进制（不设 Content-Type）
                                        上传完成后服务端自动扫描并提交解析，无需再调提交接口
    ③ GET  /api/v4/extract-results/batch/{batch_id}   轮询到 done/failed
    ④ 下载 full_zip_url，解压到 <输出目录>/<PDF 去后缀>/  （full.md 里用 images/ 相对路径引图，
       所以必须整包解压到同一目录，链接才不会断）

模型用 vlm（官方推荐），对双栏排版、跨页表格、公式与扫描件更稳。

设计要点
--------
* **幂等**：解压先落到 `<篇名>.part` 再原子换入，保证「子目录存在」== 「解压完整」。
  重跑默认跳过已产出非空 full.md 的篇目。
* **续跑**：batch_id 与各篇状态落盘到 .cache/，中断后重跑会**续轮询同一批次而不重传**（省额度）。
* **上传失败必须单独兜住**：某篇 PUT 失败 → 文件没进 OSS → 服务端扫不到 → 该篇会**永久停在
  waiting-file 或压根不出现在结果里**，不会变成 failed。所以批次结束后把所有非 done 的篇目
  收拢起来另起一批补跑，轮数由 --retry-failed 限制。
* **额度**：每日 1000 页最高优先级。--force 会重新消耗额度，故要求确认。

用法
----
    PY=.venv/bin/python      # 或 /opt/anaconda3/bin/python3
    S=scripts/mineru_pdf_to_md.py

    $PY $S --dry-run            # 零网络：看会处理哪些篇目、doc_id 与目录名
    $PY $S --only 甘蜜          # 只跑 1 篇，先走通全链路
    $PY $S                      # 全量（跳过已完成，可反复跑）
    $PY $S --verify-only        # 零网络：按磁盘现状重算清单并校验
    $PY $S --force              # 忽略已完成重做（重新耗额度，需确认）
    $PY $S --move-to paper/converted
                                # 转换并校验通过后，把源 PDF 移出 origin

默认路径（相对仓库根，由脚本位置自动定位）：输入 `paper/origin/`、输出 `paper/md/`。
每篇一个子目录，内含 full.md、images/ 与 *_content_list.json。移动只针对**校验通过**的篇目，
失败/未完成的仍留在 origin 里便于重跑。

**解释器必须链接 OpenSSL 3.x**。系统 /usr/bin/python3 链接 LibreSSL 2.8.3，TLS 会以难懂的方式
失败；仓库 `.venv/bin/python`（3.12，OpenSSL 3.0.15）与 /opt/anaconda3/bin/python3 均可。

依赖: requests（密钥读仓库根 `.env` 的 MINERU_API_KEY）

注意
----
不要把 paper/ 整个 git add —— 里面是原始 PDF 与解析出的大量图片；full.md 与清单文件才是
需要入库的产物。状态文件在 scripts/.cache/（续跑用，可随时删）。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import ssl
import sys
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

# ---- 解释器守卫：LibreSSL 下 TLS 握手不可靠，与其让人踩坑不如提前拒绝 ----
if "LibreSSL" in ssl.OPENSSL_VERSION:
    sys.exit(
        "当前解释器链接 LibreSSL（%s），无法可靠完成 TLS 握手。\n"
        "请改用：/opt/anaconda3/bin/python3 scripts/01_literature_search/mineru_pdf_to_md.py"
        % ssl.OPENSSL_VERSION
    )

import requests  # noqa: E402  （必须在解释器守卫之后导入）

ROOT = Path(__file__).resolve().parents[1]      # 仓库根
IN_DIR = ROOT / "paper" / "origin"
OUT_DIR = ROOT / "paper" / "md"
MOVE_DIR = ROOT / "paper" / "converted"
CACHE = Path(__file__).resolve().parent / ".cache"
STATE_FILE = CACHE / "mineru_state.json"

BASE = "https://mineru.net"
API_SUBMIT = "/api/v4/file-urls/batch"
API_RESULT = "/api/v4/extract-results/batch/%s"

# state 取值：new / waiting-file / pending / running / converting / done / failed / upload_failed
TERMINAL = {"done", "failed"}
# 上传链接有效期 24h；超过这个时长就不再续用旧批次
BATCH_MAX_AGE = 20 * 3600
# 上传后多久还没出现在结果列表里，就判定为上传失败
UPLOAD_VANISH_SEC = 300
# 解压总体积护栏（防 zip 炸弹）
MAX_UNZIP_BYTES = 2 * 1024 ** 3

IMG_RE = re.compile(r"!\[[^\]]*\]\((?:<)?([^)\s>]+)(?:>)?")


class MineruError(RuntimeError):
    def __init__(self, code, msg):
        super().__init__("MinerU code=%s msg=%s" % (code, msg))
        self.code = code
        self.msg = msg


def log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def hms(sec):
    sec = int(sec)
    return "%d分%02d秒" % (sec // 60, sec % 60) if sec >= 60 else "%d秒" % sec


def rel_to(p: Path) -> str:
    """相对仓库根的展示路径；目录不在仓库内时退回原样（避免 relative_to 抛错）。"""
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


# --------------------------------------------------------------------------
# 环境与状态
# --------------------------------------------------------------------------
def load_env(env_file: Path) -> bool:
    """逐行读 .env（与 scripts/02_data_description/literature_search.py 同款做法）。

    用 setdefault，使 shell 里已导出的变量优先于文件里的值。
    """
    if not env_file.exists():
        return False
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    return True


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log("状态文件损坏，按空状态继续（已完成篇目仍由磁盘产物判定）：%s" % e)
    return {"version": 1, "files": {}}


def save_state(state: dict):
    """先写 .tmp 再原子替换，避免中途中断把状态文件写坏。"""
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_FILE)


# --------------------------------------------------------------------------
# 篇目扫描与命名
# --------------------------------------------------------------------------
@dataclass
class Doc:
    doc_id: str
    path: Path
    out_dir: Path
    batch_id: str = ""
    state: str = "new"
    err_msg: str = ""
    total_pages: int = 0
    extracted_pages: int = 0
    zip_url: str = ""
    uploaded_at: float = 0.0
    round: int = 0
    out_dir_name: str = ""
    pdf_bytes: int = 0          # 扫描时记下，源 PDF 移走后报告里仍要有原始大小
    moved_to: str = ""          # 实际移动到的位置（未移动为空）

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def stem(self) -> str:
        return self.path.stem


def safe_dirname(stem: str) -> str:
    """PDF 文件名 → 安全的子目录名。

    实测 17 个文件名最长 126 字节（macOS 单段上限 255），不会触发截断；
    截断逻辑只作为将来新增文件时的护栏。
    """
    s = re.sub(r'[/\\:\x00]', "_", stem)
    s = s.rstrip(". ")          # 处理 "...出行特性分析..pdf" 这类结尾点
    s = s.strip()
    if not s:
        s = "untitled"
    while len(s.encode("utf-8")) > 200:
        s = s[:-1]
    return s


def scan_pdfs() -> list:
    if not IN_DIR.is_dir():
        sys.exit("输入目录不存在：%s" % IN_DIR)
    return sorted(p for p in IN_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")


def build_docs(pdfs: list, state: dict) -> list:
    """给每篇分配稳定的 doc_id，并复用状态文件里已有的分配。"""
    known = {rec.get("name"): did for did, rec in state["files"].items() if rec.get("name")}
    used_ids = set(known.values())
    next_seq = 1
    docs = []
    used_dirs = {}
    for p in pdfs:
        did = known.get(p.name)
        if did is None:
            while "doc%02d" % next_seq in used_ids:
                next_seq += 1
            did = "doc%02d" % next_seq
            used_ids.add(did)
        dname = safe_dirname(p.stem)
        # 清洗后重名兜底（17 篇不会发生，纯防御）
        if dname in used_dirs:
            used_dirs[dname] += 1
            dname = "%s_%d" % (dname, used_dirs[dname])
        else:
            used_dirs[dname] = 1
        rec = state["files"].setdefault(did, {})
        rec["name"] = p.name
        docs.append(Doc(
            doc_id=did, path=p, out_dir=OUT_DIR / dname, out_dir_name=dname,
            pdf_bytes=p.stat().st_size,
            batch_id=rec.get("batch_id", ""),
            state=rec.get("state", "new"),
            err_msg=rec.get("err_msg", ""),
            total_pages=rec.get("total_pages", 0) or 0,
            extracted_pages=rec.get("extracted_pages", 0) or 0,
            round=rec.get("round", 0) or 0,
        ))
    return docs


def persist(doc: Doc, state: dict):
    rec = state["files"].setdefault(doc.doc_id, {})
    rec.update({
        "name": doc.name, "out_dir": doc.out_dir_name, "batch_id": doc.batch_id,
        "state": doc.state, "err_msg": doc.err_msg,
        "total_pages": doc.total_pages, "extracted_pages": doc.extracted_pages,
        "round": doc.round,
    })  # zip_url 刻意不落盘：预签名链接会过期，需要时重新轮询即可拿到


def is_done_on_disk(doc: Doc) -> bool:
    md = doc.out_dir / "full.md"
    return md.is_file() and md.stat().st_size > 0


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
def api_call(sess, method, path, token, *, queue_retry=0, **kw):
    """统一分派 code。所有错误都原样打出 code/msg/trace_id，不吞。"""
    last = None
    for attempt in range(queue_retry + 1):
        try:
            r = sess.request(method, BASE + path,
                             headers={"Authorization": "Bearer %s" % token}, **kw)
        except requests.RequestException as e:
            last = "%s: %s" % (type(e).__name__, e)
            log("  请求异常（第 %d 次）：%s" % (attempt + 1, last))
            if attempt < queue_retry:
                time.sleep(10 * (attempt + 1))
                continue
            raise MineruError("network", last)
        if r.status_code != 200:
            raise MineruError("http-%d" % r.status_code, r.text[:200])

        j = r.json()
        code = j.get("code")
        if code == 0:
            return j.get("data") or {}
        msg = j.get("msg") or ""
        log("  MinerU 错误 code=%s msg=%s trace_id=%s" % (code, msg, j.get("trace_id")))
        if code in ("A0202", "A0211"):
            sys.exit("Token 无效或已过期（code=%s）：检查 scripts/.env 的 MINERU_API_KEY 与 Bearer 前缀" % code)
        if code == "-60018":
            sys.exit("今日解析额度（1000 页）已用尽，请明日再跑；state 已保存，可直接重跑续上")
        if code == "-60009" and attempt < queue_retry:
            wait = 30 * (attempt + 1)
            log("  提交队列已满，%d 秒后重试" % wait)
            time.sleep(wait)
            continue
        raise MineruError(code, msg)
    raise MineruError("retry-exhausted", last or "")


def upload_one(sess, url: str, pdf: Path, retries: int = 3):
    """PUT 到预签名链接。刻意不带 Authorization（会破坏签名）与 Content-Type（文档要求）。"""
    last = ""
    for i in range(1, retries + 1):
        try:
            with open(pdf, "rb") as fh:
                r = sess.put(url, data=fh, timeout=600)
            if r.status_code in (200, 201, 204):
                return True, ""
            last = "HTTP %d %s" % (r.status_code, r.text[:120])
        except requests.RequestException as e:
            last = ("%s: %s" % (type(e).__name__, e))[:160]
        if i < retries:
            time.sleep(3 * i)
    return False, last


def submit_and_upload(sess, token, docs: list, args, state: dict, round_no: int):
    """一轮提交：申请链接 → 逐篇上传。返回 batch_id。"""
    body = {
        "files": [{"name": d.name, "data_id": d.doc_id} for d in docs],
        "model_version": args.model,
        "language": args.lang,
        "enable_formula": True,
        "enable_table": True,
    }
    log("申请上传链接：%d 篇" % len(docs))
    data = api_call(sess, "POST", API_SUBMIT, token, queue_retry=3, json=body)
    batch_id = data.get("batch_id") or ""
    urls = data.get("file_urls") or []
    if not batch_id or len(urls) != len(docs):
        raise MineruError(0, "batch_id=%r 与 file_urls 数量 %d 不匹配（预期 %d）"
                          % (batch_id, len(urls), len(docs)))
    log("batch_id = %s" % batch_id)

    now = time.time()
    for d, u in zip(docs, urls):
        d.batch_id, d.round = batch_id, round_no
        ok, msg = upload_one(sess, u, d.path)
        if ok:
            d.state, d.err_msg, d.uploaded_at = "waiting-file", "", now
            log("  ✓ 已上传 %s  %s" % (d.doc_id, d.name[:46]))
        else:
            d.state, d.err_msg = "upload_failed", msg
            log("  × 上传失败 %s  %s -> %s" % (d.doc_id, d.name[:46], msg))
        persist(d, state)
        save_state(state)
    state.setdefault("batches", {})[batch_id] = {
        "round": round_no, "created_at": now, "doc_ids": [d.doc_id for d in docs],
    }
    save_state(state)
    return batch_id


def poll_batch(sess, token, batch_id: str, docs: list, state: dict, args, started: float):
    deadline = started + args.timeout
    interval = args.poll_interval
    shown = {}
    while True:
        data = api_call(sess, "GET", API_RESULT % batch_id, token)
        results = {it.get("data_id"): it for it in (data.get("extract_result") or [])}

        pending = failed = 0
        pages_done = pages_total = 0
        for d in docs:
            it = results.get(d.doc_id)
            if it is None:
                if d.uploaded_at and time.time() - d.uploaded_at > UPLOAD_VANISH_SEC:
                    d.state = "upload_failed"
                    d.err_msg = d.err_msg or "上传后 %d 秒仍未出现在任务列表" % UPLOAD_VANISH_SEC
                pending += 1
                continue
            d.state = it.get("state") or ""
            d.err_msg = it.get("err_msg") or ""
            prog = it.get("extract_progress") or {}
            d.total_pages = prog.get("total_pages") or d.total_pages
            # done 时服务端不再返回 extract_progress，此时不能用 0 覆盖已有进度
            d.extracted_pages = prog.get("extracted_pages") or d.extracted_pages
            if d.state == "done":
                d.zip_url = it.get("full_zip_url") or ""
                d.extracted_pages = d.total_pages or d.extracted_pages
            elif d.state not in TERMINAL:
                pending += 1
            if d.state == "failed":
                failed += 1
            pages_done += d.extracted_pages
            pages_total += d.total_pages or 0
            line = "%s %s/%s" % (d.state, d.extracted_pages, d.total_pages)
            if shown.get(d.doc_id) != line:
                shown[d.doc_id] = line
                if d.state == "failed":
                    log("  × %s 解析失败：%s" % (d.doc_id, d.err_msg))
                else:
                    log("  · %s  %s" % (d.doc_id, line))
            persist(d, state)
        save_state(state)

        if pending == 0:
            return
        log("轮询 完成 %d/%d ｜ 进行中 %d ｜ 失败 %d ｜ 页 %d/%d ｜ 已用 %s"
            % (sum(1 for d in docs if d.state == "done"), len(docs),
               pending - failed, failed, pages_done, pages_total, hms(time.time() - started)))
        if time.time() > deadline:
            log("轮询超时，仍有 %d 篇未完成。状态已保存 —— 直接重跑本脚本即可续查（不会重传）" % pending)
            return
        time.sleep(interval)
        interval = min(60, interval + 5)


# --------------------------------------------------------------------------
# 下载与解压
# --------------------------------------------------------------------------
def extract_zip_to(zip_bytes: bytes, out_dir: Path):
    """整包安全解压到 out_dir：先落 .part，校验通过后原子换入。"""
    out_dir = out_dir.resolve()
    tmp = out_dir.parent / (out_dir.name + ".part")
    if tmp.exists():
        shutil.rmtree(tmp)          # 清理上次中断的残留
    tmp.mkdir(parents=True)

    total = 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        if zf.testzip() is not None:
            raise ValueError("zip 内容损坏（CRC 校验失败）")
        for info in zf.infolist():
            if info.is_dir() or info.filename.startswith("__MACOSX/"):
                continue
            p = PurePosixPath(info.filename)
            if p.is_absolute() or ".." in p.parts or "\\" in info.filename:
                raise ValueError("zip 内可疑路径，已中止：%s" % info.filename)
            target = (tmp / p).resolve()
            # 前缀必须带 os.sep，否则 /out 会误匹配 /out2
            if not str(target).startswith(str(tmp) + os.sep):
                raise ValueError("检测到路径穿越（zip slip）：%s" % info.filename)
            total += info.file_size
            if total > MAX_UNZIP_BYTES:
                raise ValueError("解压总体积异常，已中止")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)

    md = tmp / "full.md"
    if not md.is_file() or md.stat().st_size == 0:
        raise ValueError("zip 内没有非空 full.md")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    os.replace(tmp, out_dir)        # 同父目录，原子换入


def prune_extracted(out_dir: Path) -> int:
    """删掉 zip 附带的大块调试产物，只留 full.md / images/ / *_content_list.json。

    *  *_origin.pdf          源 PDF 的副本 —— 仓库里本来就有原文件，纯冗余
    *  layout.json           版面中间结果，1.8 MB 量级
    *  *_model.json          模型推理结果
    *  *_content_list_v2.json 与 content_list.json 重复的旧版

    幂等：对已完成目录重复调用无副作用。返回释放的字节数。
    """
    freed = 0
    for p in sorted(out_dir.iterdir()):
        if p.name in ("full.md", "images"):
            continue
        if p.is_file() and p.name.endswith("_content_list.json"):
            continue
        if p.is_dir():
            freed += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            shutil.rmtree(p)
        else:
            freed += p.stat().st_size
            p.unlink()
    return freed


def pages_from_content_list(out_dir: Path) -> int:
    """从 MinerU 自带的 *_content_list.json 推页数（各条目带 page_idx）。

    为什么需要：某篇若在首次轮询时就已 done，服务端不再返回 extract_progress，
    页数就拿不到；而报告里要拿它核对，content_list 是可靠的兜底来源。
    """
    for p in out_dir.glob("*_content_list.json"):
        try:
            items = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(items, list):
            continue
        idx = [it["page_idx"] for it in items
               if isinstance(it, dict) and isinstance(it.get("page_idx"), int)]
        if idx:
            return max(idx) + 1
    return 0


def fetch_and_extract(sess, doc: Doc, state: dict):
    log("  下载结果包 %s ..." % doc.doc_id)
    r = sess.get(doc.zip_url, timeout=600)
    r.raise_for_status()
    log("  解压 %s（%.1f MB）" % (doc.doc_id, len(r.content) / 1048576))
    extract_zip_to(r.content, doc.out_dir)
    freed = prune_extracted(doc.out_dir)
    if freed:
        log("  精简 %s：删除 %.1f MB 调试产物" % (doc.doc_id, freed / 1048576))
    if not doc.total_pages:
        doc.total_pages = pages_from_content_list(doc.out_dir)


# --------------------------------------------------------------------------
# 校验与清单
# --------------------------------------------------------------------------
def verify_doc(doc: Doc) -> dict:
    md = doc.out_dir / "full.md"
    if not md.is_file() or md.stat().st_size == 0:
        return {"ok": False, "reason": "无 full.md 或为空"}
    text = md.read_text(encoding="utf-8", errors="replace")
    imgs = [u for u in IMG_RE.findall(text)
            if not u.startswith(("http://", "https://", "data:"))]
    missing = [u for u in imgs if not (doc.out_dir / unquote(u)).exists()]
    on_disk = len(list((doc.out_dir / "images").glob("*"))) if (doc.out_dir / "images").is_dir() else 0
    headings = len(re.findall(r"^#{1,6}\s", text, re.M))
    bad_html = any(k in text[:400].lower() for k in ("<html", "access denied", "<!doctype"))
    ok = (not missing) and headings > 0 and not bad_html
    reason = ""
    if missing:
        reason = "%d 处图片断链" % len(missing)
    elif headings == 0:
        reason = "无 Markdown 标题"
    elif bad_html:
        reason = "疑似错误页而非正文"
    return {
        "ok": ok, "reason": reason,
        "md_bytes": md.stat().st_size, "md_lines": text.count("\n") + 1,
        "headings": headings, "images_referenced": len(imgs),
        "images_missing": len(missing), "images_on_disk": on_disk,
    }


def write_reports(docs: list, elapsed: float, args):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items, n_ok, pages = [], 0, 0
    for i, d in enumerate(docs, 1):
        v = verify_doc(d)
        n_ok += 1 if v.get("ok") else 0
        if not d.total_pages:       # 兜底：从 content_list.json 补页数
            d.total_pages = pages_from_content_list(d.out_dir)
        pages += d.total_pages or 0
        items.append({
            "index": i, "data_id": d.doc_id, "pdf_name": d.name,
            "pdf_bytes": d.pdf_bytes, "moved_to": d.moved_to,
            "batch_id": d.batch_id, "state": d.state, "err_msg": d.err_msg,
            "total_pages": d.total_pages, "extracted_pages": d.extracted_pages,
            "out_dir": d.out_dir_name, "round": d.round,
            "full_md_bytes": v.get("md_bytes", 0), "headings": v.get("headings", 0),
            "images_referenced": v.get("images_referenced", 0),
            "images_missing": v.get("images_missing", 0),
            "images_on_disk": v.get("images_on_disk", 0),
            "ok": bool(v.get("ok")), "reason": v.get("reason", ""),
        })

    manifest = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model_version": args.model, "language": args.lang,
        "input_dir": rel_to(IN_DIR), "output_dir": rel_to(OUT_DIR),
        "move_dir": rel_to(args.move_to) if args.move_to else "",
        "summary": {
            "total": len(docs), "ok": n_ok, "failed": len(docs) - n_ok,
            "pages_total": pages,
            "images_missing": sum(i["images_missing"] for i in items),
            "elapsed_sec": int(elapsed),
        },
        "items": items,
    }
    (OUT_DIR / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    bad = [i for i in items if not i["ok"]]
    lines = [
        "# MinerU 解析报告", "",
        "- 生成时间：%s" % manifest["generated_at"],
        "- 输入：`%s`（%d 篇）" % (manifest["input_dir"], len(items)),
        "- 输出：`%s`" % manifest["output_dir"],
        "- 模型：`%s` / language `%s`" % (args.model, args.lang),
    ]
    if elapsed >= 5:        # --verify-only 是零网络复算，耗时无意义，不显示
        lines.append("- 转换耗时：%s" % hms(elapsed))
    lines += [
        "- **结果：%d/%d 篇通过校验；总页数 %d；图片断链 %d 处**"
        % (n_ok, len(items), pages, manifest["summary"]["images_missing"]),
        "",
        "| # | 文献 | 页 | full.md | 图（缺/引用） | 状态 |",
        "|---|---|---|---|---|---|",
    ]
    for i in items:
        status = "✅" if i["ok"] else "❌ %s" % (i["reason"] or i["err_msg"] or i["state"])
        label = i["pdf_name"]
        if label.lower().endswith(".pdf"):
            label = label[:-4]
        link = "[%s](%s/full.md)" % (
            label[:52] + ("…" if len(label) > 52 else ""),
            i["out_dir"].replace(" ", "%20"))
        md_size = "%.0f KB" % (i["full_md_bytes"] / 1024) if i["full_md_bytes"] else "—"
        imgs = "%d/%d" % (i["images_missing"], i["images_referenced"])
        lines.append("| %d | %s | %s | %s | %s | %s |"
                     % (i["index"], link, i["total_pages"] or "—", md_size, imgs, status))
    lines.append("")
    if bad:
        lines += ["## 需人工处理", ""]
        for i in bad:
            lines.append("- **%s**：state=`%s`，%s" % (i["pdf_name"], i["state"],
                                                  i["err_msg"] or i["reason"] or "未完成"))
        lines.append("")
    moved = [i for i in items if i.get("moved_to")]
    if moved:
        lines += ["", "> 源 PDF 已移动 %d 篇至 `%s`（未通过校验的仍留在输入目录）。"
                  % (len(moved), rel_to(args.move_to) if args.move_to else ""), ""]
    lines += ["> 图片体积大，入库前建议把 `images/` 排除；`full.md` 与清单文件才是入库产物。",
              ""]
    (OUT_DIR / "_转换报告.md").write_text("\n".join(lines), encoding="utf-8")

    log("已写出 %s 与 %s" % (rel_to(OUT_DIR / "_转换报告.md"),
                          rel_to(OUT_DIR / "_manifest.json")))
    return n_ok, len(items)


def move_done_pdfs(docs: list, target_dir: Path) -> list:
    """把「校验通过」的篇目源 PDF 移到 target_dir，返回实际移动的篇目。

    失败的、超时未完成的、以及 full.md 为空/断图的篇目一律留在原处 —— 便于重跑重试，
    也避免把没转成功的文件误当作已处理。目标重名时加 _1/_2 后缀，不覆盖。
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    moved = []
    for d in docs:
        if not d.path.is_file():
            continue
        v = verify_doc(d)
        if not v.get("ok"):
            log("  保留 %s（%s），不移入 %s" % (d.name[:46], v.get("reason") or "未完成",
                                           rel_to(target_dir)))
            continue
        dest = target_dir / d.name
        n = 1
        while dest.exists():
            dest = target_dir / ("%s_%d%s" % (d.path.stem, n, d.path.suffix))
            n += 1
        shutil.move(str(d.path), str(dest))
        d.moved_to = str(dest)
        moved.append(d)
        log("  已移动 %s → %s" % (d.name[:46], rel_to(dest)))
    return moved


def finish(docs: list, started: float, args) -> int:
    """收尾：按需移动源 PDF，再出报告（报告据此记录 moved_to）。"""
    if args.move_to:
        moved = move_done_pdfs(docs, args.move_to)
        log("移动完成：%d 篇 → %s" % (len(moved), rel_to(args.move_to)))
    n_ok, n = write_reports(docs, time.time() - started, args)
    log("完成：%d/%d 篇通过校验，用时 %s" % (n_ok, n, hms(time.time() - started)))
    return 0 if n_ok == n else 1


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def main():
    global IN_DIR, OUT_DIR
    ap = argparse.ArgumentParser(description="用 MinerU 精准解析 API 把文献 PDF 批量转 Markdown")
    ap.add_argument("--input", type=Path, default=IN_DIR, help="输入 PDF 目录")
    ap.add_argument("--output", type=Path, default=OUT_DIR, help="输出根目录")
    ap.add_argument("--only", action="append", default=[], metavar="子串",
                    help="只处理文件名含该子串的篇目，可重复")
    ap.add_argument("--force", action="store_true", help="忽略已完成，全部重新提交（重新消耗额度）")
    ap.add_argument("--move-to", type=Path, default=None, metavar="目录",
                    help="转换并校验通过后，把源 PDF 移入该目录（失败篇留在原处）；"
                         "仓库内约定为 paper/converted")
    ap.add_argument("--verify-only", action="store_true", help="零网络：只按磁盘现状重算清单并校验")
    ap.add_argument("--dry-run", action="store_true", help="零网络：只打印将处理的篇目")
    ap.add_argument("--retry-failed", type=int, default=1, metavar="N",
                    help="失败篇目自动补跑轮数，0 表示不补跑")
    ap.add_argument("--batch-size", type=int, default=50, help="单次申请链接数（接口上限 50）")
    ap.add_argument("--poll-interval", type=int, default=20, help="起始轮询间隔秒")
    ap.add_argument("--timeout", type=int, default=3600, help="轮询总超时秒")
    ap.add_argument("--model", default="vlm", choices=["pipeline", "vlm"], help="模型版本")
    ap.add_argument("--lang", default="ch", help="文档语言")
    ap.add_argument("--env", type=Path, default=ROOT / ".env", help="密钥文件（默认仓库根 .env）")
    args = ap.parse_args()

    IN_DIR, OUT_DIR = args.input, args.output
    started = time.time()

    env_ok = load_env(args.env)
    pdfs = scan_pdfs()
    if args.only:
        pats = [s.lower() for s in args.only]
        pdfs = [p for p in pdfs if any(s in p.name.lower() for s in pats)]
    if not pdfs:
        # 不是错误：首次跑前的空目录、以及「已全部转换并移走」后的重跑都走这里
        log("输入目录没有 PDF，无需转换：%s" % rel_to(IN_DIR))
        return 0

    state = load_state()
    docs = build_docs(pdfs, state)
    todo = [d for d in docs if args.force or not is_done_on_disk(d)]

    if args.dry_run:
        log("输入目录：%s" % IN_DIR)
        log("输出目录：%s" % OUT_DIR)
        log("共 %d 篇，其中待处理 %d 篇：" % (len(docs), len(todo)))
        for d in docs:
            mark = "待处理" if d in todo else "已完成"
            log("  %s  %-6s %s\n         → %s/" % (d.doc_id, mark, d.name[:64], d.out_dir_name))
        return 0

    if args.verify_only:
        n_ok, n = write_reports(docs, time.time() - started, args)
        log("校验完成：%d/%d 篇通过" % (n_ok, n))
        return 0 if n_ok == n else 1

    token = os.environ.get("MINERU_API_KEY", "").strip()
    if not token:
        sys.exit("缺少 MINERU_API_KEY。请在 %s 中设置（或 export 后重试）" % args.env)
    if not env_ok:
        log("提示：%s 不存在，改用环境变量中的 MINERU_API_KEY" % args.env)

    if not todo:
        log("全部 %d 篇均已完成，无需请求 API。用 --force 可强制重做。" % len(docs))
        return finish(docs, started, args)

    if args.force:
        log("--force：将重新提交 %d 篇，预计消耗今日解析额度。日额度 1000 页，全量约 242 页。"
            % len(todo))
        if sys.stdin.isatty():
            if input("确认继续？输入 yes 回车：").strip().lower() != "yes":
                log("已取消。")
                return 1
        else:
            log("（非交互环境，直接继续）")

    log("待处理 %d 篇 / 共 %d 篇" % (len(todo), len(docs)))

    # 对上次已解压的目录补一次精简（幂等），这样调整保留策略后不必重新下载
    for d in docs:
        if is_done_on_disk(d):
            freed = prune_extracted(d.out_dir)
            if freed:
                log("精简 %s：删除 %.1f MB 调试产物" % (d.doc_id, freed / 1048576))

    sess = requests.Session()
    sess.headers.update({"Accept": "*/*"})

    # ---- 续轮询：同一批次若还在有效期内，不重传 ----
    live = {}
    for d in todo:
        if d.batch_id and d.state not in ("done", "failed", "upload_failed"):
            created = (state.get("batches", {}).get(d.batch_id, {}) or {}).get("created_at", 0)
            if created and time.time() - created < BATCH_MAX_AGE:
                live.setdefault(d.batch_id, []).append(d)
    for bid, group in live.items():
        log("续轮询已有批次 %s（%d 篇）" % (bid, len(group)))
        poll_batch(sess, token, bid, group, state, args, started)
        for d in group:
            if d.state == "done":
                try:
                    fetch_and_extract(sess, d, state)
                except Exception as e:
                    d.state, d.err_msg = "failed", "解压失败：%s" % e
                    log("  × %s %s" % (d.doc_id, d.err_msg))
                persist(d, state)
                save_state(state)

    # ---- 正常提交 ----
    remaining = [d for d in todo if d.state != "done"]
    round_no = 1
    while remaining and round_no <= max(1, args.retry_failed + 1):
        if round_no > 1:
            log("第 %d 轮补跑：%d 篇" % (round_no, len(remaining)))
        for i in range(0, len(remaining), args.batch_size):
            chunk = remaining[i:i + args.batch_size]
            bid = submit_and_upload(sess, token, chunk, args, state, round_no)
            poll_batch(sess, token, bid, chunk, state, args, time.time())
            for d in chunk:
                if d.state == "done":
                    try:
                        fetch_and_extract(sess, d, state)
                    except Exception as e:
                        d.state, d.err_msg = "failed", "解压失败：%s" % e
                        log("  × %s %s" % (d.doc_id, d.err_msg))
                    persist(d, state)
                    save_state(state)
            remaining = [d for d in remaining if d.state != "done"]
        round_no += 1
        if remaining and round_no > args.retry_failed + 1:
            break

    return finish(docs, started, args)


if __name__ == "__main__":
    sys.exit(main())
