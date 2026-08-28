import { useState } from "react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { ProgressBar } from "@/components/ProgressBar";
import { StatusBadge } from "@/components/StatusBadge";
import { PriorityBadge } from "@/components/PriorityBadge";
import { PrdReviewPanel } from "./PrdReviewPanel";
import { PrdStakeholderList } from "./PrdStakeholderList";
import { PrdLinkPanel } from "./PrdLinkPanel";
import { useMembers } from "@/hooks/queries";
import type {
  PrdResponse,
  PrdCoverage,
  UpdatePrdPayload,
  Priority,
  PrdStatus,
} from "@/types";
import {
  Calendar,
  Tag,
  X,
  Plus,
  User,
  Users,
  History,
  ChevronDown,
  BarChart3,
  UserCheck,
  Target,
} from "lucide-react";

interface PrdMetadataPanelProps {
  prd: PrdResponse;
  coverage: PrdCoverage | null;
  onUpdate: (data: UpdatePrdPayload) => void;
  isOwner?: boolean;
}

const PRD_STATUS_OPTIONS: { value: PrdStatus; label: string }[] = [
  { value: "idea", label: "Idea" },
  { value: "draft", label: "Draft" },
  { value: "in_review", label: "In Review" },
  { value: "needs_revision", label: "Needs Revision" },
  { value: "approved", label: "Approved" },
  { value: "in_progress", label: "In Progress" },
  { value: "shipped", label: "Shipped" },
  { value: "deprecated", label: "Deprecated" },
  { value: "archived", label: "Archived" },
];

const PRIORITY_OPTIONS: { value: Priority; label: string }[] = [
  { value: "urgent", label: "Urgent" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

function MetadataRow({
  label,
  icon: Icon,
  children,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 py-2">
      <div className="flex w-28 shrink-0 items-center gap-1.5 pt-0.5">
        <Icon className="h-3.5 w-3.5 text-surface-400" />
        <span className="text-xs font-medium text-surface-500">{label}</span>
      </div>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

function SimpleSelect<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className={cn(
          "w-full appearance-none rounded-md border border-surface-200 bg-white py-1 pl-2 pr-7 text-sm",
          "transition-colors hover:border-surface-300 focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500",
        )}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-surface-400" />
    </div>
  );
}

function TagList({
  tags,
  onAdd,
  onRemove,
}: {
  tags: string[];
  onAdd: (tag: string) => void;
  onRemove: (tag: string) => void;
}) {
  const [isAdding, setIsAdding] = useState(false);
  const [newTag, setNewTag] = useState("");

  const handleAdd = () => {
    const trimmed = newTag.trim();
    if (trimmed && !tags.includes(trimmed)) {
      onAdd(trimmed);
    }
    setNewTag("");
    setIsAdding(false);
  };

  return (
    <div className="flex flex-wrap gap-1.5">
      {tags.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 rounded-md bg-surface-100 px-2 py-0.5 text-xs text-surface-600"
        >
          {tag}
          <button
            type="button"
            onClick={() => onRemove(tag)}
            className="rounded hover:bg-surface-200"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      {isAdding ? (
        <Input
          autoFocus
          value={newTag}
          onChange={(e) => setNewTag(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleAdd();
            if (e.key === "Escape") {
              setIsAdding(false);
              setNewTag("");
            }
          }}
          onBlur={handleAdd}
          className="h-6 w-24 px-1.5 text-xs"
          placeholder="Add tag..."
        />
      ) : (
        <button
          type="button"
          onClick={() => setIsAdding(true)}
          className="inline-flex items-center gap-0.5 rounded-md border border-dashed border-surface-300 px-2 py-0.5 text-xs text-surface-400 transition-colors hover:border-surface-400 hover:text-surface-500"
        >
          <Plus className="h-3 w-3" />
          Add
        </button>
      )}
    </div>
  );
}

function CoverageSection({ coverage }: { coverage: PrdCoverage }) {
  const progressColor =
    coverage.coverage_pct >= 75
      ? "green"
      : coverage.coverage_pct >= 40
        ? "amber"
        : "red";

  return (
    <div className="space-y-3">
      <ProgressBar
        value={coverage.coverage_pct}
        label={`${Math.round(coverage.coverage_pct)}%`}
        color={progressColor}
        size="md"
      />
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-md bg-surface-50 px-2 py-1.5">
          <p className="text-xs text-surface-400">Done</p>
          <p className="text-sm font-medium text-surface-700">
            {coverage.tasks_done}
          </p>
        </div>
        <div className="rounded-md bg-surface-50 px-2 py-1.5">
          <p className="text-xs text-surface-400">In Progress</p>
          <p className="text-sm font-medium text-surface-700">
            {coverage.tasks_in_progress}
          </p>
        </div>
        <div className="rounded-md bg-surface-50 px-2 py-1.5">
          <p className="text-xs text-surface-400">To Do</p>
          <p className="text-sm font-medium text-surface-700">
            {coverage.tasks_todo}
          </p>
        </div>
        <div className="rounded-md bg-surface-50 px-2 py-1.5">
          <p className="text-xs text-surface-400">Linked PRs</p>
          <p className="text-sm font-medium text-surface-700">
            {coverage.linked_prs}
          </p>
        </div>
      </div>
      {coverage.has_design && (
        <p className="text-xs text-emerald-600">Design specs attached</p>
      )}
    </div>
  );
}

function OwnerSelector({
  currentOwnerId,
  currentOwnerName,
  onChange,
}: {
  currentOwnerId: string | null;
  currentOwnerName: string | null;
  onChange: (memberId: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const { data: members } = useMembers();

  const filtered = (members ?? []).filter((m) => {
    if (!search) return true;
    const name = (m.display_name ?? m.email).toLowerCase();
    return name.includes(search.toLowerCase());
  });

  if (!isOpen) {
    return (
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="w-full rounded-md border border-surface-200 px-2 py-1 text-left text-sm text-surface-700 transition-colors hover:border-surface-300"
      >
        {currentOwnerName ?? "Unassigned"}
      </button>
    );
  }

  return (
    <div className="space-y-1.5">
      <Input
        autoFocus
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            setIsOpen(false);
            setSearch("");
          }
        }}
        placeholder="Search members..."
        className="h-7 text-sm"
      />
      <div className="max-h-40 overflow-y-auto rounded-md border border-surface-200 bg-white">
        {filtered.length === 0 ? (
          <p className="px-2 py-1.5 text-xs text-surface-400">No members found</p>
        ) : (
          filtered.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => {
                onChange(m.id);
                setIsOpen(false);
                setSearch("");
              }}
              className={cn(
                "flex w-full items-center gap-2 px-2 py-1.5 text-left text-sm transition-colors hover:bg-surface-50",
                m.id === currentOwnerId && "bg-primary-50 text-primary-700",
              )}
            >
              <User className="h-3.5 w-3.5 shrink-0 text-surface-400" />
              <span className="truncate">{m.display_name ?? m.email}</span>
            </button>
          ))
        )}
      </div>
      <button
        type="button"
        onClick={() => {
          setIsOpen(false);
          setSearch("");
        }}
        className="text-xs text-surface-400 hover:text-surface-600"
      >
        Cancel
      </button>
    </div>
  );
}

export function PrdMetadataPanel({
  prd,
  coverage,
  onUpdate,
  isOwner,
}: PrdMetadataPanelProps) {
  return (
    <ScrollArea className="h-full">
      <div className="space-y-4 p-4">
        {/* Status */}
        <MetadataRow label="Status" icon={BarChart3}>
          <div className="flex items-center gap-2">
            <StatusBadge status={prd.status} />
            <SimpleSelect
              value={prd.status}
              options={PRD_STATUS_OPTIONS}
              onChange={(status) => onUpdate({ status })}
            />
          </div>
        </MetadataRow>

        {/* Owner */}
        <MetadataRow label="Owner" icon={User}>
          <OwnerSelector
            currentOwnerId={prd.owner_member_id ?? null}
            currentOwnerName={prd.owner ?? null}
            onChange={(memberId) => onUpdate({ owner_member_id: memberId })}
          />
        </MetadataRow>

        {/* Priority */}
        <MetadataRow label="Priority" icon={ChevronDown}>
          <div className="flex items-center gap-2">
            <PriorityBadge priority={prd.priority} />
            <SimpleSelect
              value={prd.priority}
              options={PRIORITY_OPTIONS}
              onChange={(priority) => onUpdate({ priority })}
            />
          </div>
        </MetadataRow>

        {/* Target date */}
        <MetadataRow label="Target date" icon={Calendar}>
          <Input
            type="date"
            value={prd.target_date ?? ""}
            onChange={(e) =>
              onUpdate({
                target_date: e.target.value || undefined,
              })
            }
            className="h-7 text-sm"
          />
        </MetadataRow>

        <Separator />

        {/* Tags */}
        <MetadataRow label="Tags" icon={Tag}>
          <TagList
            tags={prd.tags}
            onAdd={(tag) => onUpdate({ tags: [...prd.tags, tag] })}
            onRemove={(tag) =>
              onUpdate({ tags: prd.tags.filter((t) => t !== tag) })
            }
          />
        </MetadataRow>

        {/* Linked Goals */}
        <MetadataRow label="Goals" icon={Target}>
          <PrdLinkPanel prdId={prd.id} />
        </MetadataRow>

        <Separator />

        {/* Stakeholders */}
        <MetadataRow label="Stakeholders" icon={Users}>
          <PrdStakeholderList
            prdId={prd.id}
            isOwner={isOwner ?? false}
          />
        </MetadataRow>

        {/* Reviewers */}
        <MetadataRow label="Reviewers" icon={UserCheck}>
          <PrdReviewPanel
            prdId={prd.id}
            currentStatus={prd.status}
            isOwner={isOwner ?? false}
          />
        </MetadataRow>

        <Separator />

        {/* Coverage */}
        {coverage && (
          <>
            <div className="space-y-2">
              <div className="flex items-center gap-1.5">
                <BarChart3 className="h-3.5 w-3.5 text-surface-400" />
                <span className="text-xs font-medium text-surface-500">
                  Implementation Coverage
                </span>
              </div>
              <CoverageSection coverage={coverage} />
            </div>
            <Separator />
          </>
        )}

        {/* Version history link */}
        <Button variant="ghost" size="sm" className="w-full justify-start gap-2">
          <History className="h-4 w-4" />
          Version History
        </Button>

        {/* Meta info */}
        <div className="space-y-1 px-1 text-xs text-surface-400">
          <p>
            Created{" "}
            {new Date(prd.created_at).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
              year: "numeric",
            })}
          </p>
          <p>
            Updated{" "}
            {new Date(prd.updated_at).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
              year: "numeric",
            })}
          </p>
          <p>Version {prd.version}</p>
          <p>
            {prd.block_count} block{prd.block_count !== 1 ? "s" : ""} -{" "}
            {prd.comment_count} comment{prd.comment_count !== 1 ? "s" : ""}
          </p>
        </div>
      </div>
    </ScrollArea>
  );
}
