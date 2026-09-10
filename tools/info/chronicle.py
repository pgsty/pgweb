#!/usr/bin/env python3
"""把四路来源合成一份逐日「编年」候选，供编辑模型回填历史。

    .venv/bin/python tools/info/chronicle.py 2026-03-01 2026-09-10
    .venv/bin/python tools/info/chronicle.py 2026-09-01 2026-09-10 --stats
    .venv/bin/python tools/info/chronicle.py 2026-03-01 2026-09-10 --refresh-links

来源：

1. `~/pgsty/daily/DATE.md` 中文日报（2026-05-06 起），用 extract_daily.parse_daily 解析；
2. pgnexus.ai「PostgreSQL 每日更新」，按页面 H1 的日期对齐到当天；
3. 本地库 `news_newsarticle`（已过审、已中文化）；
4. 本地库 `core_importedrssitem` 的 Planet PostgreSQL 条目。

所有链接都会跟随跳转解析到最终地址（缓存在 tmp/info/links.json），同一天里同一
最终链接的候选合并成一条，跨天重复的链接只在首次出现的那天算候选，之后进 repeats。

输出 `<out-dir>/YYYY-MM-DD.json`，范围内每天一个文件（当天没有候选也写空文件）。
除了读本地库要 Django 之外只用标准库。
"""

import argparse
import datetime as dt
import html as html_mod
import json
import os
import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import extract_daily  # noqa: E402
import fetch_pgnexus  # noqa: E402

DAILY_DIR = os.path.expanduser("~/pgsty/daily")
TMP = os.path.join(ROOT, "tmp", "info")
DEFAULT_OUT_DIR = os.path.join(TMP, "chronicle")
PGNEXUS_DIR = os.path.join(TMP, "pgnexus")
LINK_CACHE = os.path.join(TMP, "links.json")

FIRST_JOB = 60              # 60 是 2026-02-21，比回填范围早十天
PGNEXUS_WORKERS = 8
LINK_WORKERS = 16
LINK_TIMEOUT = 15

TEXT_MAX = 500
NEWS_TEXT_MAX = 600

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 pgweb-info/1.0")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en,zh;q=0.8",
}


# --------------------------------------------------------------------------
# 链接解析（enrich.py 复用这一段）
# --------------------------------------------------------------------------

TRACKING_PREFIX = ("utm_",)
TRACKING_KEYS = {"ref", "fbclid"}
HEAD_FALLBACK_CODES = {400, 403, 405, 406, 501}


def strip_tracking(url):
    """去掉 utm_* / ref / fbclid 查询参数，其余原样保留。"""
    if not url:
        return url
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    if not parts.query:
        return url
    keep = []
    for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
        low = key.lower()
        if low in TRACKING_KEYS or low.startswith(TRACKING_PREFIX):
            continue
        keep.append((key, value))
    query = urllib.parse.urlencode(keep)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def resolvable(url):
    """HN 讨论页和搜索结果页不解析：它们不是内容页，解析也没有意义。"""
    if not url or not url.lower().startswith(("http://", "https://")):
        return False
    if extract_daily.is_hn(url) or extract_daily.is_search(url):
        return False
    return True


def _probe(url, method):
    req = urllib.request.Request(url, method=method, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=LINK_TIMEOUT) as resp:
        if method == "GET":
            try:
                resp.read(2048)
            except Exception:  # noqa: BLE001 - 只是不想把整页读下来
                pass
        return resp.geturl(), getattr(resp, "status", resp.getcode())


def resolve_one(url):
    """返回 {"final","status","checked"[,"error"]}；status 0 表示请求失败。"""
    methods = ["HEAD", "GET"]
    for index, method in enumerate(methods):
        try:
            final, status = _probe(url, method)
            return {"final": strip_tracking(final or url), "status": int(status),
                    "checked": dt.datetime.now().isoformat(timespec="seconds")}
        except urllib.error.HTTPError as exc:
            if index == 0 and exc.code in HEAD_FALLBACK_CODES:
                continue
            final = getattr(exc, "url", None) or url
            return {"final": strip_tracking(final), "status": int(exc.code),
                    "checked": dt.datetime.now().isoformat(timespec="seconds")}
        except Exception as exc:  # noqa: BLE001 - 超时、DNS、证书都归为失败
            return {"final": url, "status": 0, "error": str(exc)[:120],
                    "checked": dt.datetime.now().isoformat(timespec="seconds")}
    return {"final": url, "status": 0, "error": "unreachable",
            "checked": dt.datetime.now().isoformat(timespec="seconds")}


TRANSIENT_STATUS = {0, 403, 408, 425, 429, 500, 502, 503, 504, 530}


def looks_transient(entry):
    """并发抓取时被限流、超时、握手失败的都不能直接当成失效。"""
    if not entry:
        return False
    return (entry.get("status") or 0) in TRANSIENT_STATUS


class LinkCache(object):
    """tmp/info/links.json：{url: {"final","status","checked"}}。"""

    def __init__(self, path=LINK_CACHE, refresh=False):
        self.path = path
        self.refresh = refresh
        self.lock = threading.Lock()
        self.data = {}
        self.dirty = False
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as stream:
                    loaded = json.load(stream)
                if isinstance(loaded, dict):
                    self.data = loaded
            except (ValueError, OSError):
                self.data = {}
        self.fetched = 0

    def get(self, url):
        return self.data.get(url)

    def resolve(self, urls, workers=LINK_WORKERS, progress=None):
        """把还没缓存的链接批量解析掉。"""
        todo = []
        seen = set()
        for url in urls:
            if not resolvable(url) or url in seen:
                continue
            seen.add(url)
            if self.refresh or url not in self.data:
                todo.append(url)
        if not todo:
            return 0
        done, total = [0], [len(todo)]

        def work(url):
            result = resolve_one(url)
            with self.lock:
                self.data[url] = result
                self.dirty = True
                self.fetched += 1
                done[0] += 1
                if done[0] % 500 == 0:
                    self.save()          # 长跑中途落盘，中断了也不用重头解析
                if progress and done[0] % 200 == 0:
                    progress(done[0], total[0])
            return result

        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(work, todo))

        # 第二遍：限流和超时造成的假失效，用低并发再试一次
        retry = [url for url in todo if looks_transient(self.data.get(url))]
        if retry:
            done[0], total[0] = 0, len(retry)
            if progress:
                progress(0, len(retry))
            with ThreadPoolExecutor(max_workers=max(2, workers // 4)) as pool:
                list(pool.map(work, retry))
        self.save()
        return len(todo)

    def final(self, url):
        """(最终链接, 是否失效)。没解析过的链接原样返回。"""
        if not url:
            return "", False
        entry = self.data.get(url)
        if not entry:
            return strip_tracking(url), False
        status = entry.get("status") or 0
        return entry.get("final") or url, bool(status == 0 or status >= 400)

    def save(self):
        if not self.dirty:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as stream:
            json.dump(self.data, stream, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, self.path)
        self.dirty = False


# --------------------------------------------------------------------------
# 文本工具
# --------------------------------------------------------------------------

BLOCK_TAG_RE = re.compile(r"(?i)</?(?:p|div|br|li|ul|ol|h[1-6]|tr|table|blockquote|pre|section)\b[^>]*>")
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t 　]+")
NL_RE = re.compile(r"\n{2,}")


def html_to_text(raw):
    text = BLOCK_TAG_RE.sub("\n", raw or "")
    text = TAG_RE.sub(" ", text)
    text = html_mod.unescape(text)
    text = WS_RE.sub(" ", text)
    text = NL_RE.sub("\n", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()


def clip(text, limit=TEXT_MAX):
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def norm_url(url):
    return extract_daily.norm_url(url)


HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)


def first_external_link(raw_html, skip_host_suffix="postgresql.org"):
    for href in HREF_RE.findall(raw_html or ""):
        href = html_mod.unescape(href.strip())
        if not href.lower().startswith(("http://", "https://")):
            continue
        host = urllib.parse.urlsplit(href).netloc.lower().split(":")[0]
        if host == skip_host_suffix or host.endswith("." + skip_host_suffix):
            continue
        if extract_daily.is_hn(href) or extract_daily.is_search(href):
            continue
        return href
    return ""


# --------------------------------------------------------------------------
# PostgreSQL 相关度（粗判）
# --------------------------------------------------------------------------

PG_RE = re.compile(
    r"postgre|postgres|\bpg_|\bpgsql\b|\bpsql\b|\bpgdg\b|\bpg\b|"
    r"patroni|pgbouncer|pgbackrest|timescale|citus|pgvector|pigsty|greenplum|yugabyte",
    re.I,
)
EXTENSION_FALLBACK = {
    "postgis", "timescaledb", "citus", "pgvector", "pgbouncer", "patroni",
    "pgbackrest", "pg_stat_statements", "pgaudit", "pglogical", "pg_cron",
}


def load_extension_names():
    """扩展名来自本地 pgext.universe；取不到就用内置的一小撮。"""
    try:
        setup_django()
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("select name from pgext.universe")
            names = {row[0].lower() for row in cursor.fetchall() if row[0] and len(row[0]) >= 4}
        return names or set(EXTENSION_FALLBACK)
    except Exception:  # noqa: BLE001 - 没有元数据库也要能跑
        return set(EXTENSION_FALLBACK)


def is_pg(candidate, extensions):
    if candidate["source"] in ("pgnexus", "news", "planet"):
        return True
    blob = " ".join([candidate.get("title", ""), candidate.get("text", ""), candidate.get("url", "")])
    if PG_RE.search(blob):
        return True
    for tag in candidate.get("tags") or []:
        if tag.lower() in extensions:
            return True
    return False


# --------------------------------------------------------------------------
# Django（只读本地库）
# --------------------------------------------------------------------------

_django_ready = False


def setup_django():
    global _django_ready
    if _django_ready:
        return
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pgweb.settings")
    import django
    django.setup()
    _django_ready = True


# --------------------------------------------------------------------------
# 候选构造
# --------------------------------------------------------------------------

RANK = {
    ("daily", "highlight"): 0,
    ("daily", "feature"): 0,
    ("news", "news"): 1,
    ("pgnexus", "blog"): 2,
    ("pgnexus", "industry"): 2,
    ("planet", "planet"): 3,
    ("pgnexus", "hackers"): 4,
    ("daily", "brief"): 5,
}


def rank_of(candidate):
    return RANK.get((candidate["source"], candidate["section"]), 6)


def blank(source, section, group=""):
    return {
        "source": source,
        "section": section,
        "group": group,
        "title": "",
        "text": "",
        "url": "",
        "via": "",
        "dead": False,
        "publisher": "",
        "author": "",
        "date": "",
        "importance": "",
        "hn_points": None,
        "tags": [],
        "pg": False,
    }


FEATURE_TEXT_FIELDS = ("摘要", "为什么重要", "对用户的潜在影响")


def feature_text(raw):
    """重磅条目的正文里一半是元信息，只留对编辑有用的三段。"""
    fields = raw.get("fields") or {}
    parts = [fields[key].strip() for key in FEATURE_TEXT_FIELDS if fields.get(key)]
    return " ".join(parts) if parts else (raw.get("text") or "")


def from_daily(raw):
    cand = blank("daily", raw.get("section") or "brief", raw.get("group") or "")
    cand["title"] = raw.get("title") or ""
    cand["text"] = feature_text(raw) if raw.get("section") == "feature" else (raw.get("text") or "")
    cand["url"] = raw.get("primary_url") or ""
    cand["publisher"] = raw.get("publisher") or ""
    cand["date"] = raw.get("date") or ""
    cand["importance"] = raw.get("importance") or ""
    cand["tags"] = list(raw.get("tags") or [])
    hn = raw.get("hn") or {}
    cand["hn_points"] = hn.get("points")
    for extra in raw.get("also_in") or []:
        if extra.get("text") and len(extra["text"]) > len(cand["text"]):
            cand["text"] = extra["text"]
    return cand


def pgnexus_section(group):
    text = group or ""
    low = text.lower()
    if "hacker" in low or "邮件" in text or "补丁" in text or "patch" in low or "commit" in low:
        return "hackers"
    if "行业" in text or "industry" in low or "新闻" in text or "news" in low:
        return "industry"
    return "blog"


def from_pgnexus(raw):
    group = raw.get("group") or ""
    cand = blank("pgnexus", pgnexus_section(group), group)
    cand["title"] = raw.get("title") or ""
    cand["text"] = raw.get("text") or ""
    cand["url"] = raw.get("primary_url") or ""
    cand["publisher"] = raw.get("publisher") or ""
    cand["author"] = raw.get("author") or ""
    if not cand["author"] and raw.get("participants"):
        cand["author"] = "、".join(raw["participants"][:3])
    cand["date"] = raw.get("date") or ""
    return cand


def from_news(article):
    cand = blank("news", "news")
    cand["title"] = article["title"]
    cand["text"] = clip(html_to_text(article["content"]), NEWS_TEXT_MAX)
    # Local ids differ from upstream ids, so the page must be our own copy.
    page = "https://pgsql.cc/about/news/%d/" % article["id"]
    external = first_external_link(article["content"])
    cand["url"] = external or page
    cand["via"] = page if external else ""
    cand["publisher"] = article["org"] or "PostgreSQL 新闻"
    cand["date"] = article["date"].isoformat()
    cand["tags"] = list(article["tags"])
    return cand


PLANET_SPLIT_RE = re.compile(r"：|:\s")


def from_planet(item):
    cand = blank("planet", "planet")
    title = (item["title"] or "").strip()
    match = PLANET_SPLIT_RE.search(title)
    if match and 0 < match.start() <= 40:
        cand["author"] = title[:match.start()].strip()
        cand["title"] = title[match.end():].strip() or title
    else:
        cand["title"] = title
    cand["url"] = item["url"]
    cand["date"] = item["posttime"].date().isoformat()
    return cand


# --------------------------------------------------------------------------
# 来源装载
# --------------------------------------------------------------------------


def load_daily(days, quiet=False):
    """{date: [候选]}。日报从 2026-05-06 开始，之前的日期没有文件。"""
    out = {}
    for day in days:
        path = os.path.join(DAILY_DIR, day + ".md")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as stream:
            text = stream.read()
        try:
            _meta, raw = extract_daily.parse_daily(text, day)
        except Exception as exc:  # noqa: BLE001
            if not quiet:
                print("warn: 日报 %s 解析失败：%s" % (day, exc), file=sys.stderr)
            continue
        out[day] = [from_daily(item) for item in raw]
    return out


def cache_pgnexus(refresh=False, quiet=False):
    """把 60..最新 期的 markdown 落到 tmp/info/pgnexus/；返回 (date->jobid, 报告)。"""
    os.makedirs(PGNEXUS_DIR, exist_ok=True)
    try:
        entries = fetch_pgnexus.list_jobs()
    except Exception as exc:  # noqa: BLE001
        if not quiet:
            print("warn: pgnexus 列表接口不可用：%s" % exc, file=sys.stderr)
        entries = []
    listed = {e.get("jobid"): e for e in entries if e.get("jobid") is not None}
    newest = max(list(listed) or [0])
    if not newest:
        cached = [int(n[:-3]) for n in os.listdir(PGNEXUS_DIR) if n.endswith(".md") and n[:-3].isdigit()]
        newest = max(cached or [0])
    jobs = list(range(FIRST_JOB, newest + 1))
    unlisted = [j for j in jobs if listed and j not in listed]

    todo = [j for j in jobs if j not in unlisted
            and (refresh or not os.path.isfile(os.path.join(PGNEXUS_DIR, "%d.md" % j)))]
    errors = {}
    lock = threading.Lock()

    def work(jobid):
        # 早期几期（source=file）按 jobid 取会 404，只能按 filename 取
        name = (listed.get(jobid) or {}).get("filename")
        try:
            content, _title = fetch_pgnexus.fetch_markdown(jobid)
        except Exception as exc:  # noqa: BLE001
            content = ""
            if not name:
                with lock:
                    errors[jobid] = str(exc)[:120]
                return
        if not content and name:
            url = "%s?filename=%s&language=zh" % (
                fetch_pgnexus.CONTENT_API, urllib.parse.quote(name))
            try:
                content = (json.loads(fetch_pgnexus._get(url)) or {}).get("content") or ""
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors[jobid] = str(exc)[:120]
                return
        if not content.strip():
            with lock:
                errors[jobid] = "内容为空"
            return
        with open(os.path.join(PGNEXUS_DIR, "%d.md" % jobid), "w", encoding="utf-8") as stream:
            stream.write(content)

    if todo:
        if not quiet:
            print("pgnexus：抓取 %d 期（%d..%d）" % (len(todo), todo[0], todo[-1]), file=sys.stderr)
        with ThreadPoolExecutor(max_workers=PGNEXUS_WORKERS) as pool:
            list(pool.map(work, todo))

    by_date = {}
    present = []
    for jobid in [j for j in jobs if j not in unlisted]:
        path = os.path.join(PGNEXUS_DIR, "%d.md" % jobid)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as stream:
            head = stream.read(400)
        match = fetch_pgnexus.HEAD_RE.search(head)
        if not match:
            errors.setdefault(jobid, "H1 里没有日期")
            continue
        present.append(jobid)
        date = match.group(2)
        # 同一天出现两期时用较新的一期
        if date not in by_date or jobid > by_date[date]:
            by_date[date] = jobid
    report = {
        "first_job": present[0] if present else None,
        "newest_job": newest,
        "cached": len(present),
        "unlisted": unlisted,                       # 接口列表里就没有这些期号
        "missing": sorted(set(jobs) - set(present) - set(unlisted)),
        "errors": errors,
    }
    return by_date, report


def load_pgnexus_day(jobid):
    path = os.path.join(PGNEXUS_DIR, "%d.md" % jobid)
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as stream:
        content = stream.read()
    _meta, raw = fetch_pgnexus.parse_markdown(content)
    return [from_pgnexus(item) for item in raw]


def load_news(days):
    setup_django()
    from pgweb.news.models import NewsArticle
    first, last = dt.date.fromisoformat(days[0]), dt.date.fromisoformat(days[-1])
    out = {}
    query = (NewsArticle.objects.filter(modstate=2, date__gte=first, date__lte=last)
             .select_related("org").prefetch_related("tags").order_by("date", "id"))
    for article in query:
        row = {
            "id": article.id,
            "title": article.title,
            "content": article.content,
            "org": article.org.name if article.org_id else "",
            "date": article.date,
            "tags": [tag.name for tag in article.tags.all()],
        }
        out.setdefault(article.date.isoformat(), []).append(from_news(row))
    return out


def load_planet(days):
    setup_django()
    from pgweb.core.models import ImportedRSSFeed, ImportedRSSItem
    first, last = dt.date.fromisoformat(days[0]), dt.date.fromisoformat(days[-1])
    out = {}
    try:
        feed = ImportedRSSFeed.objects.get(internalname="planet")
    except ImportedRSSFeed.DoesNotExist:
        return out
    query = (ImportedRSSItem.objects.filter(feed=feed, posttime__date__gte=first, posttime__date__lte=last)
             .order_by("posttime", "id"))
    for item in query:
        cand = from_planet({"title": item.title, "url": item.url, "posttime": item.posttime})
        out.setdefault(item.posttime.date().isoformat(), []).append(cand)
    return out


# --------------------------------------------------------------------------
# 合并
# --------------------------------------------------------------------------


def keys_of(candidate):
    keys = []
    for url in (candidate.get("url"), candidate.get("via")):
        key = norm_url(url)
        if key and key not in keys:
            keys.append(key)
    return keys


def merge_members(members):
    """同一天里同一最终链接的多条候选合成一条。members 已按 rank 排好。"""
    base = dict(members[0])
    base["tags"] = list(members[0].get("tags") or [])
    longest = max(members, key=lambda c: len(c.get("text") or ""))
    if len(longest.get("text") or "") > len(base.get("text") or ""):
        base["text"] = longest["text"]
    also = []
    for other in members[1:]:
        for tag in other.get("tags") or []:
            if tag not in base["tags"]:
                base["tags"].append(tag)
        for field in ("publisher", "author", "date", "title"):
            if not base.get(field) and other.get(field):
                base[field] = other[field]
        if other["source"] == "daily":
            if not base.get("importance") and other.get("importance"):
                base["importance"] = other["importance"]
            if base.get("hn_points") is None and other.get("hn_points") is not None:
                base["hn_points"] = other["hn_points"]
        elif base.get("hn_points") is None and other.get("hn_points") is not None:
            base["hn_points"] = other["hn_points"]
        if not base.get("via") and other.get("url") and norm_url(other["url"]) != norm_url(base["url"]):
            base["via"] = other["url"]
        title = (other.get("title") or "").strip()
        if title and title != base.get("title") and not any(a["title"] == title for a in also):
            also.append({"source": other["source"], "title": clip(title, 120)})
    base["dead"] = all(m.get("dead") for m in members)
    if members[0].get("dead") and not base["dead"]:
        # 保留下来的链接失效，但同组里有能打开的，换成能打开的那个
        alive = next(m for m in members if not m.get("dead"))
        if not base.get("via"):
            base["via"] = members[0]["url"]
        base["url"] = alive["url"]
    if also:
        base["also"] = also
    return base


def build_day(day, buckets, cache, extensions, seen):
    """把当天四路候选解析链接、合并、去重，返回 (payload, 统计)。"""
    ordered = []
    for source in ("daily", "news", "pgnexus", "planet"):
        ordered.extend(buckets.get(source) or [])
    ordered.sort(key=rank_of)

    for cand in ordered:
        if cand["url"]:
            final, dead = cache.final(cand["url"])
            if final and norm_url(final) != norm_url(cand["url"]):
                if not cand["via"]:
                    cand["via"] = cand["url"]
                cand["url"] = final
            else:
                cand["url"] = final or cand["url"]
            cand["dead"] = dead
        if cand["via"]:
            cand["via"] = cache.final(cand["via"])[0] or cand["via"]
        if cand["via"] and norm_url(cand["via"]) == norm_url(cand["url"]):
            cand["via"] = ""

    # 同一天：按最终链接（含 via）并成一组
    groups = []
    index = {}
    for cand in ordered:
        keys = keys_of(cand)
        found = None
        for key in keys:
            if key in index:
                found = index[key]
                break
        if found is None:
            groups.append([cand])
            found = len(groups) - 1
        else:
            groups[found].append(cand)
        for key in keys:
            index.setdefault(key, found)

    candidates, repeats = [], []
    for members in groups:
        merged = merge_members(members)
        keys = keys_of(merged)
        first_seen = next((seen[k] for k in keys if k in seen), None)
        if first_seen and first_seen != day:
            repeats.append({"title": merged.get("title") or merged.get("url"),
                            "url": merged.get("url"), "first_seen": first_seen})
            continue
        for key in keys:
            seen.setdefault(key, day)
        merged["pg"] = is_pg(merged, extensions)
        merged["title"] = clip(merged.get("title") or "", 160)
        merged["text"] = clip(merged.get("text") or "",
                              NEWS_TEXT_MAX if merged["source"] == "news" else TEXT_MAX)
        candidates.append(merged)

    for number, cand in enumerate(candidates, 1):
        cand["id"] = "d%03d" % number

    counts = {"daily": 0, "pgnexus": 0, "news": 0, "planet": 0}
    for cand in candidates:
        counts[cand["source"]] = counts.get(cand["source"], 0) + 1
    stats = {
        "date": day,
        "counts": counts,
        "total": len(candidates),
        "pg": sum(1 for c in candidates if c["pg"]),
        "dead": sum(1 for c in candidates if c["dead"]),
        "repeats": len(repeats),
    }
    payload = {
        "date": day,
        "sources": {
            "daily": bool(buckets.get("daily")),
            "pgnexus": buckets.get("jobid"),
            "news": len(buckets.get("news") or []),
            "planet": len(buckets.get("planet") or []),
        },
        "candidates": candidates,
        "repeats": repeats,
    }
    return payload, stats


FIELD_ORDER = ("id", "source", "section", "group", "title", "text", "url", "via", "dead",
               "publisher", "author", "date", "importance", "hn_points", "tags", "pg", "also")


def dump_day(payload, path):
    """一行一条候选，方便编辑模型扫读，也省 token。"""
    def row(item, fields):
        parts = []
        for field in fields:
            if field not in item:
                continue
            value = item[field]
            if field in ("via", "also", "group") and not value:
                continue
            parts.append("%s: %s" % (json.dumps(field, ensure_ascii=False),
                                     json.dumps(value, ensure_ascii=False)))
        return "{" + ", ".join(parts) + "}"

    lines = ["{", ' "date": %s,' % json.dumps(payload["date"]),
             ' "sources": %s,' % json.dumps(payload["sources"], ensure_ascii=False)]
    lines.append(' "candidates": [')
    body = [("  " + row(item, FIELD_ORDER)) for item in payload["candidates"]]
    lines.append(",\n".join(body))
    lines.append(" ],")
    lines.append(' "repeats": [')
    body = [("  " + row(item, ("title", "url", "first_seen"))) for item in payload["repeats"]]
    lines.append(",\n".join(body))
    lines.append(" ]")
    lines.append("}")
    text = "\n".join(line for line in lines if line != "")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as stream:
        stream.write(text + "\n")
    os.replace(tmp, path)  # editors may be reading the old file right now


# --------------------------------------------------------------------------
# 统计
# --------------------------------------------------------------------------


def median(values):
    values = sorted(values)
    if not values:
        return 0
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2.0


def print_stats(rows):
    print("date        daily pgnexus news planet | total   pg dead repeat")
    for row in rows:
        counts = row["counts"]
        print("%s %5d %7d %4d %6d | %5d %4d %4d %6d" % (
            row["date"], counts.get("daily", 0), counts.get("pgnexus", 0),
            counts.get("news", 0), counts.get("planet", 0),
            row["total"], row["pg"], row["dead"], row["repeats"]))
    months = {}
    for row in rows:
        months.setdefault(row["date"][:7], []).append(row["total"])
    print("")
    print("month     days  min  median  max   sum")
    for month in sorted(months):
        totals = months[month]
        print("%s %5d %4d %7.1f %4d %5d" % (month, len(totals), min(totals),
                                            median(totals), max(totals), sum(totals)))


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def daterange(first, last):
    start, end = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
    if end < start:
        raise ValueError("结束日期早于开始日期")
    days, cursor = [], start
    while cursor <= end:
        days.append(cursor.isoformat())
        cursor += dt.timedelta(days=1)
    return days


def main(argv=None):
    parser = argparse.ArgumentParser(description="合成逐日博览候选（编年）")
    parser.add_argument("start", help="开始日期 YYYY-MM-DD")
    parser.add_argument("end", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="输出目录，默认 tmp/info/chronicle")
    parser.add_argument("--refresh-links", action="store_true", help="忽略链接缓存重新解析")
    parser.add_argument("--recheck-dead", action="store_true",
                        help="把缓存里疑似被限流/超时的失效链接再试一次")
    parser.add_argument("--refresh-pgnexus", action="store_true", help="重新抓取 pgnexus markdown")
    parser.add_argument("--stats", action="store_true", help="打印逐日与逐月统计")
    parser.add_argument("--quiet", action="store_true", help="不打印进度")
    options = parser.parse_args(argv)

    days = daterange(options.start, options.end)
    quiet = options.quiet

    if not quiet:
        print("范围 %s..%s 共 %d 天" % (days[0], days[-1], len(days)), file=sys.stderr)

    pgnexus_by_date, pgnexus_report = cache_pgnexus(refresh=options.refresh_pgnexus, quiet=quiet)
    daily = load_daily(days, quiet=quiet)
    news = load_news(days)
    planet = load_planet(days)
    extensions = load_extension_names()

    buckets = {}
    for day in days:
        jobid = pgnexus_by_date.get(day)
        buckets[day] = {
            "daily": daily.get(day) or [],
            "pgnexus": load_pgnexus_day(jobid) if jobid else [],
            "news": news.get(day) or [],
            "planet": planet.get(day) or [],
            "jobid": jobid,
        }

    urls = []
    for day in days:
        for source in ("daily", "news", "pgnexus", "planet"):
            for cand in buckets[day][source]:
                if cand["url"]:
                    urls.append(cand["url"])
                if cand["via"]:
                    urls.append(cand["via"])
    cache = LinkCache(refresh=options.refresh_links)
    if options.recheck_dead:
        stale = [url for url, entry in cache.data.items() if looks_transient(entry)]
        for url in stale:
            cache.data.pop(url, None)
        if not quiet:
            print("重试疑似假失效的链接 %d 条" % len(stale), file=sys.stderr)

    def progress(done, total):
        print("链接解析 %d/%d" % (done, total), file=sys.stderr)

    unique = len({u for u in urls if resolvable(u)})
    if not quiet:
        print("待解析链接 %d 条（去重后），缓存已有 %d 条" % (unique, len(cache.data)), file=sys.stderr)
    cache.resolve(urls, progress=None if quiet else progress)
    cache.save()

    seen = {}
    rows = []
    for day in days:
        payload, stats = build_day(day, buckets[day], cache, extensions, seen)
        dump_day(payload, os.path.join(options.out_dir, day + ".json"))
        rows.append(stats)

    if options.stats:
        print_stats(rows)
    if not quiet:
        total = sum(r["total"] for r in rows)
        print("写出 %d 天，候选 %d 条，链接缓存 %d 条（本次新解析 %d 条）-> %s"
              % (len(rows), total, len(cache.data), cache.fetched, options.out_dir), file=sys.stderr)
        print("pgnexus：%d..%d 已缓存 %d 期；列表无此期号 %s；抓取失败 %s"
              % (pgnexus_report["first_job"] or 0, pgnexus_report["newest_job"],
                 pgnexus_report["cached"],
                 pgnexus_report["unlisted"] or "无", pgnexus_report["missing"] or "无"),
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
