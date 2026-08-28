import {
  FileText,
  CheckCircle2,
  Clock,
  Rocket,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { PrdCard } from "./PrdCard";
import { EmptyState } from "@/components/EmptyState";
import type { PrdResponse } from "@/types";

interface PrdLandingProps {
  prds: PrdResponse[];
  isLoading: boolean;
  onSelect: (id: string) => void;
  onCreateNew: () => void;
}

export function PrdLanding({ prds, isLoading, onSelect, onCreateNew }: PrdLandingProps) {
  if (isLoading) {
    return (
      <div className="px-6 py-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-32 animate-pulse rounded-xl bg-surface-100" />
          ))}
        </div>
      </div>
    );
  }

  const docs = prds.filter((p) => p.node_type !== "folder");

  if (docs.length === 0) {
    return (
      <div className="px-6 py-4">
        <EmptyState
          icon={FileText}
          title="No PRDs yet"
          description="Create your first product requirements document to start organizing your product ideas."
          action={{ label: "Create PRD", onClick: onCreateNew }}
        />
      </div>
    );
  }

  // Stats
  const total = docs.length;
  const approved = docs.filter((d) => d.status === "approved").length;
  const inProgress = docs.filter((d) => d.status === "in_progress").length;
  const shipped = docs.filter((d) => d.status === "shipped").length;
  const drafts = docs.filter((d) => d.status === "draft" || d.status === "idea");
  const inProgressDocs = docs.filter((d) => d.status === "in_progress");
  const inReviewDocs = docs.filter((d) => d.status === "in_review");
  const shippedDocs = docs.filter((d) => d.status === "shipped");
  const recentDocs = docs.slice(0, 6);

  return (
    <div className="px-6 py-5 space-y-6 max-w-5xl mx-auto">
      {/* Stats row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard icon={FileText} label="Total PRDs" value={total} color="blue" />
        <StatCard icon={CheckCircle2} label="Approved" value={approved} color="green" />
        <StatCard icon={Clock} label="In Progress" value={inProgress} color="yellow" />
        <StatCard icon={Rocket} label="Shipped" value={shipped} color="purple" />
      </div>

      {/* In Review */}
      {inReviewDocs.length > 0 && (
        <Section title="In Review" count={inReviewDocs.length}>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {inReviewDocs.map((prd) => (
              <PrdCard key={prd.id} prd={prd} onClick={() => onSelect(prd.id)} />
            ))}
          </div>
        </Section>
      )}

      {/* Currently In Progress */}
      {inProgressDocs.length > 0 && (
        <Section title="Currently In Progress" count={inProgressDocs.length}>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {inProgressDocs.map((prd) => (
              <PrdCard key={prd.id} prd={prd} onClick={() => onSelect(prd.id)} />
            ))}
          </div>
        </Section>
      )}

      {/* Recently Shipped */}
      {shippedDocs.length > 0 && (
        <Section title="Recently Shipped" count={shippedDocs.length}>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {shippedDocs.slice(0, 4).map((prd) => (
              <PrdCard key={prd.id} prd={prd} onClick={() => onSelect(prd.id)} />
            ))}
          </div>
        </Section>
      )}

      {/* Drafts */}
      {drafts.length > 0 && (
        <Section title="Drafts & Ideas" count={drafts.length}>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {drafts.slice(0, 4).map((prd) => (
              <PrdCard key={prd.id} prd={prd} onClick={() => onSelect(prd.id)} />
            ))}
          </div>
        </Section>
      )}

      {/* All recent */}
      {recentDocs.length > 0 && (
        <Section title="All PRDs" count={total}>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {recentDocs.map((prd) => (
              <PrdCard key={prd.id} prd={prd} onClick={() => onSelect(prd.id)} />
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

// ── Sub-components ──

function StatCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: number;
  color: "blue" | "green" | "yellow" | "purple";
}) {
  const bg = { blue: "bg-blue-50", green: "bg-emerald-50", yellow: "bg-yellow-50", purple: "bg-purple-50" }[color];
  const iconColor = { blue: "text-blue-600", green: "text-emerald-600", yellow: "text-yellow-600", purple: "text-purple-600" }[color];

  return (
    <div className="rounded-lg border border-surface-200 bg-white p-3">
      <div className="flex items-center gap-2 mb-1">
        <div className={cn("rounded-md p-1.5", bg)}>
          <Icon size={14} className={iconColor} />
        </div>
      </div>
      <div className="text-2xl font-bold text-surface-900">{value}</div>
      <div className="text-[11px] text-surface-500">{label}</div>
    </div>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-surface-400">
          {title}
        </h2>
        <span className="rounded-full bg-surface-100 px-1.5 py-0.5 text-[10px] font-medium text-surface-500">
          {count}
        </span>
      </div>
      {children}
    </div>
  );
}
