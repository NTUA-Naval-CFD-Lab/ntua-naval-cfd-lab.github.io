#!/usr/bin/env python3
"""Convert .bib files to a TSV matching the `publications.tsv` template.

Usage:
  python3 bib_to_tsv.py --bibdir path/to/bibs --template publications.tsv --out publications_out.tsv

The script reads the header from the template TSV and produces rows
for each BibTeX entry found under `--bibdir` (defaults to current dir).
"""

from __future__ import annotations

import argparse
import os
import re
import glob
from datetime import datetime
from typing import Dict, List, Optional


def read_template_header(template_path: str) -> List[str]:
    with open(template_path, "r", encoding="utf-8") as fh:
        first = fh.readline().strip()
    if not first:
        raise SystemExit(f"Empty template: {template_path}")
    return first.split("\t")


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text


def clean_value(val: Optional[str]) -> str:
    if not val:
        return ""
    s = val
    # remove outer braces and quotes
    s = re.sub(r"^\s*\{(.*)\}\s*$", r"\1", s)
    s = s.strip('"')
    # remove remaining LaTeX braces
    s = s.replace("{", "").replace("}", "")
    return s.strip()


def parse_bib_file(path: str) -> List[Dict[str, str]]:
    text = open(path, "r", encoding="utf-8", errors="ignore").read()
    # split entries by @<type>{key,
    entries_raw = re.split(r"\n(?=@)", text)
    results: List[Dict[str, str]] = []
    for entry in entries_raw:
        entry = entry.strip()
        if not entry:
            continue
        m = re.match(r"@(?P<type>\w+)\s*\{\s*(?P<key>[^,]+),", entry)
        if not m:
            continue
        fields: Dict[str, str] = {}
        # find field = {value} or = "value"
        for fld, val in re.findall(r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^}]*\})*\}|\"(?:[^\"])*\"),?", entry, flags=re.S):
            fields[fld.lower()] = clean_value(val)
        results.append(fields)
    return results


def format_authors(author_field: str) -> str:
    # keep authors as provided but replace ' and ' with ', '
    if not author_field:
        return ""
    authors = [a.strip() for a in re.split(r"\s+and\s+", author_field)]
    return ", ".join(authors)


def build_citation(fields: Dict[str, str]) -> str:
    authors = format_authors(fields.get("author", ""))
    year = fields.get("year", "")
    title = fields.get("title", "")
    venue = fields.get("journal", "") or fields.get("booktitle", "")
    citation = f"{authors} ({year}). \"{title}.\""
    if venue:
        citation += f" <i>{venue}</i>."
    return citation


def parse_date(fields: Dict[str, str]) -> str:
    year = fields.get("year")
    month = fields.get("month")
    day = fields.get("day")
    if not year:
        return ""
    # try to create YYYY-MM-DD; if month missing, default to 01
    mm = "01"
    if month:
        # attempt convert month name or number
        try:
            mm = f"{int(month):02d}"
        except Exception:
            try:
                dt = datetime.strptime(month[:3], "%b")
                mm = f"{dt.month:02d}"
            except Exception:
                mm = "01"
    dd = "01"
    if day:
        try:
            dd = f"{int(day):02d}"
        except Exception:
            dd = "01"
    return f"{year}-{mm}-{dd}"


def map_entry_to_row(fields: Dict[str, str], cols: List[str]) -> List[str]:
    title = clean_value(fields.get("title", ""))
    venue = clean_value(fields.get("journal", "")) or clean_value(fields.get("booktitle", ""))
    excerpt = clean_value(fields.get("abstract", "")) or clean_value(fields.get("note", ""))
    citation = build_citation(fields)
    pub_date = parse_date(fields)
    url_slug = slugify(title) if title else ""
    paper_url = fields.get("url") or ("https://doi.org/" + fields.get("doi") if fields.get("doi") else "")
    slides_url = ""

    mapping = {
        "pub_date": pub_date,
        "title": title,
        "venue": venue,
        "excerpt": excerpt,
        "citation": citation,
        "url_slug": url_slug,
        "paper_url": paper_url,
        "slides_url": slides_url,
    }
    return [mapping.get(c, "") for c in cols]


def find_bib_files(bibdir: str) -> List[str]:
    patterns = [os.path.join(bibdir, "*.bib"), os.path.join(bibdir, "**", "*.bib")]
    files = []
    for pat in patterns:
        files.extend(glob.glob(pat, recursive=True))
    # unique and sorted
    return sorted(set(files))


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert .bib entries to a TSV matching the publications template")
    parser.add_argument("--bibdir", default=".", help="Directory to search for .bib files (default: current dir)")
    parser.add_argument("--template", default="markdown_generator/publications.tsv", help="Path to template TSV (default: markdown_generator/publications.tsv)")
    parser.add_argument("--out", default="publications_out.tsv", help="Output TSV filename")
    args = parser.parse_args()

    cols = read_template_header(args.template)

    bib_files = find_bib_files(args.bibdir)
    if not bib_files:
        print("No .bib files found in", args.bibdir)
        return

    rows: List[List[str]] = []
    for bib in bib_files:
        entries = parse_bib_file(bib)
        for ent in entries:
            row = map_entry_to_row(ent, cols)
            rows.append(row)

    # remove exact duplicate rows while preserving order
    seen = set()
    unique_rows: List[List[str]] = []
    for r in rows:
        key = tuple(r)
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(r)
    rows = unique_rows

    # write TSV
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\t".join(cols) + "\n")
        for r in rows:
            fh.write("\t".join(r) + "\n")

    print(f"Wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
