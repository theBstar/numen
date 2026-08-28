// Living Mac SSO bridge.
//
// The Mac app deep-links the browser to /auth/living-mac. This page sits
// inside AuthGuard, so by the time the component renders, localStorage has a
// valid Numen access token. We POST it to /api/living/auth/mac (with
// Accept: application/json), receive the minted MCP key + redirect URI, and
// hand off to the Mac app via the living:// custom URL scheme.

import { useEffect, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "";

export function LivingMacAuth() {
  const calledRef = useRef(false);
  const [status, setStatus] = useState<"working" | "redirecting" | "error">("working");
  const [error, setError] = useState<string | null>(null);
  const [redirectUri, setRedirectUri] = useState<string | null>(null);

  useEffect(() => {
    if (calledRef.current) return;
    calledRef.current = true;

    const token = localStorage.getItem("numen_access_token");
    if (!token) {
      setStatus("error");
      setError("Not logged in. AuthGuard should have caught this.");
      return;
    }

    fetch(`${API_BASE}/api/living/auth/mac`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
      },
    })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `HTTP ${res.status}`);
        }
        return res.json() as Promise<{ token: string; redirect_uri: string }>;
      })
      .then((data) => {
        if (!data.redirect_uri || !data.redirect_uri.startsWith("living://")) {
          throw new Error("Backend returned an invalid redirect_uri");
        }
        setRedirectUri(data.redirect_uri);
        setStatus("redirecting");
        // Hand off to the Mac app. macOS routes living:// to the registered
        // .app bundle, which calls KeychainAuth.handleCallbackURL and stores
        // the token under the per-host slot for this Numen instance.
        window.location.href = data.redirect_uri;
      })
      .catch((e: Error) => {
        setStatus("error");
        setError(e.message);
      });
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-stone-950 text-stone-200">
      <div className="max-w-md w-full p-8 border border-stone-800 rounded-lg bg-stone-900 font-mono text-sm">
        <h1 className="text-lg mb-4">
          {status === "working" && "Minting your Living key…"}
          {status === "redirecting" && "Sending you back to Living…"}
          {status === "error" && "Could not connect Living"}
        </h1>

        {status === "working" && (
          <p className="text-stone-400">
            Asking Numen for an MCP key scoped to your account. This takes a
            second.
          </p>
        )}

        {status === "redirecting" && (
          <>
            <p className="text-stone-400 mb-4">
              The Living Mac app should focus automatically. If it does not,
              click the link below.
            </p>
            {redirectUri && (
              <a
                href={redirectUri}
                className="text-emerald-400 underline break-all"
              >
                Open in Living
              </a>
            )}
          </>
        )}

        {status === "error" && (
          <>
            <p className="text-red-400 mb-2">{error}</p>
            <p className="text-stone-400 text-xs">
              If your Numen session expired, log out and back in, then try
              again from the Mac app.
            </p>
            <a
              href="/dashboard"
              className="inline-block mt-4 text-emerald-400 underline"
            >
              Back to dashboard
            </a>
          </>
        )}
      </div>
    </div>
  );
}
