// Client for /api/account/keys (WS3).

const API_BASE = import.meta.env.VITE_API_URL || "";

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("numen_access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export interface AccountKey {
  id: string;
  name: string;
  org_id: string;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
}

export interface MintedKey extends AccountKey {
  plaintext: string;
}

export async function listMyKeys(): Promise<{ items: AccountKey[] }> {
  const res = await fetch(`${API_BASE}/api/account/keys`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`listMyKeys: HTTP ${res.status}`);
  return res.json();
}

export async function mintKey(opts: { name: string; org_id?: string; expires_in_days?: number }): Promise<MintedKey> {
  const res = await fetch(`${API_BASE}/api/account/keys`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(opts),
  });
  if (!res.ok) throw new Error(`mintKey: HTTP ${res.status}`);
  return res.json();
}

export async function revokeKey(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/account/keys/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`revokeKey: HTTP ${res.status}`);
}

export async function rotateKey(id: string): Promise<MintedKey> {
  const res = await fetch(`${API_BASE}/api/account/keys/${id}/rotate`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`rotateKey: HTTP ${res.status}`);
  return res.json();
}
