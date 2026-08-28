import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { exchangeConnectorCode } from "@/services/api";

export function ConnectorOAuthCallback() {
  const { connector } = useParams<{ connector: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const calledRef = useRef(false);

  useEffect(() => {
    if (calledRef.current) return;
    calledRef.current = true;

    const code = searchParams.get("code");
    const state = searchParams.get("state");

    if (!code || !connector) {
      setError("Missing authorization code or connector.");
      return;
    }

    exchangeConnectorCode(connector, code, state || "")
      .then(() => {
        navigate(`/connections/${connector}`, { replace: true });
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to connect");
      });
  }, [connector, searchParams, navigate]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-50">
        <div className="w-full max-w-sm space-y-6 rounded-xl border border-surface-200 bg-white p-8 shadow-lg text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-red-100 text-lg font-bold text-red-600">
            !
          </div>
          <h1 className="text-xl font-bold text-surface-900">Connection Failed</h1>
          <p className="text-sm text-surface-500">{error}</p>
          <button
            onClick={() => navigate("/connections", { replace: true })}
            className="w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-primary-700"
          >
            Back to Connections
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-surface-50">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-600 text-xl font-bold text-white mb-6">
        N
      </div>
      <div className="flex items-center gap-3">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary-600 border-t-transparent" />
        <p className="text-sm font-medium text-surface-600">
          Connecting {connector}...
        </p>
      </div>
    </div>
  );
}
