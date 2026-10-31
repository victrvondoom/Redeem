export type Overview = {
  counts: { missions_total: number; missions_active: number; missions_by_status: Record<string, number>; cases_total: number; cases_by_status: Record<string, number>; documents: number; browser_snapshots: number; verified_outcomes: number };
  attention: { kind: string; title: string; detail: string; href: string; at: string }[];
  recent: { at: string; source: string; type: string; href: string; mission_id?: string; case_id?: string }[]; scope: string;
};
export type Source = { id: string; domain?: string; title: string; authority: string; category: string; source_url: string | null; provenance: string; passage: string; source_path?: string;
  evidence_scores: { similarity: number; authority: number; legal_weight: number; overall: number; confidence: number } };
export type Fact = { kind: string; value: string | number; display: string; quote?: string; page?: number; span?: number[] | null };
export type DocLite = { id: string; filename: string; doc_type: string | null; version: number; sha256: string; strength: { score: number; explanation: string; matches_checklist: string[] };
  relevance: { relevant: boolean; reason: string; hits: number }; ocr_status: string | null; facts: Fact[]; near_duplicate_of: string | null; supersedes: string | null; page_count: number | null };
export type Candidate = { key: string; name: string; stage: string; benefit_inr: number; delay_days: number; risk: number; privacy: number; utility: number; eligible: boolean; missing: string[]; deadline_passed: boolean; rationale: string; assumptions: string[]; prerequisites: string[] };
export type CaseView = {
  id: string; mission_id: string | null; domain: string; domain_label: string; issue_type: string; title: string; description: string; provider: string | null; stage: string; stages: string[]; status: string;
  intake: Record<string, string>; schema: Record<string, string>; critical: string[]; entities: { amounts: { value_paise: number; text: string }[]; dates: { iso: string; text: string }[]; ids: { kind: string; value: string }[]; providers: { name: string }[] };
  missing: { field: string; question: string; example?: string }[]; checklist: { id: string; label: string; covered: boolean; strength: number; document: { id: string; filename: string } | null }[]; sources: Source[];
  analysis: { summary: string; timeline: { date: string | null; event: string }[]; established_facts: { claim: string; support: { filename: string; quote?: string; page?: number }[] }[];
    uncertain_claims: { claim: string; status: string; support: { filename?: string; note?: string }[] }[]; basis: { id: string; title: string; authority: string; provenance: string; source_url: string | null; confidence: number; passage: string }[];
    basis_note: string; remedies: { order: number; stage: string; text: string; links: string[]; source: string }[]; missing_evidence: string[]; recommended: string | null; alternatives: string[]; risks: string[];
    effort_time: string; confidence: number; confidence_explanation: string; followup_date: string; healthcare_note: string | null };
  ranking: { ranked: Candidate[]; optimal: string | null; weights: Record<string, number>; model: { formula: string; caveat: string } }; selected_action: string | null; approval: { action_key: string; at: string; draft_version: number } | null;
  approval_valid: boolean; handoff: { mode: string; internal_record: string; step: { text: string; links: string[]; stage: string }; statement: string; documents_to_attach: string[] } | null;
  outcome: { kind: string; verification: string; statement: string; amount_paise: number | null } | null; claimed_paise: number | null; incident_date: string | null; followup_date: string | null; overdue: boolean; assumption_note: string;
  draft: { version: number; body: string; status: string; origin: string; cited: string[]; content_hash: string; approval_digest: string | null; approval_action: string | null; approval_digests: Record<string, string> } | null;
  drafts: { version: number; status: string; origin: string; hash: string; created_at: string }[]; documents: DocLite[];
  claims: { field: string; claim: string; status: string; support: { filename?: string; quote?: string; note?: string }[] }[];
  events: { seq: number; type: string; data: Record<string, unknown>; at: string }[]; created_at: string; updated_at: string;
};
