#!/usr/bin/env python3
"""把 ~/pgsty/daily/YYYY-MM-DD.md 解析成「博览」候选 JSON。

用法：

    tools/info/extract_daily.py 2026-09-10
    tools/info/extract_daily.py 2026-09-10 --pgnexus 264 --out /tmp/c.json
    tools/info/extract_daily.py 2026-09-10 --pgnexus auto

只用标准库。日报格式几个月里有漂移（5 月的「今日重点」没有 `[标签]` 也没有加粗，
7 月中旬之后才稳定），解析器对这些差异都做了退化处理。

输出结构见 tools/info/README.md。
"""

import argparse
import datetime as _dt
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_DAILY_DIR = os.path.expanduser("~/pgsty/daily")

# 会话临时目录；不存在时退回系统临时目录，避免把别人机器上的路径写死。
_SCRATCH = (
    "/private/tmp/claude-501/-Users-vonng-pgsty-pgweb/"
    "956b4be5-c7ee-4a44-9a74-0ad05447c8e3/scratchpad/info"
)


def default_out_dir():
    env = os.environ.get("INFO_CANDIDATES_DIR")
    if env:
        return env
    if os.path.isdir(os.path.dirname(_SCRATCH)):
        return _SCRATCH
    return os.path.join(tempfile.gettempdir(), "pgweb-info")


# --------------------------------------------------------------------------
# markdown 基础工具
# --------------------------------------------------------------------------

# [label](url)，容忍 label 里再嵌一层方括号、url 里带一对圆括号、以及 (url "title")
LINK_RE = re.compile(
    r"\[((?:[^\[\]]|\[[^\[\]]*\])*)\]"
    r"\(\s*<?([^()<>\s]*(?:\([^()\s]*\)[^()<>\s]*)*)>?\s*(?:\"[^\"]*\")?\)"
)

ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!~|<>])")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)

ISO_DATE_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
URL_DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-/](\d{2})[-/](\d{2})(?!\d)")


def md_unescape(text):
    return ESCAPE_RE.sub(r"\1", text)


def flatten_links(text):
    """把 [label](url) 换成 label，保留可读文字。"""
    return LINK_RE.sub(lambda m: m.group(1), text)


def clean_text(text):
    """去链接语法、去加粗与行内代码标记、合并空白。"""
    text = flatten_links(text)
    text = BOLD_RE.sub(r"\1", text)
    text = text.replace("**", "")
    text = text.replace("`", "")
    text = md_unescape(text)
    text = re.sub(r"[ \t 　]+", " ", text)
    # 全角标点后不留空格（`**句子。** 后续` 展平后会多出空格）
    text = re.sub(r"([。！？；，、：）】」》])\s+", r"\1", text)
    return text.strip()


TITLE_TRAIL = " 。.；;，,、：: \t 　"


def clean_title(text):
    title = clean_text(text)
    # 反复削掉首尾的列表符号与句末标点
    title = title.lstrip("-*# \t")
    while title and title[-1] in TITLE_TRAIL:
        title = title[:-1]
    return title.strip()


def extract_links(text):
    """返回绝对 http(s) 链接列表，按出现顺序去重。"""
    out, seen = [], set()
    for m in LINK_RE.finditer(text):
        url = m.group(2).strip()
        if not url.lower().startswith(("http://", "https://")):
            continue
        url = url.rstrip("，。、；;")
        if url in seen:
            continue
        seen.add(url)
        out.append({"label": clean_text(m.group(1)), "url": url})
    return out


HN_HOST = "news.ycombinator.com"
SEARCH_RE = re.compile(
    r"(?:^https?://(?:www\.)?(?:google|bing|duckduckgo|baidu)\.[a-z.]+/)|(?:[?&]q=)|(?:/search\b)",
    re.I,
)


def is_hn(url):
    return HN_HOST in url


def is_search(url):
    return bool(SEARCH_RE.search(url))


def pick_primary(links):
    """一手链接优先：非 HN、非搜索结果页。"""
    for link in links:
        if not is_hn(link["url"]) and not is_search(link["url"]):
            return link
    for link in links:
        if not is_search(link["url"]):
            return link
    return links[0] if links else None


GENERIC_LABELS = {
    "公告", "链接", "来源", "原文", "详情", "说明", "更新", "复盘", "文档",
    "博客", "报道", "消息", "讨论", "讨论串", "评估", "分析", "帖子", "条目",
    "文章", "公告页", "新闻", "新闻归档", "归档", "release", "changelog",
    "hn", "top", "new", "show", "ask", "link", "source", "post", "blog",
    "discussion", "thread", "announcement", "docs", "doc",
}
GENERIC_SUFFIX_RE = re.compile(
    r"\s*(?:完整|官方|项目|最新|本次)?\s*"
    r"(公告|文档|复盘|说明|更新|博客|评估|条目|清单|页面|更新日志|发布说明|"
    r"changelog|blog|docs?|release notes?)$",
    re.I,
)


def publisher_from_label(label):
    if not label:
        return ""
    plain = re.sub(r"\s+", " ", label).strip()
    if plain.lower() in GENERIC_LABELS:
        return ""
    if re.fullmatch(r"讨论串\s*\d*", plain):
        return ""
    trimmed = plain
    for _ in range(3):
        stripped = GENERIC_SUFFIX_RE.sub("", trimmed).strip(" /·、与和")
        if stripped == trimmed:
            break
        trimmed = stripped
    trimmed = re.sub(r"\s*(?:完整|官方)$", "", trimmed).strip(" /·、")
    if not trimmed or trimmed.lower() in GENERIC_LABELS:
        return ""
    # "Dalibo / PostgreSQL 新闻" -> "Dalibo"
    if " / " in trimmed:
        trimmed = trimmed.split(" / ")[0].strip()
    return trimmed


def iso_date(text):
    m = ISO_DATE_RE.search(text or "")
    if not m:
        return ""
    y, mo, d = m.groups()
    try:
        _dt.date(int(y), int(mo), int(d))
    except ValueError:
        return ""
    return "%s-%s-%s" % (y, mo, d)


def date_from_url(url):
    if not url:
        return ""
    m = URL_DATE_RE.search(url)
    if not m:
        return ""
    y, mo, d = m.groups()
    try:
        _dt.date(int(y), int(mo), int(d))
    except ValueError:
        return ""
    return "%s-%s-%s" % (y, mo, d)


# --------------------------------------------------------------------------
# HN 热度
# --------------------------------------------------------------------------

_NUM = r"(\d[\d,]*)"
HN_PATTERNS = [
    re.compile(_NUM + r"\s*points?\s*[/、,，]\s*" + _NUM + r"\s*comments?", re.I),
    re.compile(_NUM + r"\s*分\s*[/、,，]\s*" + _NUM + r"\s*(?:条)?评论"),
    re.compile(r"[（(][^（）()]{0,12}?" + _NUM + r"\s*/\s*" + _NUM + r"[^（）()]{0,8}?[)）]"),
    re.compile(r"获\s*" + _NUM + r"\s*/\s*" + _NUM),
]


def _to_int(raw):
    try:
        return int(raw.replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_counts(text):
    for pat in HN_PATTERNS:
        m = pat.search(text or "")
        if m:
            p, c = _to_int(m.group(1)), _to_int(m.group(2))
            if p is not None and c is not None:
                return p, c
    return None, None


def build_hn(text, links, counts_text=None):
    hn_link = next((l for l in links if is_hn(l["url"])), None)
    if hn_link is None:
        return None
    points = comments = None
    if counts_text and "不适用" not in counts_text:
        points, comments = parse_counts(counts_text)
        if points is None:
            m = re.search(_NUM + r"\s*/\s*" + _NUM, counts_text)
            if m:
                points, comments = _to_int(m.group(1)), _to_int(m.group(2))
    if points is None:
        points, comments = parse_counts(text)
    return {"url": hn_link["url"], "points": points, "comments": comments}


# --------------------------------------------------------------------------
# 日报切分
# --------------------------------------------------------------------------


def split_h2(text):
    """按 `## ` 切分，返回 [(heading, body)]；`### ` 留在 body 里。"""
    out, cur, buf = [], None, []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.*)$", line)
        if m:
            if cur is not None:
                out.append((cur, "\n".join(buf)))
            cur, buf = m.group(1).strip(), []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        out.append((cur, "\n".join(buf)))
    return out


def find_section(sections, *keywords):
    for heading, body in sections:
        for kw in keywords:
            if kw in heading:
                return heading, body
    return None, ""


WINDOW_RE = re.compile(r"(?:本期)?覆盖(?:时间)?范围\s*[：:]\s*(.+)")


def window_line(text):
    """meta.window：优先取 H1 之后的引用块；早期日报把窗口写在文末说明里。"""
    lines = []
    started = False
    for line in text.splitlines():
        if re.match(r"^##\s", line):
            break
        s = line.strip()
        if s.startswith(">"):
            started = True
            lines.append(s.lstrip("> ").strip())
        elif started and not s:
            break
    if lines:
        return clean_text(" ".join(lines))
    for line in text.splitlines():
        m = WINDOW_RE.search(line)
        if m:
            return clean_title(m.group(1))
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(">") and len(s) > 8:
            return clean_text(s.lstrip("> ").strip())
    return ""


BULLET_RE = re.compile(r"^[-*+]\s+(.*)$")
TAG_RE = re.compile(r"^\[([^\[\]]+)\](?!\()\s*")
IMPORTANCE_TOKENS = {"极高", "很高", "高", "中高", "中", "中低", "低", "极低"}


def split_tag(rest):
    """剥掉行首的 `[标签 / 重要性 / 备注]`。"""
    m = TAG_RE.match(rest)
    if not m:
        return "", rest
    return m.group(1).strip(), rest[m.end():].lstrip()


def tag_parts(tag):
    if not tag:
        return [], ""
    parts = [p.strip() for p in re.split(r"\s*/\s*", tag) if p.strip()]
    importance = ""
    keep = []
    for p in parts:
        if not importance and p in IMPORTANCE_TOKENS:
            importance = p
        else:
            keep.append(p)
    return keep, importance


SENTENCE_SPLIT_RE = re.compile(r"[。；;！!？?：:]")


def first_sentence(text):
    for piece in SENTENCE_SPLIT_RE.split(text):
        piece = piece.strip()
        if piece:
            return piece
    return text.strip()


TAIL_SEPS = (" - ", " — ", " – ", " -- ", " − ")


def split_tail(rest):
    """把简讯行拆成 (正文, 尾部)；尾部形如 `发布方 / 日期 / [标签](链接)`。"""
    positions = []
    for sep in TAIL_SEPS:
        for m in re.finditer(re.escape(sep), rest):
            positions.append((m.start(), m.end()))
    if not positions:
        return rest, ""
    positions.sort(key=lambda x: x[0], reverse=True)
    fallback = None
    for start, end in positions:
        tail = rest[end:].strip()
        if not tail:
            continue
        if fallback is None:
            fallback = (start, tail)
        if "](" in tail or re.match(r"^[^/\n]{1,60}/", tail):
            return rest[:start].strip(), tail
    if fallback:
        return rest[:fallback[0]].strip(), fallback[1]
    return rest, ""


def parse_tail(tail):
    """尾部 -> (发布方, 日期)。链接前面的部分按 ` / ` 拆。"""
    if not tail:
        return "", ""
    m = LINK_RE.search(tail)
    prefix = tail[:m.start()] if m else tail
    prefix = clean_text(prefix)
    parts = [p.strip() for p in re.split(r"\s*/\s*", prefix) if p.strip()]
    publisher = parts[0] if parts else ""
    date = ""
    for p in parts[1:]:
        date = iso_date(p)
        if date:
            break
    if not date:
        date = iso_date(prefix)
    return publisher, date


def new_candidate(section, group):
    return {
        "section": section,
        "group": group,
        "tag": "",
        "importance": "",
        "title": "",
        "text": "",
        "links": [],
        "primary_url": "",
        "publisher": "",
        "date": "",
        "hn": None,
        "tags": [],
        "in_sections": [section],
        "also_in": [],
    }


# --------------------------------------------------------------------------
# 一、今日重点
# --------------------------------------------------------------------------


def parse_highlights(body):
    out = []
    group = ""
    for line in body.splitlines():
        s = line.strip()
        m3 = re.match(r"^###\s+(.*)$", s)
        if m3:
            group = clean_title(m3.group(1))
            continue
        m = BULLET_RE.match(s)
        if not m:
            continue
        rest = m.group(1).strip()
        if not rest:
            continue
        tag, rest = split_tag(rest)
        tags, importance = tag_parts(tag)
        links = extract_links(rest)
        primary = pick_primary(links)
        text = clean_text(rest)
        bold = BOLD_RE.search(rest)
        title = clean_title(bold.group(1)) if bold else clean_title(first_sentence(text))

        cand = new_candidate("highlight", group)
        cand["tag"] = tag
        cand["importance"] = importance
        cand["tags"] = tags
        cand["title"] = title
        cand["text"] = text
        cand["links"] = links
        cand["primary_url"] = primary["url"] if primary else ""
        cand["publisher"] = publisher_from_label(primary["label"]) if primary else ""
        cand["date"] = date_from_url(cand["primary_url"]) or iso_date(text)
        cand["hn"] = build_hn(rest, links)
        out.append(cand)
    return out


# --------------------------------------------------------------------------
# 二、简讯
# --------------------------------------------------------------------------


def parse_briefs(body):
    out = []
    group = ""
    for line in body.splitlines():
        s = line.strip()
        m3 = re.match(r"^###\s+(.*)$", s)
        if m3:
            group = clean_title(m3.group(1))
            continue
        m = BULLET_RE.match(s)
        if not m:
            continue
        rest = m.group(1).strip()
        if not rest:
            continue
        tag, rest = split_tag(rest)
        tags, importance = tag_parts(tag)
        head, tail = split_tail(rest)
        links = extract_links(rest)
        primary = pick_primary(links)
        publisher, date = parse_tail(tail)
        text = clean_text(rest)
        title = clean_title(head) or clean_title(text)

        cand = new_candidate("brief", group)
        cand["tag"] = tag
        cand["importance"] = importance
        cand["tags"] = tags
        cand["title"] = title
        cand["text"] = text
        cand["links"] = links
        cand["primary_url"] = primary["url"] if primary else ""
        cand["publisher"] = publisher or (
            publisher_from_label(primary["label"]) if primary else ""
        )
        cand["date"] = date or date_from_url(cand["primary_url"])
        cand["hn"] = build_hn(rest, links)
        out.append(cand)
    return out


# --------------------------------------------------------------------------
# 三、重磅新闻
# --------------------------------------------------------------------------

FIELD_RE = re.compile(r"^[-*+]\s+\*{0,2}([^：:*]{1,24}?)\*{0,2}\s*[：:]\s*(.*)$")
HEADING_NUM_RE = re.compile(r"^\s*[a-z]?\d+\s*[.、)]\s*")


def parse_features(body):
    out = []
    blocks = []
    cur = None
    for line in body.splitlines():
        m = re.match(r"^###\s+(.*)$", line.strip())
        if m:
            cur = {"heading": m.group(1).strip(), "lines": []}
            blocks.append(cur)
        elif cur is not None:
            cur["lines"].append(line)

    for block in blocks:
        fields = {}
        order = []
        for line in block["lines"]:
            s = line.strip()
            fm = FIELD_RE.match(s)
            if fm:
                key = clean_text(fm.group(1)).strip()
                val = fm.group(2).strip()
                if key in fields:
                    fields[key] = fields[key] + " " + val
                else:
                    fields[key] = val
                    order.append(key)
            elif s and not s.startswith("#"):
                if order:
                    fields[order[-1]] += " " + s

        raw_block = "\n".join(block["lines"])
        links = extract_links(raw_block)
        source_links = extract_links(fields.get("来源", ""))
        primary = pick_primary(source_links) or pick_primary(links)

        title = clean_title(HEADING_NUM_RE.sub("", block["heading"]))
        tags = []
        for piece in re.split(r"[、,，/]", clean_text(fields.get("分类标签", ""))):
            piece = piece.strip(" 。.")
            if piece:
                tags.append(piece)

        importance = clean_text(fields.get("重要性评级", ""))
        importance = re.split(r"[（(]", importance)[0].strip(" 。.")

        text_parts = []
        for key in order:
            val = clean_text(fields[key])
            if val:
                text_parts.append("%s：%s" % (key, val))
        text = "\n".join(text_parts)

        counts_text = fields.get("points/comments") or fields.get("HN") or ""
        hn = build_hn(raw_block, links, counts_text=counts_text)

        cand = new_candidate("feature", "")
        cand["title"] = title
        cand["text"] = text
        cand["links"] = links
        cand["primary_url"] = primary["url"] if primary else ""
        cand["publisher"] = publisher_from_label(primary["label"]) if primary else ""
        cand["date"] = date_from_url(cand["primary_url"]) or iso_date(text)
        cand["importance"] = importance
        cand["tags"] = tags
        cand["hn"] = hn
        cand["fields"] = {k: clean_text(fields[k]) for k in order}
        cand["summary"] = clean_text(fields.get("摘要", ""))
        out.append(cand)
    return out


# --------------------------------------------------------------------------
# 去重
# --------------------------------------------------------------------------

SECTION_RANK = {"feature": 3, "highlight": 2, "brief": 1}


def norm_url(url):
    if not url:
        return ""
    url = url.split("#", 1)[0]
    url = re.sub(r"^https?://", "", url, flags=re.I)
    url = re.sub(r"^www\.", "", url, flags=re.I)
    return url.rstrip("/").lower()


def dedupe(candidates):
    """同一 primary_url 跨版块出现时保留最丰富的一条，其余记入 also_in。"""
    groups = {}
    for cand in candidates:
        key = norm_url(cand["primary_url"])
        if not key:
            continue
        groups.setdefault(key, []).append(cand)

    dropped = set()
    for key, members in groups.items():
        if len(members) < 2:
            continue
        if len({m["section"] for m in members}) < 2:
            continue  # 同版块内的多条互补事实，保留
        members_sorted = sorted(
            members,
            key=lambda c: (SECTION_RANK.get(c["section"], 0), len(c["text"])),
            reverse=True,
        )
        keeper = members_sorted[0]
        for other in members_sorted[1:]:
            keeper["also_in"].append(
                {
                    "section": other["section"],
                    "group": other["group"],
                    "title": other["title"],
                    "text": other["text"],
                }
            )
            # 被折叠的条目常常带着保留条目缺的元信息
            if not keeper["date"] and other["date"]:
                keeper["date"] = other["date"]
            if not keeper["publisher"] and other["publisher"]:
                keeper["publisher"] = other["publisher"]
            if not keeper["importance"] and other["importance"]:
                keeper["importance"] = other["importance"]
            if other["hn"]:
                if not keeper["hn"]:
                    keeper["hn"] = other["hn"]
                elif keeper["hn"].get("points") is None and other["hn"].get("points") is not None:
                    keeper["hn"] = other["hn"]
            if other["section"] not in keeper["in_sections"]:
                keeper["in_sections"].append(other["section"])
            dropped.add(id(other))
    return [c for c in candidates if id(c) not in dropped]


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def parse_daily(text, date):
    sections = split_h2(text)
    _, hi_body = find_section(sections, "今日重点", "重点")
    _, br_body = find_section(sections, "简讯")
    _, fe_body = find_section(sections, "重磅新闻", "重磅")

    highlights = parse_highlights(hi_body)
    briefs = parse_briefs(br_body)
    features = parse_features(fe_body)

    raw_counts = {
        "highlight": len(highlights),
        "brief": len(briefs),
        "feature": len(features),
    }
    candidates = dedupe(highlights + briefs + features)
    counts = {"highlight": 0, "brief": 0, "feature": 0}
    for cand in candidates:
        counts[cand["section"]] = counts.get(cand["section"], 0) + 1
    counts["total"] = len(candidates)

    meta = {
        "date": date,
        "window": window_line(text),
        "counts": counts,
        "raw_counts": raw_counts,
    }
    return meta, candidates


def load_pgnexus(jobid, date, lang, source, quiet=False):
    sys.path.insert(0, HERE)
    try:
        import fetch_pgnexus
    except ImportError as exc:  # pragma: no cover
        print("warn: 无法导入 fetch_pgnexus (%s)" % exc, file=sys.stderr)
        return None, []
    try:
        return fetch_pgnexus.fetch(jobid, date=date, lang=lang, source=source, quiet=quiet)
    except Exception as exc:  # noqa: BLE001 - pgnexus 是可选来源，失败不应阻断
        print("warn: pgnexus 抓取失败：%s" % exc, file=sys.stderr)
        return {"jobid": jobid, "error": str(exc)}, []


def main(argv=None):
    ap = argparse.ArgumentParser(description="解析 pgsty 日报，产出博览候选 JSON")
    ap.add_argument("date", help="日期 YYYY-MM-DD")
    ap.add_argument("--daily-dir", default=DEFAULT_DAILY_DIR, help="日报目录，默认 ~/pgsty/daily")
    ap.add_argument("--file", help="直接指定日报文件，覆盖 --daily-dir")
    ap.add_argument("--out", help="输出文件，默认 <tmp>/info/candidates-DATE.json")
    ap.add_argument("--pgnexus", metavar="JOBID", help="pgnexus 任务号；auto 表示按日期自动查找")
    ap.add_argument("--pgnexus-lang", default="zh", choices=["zh", "en"], help="pgnexus 语言，默认 zh")
    ap.add_argument(
        "--pgnexus-source",
        default="auto",
        choices=["auto", "api", "cdp"],
        help="auto=先试内容 API，失败退回 headless Chrome；cdp=强制用 Chrome 渲染",
    )
    ap.add_argument("--quiet", action="store_true", help="不打印统计")
    args = ap.parse_args(argv)

    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", args.date):
        ap.error("date 必须是 YYYY-MM-DD")

    path = args.file or os.path.join(os.path.expanduser(args.daily_dir), args.date + ".md")
    if not os.path.isfile(path):
        print("error: 找不到日报 %s" % path, file=sys.stderr)
        return 2
    with open(path, encoding="utf-8") as fh:
        text = fh.read()

    meta, candidates = parse_daily(text, args.date)
    meta["source_file"] = path

    payload = {"meta": meta, "candidates": candidates}

    if args.pgnexus:
        pg_meta, pg_items = load_pgnexus(
            args.pgnexus, args.date, args.pgnexus_lang, args.pgnexus_source, quiet=args.quiet
        )
        if pg_meta:
            meta["pgnexus"] = pg_meta
        meta["counts"]["pgnexus"] = len(pg_items)
        payload["pgnexus"] = pg_items

    out = args.out
    if not out:
        out = os.path.join(default_out_dir(), "candidates-%s.json" % args.date)
    out_dir = os.path.dirname(os.path.abspath(out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    if not args.quiet:
        counts = meta["counts"]
        raw = meta["raw_counts"]
        print(
            "%s  highlight=%d brief=%d feature=%d%s  total=%d  (raw %d/%d/%d)  -> %s"
            % (
                args.date,
                counts.get("highlight", 0),
                counts.get("brief", 0),
                counts.get("feature", 0),
                (" pgnexus=%d" % counts["pgnexus"]) if "pgnexus" in counts else "",
                counts.get("total", 0),
                raw["highlight"],
                raw["brief"],
                raw["feature"],
                out,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
