#!/usr/bin/env python3
"""Cross-check cleaned GDELT metadata against timestamped provider records."""
from __future__ import annotations
import argparse, csv, gzip, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src",
            "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term"}

def canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in TRACKING and not k.lower().startswith("utm_")]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/",
                       urlencode(query), ""))

def load_alpha(paths: list[Path]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in paths:
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                url = canonical_url(row["url"])
                published = datetime.fromisoformat(row["published_at"]).astimezone(timezone.utc)
                result[url] = published.isoformat()
    return result

def validate(gdelt: Path, alpha: list[Path], output: Path, manifest: Path) -> dict:
    verified = load_alpha(alpha)
    stats = {"gdelt_rows": 0, "exact_url_matches": 0, "publication_conflicts": 0,
             "unverified_rows": 0}
    output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(gdelt, "rt", newline="", encoding="utf-8") as source, \
         gzip.open(output, "wt", newline="", encoding="utf-8") as target:
        reader = csv.DictReader(source)
        fields = list(reader.fieldnames or []) + ["validation_status"]
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        for row in reader:
            stats["gdelt_rows"] += 1
            match = verified.get(canonical_url(row["canonical_url"]))
            if match:
                if row.get("published_at") and row["published_at"] != match:
                    stats["publication_conflicts"] += 1
                    row["validation_status"] = "conflict_unsafe"
                else:
                    row["published_at"] = match
                    row["replay_safe"] = "true"
                    row["replay_unsafe_reason"] = ""
                    row["validation_status"] = "exact_url_match"
                    stats["exact_url_matches"] += 1
            else:
                row["replay_safe"] = "false"
                row["replay_unsafe_reason"] = "no_independent_publication_timestamp"
                row["validation_status"] = "unverified"
                stats["unverified_rows"] += 1
            writer.writerow(row)
    stats["output_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    return stats

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gdelt", required=True, type=Path)
    parser.add_argument("--alpha", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.gdelt, args.alpha, args.output, args.manifest), indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
