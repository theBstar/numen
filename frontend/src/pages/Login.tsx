import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { setAccessToken, tryRefreshToken } from "@/services/api";
import { startGoogleLogin } from "@/services/googleLogin";

export function Login() {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // If already logged in, redirect to home
  useEffect(() => {
    const accessToken = localStorage.getItem("numen_access_token");
    if (accessToken) {
      setAccessToken(accessToken);
      navigate("/dashboard");
      return;
    }
    // Try refresh if we have a refresh token
    const refreshToken = localStorage.getItem("numen_refresh_token");
    if (refreshToken) {
      setLoading(true);
      tryRefreshToken().then((ok) => {
        if (ok) navigate("/dashboard");
        else setLoading(false);
      });
    }
  }, [navigate]);

  async function handleGoogleLogin() {
    setError(null);
    setLoading(true);
    try {
      await startGoogleLogin();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to start login");
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-50">
      <div className="w-full max-w-sm space-y-8 rounded-xl border border-surface-200 bg-white p-8 shadow-lg">
        <div className="text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-primary-600 text-lg font-bold text-white">
            N
          </div>
          <h1 className="mt-4 text-2xl font-bold text-surface-900">
            Welcome to Numen
          </h1>
          <p className="mt-2 text-sm text-surface-500">
            Sign in to access your work intelligence dashboard.
          </p>
        </div>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <button
          onClick={handleGoogleLogin}
          disabled={loading}
          className="flex w-full items-center justify-center gap-3 rounded-lg border border-surface-300 bg-white px-4 py-3 text-sm font-medium text-surface-700 shadow-sm transition-colors hover:bg-surface-50 disabled:opacity-50"
        >
          {loading ? (
            <span>Signing in...</span>
          ) : (
            <>
              <svg className="h-5 w-5" viewBox="0 0 24 24">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
              </svg>
              <span>Continue with Google</span>
            </>
          )}
        </button>

        <p className="text-center text-xs text-surface-400">
          By signing in, you agree to Numen's terms of service.
        </p>
      </div>
    </div>
  );
}
