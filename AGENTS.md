# AGENTS.md — rules for working on REDEEM
1. Read IMPLEMENTATION_STATE.md first; run its verification commands before new work.
2. Done = validated input → authz → execution → real state change → independent verification → durable storage → UI shows it → failure paths tested.
3. Never upgrade a status in FEATURE_MATRIX.md without evidence. Never simulate a live provider; show PROVIDER_NOT_CONFIGURED.
4. Tenant identity comes from the session only. Filter every query by tenant_id. Add an IDOR test for every new resource.
5. Never resend a non-idempotent action after an uncertain outcome: look it up read-only, else human review.
6. Never weaken or delete a failing test. No secrets in git.
7. No invented metrics, testimonials, citations or legal claims.
