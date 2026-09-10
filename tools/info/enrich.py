#!/usr/bin/env python3
"""给博览批次文件补最终链接和一档配图。

    .venv/bin/python tools/info/enrich.py data/info/2026-09-10.json
    .venv/bin/python tools/info/enrich.py data/info/2026-09-*.json --dry-run
    .venv/bin/python tools/info/enrich.py data/info/2026-09-10.json --missing-images tmp/info/need-image.jsonl

做两件事，都不碰 title / summary / tier / position：

1. 把每条 `url` 跟随跳转解析到最终地址（与 chronicle.py 共用 tmp/info/links.json
   缓存和同一套规则），变了就改写；失效链接只报告，不删条目。
2. 给还没有 `image` 的一档条目抓原文的 og:image / twitter:image /
   og:image:secure_url，只接受 https、能返回 200 且 content-type 是 image/* 的地址；
   tools/info/generic-images.txt 里列出的站点通用图（大象、社交默认图等）不算题图。

`--missing-images FILE` 把仍然没有配图的一档条目按行追加成 JSONL（date、key、
title、url），供之后统一生成配图。key 与导入器一致：sha1(date + "|" + url)[:16]。
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from chronicle import HEADERS, LINK_TIMEOUT, LinkCache, resolvable, strip_tracking  # noqa: E402

GENERIC_IMAGES = os.path.join(HERE, "generic-images.txt")
IMAGE_WORKERS = 8
PAGE_BYTES = 400000

META_RE = re.compile(r"<meta\b[^>]*>", re.I)
ATTR_RE = re.compile(r"""([A-Za-z:_.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""")
CHARSET_RE = re.compile(r"charset=([\w-]+)", re.I)
IMAGE_KEYS = ("og:image", "twitter:image", "og:image:secure_url")


def item_key(day, url, title):
    seed = "{}|{}".format(day, url or title)
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def load_generic():
    patterns = []
    if os.path.isfile(GENERIC_IMAGES):
        with open(GENERIC_IMAGES, encoding="utf-8") as stream:
            for line in stream:
                line = line.split("#", 1)[0].strip()
                if line:
                    patterns.append(line.lower())
    return patterns


def is_generic(url, patterns):
    low = (url or "").lower()
    return any(pattern in low for pattern in patterns)


# --------------------------------------------------------------------------
# 抓取
# --------------------------------------------------------------------------


def fetch_page(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=LINK_TIMEOUT) as resp:
        ctype = resp.headers.get("Content-Type", "")
        if "html" not in ctype.lower() and ctype:
            return "", resp.geturl()
        raw = resp.read(PAGE_BYTES)
        match = CHARSET_RE.search(ctype)
        encoding = match.group(1) if match else "utf-8"
        try:
            text = raw.decode(encoding, "replace")
        except LookupError:
            text = raw.decode("utf-8", "replace")
        return text, resp.geturl()


def meta_images(html):
    """按 og:image → twitter:image → og:image:secure_url 的顺序返回候选。"""
    found = {}
    for tag in META_RE.findall(html or ""):
        attrs = {}
        for match in ATTR_RE.finditer(tag):
            value = match.group(2) or match.group(3) or match.group(4) or ""
            attrs[match.group(1).lower()] = value
        key = (attrs.get("property") or attrs.get("name") or "").strip().lower()
        content = (attrs.get("content") or "").strip()
        if key in IMAGE_KEYS and content and key not in found:
            found[key] = content
    return [found[key] for key in IMAGE_KEYS if key in found]


def image_ok(url):
    """图片地址必须是 https、返回 200 且 content-type 是 image/*。"""
    if not url.lower().startswith("https://"):
        return False
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=LINK_TIMEOUT) as resp:
                status = getattr(resp, "status", resp.getcode())
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if method == "GET":
                    resp.read(1024)
                return status == 200 and ctype.startswith("image/")
        except urllib.error.HTTPError as exc:
            if method == "HEAD" and exc.code in (400, 403, 405, 406, 501):
                continue
            return False
        except Exception:  # noqa: BLE001
            return False
    return False


def find_image(page_url, patterns):
    """返回一个可用的题图地址，找不到返回空串。"""
    if not page_url:
        return ""
    try:
        html, final = fetch_page(page_url)
    except Exception:  # noqa: BLE001 - 抓不到就算没有配图
        return ""
    for raw in meta_images(html):
        candidate = strip_tracking(urllib.parse.urljoin(final or page_url, raw.strip()))
        if not candidate.lower().startswith("https://"):
            continue
        if is_generic(candidate, patterns):
            continue
        if image_ok(candidate):
            return candidate
    return ""


# --------------------------------------------------------------------------
# 批次文件
# --------------------------------------------------------------------------


INLINE_TAGS_RE = re.compile(r'"tags": \[\n(\s+[^\[\]]*?)\n\s+\]')
INLINE_STYLE_RE = re.compile(r'"tags": \[[^\n\]]')


def load_batch(path):
    with open(path, encoding="utf-8") as stream:
        raw = stream.read()
    return json.loads(raw), bool(INLINE_STYLE_RE.search(raw))


def collapse_tags(text):
    def repl(match):
        items = [line.strip().rstrip(",") for line in match.group(1).splitlines() if line.strip()]
        return '"tags": [' + ", ".join(items) + "]"
    return INLINE_TAGS_RE.sub(repl, text)


def save_batch(path, payload, inline_tags=False):
    """按文件原本的写法保存：两空格缩进、不转义中文、结尾换行。"""
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if inline_tags:
        text = collapse_tags(text)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(text + "\n")


def enrich(path, cache, patterns, dry_run=False):
    payload, inline_tags = load_batch(path)
    day = str(payload.get("date") or os.path.basename(path)[:10])
    items = payload.get("items") or []

    cache.resolve([item.get("url") for item in items if item.get("url")])

    changed, dead = 0, []
    for item in items:
        url = (item.get("url") or "").strip()
        if not url:
            continue
        final, is_dead = cache.final(url)
        if final and final != url:
            item["url"] = final
            changed += 1
        if is_dead:
            dead.append(item["url"])

    need = [item for item in items
            if int(item.get("tier") or 0) == 1 and not (item.get("image") or "").strip()
            and (item.get("url") or "").strip()]
    filled = 0
    if need:
        with ThreadPoolExecutor(max_workers=IMAGE_WORKERS) as pool:
            images = list(pool.map(lambda item: find_image(item["url"], patterns), need))
        for item, image in zip(need, images):
            if image:
                item["image"] = image
                filled += 1

    missing = [item for item in items
               if int(item.get("tier") or 0) == 1 and not (item.get("image") or "").strip()]
    if not dry_run and (changed or filled):
        save_batch(path, payload, inline_tags=inline_tags)
    return {
        "path": path, "date": day, "items": len(items),
        "changed": changed, "dead": dead, "filled": filled,
        "missing": [{"date": day,
                     "key": item_key(day, (item.get("url") or "").strip(), item.get("title") or ""),
                     "title": item.get("title") or "",
                     "url": (item.get("url") or "").strip()} for item in missing],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="补全博览批次文件的链接与一档配图")
    parser.add_argument("files", nargs="+", help="批次文件路径 data/info/YYYY-MM-DD.json")
    parser.add_argument("--dry-run", action="store_true", help="只报告，不写回文件")
    parser.add_argument("--missing-images", metavar="FILE", help="把仍缺配图的一档条目追加成 JSONL")
    parser.add_argument("--refresh-links", action="store_true", help="忽略链接缓存重新解析")
    options = parser.parse_args(argv)

    missing_files = [path for path in options.files if not os.path.isfile(path)]
    if missing_files:
        print("文件不存在：" + ", ".join(missing_files), file=sys.stderr)
        return 2

    cache = LinkCache(refresh=options.refresh_links)
    patterns = load_generic()
    reports = [enrich(path, cache, patterns, dry_run=options.dry_run) for path in sorted(options.files)]
    cache.save()

    if options.missing_images:
        rows = [row for report in reports for row in report["missing"]]
        if rows and not options.dry_run:
            os.makedirs(os.path.dirname(os.path.abspath(options.missing_images)), exist_ok=True)
            with open(options.missing_images, "a", encoding="utf-8") as stream:
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    total = {"changed": 0, "dead": 0, "filled": 0, "missing": 0}
    for report in reports:
        total["changed"] += report["changed"]
        total["dead"] += len(report["dead"])
        total["filled"] += report["filled"]
        total["missing"] += len(report["missing"])
        print("%s  %2d 条：链接改写 %d、失效 %d；补图 %d、一档仍缺图 %d"
              % (report["date"], report["items"], report["changed"], len(report["dead"]),
                 report["filled"], len(report["missing"])))
        for url in report["dead"]:
            print("    失效：%s" % url)
    print("合计：链接改写 %d、失效 %d；补图 %d、一档仍缺图 %d%s"
          % (total["changed"], total["dead"], total["filled"], total["missing"],
             "（--dry-run，未写回）" if options.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
