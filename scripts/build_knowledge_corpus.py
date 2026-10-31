"""Build REDEEM's knowledge corpus from a RECLAIM checkout (MIT, (c) 2026 vsrupeshkumar). Reads data only; executes nothing from it.

Usage: python -I scripts/build_knowledge_corpus.py /path/to/RECLAIM
Provenance labels (never upgraded silently):
  scraped_official  - chunk scraped by RECLAIM from an official page; REDEEM has not re-fetched it
  authored_guide    - template/FAQ written by RECLAIM's authors; NOT an official text, has no source URL
"""
import ast
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import unquote

root = Path(sys.argv[1])
out = Path(__file__).resolve().parents[1] / "apps/api/app/reclaim/data/corpus.jsonl"
rows: list[dict] = []


def add(domain, title, authority, category, url, provenance, text, source_path):
    text = text.strip()
    if len(text) < 80:
        return
    rows.append({"id": "kb_" + hashlib.sha256(f"{domain}|{source_path}|{text[:200]}".encode()).hexdigest()[:14], "domain": domain, "title": title,
                 "authority": authority or "", "category": category or "", "source_url": url, "provenance": provenance, "source_path": source_path,
                 "content_hash": hashlib.sha256(text.encode()).hexdigest(), "text": text})


for dom in ("telecom", "ecommerce"):
    reg = {}
    p = root / "knowledge" / dom / f"{dom}_source_registry.json"
    if p.exists():
        reg = {r.get("folder"): r for r in json.loads(p.read_text())}
    for line in (root / "knowledge" / dom / "chunks" / f"{dom}_chunks.jsonl").read_text().splitlines():
        r = json.loads(line)
        md = r.get("metadata") or {}
        folder = r["source_path"].split("/")[0]
        rg = reg.get(folder, {})
        title = md.get("title") or ""
        if not title or title.lower().startswith("download") or len(title) < 4:  # scraped link text like "Download(127 KB)": use the page/file instead
            url_ = md.get("source_url") or ""
            title = (f'{md.get("authority") or rg.get("authority") or ""} — {unquote(url_.rsplit("/", 1)[-1])}' if url_ else
                     f'{rg.get("title") or folder} — {Path(r["source_path"]).stem.replace("_", " ")}')
        add(dom, title, md.get("authority") or rg.get("authority"), md.get("category") or rg.get("category"),
            md.get("source_url") or rg.get("url"), "scraped_official", r["text"], f'{r["source_path"]}#{r["chunk_index"]}')

DOMAIN_OF = {"seed_banking_grievance_content": "banking", "seed_banking_knowledge": "banking", "seed_government_knowledge": "government",
             "seed_healthcare_content": "healthcare", "seed_housing_grievance_content": "housing", "seed_airlines_grievance_content": "airlines"}
for script, dom in DOMAIN_OF.items():
    tree = ast.parse((root / "backend" / "scripts" / f"{script}.py").read_text())
    for n in tree.body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "DOCUMENTS":
            for d in ast.literal_eval(n.value):  # static literal: no code executed
                add(dom, d.get("title", ""), d.get("authority"), d.get("category"), d.get("source_url"), "authored_guide", d.get("content", ""),
                    f'{d.get("folder", "")}/{d.get("filename", "")}')
out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
import collections
print(len(rows), "chunks", dict(collections.Counter((r["domain"], r["provenance"]) for r in rows)), f"{out.stat().st_size/1e6:.1f} MB")
