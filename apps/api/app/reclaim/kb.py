"""Knowledge base retrieval, evidence scoring and citation verification.

Inherited from RECLAIM (MIT, (c) 2026 vsrupeshkumar): authority tiers / evidence scoring (services/evidence_scoring.py) and deterministic claim
verification (services/citation_verification.py), adapted to REDEEM. Differences, stated plainly:
  * retrieval is BM25 (no vector DB, no embeddings); `similarity` is BM25 normalised to the best hit of the query;
  * every hit carries a `provenance` label: scraped_official (scraped by RECLAIM from an official page; REDEEM did not re-fetch it) or
    authored_guide (written by RECLAIM's authors, no official source URL). Authored guides are never presented as official text.
"""
import json
import math
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data"
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"the", "and", "for", "with", "from", "that", "this", "are", "was", "has", "have", "not", "you", "your", "can", "will", "any", "all", "its", "may"}

TIER1 = {"rbi", "dgca", "moca", "uidai", "irdai", "trai", "who", "cdsco", "icmr", "mohfw", "goi", "govt of india", "ncdrc", "rera", "national health authority", "dot", "nch"}
TIER2 = {"darpg", "mea", "income tax dept", "protean (nsdl)", "parivahan", "rti online", "tn rera", "maharera", "karnataka rera", "kerala rera", "up rera", "nha",
         "national health mission", "aiims", "cpgrams"}
LEGAL_CATS = {"act", "regulations", "kyc", "cards", "loans", "deposits", "consumer_protection", "passenger_facilities", "refunds", "accessibility", "digital_security"}


def tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if len(w) > 2 and w not in _STOP]


def authority_score(a: str) -> float:
    k = (a or "").strip().lower()
    if not k:
        return 0.5
    if k in TIER1 or any(t in k for t in TIER1):
        return 1.0
    if k in TIER2 or any(t in k for t in TIER2):
        return 0.8
    return 0.6


def legal_weight(category: str) -> float:
    k = (category or "").strip().lower()
    if k in LEGAL_CATS or "act" in k or "regulation" in k or "master_direction" in k:
        return 1.0
    if k in {"faq", "guide", "grievance_portal", "complaints", "template"}:
        return 0.7
    return 0.5 if k in {"overview", "law_overview"} else 0.6


class KnowledgeBase:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.by_id = {r["id"]: r for r in rows}
        self.tf: list[Counter] = []
        self.df: dict[str, int] = defaultdict(int)
        self.len: list[int] = []
        for r in rows:
            c = Counter(tokens(r["title"] + " " + r["text"]))
            self.tf.append(c)
            self.len.append(sum(c.values()))
            for t in c:
                self.df[t] += 1
        self.avg = (sum(self.len) / len(self.len)) if self.len else 1.0

    def stats(self) -> dict:
        by = Counter((r["domain"], r["provenance"]) for r in self.rows)
        return {"chunks": len(self.rows), "by_domain_provenance": [{"domain": d, "provenance": p, "chunks": n} for (d, p), n in sorted(by.items())]}

    def search(self, query: str, domains: list[str] | None = None, k: int = 6) -> list[dict]:
        q = tokens(query)
        if not q:
            return []
        n = len(self.rows)
        scored = []
        for i, r in enumerate(self.rows):
            if domains and r["domain"] not in domains:
                continue
            tf, dl, s = self.tf[i], self.len[i], 0.0
            for t in set(q):
                f = tf.get(t, 0)
                if not f:
                    continue
                idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                s += idf * (f * 2.2) / (f + 1.2 * (0.25 + 0.75 * dl / self.avg))
            if s > 0:
                scored.append((s, i))
        scored.sort(reverse=True)
        top = scored[:k]
        best = top[0][0] if top else 1.0
        return [self._hit(self.rows[i], s / best, q) for s, i in top]

    def _hit(self, r: dict, sim: float, q: list[str]) -> dict:
        auth, legal = authority_score(r["authority"]), legal_weight(r["category"])
        composite = 0.60 * auth + 0.25 * legal + 0.15 * 0.6
        overall = sim * (0.6 + 0.4 * composite)
        conf = overall if (r["authority"] or r["source_url"]) else overall * 0.6
        if r["provenance"] == "authored_guide":
            conf *= 0.8  # an authored guide is not an official text
        text = r["text"]
        pos = min((text.lower().find(t) for t in q if t in text.lower()), default=0)
        start = max(0, pos - 120)
        return {"id": r["id"], "domain": r["domain"], "title": r["title"], "authority": r["authority"], "category": r["category"], "source_url": r["source_url"],
                "provenance": r["provenance"], "source_path": r["source_path"], "content_hash": r["content_hash"], "passage": text[start:start + 520].strip(),
                "evidence_scores": {"similarity": round(sim, 3), "authority": round(auth, 3), "legal_weight": round(legal, 3), "overall": round(overall, 3),
                                    "confidence": round(conf, 3)}}


@lru_cache(maxsize=1)
def kb() -> KnowledgeBase:
    p = DATA / "corpus.jsonl"
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()] if p.exists() else []
    return KnowledgeBase(rows)


# ---- deterministic citation verification (ported) ------------------------------------------------------------------------------
_CSTOP = {"the", "and", "for", "with", "from", "under", "act", "rule", "rules", "of", "in", "on", "to", "a", "an", "or", "by", "is", "are", "as", "at", "this"}


def verify_claim(claim: str, source_text: str) -> bool:
    if not claim or not source_text:
        return False
    src = source_text.lower()
    if claim.lower().strip() in src:
        return True
    words = [w for w in re.findall(r"[a-z0-9]+", claim.lower()) if len(w) > 3 and w not in _CSTOP]
    if len(words) < 2:
        return True
    return sum(1 for w in words if w in src) / len(words) >= 0.7


class CitationError(Exception):
    pass


def assert_cited(text: str, allowed_ids: list[str]) -> list[str]:
    """Every [kb_xxx] marker in `text` must be one of `allowed_ids` AND exist in the corpus. Returns the cited ids."""
    cited = re.findall(r"\[(kb_[0-9a-f]{14})\]", text)
    bad = [c for c in cited if c not in allowed_ids or c not in kb().by_id]
    if bad:
        raise CitationError(f"unverified citation(s): {sorted(set(bad))}")
    return sorted(set(cited))
