import { Link } from "react-router-dom";
import { CheckCircle, AlertCircle, Cable, ArrowRight } from "lucide-react";
import type { ConnectorStatus } from "@/types";

interface SyncStatusCompactProps {
  connectors: ConnectorStatus[];
  loading?: boolean;
}

export function SyncStatusCompact({ connectors, loading }: SyncStatusCompactProps) {
  const connected = connectors.filter((c) => c.connected);
  const hasErrors = connected.some((c) => c.status === "error");

  if (loading) {
    return (
      <div className="card">
        <div className="h-4 w-28 animate-pulse rounded bg-surface-200" />
      </div>
    );
  }

  if (connectors.length === 0) {
    return (
      <div className="card">
        <Link
          to="/connections"
          className="flex items-center gap-2 text-sm text-primary-600 hover:text-primary-700"
        >
          <Cable size={14} />
          <span>Connect integrations</span>
          <ArrowRight size={14} />
        </Link>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Cable size={14} className="text-surface-400" />
          <span className="text-xs font-medium text-surface-600">
            {connected.length} connected
          </span>
        </div>
        {hasErrors ? (
          <AlertCircle size={14} className="text-red-500" />
        ) : (
          <CheckCircle size={14} className="text-green-500" />
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {connected.map((c) => (
          <Link
            key={c.connector}
            to={`/connections/${c.connector}`}
            className="inline-flex items-center gap-1 rounded-full bg-surface-100 px-2 py-0.5 text-[10px] font-medium text-surface-600 hover:bg-surface-200 transition-colors capitalize"
          >
            {c.status === "error" && (
              <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
            )}
            {c.connector}
          </Link>
        ))}
        {connectors.filter((c) => !c.connected).length > 0 && (
          <Link
            to="/connections"
            className="inline-flex items-center gap-1 rounded-full bg-primary-50 px-2 py-0.5 text-[10px] font-medium text-primary-600 hover:bg-primary-100"
          >
            + more
          </Link>
        )}
      </div>
    </div>
  );
}
