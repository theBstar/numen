// PRD-proposal review (WS1).
// List + detail + approve/reject. Minimal v0; markdown-aware diff renderer
// is a follow-up.

import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  approveProposal,
  getProposal,
  listProposals,
  PrdProposal,
  ProposalStatus,
  rejectProposal,
} from "../api/prdProposals";

const STATUS_COLORS: Record<ProposalStatus, string> = {
  pending: "#fbbf24",
  applied: "#10b981",
  rejected: "#ef4444",
  stale: "#9ca3af",
  expired: "#6b7280",
};

export function PrdProposals() {
  const { id } = useParams<{ id?: string }>();
  return id ? <PrdProposalDetail id={id} /> : <PrdProposalList />;
}

function PrdProposalList() {
  const [items, setItems] = useState<PrdProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<ProposalStatus | "all">("pending");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    listProposals({ status: filter === "all" ? undefined : filter, limit: 100 })
      .then((r) => setItems(r.items))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [filter]);

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "24px" }}>
      <h1>PRD proposals</h1>
      <p style={{ color: "#6b7280", marginBottom: 24 }}>
        Agent-proposed edits to your wiki features. Approve to apply; reject
        to discard. Stale proposals need re-filing because the wiki drifted.
      </p>

      <div style={{ marginBottom: 16 }}>
        {(["pending", "applied", "rejected", "stale", "expired", "all"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            style={{
              marginRight: 8,
              padding: "6px 12px",
              background: filter === s ? "#1f2937" : "#f3f4f6",
              color: filter === s ? "white" : "#1f2937",
              border: "1px solid #e5e7eb",
              borderRadius: 6,
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            {s}
          </button>
        ))}
      </div>

      {error && <div style={{ color: "#ef4444" }}>Error: {error}</div>}
      {loading ? (
        <div>Loading…</div>
      ) : items.length === 0 ? (
        <div style={{ color: "#6b7280" }}>No proposals in this view.</div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #e5e7eb", textAlign: "left" }}>
              <th style={{ padding: "8px 12px" }}>Feature</th>
              <th style={{ padding: "8px 12px" }}>Section</th>
              <th style={{ padding: "8px 12px" }}>Status</th>
              <th style={{ padding: "8px 12px" }}>Filed</th>
              <th style={{ padding: "8px 12px" }}>Expires</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: "8px 12px" }}><code>{p.feature_slug}</code></td>
                <td style={{ padding: "8px 12px" }}><code>#{p.section_anchor}</code></td>
                <td style={{ padding: "8px 12px" }}>
                  <span style={{
                    padding: "2px 8px",
                    background: STATUS_COLORS[p.status],
                    color: "white",
                    borderRadius: 4,
                    fontSize: 12,
                  }}>{p.status}</span>
                </td>
                <td style={{ padding: "8px 12px", color: "#6b7280", fontSize: 13 }}>
                  {new Date(p.created_at).toLocaleString()}
                </td>
                <td style={{ padding: "8px 12px", color: "#6b7280", fontSize: 13 }}>
                  {new Date(p.expires_at).toLocaleDateString()}
                </td>
                <td style={{ padding: "8px 12px" }}>
                  <Link to={`/prd-proposals/${p.id}`} style={{ color: "#2563eb" }}>
                    Review →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function PrdProposalDetail({ id }: { id: string }) {
  const navigate = useNavigate();
  const [proposal, setProposal] = useState<PrdProposal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  useEffect(() => {
    getProposal(id).then(setProposal).catch((e) => setError(e.message));
  }, [id]);

  async function handleApprove() {
    if (!proposal) return;
    setBusy(true);
    try {
      const updated = await approveProposal(proposal.id);
      setProposal(updated);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleReject() {
    if (!proposal) return;
    setBusy(true);
    try {
      const updated = await rejectProposal(proposal.id, rejectReason || undefined);
      setProposal(updated);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <div style={{ padding: 24, color: "#ef4444" }}>Error: {error}</div>;
  if (!proposal) return <div style={{ padding: 24 }}>Loading…</div>;

  const isPending = proposal.status === "pending";

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "24px" }}>
      <button onClick={() => navigate("/prd-proposals")} style={{ marginBottom: 16 }}>
        ← Back to list
      </button>

      <h1>
        Proposal for <code>{proposal.feature_slug}</code>{" "}
        <small style={{ color: "#6b7280" }}>#{proposal.section_anchor}</small>
      </h1>

      <div style={{ marginBottom: 24 }}>
        <span style={{
          padding: "4px 12px",
          background: STATUS_COLORS[proposal.status],
          color: "white",
          borderRadius: 6,
          fontSize: 14,
        }}>
          {proposal.status}
        </span>
        <span style={{ marginLeft: 16, color: "#6b7280" }}>
          Filed {new Date(proposal.created_at).toLocaleString()}
        </span>
        <span style={{ marginLeft: 16, color: "#6b7280" }}>
          Expires {new Date(proposal.expires_at).toLocaleString()}
        </span>
      </div>

      {proposal.rationale && (
        <section style={{ marginBottom: 24 }}>
          <h3 style={{ margin: 0, marginBottom: 8 }}>Rationale</h3>
          <p style={{ color: "#374151", margin: 0 }}>{proposal.rationale}</p>
        </section>
      )}

      <section style={{ marginBottom: 24 }}>
        <h3 style={{ margin: 0, marginBottom: 8 }}>Proposed content</h3>
        <pre style={{
          background: "#f9fafb",
          border: "1px solid #e5e7eb",
          borderRadius: 6,
          padding: 16,
          maxHeight: 480,
          overflow: "auto",
          whiteSpace: "pre-wrap",
          fontSize: 13,
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        }}>{proposal.diff_md}</pre>
      </section>

      {proposal.status === "stale" && (
        <div style={{
          padding: 12,
          background: "#fef3c7",
          border: "1px solid #fbbf24",
          borderRadius: 6,
          marginBottom: 16,
        }}>
          <strong>Stale.</strong> The wiki feature changed after this proposal
          was filed. Reason: <em>{proposal.decided_reason}</em>
        </div>
      )}

      {proposal.decided_at && (
        <div style={{ color: "#6b7280", marginBottom: 16, fontSize: 13 }}>
          Decided {new Date(proposal.decided_at).toLocaleString()}
          {proposal.decided_reason && <> · {proposal.decided_reason}</>}
        </div>
      )}

      {isPending && (
        <section style={{ borderTop: "1px solid #e5e7eb", paddingTop: 16 }}>
          <h3>Decision</h3>
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <div style={{ flex: 1 }}>
              <textarea
                placeholder="Optional reason if rejecting"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                rows={2}
                style={{
                  width: "100%",
                  padding: 8,
                  border: "1px solid #e5e7eb",
                  borderRadius: 6,
                  fontFamily: "inherit",
                  fontSize: 14,
                  marginBottom: 8,
                }}
              />
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={handleApprove}
                  disabled={busy}
                  style={{
                    padding: "8px 16px",
                    background: "#10b981",
                    color: "white",
                    border: "none",
                    borderRadius: 6,
                    cursor: busy ? "wait" : "pointer",
                    fontWeight: 500,
                  }}
                >
                  {busy ? "Working…" : "Approve & apply"}
                </button>
                <button
                  onClick={handleReject}
                  disabled={busy}
                  style={{
                    padding: "8px 16px",
                    background: "#ef4444",
                    color: "white",
                    border: "none",
                    borderRadius: 6,
                    cursor: busy ? "wait" : "pointer",
                  }}
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
