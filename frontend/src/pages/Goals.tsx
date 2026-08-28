import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, List, GitBranch, Target } from "lucide-react";
import { useGoals, useGoalTree } from "@/hooks/queries";
import { GoalCard } from "@/components/GoalCard";
import { GoalTree } from "@/components/GoalTree";
import { GoalForm } from "@/components/GoalForm";
import { EmptyState } from "@/components/EmptyState";
import { cn } from "@/lib/utils";
import type { GoalLevel } from "@/types";

type ViewMode = "list" | "tree";
type LevelFilter = "all" | GoalLevel;

const filterTabs: { label: string; value: LevelFilter }[] = [
  { label: "All", value: "all" },
  { label: "Company", value: "company" },
  { label: "Team", value: "team" },
  { label: "Individual", value: "individual" },
];

const levelOrder: Record<string, number> = { company: 0, team: 1, individual: 2 };

export function Goals() {
  const navigate = useNavigate();
  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [levelFilter, setLevelFilter] = useState<LevelFilter>("all");
  const [showCreateForm, setShowCreateForm] = useState(false);

  const { data: goals, isPending: loading, error, refetch: refetchGoals } = useGoals();
  const { data: goalTree, refetch: refetchTree } = useGoalTree();

  const filteredGoals = (goals ?? []).filter((g) =>
    levelFilter === "all" ? true : g.level === levelFilter
  );

  const sortedGoals = [...filteredGoals].sort((a, b) => {
    const levelDiff = (levelOrder[a.level] ?? 99) - (levelOrder[b.level] ?? 99);
    if (levelDiff !== 0) return levelDiff;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-surface-900">Goals</h1>
          <p className="mt-1 text-surface-500">
            Define goals to help Numen prioritize your briefings.
          </p>
        </div>
        <button
          onClick={() => setShowCreateForm(true)}
          className="btn-primary"
        >
          <Plus size={16} className="mr-1.5" />
          Create Goal
        </button>
      </div>

      {/* View toggle + Filter tabs */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1 rounded-lg bg-surface-100 p-1">
          <button
            onClick={() => setViewMode("list")}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              viewMode === "list"
                ? "bg-white text-surface-900 shadow-sm"
                : "text-surface-500 hover:text-surface-700"
            )}
          >
            <List size={14} />
            List
          </button>
          <button
            onClick={() => setViewMode("tree")}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              viewMode === "tree"
                ? "bg-white text-surface-900 shadow-sm"
                : "text-surface-500 hover:text-surface-700"
            )}
          >
            <GitBranch size={14} />
            Tree
          </button>
        </div>

        {viewMode === "list" && (
          <div className="flex items-center gap-1">
            {filterTabs.map((tab) => (
              <button
                key={tab.value}
                onClick={() => setLevelFilter(tab.value)}
                className={cn(
                  "px-3 py-1.5 text-sm font-medium transition-colors",
                  levelFilter === tab.value
                    ? "text-primary-700 border-b-2 border-primary-600"
                    : "text-surface-500 hover:text-surface-700"
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          Failed to load goals: {error.message}
        </div>
      )}

      {/* Loading */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="card animate-pulse">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-surface-200" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 w-3/4 rounded bg-surface-200" />
                  <div className="h-3 w-1/2 rounded bg-surface-200" />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : viewMode === "list" ? (
        sortedGoals.length === 0 ? (
          <EmptyState
            icon={Target}
            title="No goals yet"
            description="Create goals to track what matters to your team and connect them to your work."
            action={{ label: "Create Goal", onClick: () => setShowCreateForm(true) }}
            secondaryAction={{ label: "Connect your tools first", onClick: () => navigate("/connections") }}
          />
        ) : (
          <div className="space-y-3">
            {sortedGoals.map((goal) => (
              <GoalCard key={goal.id} goal={goal} />
            ))}
          </div>
        )
      ) : (
        <GoalTree goals={goalTree ?? []} />
      )}

      {/* GoalForm dialog */}
      {showCreateForm && (
        <GoalForm
          onClose={() => setShowCreateForm(false)}
          onSuccess={() => {
            setShowCreateForm(false);
            refetchGoals();
            refetchTree();
          }}
        />
      )}
    </div>
  );
}
