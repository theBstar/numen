// Client for /api/prd/proposals (WS1).

const API_BASE = import.meta.env.VITE_API_URL || "";

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("numen_access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export type ProposalStatus = "pending" | "applied" | "rejected" | "stale" | "expired";

export interface PrdProposal {
  id: string;
  org_id: string;
  feature_slug: string;
  section_anchor: string;
  diff_md: string;
  rationale: string;
  status: ProposalStatus;
  base_content_hash: string;
  base_updated_at: string | null;
  proposer_user_id: string | null;
  decided_by_user_id: string | null;
  decided_at: string | null;
  decided_reason: string | null;
  applied_content_hash: string | null;
  created_at: string;
  expires_at: string;
}

export interface ProposalListResponse {
  items: PrdProposal[];
  count: number;
}

export async function listProposals(opts: {
  status?: ProposalStatus;
  feature_slug?: string;
  only_mine?: boolean;
  limit?: number;
} = {}): Promise<ProposalListResponse> {
  const qs = new URLSearchParams();
  if (opts.status) qs.set("status", opts.status);
  if (opts.feature_slug) qs.set("feature_slug", opts.feature_slug);
  if (opts.only_mine) qs.set("only_mine", "true");
  if (opts.limit) qs.set("limit", String(opts.limit));
  const url = `${API_BASE}/api/prd/proposals${qs.toString() ? "?" + qs : ""}`;
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) throw new Error(`listProposals: HTTP ${res.status}`);
  return res.json();
}

export async function getProposal(id: string): Promise<PrdProposal> {
  const res = await fetch(`${API_BASE}/api/prd/proposals/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`getProposal: HTTP ${res.status}`);
  return res.json();
}

export async function approveProposal(id: string): Promise<PrdProposal> {
  const res = await fetch(`${API_BASE}/api/prd/proposals/${id}/approve`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail?.message || `approveProposal: HTTP ${res.status}`);
  }
  return res.json();
}

export async function rejectProposal(id: string, reason?: string): Promise<PrdProposal> {
  const res = await fetch(`${API_BASE}/api/prd/proposals/${id}/reject`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ reason: reason || null }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail?.message || `rejectProposal: HTTP ${res.status}`);
  }
  return res.json();
}
