// /account/keys - mint, list, revoke, rotate (WS3).

import { useEffect, useState } from "react";
import { AccountKey, listMyKeys, mintKey, revokeKey, rotateKey } from "../api/accountKeys";

export function AccountKeys() {
  const [keys, setKeys] = useState<AccountKey[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [mintName, setMintName] = useState("");
  const [mintExpiry, setMintExpiry] = useState(90);
  const [justMinted, setJustMinted] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      const r = await listMyKeys();
      setKeys(r.items);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleMint(e: React.FormEvent) {
    e.preventDefault();
    if (!mintName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const minted = await mintKey({ name: mintName.trim(), expires_in_days: mintExpiry });
      setJustMinted(minted.plaintext);
      setMintName("");
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke(id: string) {
    if (!window.confirm("Revoke this key? Apps using it will stop working immediately.")) return;
    setBusy(true);
    try {
      await revokeKey(id);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRotate(id: string) {
    if (!window.confirm("Rotate this key? The old one stops working immediately. You will need to update your client config.")) return;
    setBusy(true);
    try {
      const minted = await rotateKey(id);
      setJustMinted(minted.plaintext);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "24px" }}>
      <h1>API keys</h1>
      <p style={{ color: "#6b7280", marginBottom: 24 }}>
        Keys for your agent clients (Claude Code, Conductor, Cursor, etc.).
        New keys default to a 90-day expiry. Revoke anything you don't recognize.
      </p>

      {error && (
        <div style={{
          padding: 12, background: "#fef2f2", border: "1px solid #ef4444",
          borderRadius: 6, marginBottom: 16, color: "#991b1b",
        }}>
          Error: {error}
        </div>
      )}

      {justMinted && (
        <div style={{
          padding: 16, background: "#ecfdf5", border: "1px solid #10b981",
          borderRadius: 6, marginBottom: 24,
        }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>
            New key. Save it now - it will not be shown again.
          </div>
          <code style={{
            display: "block", padding: 12, background: "#f9fafb",
            border: "1px solid #e5e7eb", borderRadius: 4, wordBreak: "break-all",
          }}>{justMinted}</code>
          <button
            onClick={() => navigator.clipboard?.writeText(justMinted)}
            style={{ marginTop: 8, padding: "6px 12px" }}
          >
            Copy to clipboard
          </button>
          <button
            onClick={() => setJustMinted(null)}
            style={{ marginLeft: 8, padding: "6px 12px" }}
          >
            I've saved it - dismiss
          </button>
        </div>
      )}

      <form onSubmit={handleMint} style={{
        display: "flex", gap: 8, alignItems: "flex-end",
        padding: 16, background: "#f9fafb", border: "1px solid #e5e7eb",
        borderRadius: 6, marginBottom: 24,
      }}>
        <div style={{ flex: 1 }}>
          <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>
            Key name (e.g. "Claude Code on macbook-pro")
          </label>
          <input
            type="text"
            value={mintName}
            onChange={(e) => setMintName(e.target.value)}
            placeholder="My new key"
            style={{
              width: "100%", padding: "8px 12px",
              border: "1px solid #d1d5db", borderRadius: 6,
            }}
          />
        </div>
        <div>
          <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>
            Expires in (days)
          </label>
          <input
            type="number"
            value={mintExpiry}
            min={1}
            max={365}
            onChange={(e) => setMintExpiry(parseInt(e.target.value) || 90)}
            style={{
              width: 100, padding: "8px 12px",
              border: "1px solid #d1d5db", borderRadius: 6,
            }}
          />
        </div>
        <button
          type="submit"
          disabled={busy || !mintName.trim()}
          style={{
            padding: "8px 16px", background: "#1f2937", color: "white",
            border: "none", borderRadius: 6, cursor: "pointer",
          }}
        >
          {busy ? "…" : "Mint key"}
        </button>
      </form>

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #e5e7eb", textAlign: "left" }}>
            <th style={{ padding: "8px 12px" }}>Name</th>
            <th style={{ padding: "8px 12px" }}>Created</th>
            <th style={{ padding: "8px 12px" }}>Last used</th>
            <th style={{ padding: "8px 12px" }}>Expires</th>
            <th style={{ padding: "8px 12px" }}>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {keys.length === 0 ? (
            <tr><td colSpan={6} style={{ padding: 24, color: "#6b7280", textAlign: "center" }}>
              No keys yet. Mint one above.
            </td></tr>
          ) : keys.map((k) => (
            <tr key={k.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
              <td style={{ padding: "8px 12px" }}>{k.name}</td>
              <td style={{ padding: "8px 12px", color: "#6b7280", fontSize: 13 }}>
                {new Date(k.created_at).toLocaleDateString()}
              </td>
              <td style={{ padding: "8px 12px", color: "#6b7280", fontSize: 13 }}>
                {k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "never"}
              </td>
              <td style={{ padding: "8px 12px", color: "#6b7280", fontSize: 13 }}>
                {k.expires_at ? new Date(k.expires_at).toLocaleDateString() : "never"}
              </td>
              <td style={{ padding: "8px 12px" }}>
                <span style={{
                  padding: "2px 8px",
                  background: k.is_active ? "#10b981" : "#9ca3af",
                  color: "white", borderRadius: 4, fontSize: 12,
                }}>
                  {k.is_active ? "active" : "revoked"}
                </span>
              </td>
              <td style={{ padding: "8px 12px" }}>
                {k.is_active && (
                  <>
                    <button onClick={() => handleRotate(k.id)} disabled={busy}
                      style={{ marginRight: 8, padding: "4px 10px", fontSize: 13 }}>
                      Rotate
                    </button>
                    <button onClick={() => handleRevoke(k.id)} disabled={busy}
                      style={{ padding: "4px 10px", fontSize: 13, color: "#ef4444" }}>
                      Revoke
                    </button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
