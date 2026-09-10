#!/usr/bin/env python3
"""读取 pgnexus.ai 的「PostgreSQL 每日更新」，输出博览候选。

    tools/info/fetch_pgnexus.py 264
    tools/info/fetch_pgnexus.py auto --date 2026-09-10
    tools/info/fetch_pgnexus.py 264 --source cdp --out /tmp/pgnexus-264.json

两条取数路径：

1. `api`（默认先试）：`https://pgnexus.ai/api/daily-updates/content?jobid=N&language=zh`
   返回一份带链接的 Markdown，是最稳的来源。
2. `cdp`：`https://pgnexus.ai/daily-updates?jobid=N` 是客户端渲染的 Next.js 页面，
   用 headless Chrome 通过 CDP 打开、等 6 秒、读 `document.body.innerText`，
   同时收集 `a` 标签的 href 与标题做匹配。做法与 scratchpad/shot.py 相同，
   调试端口 9343，临时 profile 用完即删。

只用标准库；CDP 路径额外需要 websocket-client（在 scratchpad 的 pylib 目录里）。
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

BASE = "https://pgnexus.ai"
LIST_API = BASE + "/api/daily-updates/list"
CONTENT_API = BASE + "/api/daily-updates/content"
PAGE_URL = BASE + "/daily-updates?jobid=%s"

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CDP_PORT = 9343
CDP_WAIT = 6.0

# websocket-client 不一定装在系统 python 里，按顺序找几处
PYLIB_CANDIDATES = [
    os.environ.get("PGWEB_PYLIB"),
    "/private/tmp/claude-501/-Users-vonng-pgsty-pgweb/"
    "956b4be5-c7ee-4a44-9a74-0ad05447c8e3/scratchpad/pylib",
]

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 pgweb-info/1.0"

HEAD_RE = re.compile(
    r"^#\s+.*?(?:每日更新|Daily News|Daily Update)\s*#?\s*(\d+)\s+(\d{4}-\d{2}-\d{2})",
    re.M,
)
MD_LINK_RE = re.compile(r"\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\(\s*(\S+?)\s*\)")
ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!~|<>])")

AUTHOR_LABELS = ("参与者", "Participants", "参与人", "作者", "Author")


def _unescape(text):
    return ESCAPE_RE.sub(r"\1", text)


def _clean(text):
    text = MD_LINK_RE.sub(lambda m: m.group(1), text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=re.S)
    text = text.replace("**", "").replace("`", "")
    text = _unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


# --------------------------------------------------------------------------
# 任务列表
# --------------------------------------------------------------------------


def list_jobs(timeout=30):
    data = json.loads(_get(LIST_API, timeout=timeout))
    return data.get("entries", [])


def resolve_jobid(date, timeout=30):
    """按日期找任务号：先找当天，没有就找前一天（日报当天多半引用昨天的刊）。"""
    entries = list_jobs(timeout=timeout)
    by_date = {e.get("date"): e.get("jobid") for e in entries if e.get("jobid") is not None}
    if date in by_date:
        return by_date[date], date
    import datetime as dt

    try:
        prev = (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()
    except ValueError:
        prev = None
    if prev and prev in by_date:
        return by_date[prev], prev
    if entries:
        top = entries[0]
        return top.get("jobid"), top.get("date")
    return None, None


# --------------------------------------------------------------------------
# 取数：内容 API
# --------------------------------------------------------------------------


def fetch_markdown(jobid, lang="zh", timeout=30):
    url = "%s?jobid=%s&language=%s" % (CONTENT_API, jobid, lang)
    data = json.loads(_get(url, timeout=timeout))
    content = data.get("content") or ""
    if not content.strip():
        raise RuntimeError("内容 API 返回空 content（jobid=%s）" % jobid)
    return content, data.get("title") or ""


# --------------------------------------------------------------------------
# 取数：headless Chrome + CDP
# --------------------------------------------------------------------------


def _import_websocket():
    for path in PYLIB_CANDIDATES:
        if path and os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)
    import websocket  # noqa: PLC0415

    return websocket


def fetch_rendered(jobid, wait=CDP_WAIT, port=CDP_PORT, chrome=CHROME):
    """返回 (innerText, anchors)；anchors 是 [[文字, href], ...]。"""
    websocket = _import_websocket()
    if not os.path.exists(chrome):
        raise RuntimeError("找不到 Chrome：%s" % chrome)
    url = PAGE_URL % jobid
    prof = tempfile.mkdtemp(prefix="chrome-pgnexus-")
    proc = subprocess.Popen(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--remote-debugging-port=%d" % port,
            "--user-data-dir=%s" % prof,
            "--window-size=1400,2400",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        tab = None
        for _ in range(60):
            try:
                tabs = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % port))
                pages = [t for t in tabs if t.get("type") == "page"]
                if pages:
                    tab = pages[0]
                    break
            except Exception:  # noqa: BLE001 - Chrome 还没起来
                time.sleep(0.25)
        if tab is None:
            raise RuntimeError("Chrome 调试端口 %d 未就绪" % port)
        ws = websocket.create_connection(tab["webSocketDebuggerUrl"], suppress_origin=True)
        mid = [0]

        def send(method, **params):
            mid[0] += 1
            ws.send(json.dumps({"id": mid[0], "method": method, "params": params}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == mid[0]:
                    return msg.get("result", {})

        send("Page.enable")
        send("Page.navigate", url=url)
        time.sleep(wait)
        text = (
            send("Runtime.evaluate", expression="document.body.innerText", returnByValue=True)
            .get("result", {})
            .get("value", "")
            or ""
        )
        raw = (
            send(
                "Runtime.evaluate",
                expression=(
                    "JSON.stringify([...document.querySelectorAll('a')]"
                    ".map(a=>[a.textContent.trim(), a.href]))"
                ),
                returnByValue=True,
            )
            .get("result", {})
            .get("value", "")
            or "[]"
        )
        try:
            anchors = json.loads(raw)
        except ValueError:
            anchors = []
        return text, anchors
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()
        import shutil

        shutil.rmtree(prof, ignore_errors=True)


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------


def _candidate(group, title, url=""):
    return {
        "section": "pgnexus",
        "group": group,
        "tag": "",
        "importance": "",
        "title": title,
        "text": "",
        "links": ([{"label": title, "url": url}] if url else []),
        "primary_url": url,
        "publisher": "",
        "author": "",
        "date": "",
        "hn": None,
        "tags": [],
        "participants": [],
        "also_in": [],
    }


URL_DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-/](\d{2})[-/](\d{2})(?!\d)")


def _finish(cand, page_date=""):
    cand["text"] = cand["text"].strip()
    if not cand["title"]:
        # 源里偶尔出现 `[](url)` 这样的空标题，用正文首句兜底
        first = re.split(r"[。；;！!？?\n]", cand["text"])[0].strip()
        cand["title"] = first[:60] or cand["primary_url"].rsplit("/", 1)[-1]
    if cand["primary_url"]:
        m = re.match(r"^https?://([^/]+)", cand["primary_url"])
        if m:
            cand["publisher"] = re.sub(r"^www\.", "", m.group(1))
        dm = URL_DATE_RE.search(cand["primary_url"])
        if dm:
            cand["date"] = "-".join(dm.groups())
    if not cand["date"] and page_date:
        cand["date"] = page_date
    return cand


def _absorb_people(cand, rest):
    people = [p.strip() for p in re.split(r"[,，;；]", rest) if p.strip()]
    if "@" in rest:
        cand["participants"] = people
    elif rest:
        cand["author"] = rest


def parse_markdown(content):
    """解析内容 API 的 Markdown。返回 (page_meta, candidates)。"""
    jobid = date = ""
    m = HEAD_RE.search(content)
    if m:
        jobid, date = m.group(1), m.group(2)

    group = ""
    cands = []
    cur = None
    pending_people = False
    for line in content.splitlines():
        s = line.strip()
        if not s:
            continue
        if pending_people:
            pending_people = False
            if cur is not None:
                _absorb_people(cur, _clean(s))
                continue
        h2 = re.match(r"^##\s+(?!#)(.*)$", s)
        h3 = re.match(r"^###\s+(.*)$", s)
        if s.startswith("# ") and not h2 and not h3:
            continue
        if h3:
            body = h3.group(1).strip()
            link = MD_LINK_RE.search(body)
            title = _clean(link.group(1)) if link else _clean(body)
            url = link.group(2) if link else ""
            if not url.lower().startswith(("http://", "https://")):
                url = ""
            cur = _candidate(group, title, url)
            cands.append(cur)
            continue
        if h2:
            group = _clean(h2.group(1))
            cur = None
            continue
        if cur is None:
            continue
        plain = _clean(s)
        if not plain:
            continue
        label = next((l for l in AUTHOR_LABELS if plain.startswith(l)), None)
        if label:
            rest = plain[len(label):].lstrip(" :：")
            if rest:
                _absorb_people(cur, rest)
            else:
                pending_people = True  # 「参与者：」独占一行，名单在下一行
            continue
        if s.startswith("`") and s.endswith("`") and len(plain) <= 60 and not cur["author"]:
            cur["author"] = plain
            continue
        if cur["text"] and len(plain) <= 60 and not cur["author"] and "。" not in plain:
            cur["author"] = plain
            continue
        cur["text"] += ("\n" if cur["text"] else "") + plain

    return {"jobid": jobid, "date": date}, [_finish(c, date) for c in cands]


FOOTER_MARKERS = ("© ", "版权所有", "隐私政策", "Privacy Policy")
FOOTER_EXACT = ("PGNexus", "探索", "Explore")


def parse_rendered(text, anchors):
    """解析 innerText + anchors。返回 (page_meta, candidates)。"""
    lines = text.splitlines()
    jobid = date = ""
    start = 0
    head = re.compile(r"(?:每日更新|Daily News|Daily Update)\s*#?\s*(\d+)\s+(\d{4}-\d{2}-\d{2})")
    for i, line in enumerate(lines):
        m = head.search(line.strip())
        if m:
            jobid, date = m.group(1), m.group(2)
            start = i + 1
            break

    end = len(lines)
    for i in range(start, len(lines)):
        if any(mark in lines[i] for mark in FOOTER_MARKERS):
            end = i
            break

    by_title = {}
    for item in anchors or []:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        label, href = (item[0] or "").strip(), (item[1] or "").strip()
        if not label or not href.lower().startswith(("http://", "https://")):
            continue
        if "pgnexus.ai" in href:
            continue
        by_title.setdefault(label, href)

    group = ""
    cands = []
    cur = None
    i = start
    while i < end:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if s in FOOTER_EXACT or any(mark in s for mark in FOOTER_MARKERS):
            break
        nxt = lines[i + 1].strip() if i + 1 < end else ""
        if s in by_title:
            cur = _candidate(group, s, by_title[s])
            cands.append(cur)
            i += 1
            continue
        if nxt and len(s) <= 40:
            # 条目的标题、正文、作者行后面都跟着空行；紧跟非空行的短行是小标题
            group = s
            cur = None
            i += 1
            continue
        if cur is None:
            i += 1
            continue
        label = next((l for l in AUTHOR_LABELS if s.startswith(l)), None)
        if label:
            rest = s[len(label):].lstrip(" :：")
            if not rest and i + 1 < end:
                rest = lines[i + 1].strip()
                i += 1
            _absorb_people(cur, rest)
            i += 1
            continue
        if cur["text"] and len(s) <= 60 and not cur["author"]:
            cur["author"] = s
            i += 1
            continue
        cur["text"] += ("\n" if cur["text"] else "") + s
        i += 1

    return {"jobid": jobid, "date": date}, [_finish(c, date) for c in cands]


# --------------------------------------------------------------------------
# 对外入口
# --------------------------------------------------------------------------


def fetch(jobid, date=None, lang="zh", source="auto", quiet=False):
    """返回 (meta, candidates)。jobid 传 'auto' 时按 date 查表。"""
    resolved_from = ""
    if str(jobid).lower() in ("auto", "", "none"):
        if not date:
            raise RuntimeError("--pgnexus auto 需要日期")
        jobid, resolved_from = resolve_jobid(date)
        if jobid is None:
            raise RuntimeError("列表 API 里找不到 %s 附近的任务" % date)

    meta = {
        "jobid": str(jobid),
        "url": PAGE_URL % jobid,
        "lang": lang,
        "source": "",
    }
    if resolved_from:
        meta["resolved_from_date"] = resolved_from

    page_meta = {}
    cands = []
    errors = []

    if source in ("auto", "api"):
        try:
            content, title = fetch_markdown(jobid, lang=lang)
            page_meta, cands = parse_markdown(content)
            meta["source"] = "api"
            meta["file"] = title
        except Exception as exc:  # noqa: BLE001
            errors.append("api: %s" % exc)
            if source == "api":
                raise

    if not cands and source in ("auto", "cdp"):
        try:
            text, anchors = fetch_rendered(jobid)
            page_meta, cands = parse_rendered(text, anchors)
            meta["source"] = "cdp"
        except Exception as exc:  # noqa: BLE001
            errors.append("cdp: %s" % exc)
            if not cands:
                raise RuntimeError("; ".join(errors))

    meta["page_date"] = page_meta.get("date", "")
    if page_meta.get("jobid"):
        meta["page_jobid"] = page_meta["jobid"]
    groups = {}
    for cand in cands:
        groups[cand["group"]] = groups.get(cand["group"], 0) + 1
    meta["groups"] = groups
    meta["count"] = len(cands)
    if errors:
        meta["warnings"] = errors

    if date and meta["page_date"] and meta["page_date"] != date:
        note = "pgnexus #%s 的日期是 %s，与 %s 不一致（日报当天通常引用前一天的刊）" % (
            meta["jobid"],
            meta["page_date"],
            date,
        )
        meta.setdefault("warnings", []).append(note)
        if not quiet:
            print("warn: " + note, file=sys.stderr)

    return meta, cands


def main(argv=None):
    ap = argparse.ArgumentParser(description="抓取 pgnexus 每日更新并解析成候选")
    ap.add_argument("jobid", nargs="?", help="任务号，或 auto（配合 --date）；--list 时可省略")
    ap.add_argument("--date", help="期望日期 YYYY-MM-DD，用于校验或 auto 查表")
    ap.add_argument("--lang", default="zh", choices=["zh", "en"])
    ap.add_argument("--source", default="auto", choices=["auto", "api", "cdp"])
    ap.add_argument("--out", help="输出 JSON 文件，默认打印到 stdout")
    ap.add_argument("--list", action="store_true", help="只列出最近的任务号与日期")
    args = ap.parse_args(argv)

    if args.list:
        for entry in list_jobs()[:30]:
            print("%s  #%s" % (entry.get("date"), entry.get("jobid")))
        return 0
    if not args.jobid:
        ap.error("需要 jobid（或用 --list 查看可用任务）")

    meta, cands = fetch(args.jobid, date=args.date, lang=args.lang, source=args.source)
    payload = {"meta": meta, "pgnexus": cands}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print("#%s %s via %s -> %d 条 -> %s" % (meta["jobid"], meta["page_date"], meta["source"], meta["count"], args.out))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
