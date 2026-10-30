"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ErrorNote, LangSwitcher, PageTitle } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function Settings() {
  const { me, refresh } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState("");
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
      <section className="card border-danger/40"><h2 className="font-bold text-danger">Delete account</h2>
        <p className="mt-1 text-sm text-muted">Permanently deletes your workspace, missions, documents, calls and sign-in. This cannot be undone. Type <strong>DELETE</strong> to confirm.</p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row"><label htmlFor="cf" className="sr-only">Type DELETE</label><input id="cf" className="input" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          <button className="btn bg-danger text-white" disabled={confirm !== "DELETE"} onClick={() => void del()}>Delete everything</button></div></section>
    </div>
  );
}
