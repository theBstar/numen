import { trackLoginStarted } from "@/analytics/events";

const API_BASE = import.meta.env.VITE_API_URL || "";

export async function startGoogleLogin(): Promise<void> {
  trackLoginStarted("google");

  const redirectUri = `${window.location.origin}/auth/google/callback`;
  const savedRedirect = localStorage.getItem("numen_redirect_after_login") || "/dashboard";

  const res = await fetch(`${API_BASE}/api/auth/google/auth-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ redirect_uri: redirectUri, state: savedRedirect }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to start login");
  }

  const data = await res.json();
  window.location.href = data.authorization_url;
}
