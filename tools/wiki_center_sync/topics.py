"""Build Chinese topic/lock snapshots from a frozen native center dataset.

This module reads files only. Native Django importers remain the only writers.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import gzip
import hashlib
import html
from urllib.parse import urlsplit, urlunsplit
import json
from pathlib import Path
import re

DATASET_HASH = "7c31b524dfe136022d39a6ae8dcfac6b3bbd5f8fdaf422536599981252aff0c9"
TABLES = {
    "type": "data_type", "indexam": "index_am", "plan": "plan_node",
    "operator": "pg_operator_entry", "opclass": "operator_class",
    "fdw": "foreign_data_wrapper", "tableam": "table_am", "psql": "psql_command",
    "tool": "command_tool", "conn": "connection_parameter", "metric": "statistics_metric",
    "storage": "storage_structure", "protocol": "protocol_message",
    "language": "procedural_language", "fts": "text_search_component",
    "auth": "authentication_method", "locale": "collation_encoding",
    "decode": "logical_decoding_plugin", "hook": "hook", "relopts": "relopt",
    "role": "predefined_role", "oid": "oid_type", "lock": "lock_mode",
}
TOPIC_FIELDS = ("slug", "name", "name_zh", "category", "summary", "aliases", "versions")
DISPLAY_FIELDS = {"description", "description_zh", "description_zh_html", "manual_html",
                  "manual_language", "facts", "tables", "sections", "related", "center_zh",
                  "localization", "capabilities", "storage_options", "collection_tables",
                  "summary", "commands"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def write_json(path, value):
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    Path(path).write_bytes(gzip.compress(raw, compresslevel=3, mtime=0) if str(path).endswith(".gz") else raw)


def localized_url(value):
    """Change only this site's Chinese route prefix; retain original evidence URLs."""
    if not isinstance(value, str):
        return value
    if value.startswith("https://pg.center/zh/"):
        value = value[len("https://pg.center"):]
    if value.startswith(("/zh/docs/", "/zh/wiki/", "/zh/e/")):
        return value[3:]
    return value


def localized_links(value):
    if isinstance(value, list):
        return [localized_links(item) for item in value]
    if isinstance(value, dict):
        return {key: localized_url(item) if key in ("url", "href") else localized_links(item)
                for key, item in value.items()}
    return value


def canonical_text(row):
    text = row["text"]
    if text.get("locale") != "zh-Hans" or text.get("version") != row["version"]:
        raise ValueError("Expected exact-version Chinese text: " + repr((row["collection"], row["key"], row["version"])))
    if not text.get("body_html") or not text.get("content_hash"):
        raise ValueError("Missing canonical Chinese text or fingerprint")
    return {
        **deepcopy(text),
        "body_html": text["body_html"], "summary": text.get("summary", ""),
        "payload": deepcopy(text.get("payload", {})),
        "source": {"dataset_hash": DATASET_HASH, "collection": row["collection"],
                   "key": row["key"], "version": row["version"],
                   "source_database": text["source_database"],
                   "source_revision": text.get("source_revision", ""),
                   "text_hash": text["content_hash"], "locale": text["locale"]},
        "body_sha256": hashlib.sha256(text["body_html"].encode()).hexdigest(),
    }


def check_equal(before, after, path):
    if before != after:
        raise ValueError("Technical field mismatch: " + path)


def localized_capabilities(base, chinese, path):
    by_key = {item["key"]: item for item in chinese}
    check_equal(set(by_key), {item["key"] for item in base}, path + ".keys")
    result = deepcopy(base)
    for item in result:
        translated = by_key[item["key"]]
        check_equal(item["state"], translated["state"], path + ".state")
        for key in ("label", "value", "note"):
            item[key] = translated[key]
    return result


def localize_snapshot(kind, version, base, chinese, canonical):
    result = deepcopy(base)
    body = canonical_text(canonical)
    payload = body["payload"]
    summary = body["summary"]
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Canonical summary is empty")
    result["description"] = [summary]
    result["description_zh"] = summary
    result["description_zh_html"] = body["body_html"]
    result["center_zh"] = body
    # Keep canonical HTML separate: it includes both manual quotations and authored
    # guidance, and must not be presented as an entirely original manual excerpt.
    result["manual_language"] = "zh"
    if kind != "lock":
        for field in ("facts", "tables", "sections", "related"):
            if field in payload:
                value = payload[field]
            elif field + "_zh" in base:
                value = base[field + "_zh"]
            else:
                value = chinese.get(field, base.get(field, []))
            result[field] = localized_links(deepcopy(value))
        if "manual_html" in result:
            # Existing readers use center_zh when present; retaining the old manual
            # in the evidence archive avoids a contradictory second body on screen.
            result["manual_html"] = ""
        if "collection_tables" in base:
            # These are a separate catalog observation; translating headers/caption
            # must not replace the catalogued version/compatibility facts.
            translated = chinese.get("collection_tables", [])
            check_equal([t["key"] for t in base["collection_tables"]],
                        [t["key"] for t in translated], kind + ".collection_tables")
            result["collection_tables"] = deepcopy(base["collection_tables"])
            for table, zh in zip(result["collection_tables"], translated):
                check_equal(len(table["rows"]), len(zh["rows"]), kind + ".catalog_rows")
                markers = {"Unknown": "未知", "Not recorded": "未记录"}
                prose = {"description", "scope", "capability", "detail", "state"}
                for source_row, zh_row in zip(table["rows"], zh["rows"]):
                    check_equal(set(source_row), set(zh_row), kind + ".catalog_keys")
                    for field, value in source_row.items():
                        if field not in prose:
                            normalized = markers.get(value, value) if isinstance(value, str) else value
                            check_equal(normalized, zh_row[field], kind + ".catalog." + field)
                    source_row.update(deepcopy(zh_row))
                check_equal([x["key"] for x in table["columns"]],
                            [x["key"] for x in zh["columns"]], kind + ".catalog_columns")
                for field in ("title", "caption", "columns"):
                    if field in zh:
                        table[field] = deepcopy(zh[field])
        if kind == "indexam":
            result["capabilities"] = localized_capabilities(base["capabilities"], chinese["capabilities"], "indexam")
            options = {x["name"]: x for x in chinese["storage_options"]}
            check_equal(set(options), {x["name"] for x in base["storage_options"]}, "indexam.storage_options")
            for option in result["storage_options"]:
                option["description"] = deepcopy(options[option["name"]]["description"])
        result["localization"] = deepcopy(chinese.get("localization", {}))
        result["localization"].update(language="zh", source_language="en",
                                      canonical_center_text_hash=body["source"]["text_hash"])
    else:
        result["summary"] = summary
        check_equal(set(base["conflicts"]), set(chinese["conflicts"]), "lock.conflicts")
        # Match the same ordered technical command inventory. Translation changes
        # neither its stable variant ID nor its original upstream evidence.
        def command_key(command):
            return (command["slug"], command.get("source", {}).get("path"),
                    re.findall(r"\b[A-Z][A-Z0-9_]+\b", command["label"]))
        check_equal([command_key(c) for c in base["commands"]],
                    [command_key(c) for c in chinese["commands"]], "lock.command_identity")
        for command, zh in zip(result["commands"], chinese["commands"]):
            for field in ("label", "note"):
                command[field] = zh[field]
    # Every other field, including comparison data, source pins, signatures,
    # source catalog values and runtime flags, must remain byte-for-byte equivalent.
    for key, value in base.items():
        if key not in DISPLAY_FIELDS:
            check_equal(value, result[key], kind + "@" + version + "." + key)
    return result



def revalidate_index_evidence(base, adapted, replay):
    """Close inherited nested-pin drift only after exact same-version quote checks."""
    check_equal(base["release"], replay["release"], "indexam replay release")
    check_equal(base["sources"], replay["sources"], "indexam replay source pages")
    changes = []
    check_equal(len(base["capabilities"]), len(replay["capabilities"]), "indexam replay capability count")
    for old, new, target in zip(base["capabilities"], replay["capabilities"], adapted["capabilities"]):
        for field in ("key", "state"):
            check_equal(old[field], new[field], "indexam replay " + field)
        check_equal(len(old["evidence"]), len(new["evidence"]), "indexam replay evidence count")
        for index, (evidence, current) in enumerate(zip(old["evidence"], new["evidence"])):
            for field in ("quote", "file", "anchor", "url"):
                check_equal(evidence.get(field), current.get(field), "indexam replay " + field)
            if evidence != current:
                updated = deepcopy(current)
                updated["prior_evidence"] = deepcopy(evidence)
                updated["revalidation"] = {"kind": "exact-same-version-quote-and-state-replay", "runtime_rerun": False}
                target["evidence"][index] = updated
                changes.append({"field": "capabilities." + old["key"] + ".evidence." + str(index),
                                "before_sha256": evidence.get("sha256"), "after_sha256": current.get("sha256"),
                                "quote_sha256": digest(evidence["quote"])})
    check_equal(len(base["storage_options"]), len(replay["storage_options"]), "indexam replay option count")
    for old, new, target in zip(base["storage_options"], replay["storage_options"], adapted["storage_options"]):
        for field in ("name", "description", "url"):
            check_equal(old.get(field), new.get(field), "indexam replay option " + field)
        if old["source"] != new["source"]:
            target["source"] = deepcopy(new["source"])
            target["source"]["prior_evidence"] = deepcopy(old["source"])
            target["source"]["revalidation"] = {"kind": "exact-same-version-option-description-replay", "runtime_rerun": False}
            changes.append({"field": "storage_options." + old["name"] + ".source",
                            "before_sha256": old["source"].get("sha256"),
                            "after_sha256": new["source"].get("sha256"),
                            "description_sha256": digest(old["description"])})
    return changes


def manual_link_map(body, pages, cache):
    mappings, issues = {}, []
    for original in set(html.unescape(x) for x in re.findall(r'(?:href|src)=["\']([^"\']+)["\']', body)):
        local = localized_url(original)
        parsed = urlsplit(local)
        if parsed.netloc or not parsed.path.startswith("/docs/"):
            continue
        if local in cache:
            mapped, problem = cache[local]
        else:
            parts = parsed.path.split("/", 3)
            mapped, problem = local, None
            if len(parts) < 4 or not parts[3]:
                cache[local] = (mapped, problem)
                continue
            version, filename = parts[2:]
            page = pages.get((version, filename))
            if page is None:
                choices = [(name, row) for (v, name), row in pages.items()
                           if v == version and name.casefold() == filename.casefold()]
                if len(choices) == 1:
                    filename, page = choices[0]
            if page is None:
                problem = "page-not-in-fixed-target-manuals"
            else:
                fragment = parsed.fragment
                if fragment and fragment not in page["anchors"]:
                    matches = [anchor for anchor in page["anchors"] if anchor.casefold() == fragment.casefold()]
                    if len(matches) == 1:
                        fragment = matches[0]
                    else:
                        problem = "anchor-not-in-fixed-target-page"
                mapped = urlunsplit(parsed._replace(path="/docs/" + version + "/" + filename, fragment=fragment))
            cache[local] = (mapped, problem)
        if problem:
            issues.append({"url": original, "local_url": local, "reason": problem})
        elif mapped != original:
            mappings[original] = mapped
    return mappings, issues

def build(source_root, target_root, output_dir):
    source_root, target_root, output_dir = map(Path, (source_root, target_root, output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise ValueError("Output directory must be empty")
    manifest = json.loads((source_root / "manifest.json").read_text())
    if manifest.get("dataset_hash") != DATASET_HASH or manifest.get("dataset_id") != 3:
        raise ValueError("Source manifest is not the accepted center dataset")
    canonical_path = source_root / "canonical.jsonl.gz"
    source_files = [canonical_path] + [source_root / "raw" / db / (table + ".jsonl.gz")
                                      for table in TABLES.values() for db in ("center", "pgweb")]
    for path in source_files:
        relative = str(path.relative_to(source_root))
        if manifest["files"][relative]["sha256"] != file_sha(path):
            raise ValueError("Source file changed: " + relative)
    canonical = {}
    for row in read_rows(canonical_path):
        if row["collection"] not in TABLES:
            continue
        key = (row["collection"], row["key"], row["version"])
        if key in canonical:
            raise ValueError("Duplicate canonical identity")
        canonical[key] = row
    support = source_root.parent / "support" / "indexam-replay.json.gz"
    support_manifest = json.loads((support.parent / "indexam-replay-manifest.json").read_text())
    check_equal(file_sha(support), support_manifest["sha256"], "replay support sha256")
    replay = json.loads(gzip.decompress(support.read_bytes()))["definitions"]
    target_manifest = json.loads((target_root / "manifest.json").read_text())
    manual_path = target_root / "manual-pages.jsonl.gz"
    check_equal(file_sha(manual_path), target_manifest["files"][manual_path.name]["sha256"], "target manual coordinates")
    pages = {(row["version"], row["file"]): row for row in read_rows(manual_path)}
    link_cache, link_issues, metadata_changes = {}, [], []
    reports, receipts, files = {}, [], []
    source_hashes = {str(canonical_path): file_sha(canonical_path), str(support): file_sha(support),
                     str(manual_path): file_sha(manual_path)}
    for kind, table in TABLES.items():
        paths = {db: source_root / "raw" / db / (table + ".jsonl.gz") for db in ("center", "pgweb")}
        raw = {db: {row["slug"]: row for row in read_rows(path)} for db, path in paths.items()}
        target_path = target_root / (table + ".jsonl.gz")
        check_equal(file_sha(target_path), target_manifest["files"][target_path.name]["sha256"], "target " + table)
        target = {row["slug"]: row for row in read_rows(target_path)}
        for path in (*paths.values(), target_path):
            source_hashes[str(path)] = file_sha(path)
        items, releases, count = [], {}, 0
        for slug, original in sorted(raw["center"].items()):
            zh = raw["pgweb"].get(slug)
            if zh is None:
                raise ValueError("Missing reviewed Chinese source row: " + kind + "/" + slug)
            fields = TOPIC_FIELDS if kind != "lock" else ("slug", "name", "name_zh", "abbrev", "scope", "summary", "position", "versions")
            item = {field: deepcopy(original[field]) for field in fields}
            for field in ("name_zh", "category"):
                if field in fields and zh.get(field):
                    item[field] = zh[field]
            for version, snapshot in original["versions"].items():
                key = (kind, slug, version)
                selected = canonical[key]
                if selected["definition"]["source_database"] != "center":
                    raise ValueError("Canonical fact source differs from center archive")
                adapted = localize_snapshot(kind, version, snapshot, zh["versions"][version], selected)
                if kind == "indexam" and version in replay:
                    for change in revalidate_index_evidence(snapshot, adapted, replay[version][slug]):
                        metadata_changes.append(dict(change, collection=kind, key=slug, version=version,
                                                     replay_support_sha256=file_sha(support)))
                link_map, issues = manual_link_map(adapted["center_zh"]["body_html"], pages, link_cache)
                adapted["center_zh"]["link_map"] = link_map
                link_issues.extend(dict(issue, collection=kind, key=slug, version=version) for issue in issues)
                item["versions"][version] = adapted
                release = snapshot["release"] if kind != "lock" else snapshot["provenance"]
                if version in releases:
                    check_equal(releases[version], release, kind + " release " + version)
                releases[version] = deepcopy(release)
                receipts.append({"collection": kind, "key": slug, "version": version,
                                 "source_text_hash": selected["text"]["content_hash"],
                                 "body_sha256": adapted["center_zh"]["body_sha256"],
                                 "source_snapshot_sha256": digest(snapshot),
                                 "adapted_snapshot_sha256": digest(adapted),
                                 "target_before_sha256": digest(target.get(slug, {}).get("versions", {}).get(version)),
                                 "changed_fields": sorted(field for field in set(adapted) | set(target.get(slug, {}).get("versions", {}).get(version, {}))
                                                          if adapted.get(field) != target.get(slug, {}).get("versions", {}).get(version, {}).get(field)),
                                 "runtime_rerun": False})
                count += 1
            latest = max(item["versions"], key=lambda value: tuple(map(int, value.split("."))))
            item["summary"] = item["versions"][latest]["center_zh"]["summary"]
            items.append(item)
        ordered = [releases[v] for v in sorted(releases, key=lambda value: tuple(map(int, value.split("."))))]
        if kind == "lock":
            data = {"format": 1, "default_major": "18", "versions": ordered, "modes": items}
        else:
            data = {"format": 1, "kind": kind, "language": "zh", "releases": ordered, "items": items}
            if kind == "plan":
                data["inventories"] = {v: sorted(s["node_tag"].removeprefix("T_") for item in items
                                                if (s := item["versions"].get(v))) for v in releases}
        path = output_dir / (kind + ".json.gz")
        write_json(path, data)
        files.append({"kind": kind, "path": str(path), "sha256": file_sha(path)})
        reports[kind] = {"entities": len(items), "versions": count,
                         "added_entities": sorted(set(raw["center"]) - set(target)),
                         "target_only_entities": sorted(set(target) - set(raw["center"]))}
    check_equal(set(canonical), {(r["collection"], r["key"], r["version"]) for r in receipts}, "canonical coverage")
    receipt_path = output_dir / "receipts.jsonl.gz"
    receipt_path.write_bytes(gzip.compress("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in receipts).encode(), mtime=0))
    write_json(output_dir / "source-metadata-corrections.json", metadata_changes)
    write_json(output_dir / "manual-link-issues.json", link_issues)
    report = {"source_dataset_hash": DATASET_HASH, "collections": reports,
              "entities": sum(x["entities"] for x in reports.values()),
              "versions": len(receipts), "canonical_bodies_preserved": len(receipts),
              "nested_metadata_corrections": len(metadata_changes), "manual_link_issues": len(link_issues),
              "code_sha256": file_sha(__file__),
              "files": files, "inputs": source_hashes,
              "receipts_sha256": file_sha(receipt_path), "database_writes": False,
              "native_import_validation": "required separately before publication"}
    write_json(output_dir / "report.json", report)
    return report
