import { useNavigate } from "react-router-dom";
import { ConnectorCard } from "@/components/ConnectorCard";
import { useConnectors } from "@/hooks/queries";
import { getConnectorAuthUrl } from "@/services/api";

export function Connections() {
  const navigate = useNavigate();
  const { data: connectors, isPending: loading } = useConnectors();
  const displayConnectors = connectors ?? [];

  async function handleToggle(connectorName: string, connected: boolean) {
    if (connected) {
      // Navigate to detail page for disconnect
      navigate(`/connections/${connectorName}`);
      return;
    }
    try {
      const url = await getConnectorAuthUrl(connectorName);
      if (url) window.location.href = url;
    } catch (err) {
      console.error("Failed to get auth URL:", err);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-surface-900">Connections</h1>
        <p className="mt-1 text-surface-500">
          Connect your tools so Numen can build your knowledge graph.
        </p>
      </div>

      {loading && displayConnectors.length === 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="card animate-pulse h-40" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {displayConnectors.map((connector) => (
            <ConnectorCard
              key={connector.connector}
              connector={connector}
              onToggle={() => handleToggle(connector.connector, connector.connected)}
              onConnectedClick={() => navigate(`/connections/${connector.connector}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
