export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public body?: unknown) {
    super(message);
  }
}

let csrf = "";
export const setCsrf = (t: string) => { csrf = t; };

export async function api<T = unknown>(path: string, init: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  const method = init.method ?? (init.body || init.form ? "POST" : "GET");
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRF-Token"] = csrf;
  let body: BodyInit | undefined;
  if (init.form) body = init.form;
  else if (init.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(init.body); }
  const res = await fetch(`/api/v1${path}`, { method, headers, body, credentials: "same-origin" });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = (data as { error?: { code?: string; message?: string } }).error;
    throw new ApiError(res.status, e?.code ?? "error", e?.message ?? `Request failed (${res.status})`, data);
  }
  return data as T;
}

export type Me = { id: string; email: string; name: string; language: Lang; csrf_token: string };
export type Lang = "en" | "hi" | "hinglish" | "ta" | "te";

export type Candidate = { id: string; label: string; hint?: string };
export type Clarification = { type: string; role?: string; message: string; candidates?: Candidate[]; transcript?: string };
export type PlanAction = {
  id: string; kind: string; params: Record<string, unknown>; amount_paise: number | null; risk: string;
  status: string; digest: string; revision: number;
};
export type Mission = {
  id: string; status: string; intent: string; revision: number; scenario: string; domains: string[];
  language_selected: Lang; language_detected: string; source: string; bindings: Record<string, string>;
  clarification: Clarification | null; created_at: string; updated_at: string;
  plan: { summary?: string; actions?: PlanAction[]; blocked?: { kind: string; reason: string; detail: string }[];
          notes?: string[]; policy_citations?: { id: string; title: string; source: string; effective_date: string; jurisdiction: string; is_fixture: boolean }[] };
  outcome: null | {
    status: string; headline: string; headline_en: string; summary?: string; reason?: string;
    alternatives?: { id: string; name: string; stock: number }[];
    claims?: { action_id: string; result: string; evidence: Record<string, unknown> }[];
    outstanding?: { kind: string; reason: string }[]; ledger_chain_head?: string; ledger_events?: number;
    generated_at?: string; scope?: { note: string };
  };
};
export type LedgerEvent = { seq: number; type: string; action_id: string | null; data: Record<string, unknown>; created_at: string };
