#!/usr/bin/env python3
"""Archive PGNexus's public developer directory and emit an importable snapshot.

Run from the repository root: .venv/bin/python tools/hacker/collect.py
Each run gets its own directory. --output resumes a previous run without replacing
successful responses. No login, hidden API, or external personal-data crawl is used.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlencode, urljoin, urlsplit
from uuid import uuid4

from bs4 import BeautifulSoup
from PIL import Image, ImageOps
import requests


ORIGIN = "https://pgnexus.ai"
DIRECTORY_URL = ORIGIN + "/hacker-profiles"
SECTION_APIS = {
    "DiscussionsSection": ("discussions", "contributorId"),
    "PatchReportsSection": ("patch-reports", "contributorId"),
    "ActivityMentionsSection": ("activity-mentions", "name"),
    "SuggestedArticlesSection": ("suggestions", "userId"),
    "SandboxSection": ("sandbox", "userId"),
    "ReviewsSection": ("reviews", "userId"),
    "KnowledgePostsSection": ("knowledge-posts", "userId"),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def slugify(value):
    # This is PGNexus's actual slug rule, rather than transliteration.
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


class Archive:
    def __init__(self, root):
        self.root = root
        self.local = threading.local()

    def fetch(self, url, relative, required=True):
        path = self.root / relative
        meta_path = path.with_name(path.name + ".meta.json")
        if path.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text())
            data = path.read_bytes()
            if meta["url"] != url or meta["sha256"] != sha256(data).hexdigest():
                raise ValueError(f"Cached response changed: {relative}")
            return data, meta
        if not hasattr(self.local, "session"):
            self.local.session = requests.Session()
            self.local.session.headers["User-Agent"] = (
                "PGSQL.CC public developer directory archive (+https://pgsql.cc/)"
            )
        last_error = None
        for attempt in range(3 if required else 1):
            started = now()
            error_path = self.root / "errors" / f"{sha256(url.encode()).hexdigest()[:20]}-{uuid4().hex[:12]}"
            try:
                response = self.local.session.get(url, timeout=(20, 60) if required else (5, 10))
                body = response.content
                meta = {
                    "url": url,
                    "final_url": response.url,
                    "fetched_at": started,
                    "status": response.status_code,
                    "content_type": response.headers.get("Content-Type", ""),
                    "sha256": sha256(body).hexdigest(),
                    "bytes": len(body),
                    "path": relative,
                }
                if response.status_code == 200:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(body)
                    dump(meta_path, meta)
                    return body, meta
                last_error = f"HTTP {response.status_code}"
                dump(error_path.with_suffix(".json"), meta)
                error_path.with_suffix(".bin").write_bytes(body)
                # Permanent missing files need no repeated traffic.
                if response.status_code in (400, 401, 403, 404, 410):
                    break
            except requests.RequestException as exc:
                last_error = str(exc)
                dump(error_path.with_suffix(".json"), {
                    "url": url, "fetched_at": started, "error": last_error,
                })
            time.sleep(1 + attempt)
        if required:
            raise RuntimeError(f"{url}: {last_error}")
        return None, {"url": url, "error": last_error}


def flight_sections(html):
    """Decode embedded public React Flight props without executing JavaScript."""
    soup = BeautifulSoup(html, "html.parser")
    chunks = []
    for tag in soup.find_all("script"):
        text = tag.get_text()
        prefix = "self.__next_f.push("
        if text.startswith(prefix):
            packet = json.loads(text[len(prefix):-1])
            if len(packet) > 1 and isinstance(packet[1], str):
                chunks.append(packet[1])
    flight = "".join(chunks)
    records, names = {}, {}
    # Flight's T records carry a hexadecimal UTF-8 byte length and need not end
    # with a newline. Parsing by lines alone silently loses the following record.
    wire = flight.encode("utf-8")
    position = 0
    while position < len(wire):
        header = re.match(rb"([0-9a-f]+):", wire[position:])
        if not header:
            position += 1
            continue
        key = header.group(1).decode()
        position += header.end()
        text_header = re.match(rb"T([0-9a-f]+),", wire[position:])
        if text_header:
            position += text_header.end()
            length = int(text_header.group(1), 16)
            records[key] = wire[position:position + length].decode("utf-8")
            position += length
            continue
        end = wire.find(b"\n", position)
        if end == -1:
            end = len(wire)
        payload = wire[position:end].decode("utf-8")
        position = end + 1
        kind = "I" if payload.startswith("I") else ""
        try:
            value = json.loads(payload[len(kind):])
        except ValueError:
            continue
        records[key] = value
        if kind == "I" and isinstance(value, list) and isinstance(value[-1], str):
            names["$L" + key] = value[-1]

    def resolve(value, seen=frozenset()):
        if isinstance(value, str):
            if value.startswith("$D"):
                return value[2:]
            if value.startswith("$$"):
                return value[1:]
            if re.fullmatch(r"\$[0-9a-f]+", value) and value[1:] in records and value not in seen:
                return resolve(records[value[1:]], seen | {value})
        elif isinstance(value, list):
            return [resolve(child, seen) for child in value]
        elif isinstance(value, dict):
            return {key: resolve(child, seen) for key, child in value.items()}
        return value
    sections = {}

    def walk(value):
        if isinstance(value, list):
            if len(value) == 4 and value[0] == "$" and isinstance(value[1], str):
                component = names.get(value[1])
                if component and (component.endswith("Section") or component in {"ProfileHero", "DiscussionPeers", "RelatedContributors"}) and isinstance(value[3], dict):
                    sections[component] = resolve(value[3])
            for child in value:
                walk(child)
        elif isinstance(value, dict):
            for child in value.values():
                walk(child)

    for record in records.values():
        walk(record)
    if "ProfileHero" not in sections:
        raise ValueError("Public page does not contain ProfileHero data")
    return soup, sections, flight


def archive_assets(archive, html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", src=True):
        src = tag["src"]
        if src.startswith("/_next/") and ("hacker-profiles/" in src or "/9821-" in src or "/app/c/" in src or "/app/u/" in src):
            archive.fetch(urljoin(ORIGIN, src), "raw/scripts/" + src.rsplit("/", 1)[-1])


def collect_person(archive, item):
    source_id = str(item["id"])
    slug = (slugify(item["name"]) or "developer")[:140] + "-" + source_id
    if item.get("is_synced") and item.get("user_id"):
        source_path = "/u/" + (slugify(item.get("user_name")) or "user") + "-" + str(item["user_id"])
    else:
        source_path = "/c/" + slugify(item["name"]) + "-" + source_id
    source_url = ORIGIN + source_path
    html, meta = archive.fetch(source_url, f"raw/details/{source_id}.html")
    soup, sections, flight = flight_sections(html)
    dump(archive.root / f"parsed/{source_id}-sections.json", sections)
    (archive.root / f"raw/details/{source_id}.flight.txt").write_text(flight)
    profile = sections["ProfileHero"]["profile"]
    detail = sections["ProfileHero"]
    for name, section in sections.items():
        if name not in SECTION_APIS and section.get("total", 0) > len(section.get("initialItems", [])):
            raise ValueError(f"Unknown paginated section {name}; add its public API before continuing")
    # Preserve the complete paginated public sections, not only the five SSR rows.
    for name, (endpoint, identity_key) in SECTION_APIS.items():
        section = sections.get(name)
        if not section:
            continue
        initial = section.get("initialItems", [])
        expected = section.get("total", len(initial))
        identity = section.get(identity_key)
        items = list(initial)
        responses = []
        while len(items) < expected and identity is not None:
            offset = len(items)
            url = ORIGIN + "/api/profile/" + endpoint + "?" + urlencode({identity_key: identity, "limit": 100, "offset": offset})
            body, response_meta = archive.fetch(url, f"raw/sections/{source_id}/{endpoint}-{offset:05}.json")
            payload = json.loads(body)
            responses.append({"path": response_meta["path"], "payload": payload})
            new = payload.get("items", [])
            if not new:
                raise ValueError(f"Pagination ended before total: {source_id}/{name}: {len(items)}/{expected}")
            items.extend(new)
        section["items"] = items
        section["responses"] = responses
        section["collected_count"] = len(items)
    links = []
    for field, label in (("github_profile", "GitHub"), ("linkedin_profile", "LinkedIn"), ("website", "个人网站"), ("website_url", "个人网站"), ("twitter_profile", "X / Twitter")):
        value = profile.get(field) or item.get(field)
        if value:
            links.append({"label": label, "url": value, "source_url": source_url})
    emails = []
    # Only explicit profile fields and mailto links in the profile hero are contacts.
    for key in ("email", "public_email", "contact_email"):
        if profile.get(key):
            emails.append({"email": profile[key], "source_url": source_url})
    page_main = soup.find("main") or soup
    page_links = [{"label": a.get_text(" ", strip=True), "url": urljoin(source_url, a["href"])} for a in page_main.find_all("a", href=True)]
    avatar = None
    avatar_sources = list(dict.fromkeys(x for x in (profile.get("imgurl"), item.get("imgurl"), profile.get("image")) if x))
    avatar_errors = []
    for index, url in enumerate(avatar_sources):
        raw, raw_meta = archive.fetch(url, f"raw/avatars/{source_id}-{index}.bin", required=False)
        if raw is None:
            avatar_errors.append(raw_meta)
            continue
        try:
            if urlsplit(url).hostname == "static.licdn.com" and b"<svg" in raw[:1000]:
                avatar_errors.append({"url": url, "error": "Source uses a generic LinkedIn SVG placeholder, not a portrait", "raw_path": raw_meta["path"]})
                continue
            with Image.open(BytesIO(raw)) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail((512, 512))
                image = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P") else "RGB")
                target = BytesIO()
                image.save(target, "WEBP", quality=88, method=6)
                data = target.getvalue()
                path = f"avatars/{source_id}.webp"
                (archive.root / "avatars").mkdir(exist_ok=True)
                (archive.root / path).write_bytes(data)
                avatar = {"path": path, "sha256": sha256(data).hexdigest(), "content_type": "image/webp", "source_url": url, "raw_path": raw_meta["path"], "width": image.width, "height": image.height}
                break
        except (ValueError, OSError) as exc:
            avatar_errors.append({"url": url, "error": type(exc).__name__, "raw_path": raw_meta["path"]})
    record = {
        "source_id": source_id, "slug": slug, "name": profile.get("name") or item["name"],
        "organization": profile.get("organization") or item.get("organization") or "",
        "country": profile.get("country") or item.get("country") or "",
        "bio": profile.get("bio") or item.get("bio") or "",
        "source_url": source_url,
        "data": {"list": item, "detail": detail, "sections": sections, "emails": emails, "links": links, "source_url": source_url, "page_text": page_main.get_text("\n", strip=True), "page_links": page_links, "avatar_sources": avatar_sources, "avatar_errors": avatar_errors},
        "avatar": avatar,
    }
    dump(archive.root / f"parsed/{source_id}.json", record)
    return record


def manifest(root):
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            body = path.read_bytes()
            files.append({"path": str(path.relative_to(root)), "bytes": len(body), "sha256": sha256(body).hexdigest()})
    dump(root / "manifest.json", {"created_at": now(), "files": files})


def archive_section_media(archive, profiles):
    """Keep images displayed in a person's content cards; do not crawl articles."""
    cache, profile_urls = {}, {}
    for profile in profiles:
        urls = set()
        detail = profile["data"]["detail"].get("profile", {})
        if detail.get("banner_url"):
            urls.add(detail["banner_url"])
        for name in SECTION_APIS:
            for item in profile["data"]["sections"].get(name, {}).get("items", []):
                for field in ("imgurl", "feature_image_url", "image_url", "banner_url"):
                    if item.get(field):
                        urls.add(item[field])
        profile_urls[profile["source_id"]] = []
        for url in sorted(urls):
            if urlsplit(url).scheme not in ("http", "https"):
                continue
            cache[url] = None
            profile_urls[profile["source_id"]].append(url)
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(archive.fetch, url, "raw/assets/" + sha256(url.encode()).hexdigest() + ".bin", False): url for url in cache}
        for job in as_completed(jobs):
            _, meta = job.result()
            cache[jobs[job]] = meta
    for profile in profiles:
        profile["data"]["assets"] = [cache[url] for url in profile_urls[profile["source_id"]]]
    return cache


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Use or resume this archive directory")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    root = args.output or Path("tmp/hacker") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root.mkdir(parents=True, exist_ok=True)
    archive = Archive(root)
    html, start_meta = archive.fetch(DIRECTORY_URL, "raw/directory.html")
    archive_assets(archive, html)
    listed = []
    expected = None
    while True:
        offset = len(listed)
        url = ORIGIN + "/api/contributors/profiles?" + urlencode({"limit": 40, "offset": offset})
        body, _ = archive.fetch(url, f"raw/list-{offset:05}.json")
        response = json.loads(body)
        if expected is None:
            expected = response["total"]
        elif expected != response["total"]:
            raise ValueError("Directory changed during collection; retry with a new archive")
        listed.extend(response["profiles"])
        if not response.get("hasMore"):
            break
        if not response["profiles"]:
            raise ValueError("Empty listing page with hasMore=true")
    if len(listed) != expected or len({str(p["id"]) for p in listed}) != expected:
        raise ValueError("Listing count/identity mismatch")
    print(f"Archive: {root}; directory has {expected} profiles", flush=True)
    profiles, failures = {}, []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as pool:
        jobs = {pool.submit(collect_person, archive, item): item for item in listed}
        for job in as_completed(jobs):
            item = jobs[job]
            try:
                profile = job.result()
                profiles[str(item["id"])] = profile
                print(f"{len(profiles):3}/{expected}: {profile['name']} avatar={'yes' if profile['avatar'] else 'NO'}", flush=True)
            except Exception as exc:
                failures.append({"id": str(item["id"]), "name": item["name"], "error": str(exc)})
                print(f"FAILED: {item['name']}: {exc}", flush=True)
    if profiles:
        first = next(iter(profiles))
        archive_assets(archive, (root / f"raw/details/{first}.html").read_bytes())
        for profile in profiles.values():
            if profile["data"]["list"].get("is_synced"):
                archive_assets(archive, (root / f"raw/details/{profile['source_id']}.html").read_bytes())
    ordered = [profiles[str(item["id"])] for item in listed if str(item["id"]) in profiles]
    assets = archive_section_media(archive, ordered)
    snapshot = {"format": 1, "fetched_at": start_meta["fetched_at"], "source_url": DIRECTORY_URL, "expected_count": expected, "profiles": ordered}
    dump(root / "profiles.json", snapshot)
    report = {"expected_count": expected, "collected_count": len(profiles), "avatars": sum(bool(p["avatar"]) for p in profiles.values()), "failures": failures, "missing_avatars": [{"id": p["source_id"], "name": p["name"], "errors": p["data"]["avatar_errors"]} for p in profiles.values() if not p["avatar"]], "sections": {name: sum(len(p["data"]["sections"].get(name, {}).get("items", [])) for p in profiles.values()) for name in SECTION_APIS}}
    report["content_assets"] = {"count": len(assets), "failed": [v for v in assets.values() if v.get("error")]}
    dump(root / "report.json", report)
    manifest(root)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
