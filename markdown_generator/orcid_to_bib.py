#!/usr/bin/env python3
"""Convert ORCID works to a .bib file.

This script is a straight conversion of the `OrcidToBib.ipynb` notebook
into a small command-line tool. It fetches the list of works for an ORCID
identifier, retrieves citation information for each work, and writes the
citations to a `.bib` file.
"""

from __future__ import annotations

import sys
import re
from typing import List

import requests


def fetch_put_codes(orcid: str) -> List[int]:
    headers = {"Accept": "application/orcid+json"}
    resp = requests.get(f"https://pub.orcid.org/v3.0/{orcid}/works", headers=headers, timeout=30)
    resp.raise_for_status()
    record = resp.json()
    put_codes: List[int] = []
    for work in record.get("group", []):
        summary = work.get("work-summary", [])
        if not summary:
            continue
        put_code = summary[0].get("put-code")
        if put_code is not None:
            put_codes.append(put_code)
    return put_codes


def fetch_citations(orcid: str, put_codes: List[int]) -> List[str]:
    headers = {"Accept": "application/orcid+json"}
    citations: List[str] = []
    for put_code in put_codes:
        resp = requests.get(f"https://pub.orcid.org/v3.0/{orcid}/work/{put_code}", headers=headers, timeout=30)
        if resp.status_code != 200:
            continue
        work = resp.json()
        citation = work.get("citation")
        if citation and citation.get("citation-value"):
            citations.append(citation["citation-value"])
        else:
            # build a fallback BibTeX entry from the work metadata
            bib_entry = build_bib_from_work(work, put_code)
            if bib_entry:
                citations.append(bib_entry)
    return citations


def _bib_escape(s: str) -> str:
    if not s:
        return ""
    # remove outer braces/quotes and trim
    s = re.sub(r"^\s*\{(.*)\}\s*$", r"\1", s)
    s = s.strip('"')
    # replace newlines
    s = s.replace("\n", " ").strip()
    return s


def build_bib_from_work(work: dict, put_code: int | None = None) -> str:
    """Build a BibTeX entry string from an ORCID work record.

    The function extracts common metadata and formats a minimal BibTeX
    entry. If insufficient data exists, returns an empty string.
    """
    def _get_title(w: dict) -> str:
        for path in (('work-title', 'title', 'value'), ('title', 'title', 'value'), ('title', 'value')):
            cur = w
            try:
                for p in path:
                    cur = cur[p]
                if cur:
                    return _bib_escape(cur)
            except Exception:
                continue
        for key in ('short-description', 'translated-title'):
            v = w.get(key)
            if isinstance(v, dict) and v.get('value'):
                return _bib_escape(v.get('value'))
            if isinstance(v, str):
                return _bib_escape(v)
        return ''

    def _get_authors(w: dict) -> List[str]:
        out: List[str] = []
        contributors = []
        if isinstance(w.get('contributors'), dict):
            contributors = w.get('contributors', {}).get('contributor', [])
        for c in contributors:
            name = ''
            if isinstance(c.get('credit-name'), dict):
                name = c.get('credit-name', {}).get('value', '')
            elif c.get('credit-name'):
                name = c.get('credit-name')
            if not name and c.get('contributor-orcid'):
                name = c.get('contributor-orcid', {}).get('path', '')
            if name:
                out.append(_bib_escape(name))
        return out

    def _get_year(w: dict) -> str:
        pd = w.get('publication-date', {}) or {}
        y = pd.get('year', {}) if isinstance(pd.get('year'), dict) else pd.get('year')
        if isinstance(y, dict):
            return y.get('value', '')
        return y or ''

    def _get_venue(w: dict) -> str:
        jt = w.get('journal-title') or w.get('journal', {})
        if isinstance(jt, dict):
            return _bib_escape(jt.get('value', ''))
        return _bib_escape(jt) if isinstance(jt, str) else ''

    title = _get_title(work)
    authors = _get_authors(work)
    year = _get_year(work)
    venue = _get_venue(work)

    def _as_text(val):
        if not val:
            return ''
        if isinstance(val, str):
            return val
        if isinstance(val, dict):
            for k in ('value', 'uri', 'url', 'path'):
                v = val.get(k)
                if isinstance(v, str):
                    return v
            # if dictionary contains nested strings, try first string-like value
            for v in val.values():
                if isinstance(v, str):
                    return v
            return ''
        if isinstance(val, list):
            return ' '.join([_as_text(x) for x in val if x])
        return str(val)

    publisher = _bib_escape(_as_text(work.get('publisher', '')))
    pages = _bib_escape(_as_text(work.get('pages', '')))
    doi = _bib_escape(_as_text(work.get('doi', '')))
    url = _bib_escape(_as_text(work.get('url', '')))
    abstract = _bib_escape(_as_text(work.get('short-description', '') or work.get('description', '')))

    if not title and not authors:
        return ''

    # choose entry type
    wtype = (work.get('type') or '').lower() if work.get('type') else ''
    if 'journal' in wtype or 'article' in wtype:
        entry_type = 'article'
    elif 'conference' in wtype or 'proceeding' in wtype:
        entry_type = 'inproceedings'
    elif 'book' in wtype or 'chapter' in wtype:
        entry_type = 'incollection'
    else:
        entry_type = 'misc'

    # build key
    if authors:
        last = authors[0].split()[-1]
        key = f"{last}{year}" if year else f"{last}"
    elif put_code:
        key = f"orcid{put_code}"
    else:
        key = slug = re.sub(r"[^A-Za-z0-9]+", '', title)[:20]

    # build fields
    lines = [f"@{entry_type}{{{key},"]
    if authors:
        lines.append(f"  author = {{{' and '.join(authors)}}},")
    if title:
        lines.append(f"  title = {{{title}}},")
    if venue and entry_type == 'article':
        lines.append(f"  journal = {{{venue}}},")
    elif venue and entry_type == 'inproceedings':
        lines.append(f"  booktitle = {{{venue}}},")
    if year:
        lines.append(f"  year = {{{year}}},")
    if publisher:
        lines.append(f"  publisher = {{{publisher}}},")
    if pages:
        lines.append(f"  pages = {{{pages}}},")
    if doi:
        lines.append(f"  doi = {{{doi}}},")
    if url:
        lines.append(f"  url = {{{url}}},")
    if abstract:
        lines.append(f"  abstract = {{{abstract}}},")
    # remove trailing comma from last field
    if lines[-1].endswith(','):
        lines[-1] = lines[-1].rstrip(',')
    lines.append('}')
    return '\n'.join(lines)


def write_bib(citations: List[str], filename: str) -> None:
    with open(filename, "w", encoding="utf-8") as fh:
        for citation in citations:
            fh.write(citation)
            fh.write("\n")


def main() -> None:

    orcid_tag = "0000-0002-2124-6670"
    ouput_file = "{}.bib".format(orcid_tag).replace("-", "_")

    try:
        put_codes = fetch_put_codes(orcid_tag)
    except requests.RequestException as exc:
        print(f"Failed to fetch works for ORCID {orcid_tag}: {exc}", file=sys.stderr)
        sys.exit(1)
    print(put_codes)

    if not put_codes:
        print("No works found for ORCID", file=sys.stderr)
        sys.exit(1)

    citations = fetch_citations(orcid_tag, put_codes)

    if not citations:
        print("No citations found for ORCID works", file=sys.stderr)
        sys.exit(1)

    write_bib(citations, ouput_file)
    print(f"Wrote {len(citations)} citations to {ouput_file}")


if __name__ == "__main__":
    main()
