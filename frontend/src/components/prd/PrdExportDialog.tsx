import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useExportPrd } from "@/hooks/prdMutations";
import type { ExportFormat } from "@/services/api";
import {
  FileText,
  Code,
  FileDown,
  ExternalLink,
  Loader2,
  Check,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface PrdExportDialogProps {
  open: boolean;
  onClose: () => void;
  prdId: string;
  prdTitle: string;
}

interface FormatOption {
  value: ExportFormat;
  label: string;
  description: string;
  icon: React.ReactNode;
  type: "file" | "api";
}

const FORMAT_OPTIONS: FormatOption[] = [
  {
    value: "markdown",
    label: "Markdown",
    description: "Plain text format compatible with GitHub, GitLab, and static sites",
    icon: <FileText className="h-5 w-5" />,
    type: "file",
  },
  {
    value: "html",
    label: "HTML",
    description: "Styled web page with table of contents and metadata",
    icon: <Code className="h-5 w-5" />,
    type: "file",
  },
  {
    value: "pdf",
    label: "PDF",
    description: "Professional document with cover page and page numbers",
    icon: <FileDown className="h-5 w-5" />,
    type: "file",
  },
  {
    value: "notion",
    label: "Notion",
    description: "Create a new page in your Notion workspace",
    icon: <ExternalLink className="h-5 w-5" />,
    type: "api",
  },
  {
    value: "confluence",
    label: "Confluence",
    description: "Create a new page in your Confluence space",
    icon: <ExternalLink className="h-5 w-5" />,
    type: "api",
  },
  {
    value: "google_docs",
    label: "Google Docs",
    description: "Create a new document in Google Drive",
    icon: <ExternalLink className="h-5 w-5" />,
    type: "api",
  },
];

export function PrdExportDialog({
  open,
  onClose,
  prdId,
  prdTitle,
}: PrdExportDialogProps) {
  const [selectedFormat, setSelectedFormat] = useState<ExportFormat>("markdown");
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // API format options
  const [notionToken, setNotionToken] = useState("");
  const [notionParentPageId, setNotionParentPageId] = useState("");
  const [confluenceBaseUrl, setConfluenceBaseUrl] = useState("");
  const [confluenceToken, setConfluenceToken] = useState("");
  const [confluenceSpaceKey, setConfluenceSpaceKey] = useState("");
  const [googleToken, setGoogleToken] = useState("");
  const [googleFolderId, setGoogleFolderId] = useState("");

  const exportMutation = useExportPrd();

  const selectedOption = FORMAT_OPTIONS.find((f) => f.value === selectedFormat);
  const isFileFormat = selectedOption?.type === "file";

  function resetState() {
    setResultUrl(null);
    setError(null);
  }

  function handleFormatChange(format: ExportFormat) {
    setSelectedFormat(format);
    resetState();
  }

  function handleClose() {
    resetState();
    onClose();
  }

  function buildOptions(): Record<string, unknown> | undefined {
    switch (selectedFormat) {
      case "notion":
        return {
          access_token: notionToken,
          parent_page_id: notionParentPageId || undefined,
        };
      case "confluence":
        return {
          base_url: confluenceBaseUrl,
          access_token: confluenceToken,
          space_key: confluenceSpaceKey || undefined,
        };
      case "google_docs":
        return {
          access_token: googleToken,
          folder_id: googleFolderId || undefined,
        };
      default:
        return undefined;
    }
  }

  function isExportDisabled(): boolean {
    if (exportMutation.isPending) return true;
    switch (selectedFormat) {
      case "notion":
        return !notionToken;
      case "confluence":
        return !confluenceBaseUrl || !confluenceToken;
      case "google_docs":
        return !googleToken;
      default:
        return false;
    }
  }

  async function handleExport() {
    setError(null);
    setResultUrl(null);

    try {
      const result = await exportMutation.mutateAsync({
        prdId,
        format: selectedFormat,
        options: buildOptions(),
      });

      // API formats return a URL
      if (result && "url" in result && result.url) {
        setResultUrl(result.url);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Export failed";
      setError(message);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && handleClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Export PRD</DialogTitle>
          <DialogDescription>
            Export &quot;{prdTitle}&quot; to your preferred format.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Format selection */}
          <div className="grid grid-cols-3 gap-2">
            {FORMAT_OPTIONS.map((fmt) => (
              <button
                key={fmt.value}
                type="button"
                onClick={() => handleFormatChange(fmt.value)}
                className={cn(
                  "flex flex-col items-center gap-1.5 rounded-lg border p-3 text-center transition-colors",
                  "hover:bg-surface-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                  selectedFormat === fmt.value
                    ? "border-primary-500 bg-primary-50 text-primary-700"
                    : "border-surface-200 text-surface-600",
                )}
              >
                {fmt.icon}
                <span className="text-xs font-medium">{fmt.label}</span>
              </button>
            ))}
          </div>

          {/* Format description */}
          {selectedOption && (
            <p className="text-sm text-surface-500">{selectedOption.description}</p>
          )}

          {/* API format options */}
          {selectedFormat === "notion" && (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="notion-token">
                  Integration Token <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="notion-token"
                  type="password"
                  value={notionToken}
                  onChange={(e) => setNotionToken(e.target.value)}
                  placeholder="ntn_..."
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="notion-parent">Parent Page ID (optional)</Label>
                <Input
                  id="notion-parent"
                  value={notionParentPageId}
                  onChange={(e) => setNotionParentPageId(e.target.value)}
                  placeholder="Page ID to nest under"
                />
              </div>
            </div>
          )}

          {selectedFormat === "confluence" && (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="confluence-url">
                  Base URL <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="confluence-url"
                  value={confluenceBaseUrl}
                  onChange={(e) => setConfluenceBaseUrl(e.target.value)}
                  placeholder="https://your-domain.atlassian.net"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="confluence-token">
                  API Token <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="confluence-token"
                  type="password"
                  value={confluenceToken}
                  onChange={(e) => setConfluenceToken(e.target.value)}
                  placeholder="Your API token"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="confluence-space">Space Key (optional)</Label>
                <Input
                  id="confluence-space"
                  value={confluenceSpaceKey}
                  onChange={(e) => setConfluenceSpaceKey(e.target.value)}
                  placeholder="e.g. PROD"
                />
              </div>
            </div>
          )}

          {selectedFormat === "google_docs" && (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="google-token">
                  Access Token <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="google-token"
                  type="password"
                  value={googleToken}
                  onChange={(e) => setGoogleToken(e.target.value)}
                  placeholder="OAuth access token"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="google-folder">Drive Folder ID (optional)</Label>
                <Input
                  id="google-folder"
                  value={googleFolderId}
                  onChange={(e) => setGoogleFolderId(e.target.value)}
                  placeholder="Folder ID to place document in"
                />
              </div>
            </div>
          )}

          {/* Result URL for API formats */}
          {resultUrl && (
            <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3">
              <Check className="h-4 w-4 flex-shrink-0 text-green-600" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-green-800">
                  Document created successfully
                </p>
                <a
                  href={resultUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-green-700 underline break-all"
                >
                  {resultUrl}
                </a>
              </div>
            </div>
          )}

          {/* Error state */}
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3">
              <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-600" />
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={handleClose}>
            {resultUrl ? "Done" : "Cancel"}
          </Button>
          <Button
            type="button"
            onClick={handleExport}
            disabled={isExportDisabled()}
          >
            {exportMutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Exporting...
              </>
            ) : isFileFormat ? (
              "Download"
            ) : resultUrl ? (
              "Export Again"
            ) : (
              "Export"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
