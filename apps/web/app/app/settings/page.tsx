"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorNote, LangSwitcher, PageTitle } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function Settings() {
  const { me, refresh } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState("");
  const [audit, setAudit] = useState<{ action: string; target: string | null; at: string }[]>([]);
  useEffect(() => { api<{ items: { action: string; target: string | null; at: string }[] }>("/audit").then((r) => setAudit(r.items)).catch(() => undefined); }, []);
  const exportData = async () => {
    try {
      const data = await api("/privacy/export");
      const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })); a.download = "redeem-export.json"; a.click(); URL.revokeObjectURL(a.href);
    } catch (e) { setError(e instanceof ApiError ? e.message : "Export failed"); }
  };
  const del = async () => {
    try { await api("/users/me", { method: "DELETE" }); await refresh(); router.push("/"); } catch (e) { setError(e instanceof ApiError ? e.message : "Delete failed"); }
  };
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageTitle title="Settings and privacy" />
      <ErrorNote error={error} />
      <section className="card"><h2 className="font-bold">Profile</h2><p className="mt-1 text-sm text-muted">{me?.name} · {me?.email}</p><div className="mt-3"><LangSwitcher /></div></section>
      <section className="card"><h2 className="font-bold">Your data</h2>
        <p className="mt-1 text-sm text-muted">Download everything REDEEM holds for your workspace. Individual missions can be deleted from their history entry via the API; call-data retention controls are not built yet.</p>
        <button className="btn-ghost mt-3" onClick={() => void exportData()}>Export my data (JSON)</button></section>
      <section className="card" aria-labelledby="au-h"><h2 id="au-h" className="font-bold">Audit history</h2><p className="mt-1 text-sm text-muted">Important actions on your workspace, newest first. Destination phone numbers and document contents are never logged.</p>
        {audit.length ? <ul className="mt-3 max-h-64 divide-y divide-line overflow-y-auto text-sm">{audit.slice(0, 40).map((a, i) => <li key={i} className="flex flex-wrap justify-between gap-2 py-1.5"><span className="font-medium">{a.action}</span><span className="text-xs text-muted">{a.target ?? ""} · {new Date(a.at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}</span></li>)}</ul> : <p className="mt-2 text-sm text-muted">Nothing recorded yet.</p>}</section>
      <section className="card" aria-labelledby="rt-h"><h2 id="rt-h" className="font-bold">Retention</h2><p className="mt-1 text-sm text-muted">Missions, cases, documents (and their stored bytes), browser screenshots and files are kept until you delete them. Deleting a case keeps its documents in the vault; deleting an account removes everything, including stored files. Automatic expiry rules are not built yet.</p></section>
      <section className="card border-danger/40"><h2 className="font-bold text-danger">Delete account</h2>
        <p className="mt-1 text-sm text-muted">Permanently deletes your workspace, missions, documents, calls and sign-in. This cannot be undone. Type <strong>DELETE</strong> to confirm.</p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row"><label htmlFor="cf" className="sr-only">Type DELETE</label><input id="cf" className="input" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          <button className="btn bg-danger text-white" disabled={confirm !== "DELETE"} onClick={() => void del()}>Delete everything</button></div></section>
    </div>
  );
}
