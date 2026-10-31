# Functional completion report

Status words: **Verified** = observed working through its real execution path in this repo, with tests. **Contract-verified** = behaviour proven against an in-process fake of the provider's documented API, not the provider. **Credential-blocked** = adapter complete, needs the owner's authorization. **Fixture** = runs on labelled simulated apps. **Not done** = not implemented.

| Feature | UI | Backend | Database | Live provider | Verification | Final status |
|---|---|---|---|---|---|---|
| Mission engine (approvals, ledger, reconcile-not-resend, recovery) | Mission workspace, Live Engine | Yes | Yes | n/a (fixture connectors) | 240 backend tests | Verified on **fixtures** |
| Eight consumer-rights case workflows | Cases, Domains | Yes | Yes | none (prepare and hand off only) | RECLAIM tests, E2E | Verified; never files anything |
| Real browser on simulated apps | Mission browser panel | Yes | Yes | n/a | tests, E2E | Fixture |
| OCR (images, scanned PDFs) with review | Evidence Vault | Yes (RapidOCR) | Yes (encrypted) | n/a | `test_ocr.py`, E2E | **Verified** |
| Brief to PDF | PDF Studio | Yes | Yes (encrypted) | n/a | `test_brief.py`, E2E | **Verified** |
| Persistent encrypted memory, context, history, graph | Memory, History, Graph | Yes | Yes | n/a | `test_memory.py`, `test_context.py`, E2E | Verified |
| Envelope encryption, rotation, privacy export and delete | Privacy Center | Yes | Yes | n/a | tests | Verified (server-held key, no KMS) |
| PostgreSQL | n/a | Yes | Yes | n/a | suite on PG16 earlier | Verified locally; Docker untested |
| Google Calendar and Gmail actions | Connections Center | Yes | Yes (encrypted tokens) | Needs Google OAuth client | 11 contract tests | **Contract-verified; credential-blocked** |
| Bolna voice and `save_answer`/`recall` tools | Voice Studio, Connections | Yes | Yes | Needs Bolna key | mock-transport tests | **Credential-blocked; request shapes unverified** |
| Memory capture from a real Bolna call | Memory Center | Yes | Yes | Needs Bolna | transcript fixtures | Credential-blocked |
| Demo/production separation | banner text in Connections | Yes | n/a | n/a | test | Verified |
| Live browser run viewer with pause/resume/stop mid-run | Browser skills page (frames poll every 0.7 s from the running session) | Yes (background thread, control checked between steps) | Yes (`browser_skill_runs`, `browser_snapshots`) | n/a | `test_live_run_pause_resume_stop`, E2E | **Verified** on the local practice apps (screenshot per step, not a video stream; control is process-local) |
| Recorded browser skills (record by doing, replay, parameters) | Browser skills page | Yes (`resolve/skills.py`) | Yes (`browser_skills`, migration 0010) | n/a (allow-listed local apps only) | 4 backend tests incl. independent read of the app's API, E2E | **Verified** on the local practice apps; failed run after a click is marked uncertain, never retried |
| Project Store (group missions, cases, documents) | Projects page | Yes | Yes (`projects`, `project_items`) | n/a | CRUD + IDOR + export test, E2E | **Verified** |
| DevOps, Science, Creative adapters | none | none | none | n/a | none | Not done |
| LLM processing, local speech-to-text | none | none | none | needs key / model download | none | Not done |
| Other connectors (booking, bank, insurance, telecom, government, healthcare portals) | cards | none | none | no adapters | none | Not done |
| OAuth for other providers, webhooks beyond Bolna | none | none | none | n/a | none | Not done |
| Cinematic intro (Bolna and Wispr Flow cubes) | Landing | n/a | n/a | n/a | E2E checks both logo images | **Verified**: official logo files downloaded unmodified from bolna.ai and wisprflow.ai (CSS 3D, not WebGL) |
| WebGL / real-time 3D | none | n/a | n/a | n/a | none | Not done (CSS 3D only) |

## What this pass could not do, and why
Most of the mandate needs accounts and decisions that do not exist in this environment: Bolna and Google credentials, provider programs for airlines, banks and portals, an LLM key, and logo files from sites the sandbox cannot reach. The code side of Google is finished; everything else listed above as Not done is missing implementation, not missing credentials, and remains open.
