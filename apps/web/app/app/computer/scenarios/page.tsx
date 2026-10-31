// STATIC: placeholder data. Replace SCENARIOS with GET /api/v1/computer/scenarios (see docs/STATIC_TODO.md).
const SCENARIOS = [
  { name: "CRM operator", status: "Working (cloud computer, tested)", steps: ["Open CRM", "Find Priya Sharma", "Set WhatsApp", "Add follow-up", "Save draft", "Verify after reload"] },
  { name: "File Explorer + PDF", status: "Not built (static preview)", steps: ["Find invoice in Downloads", "Create customer folder", "Move invoice", "Open PDF", "Confirm amount"] },
  { name: "Consumer case via portal", status: "Not built (static preview)", steps: ["Create case from call", "Open provider portal", "Fill request", "Ask approval", "Submit", "Capture acknowledgement"] },
  { name: "Recovery", status: "Working (tested: page changed during takeover)", steps: ["Detect change", "Stop stale action", "Observe again", "Re-plan"] },
  { name: "User takeover", status: "Working (tested)", steps: ["Pause", "You control", "Hand back", "Agent re-observes"] },
];
export default function Scenarios() {
  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <h1 className="text-2xl font-bold">Computer scenarios</h1>
      <p className="text-sm text-muted">Static overview. Rows marked “static preview” are not implemented yet.</p>
      <ul className="grid gap-3 md:grid-cols-2">{SCENARIOS.map((s) => (
        <li key={s.name} className="card"><h2 className="font-bold">{s.name}</h2><p className="text-xs text-muted">{s.status}</p>
          <ol className="mt-2 list-decimal pl-5 text-sm">{s.steps.map((x) => <li key={x}>{x}</li>)}</ol></li>))}</ul>
    </div>
  );
}
