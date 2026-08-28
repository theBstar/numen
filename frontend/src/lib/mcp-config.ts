/**
 * MCP config builder - generates ready-to-copy JSON configs for AI tools.
 */

export type McpClient =
  | "claude-code"
  | "claude-desktop"
  | "cursor"
  | "windsurf"
  | "cli";

export interface McpClientInfo {
  id: McpClient;
  label: string;
  description: string;
  configPath: string;
}

export const MCP_CLIENTS: McpClientInfo[] = [
  {
    id: "claude-code",
    label: "Claude Code",
    description: "Run one command in your terminal - no config file editing.",
    configPath: "",
  },
  {
    id: "claude-desktop",
    label: "Claude Desktop",
    description: "Add to your Claude Desktop configuration file.",
    configPath: "~/Library/Application Support/Claude/claude_desktop_config.json",
  },
  {
    id: "cursor",
    label: "Cursor",
    description: "Add to your Cursor MCP settings.",
    configPath: ".cursor/mcp.json",
  },
  {
    id: "windsurf",
    label: "Windsurf",
    description: "Add to your Windsurf MCP configuration.",
    configPath: "~/.codeium/windsurf/mcp_config.json",
  },
  {
    id: "cli",
    label: "CLI (stdio)",
    description: "For local use with the numen-mcp command.",
    configPath: "N/A - run numen-mcp directly",
  },
];

function getServerUrl(): string {
  const base = import.meta.env.VITE_API_URL || window.location.origin;
  // Trailing slash matters: the FastAPI mount at /mcp serves the inner MCP
  // app's "/" route only on /mcp/, not /mcp.
  return `${base}/mcp/`;
}

export function buildMcpConfig(client: McpClient, apiKey: string): string {
  if (client === "claude-code") {
    // One-step setup: a single shell command that registers the remote MCP
    // server with Claude Code's local config. No JSON file editing.
    return `claude mcp add --transport http numen ${getServerUrl()} --header "Authorization: Bearer ${apiKey}"`;
  }

  if (client === "cli") {
    return JSON.stringify(
      {
        mcpServers: {
          numen: {
            command: "numen-mcp",
            env: {
              NUMEN_API_KEY: apiKey,
            },
          },
        },
      },
      null,
      2,
    );
  }

  // SSE-based clients (Claude Desktop, Cursor, Windsurf)
  return JSON.stringify(
    {
      mcpServers: {
        numen: {
          url: getServerUrl(),
          headers: {
            Authorization: `Bearer ${apiKey}`,
          },
        },
      },
    },
    null,
    2,
  );
}
