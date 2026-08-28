import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { setAccessToken } from "@/services/api";
import { analytics } from "@/analytics";
import { trackLoggedIn } from "@/analytics/events";

const API_BASE = import.meta.env.VITE_API_URL || "";

export function AuthCallback() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const calledRef = useRef(false);

  useEffect(() => {
    if (calledRef.current) return;
    calledRef.current = true;

    const code = searchParams.get("code");
    const state = searchParams.get("state");

    if (!code) {
      setError("No authorization code received from Google.");
      return;
    }

    const redirectUri = `${window.location.origin}/auth/google/callback`;

    fetch(`${API_BASE}/api/auth/google/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, redirect_uri: redirectUri }),
    })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || "Login failed");
        }
        return res.json();
      })
      .then((data) => {
        if (!data.access_token) {
          throw new Error("No access token received");
        }

        setAccessToken(data.access_token);
        localStorage.setItem("numen_access_token", data.access_token);

        if (data.refresh_token) {
          localStorage.setItem("numen_refresh_token", data.refresh_token);
        }

        // Store user info for onboarding pre-fill and context
        if (data.user) {
          localStorage.setItem("numen_user", JSON.stringify(data.user));
        }

        if (data.user?.is_admin) {
          localStorage.setItem("numen_is_admin", "true");
        } else {
          localStorage.removeItem("numen_is_admin");
        }

        if (data.orgs) {
          localStorage.setItem("numen_orgs", JSON.stringify(data.orgs));
        }

        if (data.needs_onboarding) {
          localStorage.setItem("numen_needs_onboarding", "true");
        } else {
          localStorage.removeItem("numen_needs_onboarding");
          if (data.orgs?.length > 0) {
            const firstOrg = data.orgs[0];
            localStorage.setItem("numen_org_id", firstOrg.id);
            localStorage.setItem("numen_org_name", firstOrg.name);
            localStorage.setItem("numen_is_demo", String(!!firstOrg.is_demo));
          }
        }

        const firstOrg = data.orgs?.[0];
        if (data.user && firstOrg) {
          analytics.identify(String(data.user.id ?? data.user.email ?? ""), {
            email: data.user.email,
            name: data.user.name,
          });
          analytics.group(String(firstOrg.id), { name: firstOrg.name, is_demo: !!firstOrg.is_demo });
          trackLoggedIn({
            memberId: String(data.user.id ?? data.user.email ?? ""),
            orgId: String(firstOrg.id),
            isNewMember: !!data.needs_onboarding,
          });
        }

        // Always go to the intended page - onboarding modal will overlay if needed
        const savedRedirect = localStorage.getItem("numen_redirect_after_login");
        localStorage.removeItem("numen_redirect_after_login");
        const redirectTo = state || savedRedirect || "/dashboard";
        navigate(redirectTo, { replace: true });
      })
      .catch((err) => {
        setError(err.message || "Authentication failed");
      });
  }, [searchParams, navigate]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-50">
        <div className="w-full max-w-sm space-y-6 rounded-xl border border-surface-200 bg-white p-8 shadow-lg text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-red-100 text-lg font-bold text-red-600">
            !
          </div>
          <h1 className="text-xl font-bold text-surface-900">Login Failed</h1>
          <p className="text-sm text-surface-500">{error}</p>
          <button
            onClick={() => navigate("/login", { replace: true })}
            className="w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-primary-700"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  // Full-page branded loader
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-surface-50">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-600 text-xl font-bold text-white mb-6">
        N
      </div>
      <div className="flex items-center gap-3">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary-600 border-t-transparent" />
        <p className="text-sm font-medium text-surface-600">Signing you in...</p>
      </div>
    </div>
  );
}
