import { useState } from "react";
import { Copy, Check, Key, Trash2, AlertTriangle } from "lucide-react";
import { useApiKeys } from "@/hooks/queries";
import { useCreateApiKey, useRevokeApiKey } from "@/hooks/mutations";
import { MCP_CLIENTS, buildMcpConfig } from "@/lib/mcp-config";
import type { McpClient } from "@/lib/mcp-config";
import type { ApiKeyCreateResponse } from "@/services/api";

export function McpSetup() {
  const [selectedClient, setSelectedClient] = useState<McpClient>("claude-code");
  const [createdKey, setCreatedKey] = useState<ApiKeyCreateResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [revokeConfirm, setRevokeConfirm] = useState<string | null>(null);

  const { data: apiKeys, isLoading } = useApiKeys();
  const createKey = useCreateApiKey();
  const revokeKey = useRevokeApiKey();

  const clientInfo = MCP_CLIENTS.find((c) => c.id === selectedClient)!;

  async function handleGenerate() {
    const label = MCP_CLIENTS.find((c) => c.id === selectedClient)!.label;
    const date = new Date().toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
    const result = await createKey.mutateAsync(`MCP - ${label} - ${date}`);
    setCreatedKey(result);
    setCopied(false);
  }

  async function handleCopy() {
    if (!createdKey) return;
    const config = buildMcpConfig(selectedClient, createdKey.key);
    await navigator.clipboard.writeText(config);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  }

  async function handleRevoke(keyId: string) {
    await revokeKey.mutateAsync(keyId);
    setRevokeConfirm(null);
    if (createdKey?.id === keyId) setCreatedKey(null);
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-surface-900">MCP Setup</h1>
        <p className="mt-1 text-surface-500">
          Connect your AI tools to Numen in one click.
        </p>
      </div>

      <div className="max-w-2xl space-y-6">
        {/* Client selector */}
        <div className="card space-y-4">
          <h2 className="font-semibold text-surface-900">1. Choose your AI tool</h2>
          <div className="flex flex-wrap gap-2">
            {MCP_CLIENTS.map((client) => (
              <button
                key={client.id}
                onClick={() => {
                  setSelectedClient(client.id);
                  setCreatedKey(null);
                  setCopied(false);
                }}
                className={
                  selectedClient === client.id
                    ? "rounded-lg px-4 py-2 text-sm font-medium bg-primary-50 text-primary-700 ring-1 ring-primary-200"
                    : "rounded-lg px-4 py-2 text-sm font-medium bg-surface-100 text-surface-600 hover:bg-surface-200"
                }
              >
                {client.label}
              </button>
            ))}
          </div>
        </div>

        {/* Generate key */}
        <div className="card space-y-4">
          <h2 className="font-semibold text-surface-900">2. Generate API key</h2>
          <p className="text-sm text-surface-500">{clientInfo.description}</p>

          {!createdKey ? (
            <button
              onClick={handleGenerate}
              disabled={createKey.isPending}
              className="btn-primary disabled:opacity-50"
            >
              <Key size={16} className="mr-2 inline" />
              {createKey.isPending ? "Generating..." : `Generate Key for ${clientInfo.label}`}
            </button>
          ) : (
            <div className="space-y-3">
              {/* Warning */}
              <div className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                <span>
                  This API key is shown only once. Copy the config below before
                  navigating away.
                </span>
              </div>

              {/* Config JSON */}
              <div className="relative">
                <pre className="overflow-x-auto rounded-lg bg-surface-900 p-4 text-sm text-surface-100 font-mono">
                  {buildMcpConfig(selectedClient, createdKey.key)}
                </pre>
                <button
                  onClick={handleCopy}
                  className="absolute right-3 top-3 rounded-md bg-surface-700 p-1.5 text-surface-300 hover:bg-surface-600 hover:text-white transition-colors"
                  title="Copy to clipboard"
                >
                  {copied ? <Check size={16} /> : <Copy size={16} />}
                </button>
              </div>

              {/* Instructions */}
              {selectedClient === "claude-code" ? (
                <p className="text-xs text-surface-500">
                  Run this command in your terminal. New <code className="rounded bg-surface-100 px-1 py-0.5">claude</code> sessions will see Numen automatically.
                </p>
              ) : selectedClient !== "cli" ? (
                <p className="text-xs text-surface-500">
                  Paste this into <code className="rounded bg-surface-100 px-1 py-0.5">{clientInfo.configPath}</code>
                </p>
              ) : null}

              {/* Generate another */}
              <button
                onClick={() => {
                  setCreatedKey(null);
                  setCopied(false);
                }}
                className="text-sm text-primary-600 hover:text-primary-700"
              >
                Generate another key
              </button>
            </div>
          )}
        </div>

        {/* Existing keys */}
        <div className="card space-y-4">
          <h2 className="font-semibold text-surface-900">API Keys</h2>

          {isLoading ? (
            <p className="text-sm text-surface-500">Loading...</p>
          ) : !apiKeys?.length ? (
            <p className="text-sm text-surface-500">No API keys yet.</p>
          ) : (
            <div className="divide-y divide-surface-100">
              {apiKeys
                .filter((k) => k.is_active)
                .map((key) => (
                  <div
                    key={key.id}
                    className="flex items-center justify-between py-3 first:pt-0 last:pb-0"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-surface-900 truncate">
                        {key.name}
                      </p>
                      <p className="text-xs text-surface-500">
                        Created{" "}
                        {new Date(key.created_at).toLocaleDateString()}
                        {key.last_used_at && (
                          <>
                            {" "}
                            - Last used{" "}
                            {new Date(key.last_used_at).toLocaleDateString()}
                          </>
                        )}
                      </p>
                    </div>
                    {revokeConfirm === key.id ? (
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-surface-500">Revoke?</span>
                        <button
                          onClick={() => handleRevoke(key.id)}
                          disabled={revokeKey.isPending}
                          className="text-xs font-medium text-red-600 hover:text-red-700"
                        >
                          Yes
                        </button>
                        <button
                          onClick={() => setRevokeConfirm(null)}
                          className="text-xs font-medium text-surface-500 hover:text-surface-700"
                        >
                          No
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setRevokeConfirm(key.id)}
                        className="rounded p-1.5 text-surface-400 hover:bg-red-50 hover:text-red-600 transition-colors"
                        title="Revoke key"
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </div>
                ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
