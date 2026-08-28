import { useState, useCallback, useRef } from "react";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useImportPrd, useImportPrdFile } from "@/hooks/prdMutations";
import { useNavigate } from "react-router-dom";
import type { ImportSource } from "@/services/api";

interface PrdImportDialogProps {
  open: boolean;
  onClose: () => void;
  parentFolderId?: string | null;
}

// Helpers to parse document IDs from URLs

function parseNotionPageId(input: string): string {
  // Accept raw IDs or full Notion URLs
  // https://www.notion.so/workspace/Page-Title-abc123def456...
  const uuidMatch = input.match(
    /[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}/i,
  );
  if (uuidMatch) return uuidMatch[0];

  // Notion URLs have the page ID as the last 32-char hex segment
  const hexMatch = input.match(/([0-9a-f]{32})\s*$/i);
  if (hexMatch?.[1]) return hexMatch[1];

  return input.trim();
}

function parseConfluencePageId(input: string): string {
  // Accept raw numeric IDs or Confluence URLs
  // https://myorg.atlassian.net/wiki/spaces/SPACE/pages/12345/Page+Title
  const pagesMatch = input.match(/\/pages\/(\d+)/);
  if (pagesMatch?.[1]) return pagesMatch[1];

  return input.trim();
}

function parseConfluenceBaseUrl(input: string): string {
  // Extract base URL from a full Confluence page URL
  try {
    const url = new URL(input);
    return `${url.protocol}//${url.host}`;
  } catch {
    return "";
  }
}

function parseGoogleDocsId(input: string): string {
  // Accept raw IDs or Google Docs URLs
  // https://docs.google.com/document/d/DOCUMENT_ID/edit
  const match = input.match(/\/document\/d\/([a-zA-Z0-9_-]+)/);
  if (match?.[1]) return match[1];

  return input.trim();
}

const ACCEPTED_EXTENSIONS = ".md,.html,.htm,.pdf";

export function PrdImportDialog({
  open,
  onClose,
  parentFolderId,
}: PrdImportDialogProps) {
  const [activeTab, setActiveTab] = useState<string>("file");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  // Notion state
  const [notionInput, setNotionInput] = useState("");

  // Confluence state
  const [confluenceInput, setConfluenceInput] = useState("");
  const [confluenceBaseUrl, setConfluenceBaseUrl] = useState("");

  // Google Docs state
  const [googleDocsInput, setGoogleDocsInput] = useState("");

  // File upload state
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const importPrd = useImportPrd();
  const importPrdFile = useImportPrdFile();

  const isLoading = importPrd.isPending || importPrdFile.isPending;

  function resetState() {
    setNotionInput("");
    setConfluenceInput("");
    setConfluenceBaseUrl("");
    setGoogleDocsInput("");
    setSelectedFile(null);
    setError(null);
  }

  function handleClose() {
    resetState();
    onClose();
  }

  function navigateToPrd(prdId: string) {
    handleClose();
    navigate(`/prds/${prdId}`);
  }

  async function handleImportApi(source: ImportSource) {
    setError(null);

    let sourceId = "";
    let baseUrl: string | undefined;

    if (source === "notion") {
      sourceId = parseNotionPageId(notionInput);
      if (!sourceId) {
        setError("Please enter a valid Notion page URL or ID");
        return;
      }
    } else if (source === "confluence") {
      sourceId = parseConfluencePageId(confluenceInput);
      baseUrl = confluenceBaseUrl || parseConfluenceBaseUrl(confluenceInput);
      if (!sourceId) {
        setError("Please enter a valid Confluence page URL or ID");
        return;
      }
      if (!baseUrl) {
        setError("Please enter your Confluence base URL (e.g. https://myorg.atlassian.net)");
        return;
      }
    } else if (source === "google_docs") {
      sourceId = parseGoogleDocsId(googleDocsInput);
      if (!sourceId) {
        setError("Please enter a valid Google Docs URL or document ID");
        return;
      }
    }

    try {
      const prd = await importPrd.mutateAsync({
        source,
        sourceId,
        parentFolderId: parentFolderId ?? undefined,
        baseUrl,
      });
      navigateToPrd(prd.id);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Import failed";
      setError(message);
    }
  }

  async function handleImportFile() {
    if (!selectedFile) {
      setError("Please select a file to import");
      return;
    }

    setError(null);

    try {
      const prd = await importPrdFile.mutateAsync({
        file: selectedFile,
        parentFolderId: parentFolderId ?? undefined,
      });
      navigateToPrd(prd.id);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Import failed";
      setError(message);
    }
  }

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const files = e.dataTransfer.files;
    const file = files[0] ?? null;
    if (file) {
      const ext = file.name.toLowerCase().split(".").pop();
      if (ext === "md" || ext === "html" || ext === "htm" || ext === "pdf") {
        setSelectedFile(file);
        setError(null);
      } else {
        setError("Only .md, .html, and .pdf files are supported");
      }
    }
  }, []);

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    if (file) {
      setSelectedFile(file);
      setError(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && handleClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Import Document</DialogTitle>
          <DialogDescription>
            Import a document from Notion, Confluence, Google Docs, or upload a
            Markdown/HTML file.
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="file">File</TabsTrigger>
            <TabsTrigger value="notion">Notion</TabsTrigger>
            <TabsTrigger value="confluence">Confluence</TabsTrigger>
            <TabsTrigger value="google_docs">Google Docs</TabsTrigger>
          </TabsList>

          {/* File Upload Tab */}
          <TabsContent value="file" className="space-y-4">
            <div
              className={`
                relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors
                ${dragActive ? "border-primary bg-primary/5" : "border-muted-foreground/25"}
                ${selectedFile ? "bg-muted/50" : ""}
              `}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
            >
              {selectedFile ? (
                <div className="text-center">
                  <p className="text-sm font-medium">{selectedFile.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {(selectedFile.size / 1024).toFixed(1)} KB
                  </p>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="mt-2"
                    onClick={() => setSelectedFile(null)}
                  >
                    Remove
                  </Button>
                </div>
              ) : (
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">
                    Drag and drop a file here, or
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-2"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    Browse Files
                  </Button>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Accepts .md, .html, and .pdf files
                  </p>
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_EXTENSIONS}
                onChange={handleFileSelect}
                className="hidden"
              />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={handleClose}>
                Cancel
              </Button>
              <Button
                type="button"
                disabled={!selectedFile || isLoading}
                onClick={handleImportFile}
              >
                {isLoading ? "Importing..." : "Import"}
              </Button>
            </DialogFooter>
          </TabsContent>

          {/* Notion Tab */}
          <TabsContent value="notion" className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="notion-input">Notion Page URL or ID</Label>
              <Input
                id="notion-input"
                value={notionInput}
                onChange={(e) => setNotionInput(e.target.value)}
                placeholder="https://notion.so/... or page ID"
              />
              <p className="text-xs text-muted-foreground">
                Paste a Notion page URL or the page ID (32-character hex string)
              </p>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={handleClose}>
                Cancel
              </Button>
              <Button
                type="button"
                disabled={!notionInput.trim() || isLoading}
                onClick={() => handleImportApi("notion")}
              >
                {isLoading ? "Importing..." : "Import from Notion"}
              </Button>
            </DialogFooter>
          </TabsContent>

          {/* Confluence Tab */}
          <TabsContent value="confluence" className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="confluence-base-url">Confluence Base URL</Label>
              <Input
                id="confluence-base-url"
                value={confluenceBaseUrl}
                onChange={(e) => setConfluenceBaseUrl(e.target.value)}
                placeholder="https://myorg.atlassian.net"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confluence-input">Page URL or ID</Label>
              <Input
                id="confluence-input"
                value={confluenceInput}
                onChange={(e) => setConfluenceInput(e.target.value)}
                placeholder="https://myorg.atlassian.net/wiki/spaces/.../pages/12345 or page ID"
              />
              <p className="text-xs text-muted-foreground">
                Paste a Confluence page URL or the numeric page ID
              </p>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={handleClose}>
                Cancel
              </Button>
              <Button
                type="button"
                disabled={!confluenceInput.trim() || isLoading}
                onClick={() => handleImportApi("confluence")}
              >
                {isLoading ? "Importing..." : "Import from Confluence"}
              </Button>
            </DialogFooter>
          </TabsContent>

          {/* Google Docs Tab */}
          <TabsContent value="google_docs" className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="gdocs-input">Google Docs URL or Document ID</Label>
              <Input
                id="gdocs-input"
                value={googleDocsInput}
                onChange={(e) => setGoogleDocsInput(e.target.value)}
                placeholder="https://docs.google.com/document/d/... or document ID"
              />
              <p className="text-xs text-muted-foreground">
                Paste a Google Docs URL or the document ID
              </p>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={handleClose}>
                Cancel
              </Button>
              <Button
                type="button"
                disabled={!googleDocsInput.trim() || isLoading}
                onClick={() => handleImportApi("google_docs")}
              >
                {isLoading ? "Importing..." : "Import from Google Docs"}
              </Button>
            </DialogFooter>
          </TabsContent>
        </Tabs>

        {error && (
          <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
