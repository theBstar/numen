import { Users } from "lucide-react";
import type { TeamMemberWorkload } from "@/types";

interface TeamWorkloadWidgetProps {
  members: TeamMemberWorkload[];
}

export function TeamWorkloadWidget({ members }: TeamWorkloadWidgetProps) {
  const sorted = [...members].sort((a, b) => b.total - a.total);

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-3">
        <Users size={14} className="text-surface-400" />
        <h3 className="text-sm font-semibold text-surface-700">Team Workload</h3>
      </div>

      {sorted.length > 0 ? (
        <div className="space-y-2.5">
          {sorted.slice(0, 6).map((m) => {
            const maxVal = Math.max(...sorted.map((s) => s.total), 1);
            return (
              <div key={m.person_id}>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="font-medium text-surface-700 truncate">{m.person_name}</span>
                  <span className="text-surface-400 shrink-0 ml-2">{m.total}</span>
                </div>
                <div className="flex h-2 rounded-full overflow-hidden bg-surface-100">
                  {m.in_progress > 0 && (
                    <div
                      className="bg-blue-500 transition-all"
                      style={{ width: `${(m.in_progress / maxVal) * 100}%` }}
                      title={`In progress: ${m.in_progress}`}
                    />
                  )}
                  {m.in_review > 0 && (
                    <div
                      className="bg-amber-400 transition-all"
                      style={{ width: `${(m.in_review / maxVal) * 100}%` }}
                      title={`In review: ${m.in_review}`}
                    />
                  )}
                  {m.todo > 0 && (
                    <div
                      className="bg-surface-300 transition-all"
                      style={{ width: `${(m.todo / maxVal) * 100}%` }}
                      title={`Todo: ${m.todo}`}
                    />
                  )}
                  {m.done > 0 && (
                    <div
                      className="bg-green-400 transition-all"
                      style={{ width: `${(m.done / maxVal) * 100}%` }}
                      title={`Done: ${m.done}`}
                    />
                  )}
                </div>
              </div>
            );
          })}
          <div className="flex items-center gap-3 text-[10px] text-surface-400 pt-1">
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-500" /> Active</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-400" /> Review</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-surface-300" /> Todo</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-400" /> Done</span>
          </div>
        </div>
      ) : (
        <p className="text-xs text-surface-400 text-center py-3">No team data available</p>
      )}
    </div>
  );
}
