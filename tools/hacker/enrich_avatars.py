#!/usr/bin/env python3
"""Supplement broken PGNexus portraits with verified public professional sources."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from PIL import Image, ImageOps

from collect import Archive, archive_section_media, dump, manifest


# Each identity was checked against the named professional page and its photo.
# These are source links, never a guessed avatar path or a name-only image search.
SOURCES = {
    "33": {
        "name": "Andres Freund", "label": "PGConf NYC 讲者资料",
        "page": "https://postgresql.us/events/pgconfus2025/schedule/speaker/79-andres-freund/",
        "selector": 'img[alt="Photo of Andres Freund"]',
    },
    "44": {
        "name": "Laurenz Albe", "label": "GitHub",
        "page": "https://github.com/laurenz",
        "selector": 'img[alt="View laurenz\'s full-sized avatar"]',
    },
    "45": {
        "name": "Richard Guo", "label": "PGCon 讲者资料",
        "page": "https://www.pgcon.org/2020/schedule/speaker/38-richard-guo/",
        "selector": 'img[alt="Photo of Richard Guo"]',
    },
    "66": {
        "name": "Dilip Kumar", "label": "PGConf India 讲者资料",
        "page": "https://live.pgconf.in/speakers/dilip-kumar",
        # This exact path occurs in the public Flight img element with
        # alt="Dilip Kumar" and the same LinkedIn identity as PGNexus.
        "image_path": "/api/uploads/orgs/1/speakers/dilip-kumar.png",
    },
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-content-media", action="store_true", help="Write the portrait supplement without waiting for card images")
    args = parser.parse_args()
    if args.input.resolve().parent != args.output.resolve().parent:
        parser.error("Keep the output alongside the input so relative assets remain valid")
    if args.input.resolve() == args.output.resolve():
        parser.error("Use a separate output to retain the original snapshot")
    root = args.input.parent
    archive = Archive(root)
    snapshot = json.loads(args.input.read_text())
    added, failures = [], []
    for profile in snapshot["profiles"]:
        source = SOURCES.get(profile["source_id"])
        if profile["avatar"] or source is None:
            continue
        if profile["name"] != source["name"]:
            raise ValueError("Source identity changed")
        raw, page_meta = archive.fetch(source["page"], f"raw/supplements/{profile['source_id']}.html", required=False)
        if raw is None:
            failures.append(page_meta)
            continue
        soup = BeautifulSoup(raw, "html.parser")
        if source["name"] not in raw.decode("utf-8"):
            raise ValueError("Source name missing from professional profile")
        if source.get("image_path"):
            image_path = source["image_path"]
            if image_path not in raw.decode("utf-8"):
                raise ValueError("Photo path no longer appears in source page")
        else:
            tag = soup.select_one(source["selector"])
            if tag is None:
                raise ValueError("Verified photo element no longer appears")
            image_path = tag["src"]
        image_url = urljoin(page_meta["final_url"], image_path)
        image_raw, image_meta = archive.fetch(image_url, f"raw/supplements/{profile['source_id']}-avatar.bin", required=False)
        if image_raw is None:
            failures.append(image_meta)
            continue
        with Image.open(BytesIO(image_raw)) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((512, 512))
            image = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P") else "RGB")
            output = BytesIO()
            image.save(output, "WEBP", quality=88, method=6)
            data = output.getvalue()
            path = f"avatars/{profile['source_id']}-supplement.webp"
            (root / path).write_bytes(data)
            profile["avatar"] = {"path": path, "sha256": sha256(data).hexdigest(), "content_type": "image/webp", "source_url": image_url, "source_page": source["page"], "raw_path": image_meta["path"], "width": image.width, "height": image.height}
        profile["data"].setdefault("public_sources", []).append({"kind": "portrait", "source_url": source["page"], "image_url": image_url, "fetched_at": page_meta["fetched_at"], "raw_path": page_meta["path"]})
        link = {"label": source["label"], "url": source["page"], "source_url": source["page"]}
        if all(value.get("url") != link["url"] for value in profile["data"]["links"]):
            profile["data"]["links"].append(link)
        added.append({"id": profile["source_id"], "name": profile["name"], "source": source["page"]})
        print(f"Supplemented {profile['name']}", flush=True)
    # Portraits are immediately reviewable even if optional external card images
    # are slow or refuse access. A later run can append their archive metadata.
    dump(args.output, snapshot)
    assets = {} if args.skip_content_media else archive_section_media(archive, snapshot["profiles"])
    dump(args.output, snapshot)
    report = {"profiles": len(snapshot["profiles"]), "avatars": sum(bool(p["avatar"]) for p in snapshot["profiles"]), "supplemented": added, "failures": failures, "missing_avatars": [{"id": p["source_id"], "name": p["name"], "errors": p["data"]["avatar_errors"]} for p in snapshot["profiles"] if not p["avatar"]], "content_assets": {"count": len(assets), "failed": [v for v in assets.values() if v.get("error")]}}
    dump(root / "supplement-report.json", report)
    manifest(root)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
