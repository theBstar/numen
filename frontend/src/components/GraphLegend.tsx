const legendItems = [
  { type: "task", label: "Task", color: "#3B82F6" },
  { type: "goal", label: "Goal", color: "#8B5CF6" },
  { type: "project", label: "Project", color: "#6366F1" },
  { type: "commit_pr", label: "PR", color: "#22C55E" },
  { type: "person", label: "Person", color: "#F59E0B" },
  { type: "incident", label: "Incident", color: "#EF4444" },
  { type: "feature", label: "Feature", color: "#14B8A6" },
  { type: "document", label: "Document", color: "#6B7280" },
  { type: "decision", label: "Decision", color: "#F97316" },
  { type: "deploy", label: "Deploy", color: "#06B6D4" },
];

export function GraphLegend() {
  return (
    <div className="mt-2 flex flex-wrap gap-3 text-xs text-surface-600">
      {legendItems.map((t) => (
        <div key={t.type} className="flex items-center gap-1">
          <div
            className="h-3 w-3 rounded-full"
            style={{ backgroundColor: t.color }}
          />
          {t.label}
        </div>
      ))}
    </div>
  );
}
