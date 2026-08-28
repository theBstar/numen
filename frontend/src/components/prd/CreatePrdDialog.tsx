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
import { Textarea } from "@/components/ui/textarea";
import { useCreatePrd } from "@/hooks/prdMutations";
import type { PrdNodeType, Priority } from "@/types";

interface CreatePrdDialogProps {
  open: boolean;
  onClose: () => void;
  parentId?: string | null;
  defaultNodeType?: PrdNodeType;
}

const NODE_TYPE_OPTIONS: { value: PrdNodeType; label: string }[] = [
  { value: "document", label: "Document" },
  { value: "folder", label: "Folder" },
];

const PRIORITY_OPTIONS: { value: Priority; label: string }[] = [
  { value: "urgent", label: "Urgent" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

export function CreatePrdDialog({
  open,
  onClose,
  parentId,
  defaultNodeType = "document",
}: CreatePrdDialogProps) {
  const [title, setTitle] = useState("");
  const [nodeType, setNodeType] = useState<PrdNodeType>(defaultNodeType);
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<Priority>("medium");
  const [tags, setTags] = useState("");

  const createPrd = useCreatePrd();

  function resetForm() {
    setTitle("");
    setNodeType(defaultNodeType);
    setDescription("");
    setPriority("medium");
    setTags("");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;

    const tagList = tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);

    await createPrd.mutateAsync({
      title: title.trim(),
      node_type: nodeType,
      parent_id: parentId ?? null,
      description: description.trim() || undefined,
      priority,
      tags: tagList.length > 0 ? tagList : undefined,
    });

    resetForm();
    onClose();
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {defaultNodeType === "folder" ? "Create Folder" : "Create PRD"}
          </DialogTitle>
          <DialogDescription>
            {defaultNodeType === "folder"
              ? "Create a folder to organize your PRDs."
              : "Create a new product requirements document."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Title */}
          <div className="space-y-2">
            <Label htmlFor="prd-title">
              Title <span className="text-red-500">*</span>
            </Label>
            <Input
              id="prd-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={nodeType === "folder" ? "Folder name" : "PRD title"}
              required
              autoFocus
            />
          </div>

          {/* Node type */}
          <div className="space-y-2">
            <Label htmlFor="prd-node-type">Type</Label>
            <select
              id="prd-node-type"
              value={nodeType}
              onChange={(e) => setNodeType(e.target.value as PrdNodeType)}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              {NODE_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Description - only for documents */}
          {nodeType !== "folder" && (
            <div className="space-y-2">
              <Label htmlFor="prd-description">Description</Label>
              <Textarea
                id="prd-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Brief description of this PRD"
                rows={3}
              />
            </div>
          )}

          {/* Priority - only for documents */}
          {nodeType !== "folder" && (
            <div className="space-y-2">
              <Label htmlFor="prd-priority">Priority</Label>
              <select
                id="prd-priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value as Priority)}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {PRIORITY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Tags - only for documents */}
          {nodeType !== "folder" && (
            <div className="space-y-2">
              <Label htmlFor="prd-tags">Tags</Label>
              <Input
                id="prd-tags"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="Comma-separated tags (e.g. mobile, v2, backend)"
              />
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!title.trim() || createPrd.isPending}>
              {createPrd.isPending ? "Creating..." : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
