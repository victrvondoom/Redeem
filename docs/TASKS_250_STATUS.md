# 250-task brief: honest status

Legend: **Done** = implemented + tested in this repo. **Partial** = some of it exists. **Not done** = not implemented in this pass. **Blocked** = needs external access. Done does not mean "complete in production"; see Limits.
This pass covered the highest-leverage, dependency-first items; the rest remains open work.

| # | Workstream (tasks) | Status | Evidence / gap |
|---|---|---|---|
| 01 | Repository recovery (001-010) | Partial | Repo inspected, baseline run, state docs updated. Commits `b6079a5` exists on the current branch; `654fb55` and branch `claude/beautiful-bardeen-fw59qp` do not exist in this clone, so nothing to merge. Source repos RESOLVE/RECLAIM were read as data in earlier passes. No parallel work queue file. |
| 02 | RESOLVE/RECLAIM inheritance (011-020) | Partial | Core inherited + matrix (see FEATURE_INHERITANCE_MATRIX.md). Not ported: browser skills, brief-to-PDF, DevOps/Science/Creative adapters, Project Store, OCR, LLM, local STT. `registry/features.json` is the new machine-readable feature registry (README is generated from it); there is no full capability/tool registry for the engine yet. |
| 03 | Database (021-030) | Partial | PostgreSQL 16 verified (migrations 0001-0007, no drift, full suite). Persistence tests exist; indexes added for memory; transactions are per-request commits; no monitoring UI beyond `/health` dialect; backup/restore procedure not written or tested; Docker build untested. |
| 04 | Auth + isolation (031-040) | Partial | Tenant isolation + IDOR tests for existing resources and all new memory/privacy endpoints. Password recovery, roles beyond single owner, worker tenant context, browser-session isolation tests: not done. |
| 05 | Encryption (041-050) | Done (scope below) | Envelope encryption, key ids/versions, DEK + KEK rotation, tamper/wrong-key/wrong-tenant tests, fail-closed in production. **Not**: KMS, encryption of connector credentials beyond existing handling, voice audio (not stored), browser secrets. |
| 06 | Privacy (051-060) | Partial | Privacy Center, JSON export (incl. memory), memory/document/mission deletion, account deletion with key destruction, memory expiry purge. Not done: export of evidence files in a bundle, retention settings UI, log-redaction audit, connector revocation clearing credentials audit. |
| 07 | Persistent memory (061-070) | Done | Encrypted DB memory, provenance, confirm/correct/reject/pin/delete, clarification on ambiguity, retrieval into missions (confirmed only), Memory Center UI, tests. Mapper is rule-based, not an LLM; inferred (non-explicit) extraction is not generated. |
| 08 | Bolna voice (071-080) | Partial | Adapter/session/webhook/consent existed (mock-transport tested); new `save_answer`/`recall` agent tools and transcript-to-memory. **Blocked**: live call, live transcript retrieval, multilingual live ASR. No conversation-context model beyond the mission reply flow. |
| 09 | Mission orchestration (081-090) | Partial | Existing engine covers plan DAG, revisions, recovery, cancellation, verification, receipts. Not re-audited against each task here. |
| 10 | Connectors (091-100) | Partial | Fixture connectors + manifests/health; no OAuth, no real calendar/email/CRM/commerce adapters. |
| 11 | Browser + live video (101-110) | Partial | Real Chromium on fixtures with snapshots, pause for user-only steps. **Not done**: live screencast stream, replay recorder, pause/resume controls mid-run. The Live Engine page replays the ledger (not a browser video). |
| 12 | Recorded browser skills (111-120) | Not done | |
| 13 | Other RESOLVE modules (121-130) | Not done | |
| 14 | Eight domains (131-140) | Partial | Existing RECLAIM workflows for all eight with tests; per-domain failure-scenario matrix not completed. |
| 15 | Documents/evidence/knowledge (141-150) | Partial | Ingestion, facts with provenance, evidence-to-claim mapping, BM25 knowledge, citation verification, vault, export existed; OCR blocked (no engine). |
| 16 | Agent OS (151-160) | Partial | Role capability matrix + activity timeline existed; arbitration/observability not extended here. |
| 17 | Design system (161-170) | Done (core) | Warm graphite + single orange token system applied app-wide (CSS variables), 3D glass cards, buttons, tabs. No separate page-by-page audit document. |
| 18 | Landing + intro (171-180) | Partial | Intro corrected to REDEEM + orange tagline; Bolna and Wispr Flow cubes enter from opposite sides, collide, emblem + wordmark + tagline, pull-back transition, skip/Esc/replay/reduced-motion, tested, frames captured. **Official logos not embedded (blocked)**: cubes show partner names as text. |
| 19 | 3D pipeline (181-190) | Partial | CSS 3D cube, isometric SVG emblem with documented geometry, non-WebGL fallback by construction. **No three.js/WebGL, no materials/lighting model, no GLB asset library.** |
| 20 | Motion (191-200) | Partial | Reveals, tilt, route-independent animations, reduced-motion handled. No frame-rate/memory measurement. |
| 21 | App experiences (201-210) | Partial | Command Center, Mission, Case, Domains, Evidence/Knowledge, Voice Studio, Connections existed; new Memory Center, Privacy Center, Live Engine. Project Workspace and Browser Skills workspace: not done. |
| 22 | Interaction quality (211-220) | Partial | App shell, stage stepper, DAG renderer, live updates (SSE), state feedback exist. Full a11y audit not redone. |
| 23 | Demos (221-230) | Partial | Scenarios A/B/C/D with reset exist and replay in Live Engine. Memory-continuity demo = Memory Center + later mission (tested). Browser live-video demo: not done. Reliability benchmark exists (fixture). |
| 24 | README (231-240) | Partial | New README with expandable sections, real screenshots, intro GIF, live-engine GIF/MP4, emblem with measurements, generated feature table + CI staleness check. **Official Bolna/Wispr/YC/WeMakeDevs logos not embedded (blocked)**; named and linked instead. No architecture diagram image. |
| 25 | Release (241-250) | Partial | Backend 217, E2E 38, tsc/eslint/ruff/build run; screenshots captured; docs updated; committed and pushed. No recorded product video (GIF/MP4 are assembled from screenshots). |

## Update: context memory, graph memory, history, theme (this pass)
Added: encrypted per-user conversation context (migration 0008), follow-up resolution, unified history timeline API + UI, derived Memory Graph API + UI, Voice Studio link panel, black/green/orange theme with the pixel-serif display font (Gloock + SVG pixelate filter, closest available match to the event artwork's font), partner-logo manifest (no more 404s). Graph is derived from relational rows, **not** a graph database or vector store (registry: `graph-db` not_done).
