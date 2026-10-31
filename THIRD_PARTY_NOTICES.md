# Third-party notices
REDEEM inherits code and data from two sibling projects by the same author group, both MIT-licensed. Attribution:

## RECLAIM — https://github.com/victrvondoom/RECLAIM  (MIT, Copyright (c) 2026 vsrupeshkumar (RECLAIM))
Inherited/adapted: domain profiles (`apps/api/app/reclaim/data/domain_profiles.json`), router vocabulary (`domain_keywords.json`), the knowledge corpus
(`corpus.jsonl`: 799 telecom + 290 e-commerce chunks scraped by RECLAIM from official pages, and ~70 authored guide documents), evidence-scoring authority tiers,
citation verification, the multi-objective decision engine, and document-relevance rules. Corpus provenance is preserved per passage; REDEEM did not re-fetch or
independently verify any of it. Build script: `scripts/build_knowledge_corpus.py` (reads RECLAIM data only; executes nothing from it).

## RESOLVE — https://github.com/victrvondoom/Resolve  (MIT, Copyright (c) 2026 RESOLVE contributors)
Inherited/adapted: stateful web fixture apps, the browser executor design, document studio, file worker, effect-graph and agent-runtime concepts (see docs/FEATURE_INHERITANCE_MATRIX.md).

Neither project's license text is reproduced here; consult their repositories for the full MIT license.
