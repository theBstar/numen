import { useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Check,
  X,
  RefreshCw,
  Cable,
  ExternalLink,
  Lock,
  Globe,
  Search,
} from "lucide-react";
import { useConnectors, useEntities, useGitHubRepos } from "@/hooks/queries";
import { useOrgContext } from "@/contexts/OrgContext";
import { connectorMeta } from "@/components/ConnectorCard";
import { EmptyState } from "@/components/EmptyState";
import {
  getConnectorAuthUrl,
  disconnectConnector,
  updateConnectorSettings,
  triggerSync,
} from "@/services/api";
import { cn, formatRelativeTime } from "@/lib/utils";

const TYPE_LABELS: Record<string, string> = {
  task: "Task",
  commit_pr: "PR",
  deploy: "Deploy",
  person: "Person",
  goal: "Goal",
  project: "Project",
  feature: "Feature",
  incident: "Incident",
  error_event: "Error",
  decision: "Decision",
  document: "Document",
  metric_snapshot: "Metric",
};

const TYPE_COLORS: Record<string, string> = {
  task: "bg-blue-100 text-blue-700",
  commit_pr: "bg-purple-100 text-purple-700",
  deploy: "bg-green-100 text-green-700",
  person: "bg-amber-100 text-amber-700",
  goal: "bg-red-100 text-red-700",
  project: "bg-indigo-100 text-indigo-700",
  feature: "bg-cyan-100 text-cyan-700",
  incident: "bg-orange-100 text-orange-700",
  error_event: "bg-rose-100 text-rose-700",
  decision: "bg-teal-100 text-teal-700",
  document: "bg-slate-100 text-slate-700",
};

function getStatusFromProps(properties: Record<string, unknown>): string | null {
  return (
    (properties?.status as string) ||
    (properties?.state as string) ||
    (properties?.state_name as string) ||
    null
  );
}

export function ConnectorDetail() {
  const { connector } = useParams<{ connector: string }>();
  const navigate = useNavigate();
  useOrgContext(); // ensure org context is ready
  const { data: connectors, refetch: refetchConnectors } = useConnectors();
  const { data: sourceEntities, refetch: refetchEntities } = useEntities({
    source: connector,
    pageSize: 200,
  });
  const { data: repoData, isPending: reposLoading, refetch: refetchRepos } = useGitHubRepos();

  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<string | null>(null);
  const [repoSearch, setRepoSearch] = useState("");
  const [togglingRepo, setTogglingRepo] = useState<string | null>(null);

  const meta = connector
    ? connectorMeta[connector] ?? {
        name: connector,
        color: "bg-surface-600",
        description: "External data source",
      }
    : null;

  const status = connectors?.find((c) => c.connector === connector);
  const isGitHub = connector === "github";

  const entities = useMemo(() => {
    if (!sourceEntities) return [];
    return [...sourceEntities].sort(
      (a, b) =>
        new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    );
  }, [sourceEntities]);

  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const e of entities) {
      counts[e.type] = (counts[e.type] || 0) + 1;
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [entities]);

  const filteredRepos = useMemo(() => {
    if (!repoData?.repos) return [];
    if (!repoSearch) return repoData.repos;
    const q = repoSearch.toLowerCase();
    return repoData.repos.filter(
      (r) =>
        r.full_name.toLowerCase().includes(q) ||
        (r.description || "").toLowerCase().includes(q),
    );
  }, [repoData, repoSearch]);

  const enabledCount = repoData?.repos.filter((r) => r.enabled).length ?? 0;

  if (!connector || !meta) {
    return (
      <div className="space-y-4">
        <p className="text-surface-500">Connector not found.</p>
      </div>
    );
  }

  async function handleConnect() {
    try {
      const url = await getConnectorAuthUrl(connector!);
      if (url) window.location.href = url;
    } catch (err) {
      console.error("Failed to get auth URL:", err);
    }
  }

  async function handleDisconnect() {
    try {
      await disconnectConnector(connector!);
      refetchConnectors();
    } catch {
      // ignore
    }
  }

  async function handleSync() {
    setSyncing(true);
    setSyncResult(null);
    try {
      const result = await triggerSync(connector!);
      setSyncResult(
        `Synced: ${result.entities_created} created, ${result.entities_updated} updated`,
      );
      refetchConnectors();
      refetchEntities();
    } catch (err) {
      setSyncResult(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  async function handleToggleRepo(repoFullName: string, currentlyEnabled: boolean) {
    if (!repoData) return;
    setTogglingRepo(repoFullName);

    const currentSelected = repoData.repos
      .filter((r) => r.enabled)
      .map((r) => r.full_name);

    const newSelected = currentlyEnabled
      ? currentSelected.filter((r) => r !== repoFullName)
      : [...currentSelected, repoFullName];

    try {
      await updateConnectorSettings(connector!, { selected_repos: newSelected });
      refetchRepos();
    } catch (err) {
      console.error("Failed to update settings:", err);
    } finally {
      setTogglingRepo(null);
    }
  }

  return (
    <div className="space-y-6">
      {/* Back link */}
      <button
        onClick={() => navigate("/connections")}
        className="flex items-center gap-1.5 text-sm text-surface-500 hover:text-surface-700 transition-colors"
      >
        <ArrowLeft size={14} />
        Back to Connections
      </button>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <div
            className={cn(
              "flex h-12 w-12 items-center justify-center rounded-xl text-white text-lg font-bold",
              meta.color,
            )}
          >
            {meta.name.charAt(0)}
          </div>
          <div>
            <h1 className="text-2xl font-bold text-surface-900">{meta.name}</h1>
            <p className="text-surface-500">{meta.description}</p>
          </div>
        </div>

        {status?.connected ? (
          <button
            onClick={handleDisconnect}
            className="flex items-center gap-2 rounded-lg border border-red-200 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 transition-colors"
          >
            <X size={14} />
            Disconnect
          </button>
        ) : (
          <button
            onClick={handleConnect}
            className="flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 transition-colors"
          >
            Connect {meta.name}
          </button>
        )}
      </div>

      {/* Connection details card */}
      <div className="rounded-xl border border-surface-200 bg-white p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-surface-900">
            Connection Details
          </h2>
          {status?.connected && (
            <button
              onClick={handleSync}
              disabled={syncing}
              className="flex items-center gap-2 rounded-lg border border-surface-200 px-3 py-1.5 text-sm font-medium text-surface-600 hover:bg-surface-50 transition-colors disabled:opacity-50"
            >
              <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
              {syncing ? "Syncing..." : "Sync Now"}
            </button>
          )}
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <p className="text-xs text-surface-500 mb-1">Status</p>
            <div className="flex items-center gap-1.5">
              {status?.connected ? (
                <>
                  <Check size={14} className="text-green-600" />
                  <span className="text-sm font-medium text-green-700">
                    Connected
                  </span>
                </>
              ) : (
                <>
                  <X size={14} className="text-surface-400" />
                  <span className="text-sm font-medium text-surface-500">
                    Disconnected
                  </span>
                </>
              )}
            </div>
          </div>
          <div>
            <p className="text-xs text-surface-500 mb-1">Last Synced</p>
            <p className="text-sm text-surface-700">
              {status?.last_sync_at
                ? formatRelativeTime(status.last_sync_at)
                : "-"}
            </p>
          </div>
          <div>
            <p className="text-xs text-surface-500 mb-1">Sync Status</p>
            <div className="flex items-center gap-1.5">
              {status?.status === "syncing" && (
                <RefreshCw size={12} className="animate-spin text-blue-500" />
              )}
              <span
                className={cn(
                  "text-sm capitalize",
                  status?.status === "error"
                    ? "text-red-600"
                    : "text-surface-700",
                )}
              >
                {status?.status || "-"}
              </span>
            </div>
          </div>
          <div>
            <p className="text-xs text-surface-500 mb-1">Entities</p>
            <p className="text-sm font-medium text-surface-700">
              {entities.length}
            </p>
          </div>
        </div>
        {status?.error_message && (
          <div className="mt-4 rounded-lg bg-red-50 border border-red-100 px-4 py-3">
            <p className="text-sm text-red-700">{status.error_message}</p>
          </div>
        )}
        {syncResult && (
          <div className="mt-4 rounded-lg bg-blue-50 border border-blue-100 px-4 py-3">
            <p className="text-sm text-blue-700">{syncResult}</p>
          </div>
        )}
      </div>

      {/* GitHub Repo Selection */}
      {isGitHub && status?.connected && (
        <div className="rounded-xl border border-surface-200 bg-white p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-semibold text-surface-900">
                Repositories
              </h2>
              <p className="text-xs text-surface-500 mt-0.5">
                {enabledCount > 0
                  ? `${enabledCount} of ${repoData?.repos.length ?? 0} enabled - webhooks active for real-time updates`
                  : "Enable repos to sync data and receive real-time webhook updates"}
              </p>
            </div>
          </div>

          {/* Search */}
          <div className="relative mb-3">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" size={14} />
            <input
              type="text"
              placeholder="Search repos..."
              value={repoSearch}
              onChange={(e) => setRepoSearch(e.target.value)}
              className="w-full rounded-lg border border-surface-200 bg-white py-2 pl-9 pr-4 text-sm placeholder:text-surface-400 focus:border-primary-300 focus:outline-none focus:ring-2 focus:ring-primary-100"
            />
          </div>

          {/* Repo list */}
          {reposLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-12 animate-pulse rounded-lg bg-surface-100" />
              ))}
            </div>
          ) : filteredRepos.length === 0 ? (
            <p className="py-4 text-center text-sm text-surface-400">
              {repoSearch ? "No repos match your search." : "No repos found."}
            </p>
          ) : (
            <div className="max-h-80 overflow-y-auto space-y-1">
              {filteredRepos.map((repo) => (
                <div
                  key={repo.full_name}
                  className="flex items-center justify-between rounded-lg px-3 py-2.5 hover:bg-surface-50 transition-colors"
                >
                  <div className="min-w-0 flex-1 mr-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-surface-900 truncate">
                        {repo.full_name}
                      </span>
                      {repo.private ? (
                        <Lock size={12} className="shrink-0 text-surface-400" />
                      ) : (
                        <Globe size={12} className="shrink-0 text-surface-400" />
                      )}
                    </div>
                    {repo.description && (
                      <p className="text-xs text-surface-500 truncate mt-0.5">
                        {repo.description}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={() => handleToggleRepo(repo.full_name, repo.enabled)}
                    disabled={togglingRepo === repo.full_name}
                    className={cn(
                      "relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50",
                      repo.enabled ? "bg-primary-600" : "bg-surface-200",
                    )}
                  >
                    <span
                      className={cn(
                        "pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out",
                        repo.enabled ? "translate-x-5" : "translate-x-0",
                      )}
                    />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Type breakdown */}
      {typeCounts.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {typeCounts.map(([type, count]) => (
            <span
              key={type}
              className={cn(
                "rounded-full px-2.5 py-1 text-xs font-medium",
                TYPE_COLORS[type] || "bg-surface-100 text-surface-600",
              )}
            >
              {count} {TYPE_LABELS[type] || type}
              {count !== 1 ? "s" : ""}
            </span>
          ))}
        </div>
      )}

      {/* Data table */}
      <div>
        <h2 className="text-sm font-semibold text-surface-900 mb-3">
          Data from {meta.name}
        </h2>

        {entities.length === 0 ? (
          <EmptyState
            icon={Cable}
            title={`No data from ${meta.name}`}
            description={
              status?.connected
                ? "Enable repos above and click Sync Now, or data will appear after the next sync cycle."
                : `Connect ${meta.name} to start syncing data.`
            }
            action={
              !status?.connected
                ? { label: `Connect ${meta.name}`, onClick: handleConnect }
                : undefined
            }
          />
        ) : (
          <div className="rounded-xl border border-surface-200 bg-white overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-surface-100 bg-surface-50 text-left">
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-surface-500">
                    Type
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-surface-500">
                    Name
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-surface-500">
                    Status
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-surface-500">
                    Last Updated
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-surface-500 w-10"></th>
                </tr>
              </thead>
              <tbody>
                {entities.map((entity) => {
                  const props = (entity.properties || {}) as Record<
                    string,
                    unknown
                  >;
                  const entityStatus = getStatusFromProps(props);

                  return (
                    <tr
                      key={entity.id}
                      className="border-b border-surface-50 transition-colors hover:bg-surface-50 cursor-pointer"
                      onClick={() => navigate(`/entities/${entity.id}`)}
                    >
                      <td className="px-4 py-3">
                        <span
                          className={cn(
                            "rounded-full px-2 py-0.5 text-xs font-medium",
                            TYPE_COLORS[entity.type] ||
                              "bg-surface-100 text-surface-600",
                          )}
                        >
                          {TYPE_LABELS[entity.type] || entity.type}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-sm font-medium text-surface-900">
                          {entity.canonical_name}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {entityStatus ? (
                          <span className="text-sm text-surface-600 capitalize">
                            {entityStatus.replace(/_/g, " ")}
                          </span>
                        ) : (
                          <span className="text-sm text-surface-400">-</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-surface-500">
                        {formatRelativeTime(entity.updated_at)}
                      </td>
                      <td className="px-4 py-3">
                        <ExternalLink
                          size={14}
                          className="text-surface-300"
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
