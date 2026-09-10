#!/usr/bin/env python3
"""Normalize GDELT 2.0 GKG archives for replay-safe BTC/ETH research."""
from __future__ import annotations
import argparse, csv, gzip, hashlib, json, re, zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

STRONG = re.compile(r"(?i)\b(?:bitcoin|btc|ethereum)\b")
ETH_CONTEXT = re.compile(r"(?i)\b(?:ethereum|eth(?:ereum)?|ether)\b")
TRACKING = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src",
            "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term"}

def canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in TRACKING and not k.lower().startswith("utm_")]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/",
                       urlencode(query), ""))

def parse_gdelt_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)

def relevance(fields: list[str]) -> str | None:
    searchable = "\t".join((fields[4], fields[7], fields[11], fields[12]))
    if STRONG.search(searchable):
        return "strong"
    if ETH_CONTEXT.search(searchable) and re.search(
        r"(?i)\b(?:crypto|blockchain|token|coin)\b", searchable
    ):
        return "contextual"
    return None

def clean(paths: list[Path], output: Path, *, cutoff: datetime | None = None,
          max_invalid_ratio: float = 0.05) -> dict:
    retrieved_at = datetime.now(timezone.utc)
    seen: set[str] = set()
    rows: list[list[str]] = []
    stats = {"archives": 0, "rows_seen": 0, "malformed": 0, "invalid_timestamp": 0,
             "invalid_url": 0, "future_seen": 0, "irrelevant": 0, "ambiguous": 0,
             "duplicates": 0, "rows_written": 0, "input_archives": []}
    for path in sorted(paths):
        stats["input_archives"].append({
            "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        })
        stats["archives"] += 1
        with zipfile.ZipFile(path) as archive:
            for raw in archive.open(archive.namelist()[0]):
                stats["rows_seen"] += 1
                fields = raw.decode("utf-8", "replace").rstrip("\n").split("\t")
                if len(fields) < 16:
                    stats["malformed"] += 1
                    continue
                try:
                    seen_at = parse_gdelt_time(fields[1])
                except ValueError:
                    stats["invalid_timestamp"] += 1
                    continue
                if cutoff and seen_at > cutoff:
                    stats["future_seen"] += 1
                    continue
                url = canonical_url(fields[4])
                if not (url.startswith("http://") or url.startswith("https://")):
                    stats["invalid_url"] += 1
                    continue
                match = relevance(fields)
                if match is None:
                    stats["irrelevant"] += 1
                    continue
                if match == "contextual":
                    stats["ambiguous"] += 1
                    continue
                content_id = hashlib.sha256((url + "|" + seen_at.isoformat()).encode()).hexdigest()
                if content_id in seen:
                    stats["duplicates"] += 1
                    continue
                seen.add(content_id)
                tone = fields[15].split(",", 1)[0] if fields[15] else ""
                rows.append([
                    content_id, seen_at.isoformat(), "", seen_at.isoformat(),
                    retrieved_at.isoformat(), fields[3], url, "news", "BTC|ETH",
                    tone, fields[7], "gdelt_seen_at", "false",
                    "publication_timestamp_unavailable",
                ])
    invalid = stats["malformed"] + stats["invalid_timestamp"] + stats["invalid_url"]
    stats["invalid_ratio"] = invalid / stats["rows_seen"] if stats["rows_seen"] else 0.0
    if stats["invalid_ratio"] > max_invalid_ratio:
        raise ValueError(f"input quality gate failed: invalid ratio {stats['invalid_ratio']:.4f}")
    rows.sort(key=lambda row: (row[1], row[0]))
    output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "content_id", "gdelt_seen_at", "published_at", "first_seen_at",
            "retrieved_at", "source", "canonical_url", "category", "symbol_or_query",
            "tone", "themes", "source_time_basis", "replay_safe",
            "replay_unsafe_reason",
        ])
        writer.writerows(rows)
    stats["rows_written"] = len(rows)
    stats["output_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    return stats

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--cutoff", type=lambda value: datetime.fromisoformat(value).astimezone(timezone.utc))
    parser.add_argument("--max-invalid-ratio", type=float, default=0.05)
    args = parser.parse_args()
    stats = clean(args.archives, args.output, cutoff=args.cutoff,
                  max_invalid_ratio=args.max_invalid_ratio)
    args.manifest.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
