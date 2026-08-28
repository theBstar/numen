import {
  CheckSquare,
  GitPullRequest,
  User,
  Target,
  FileText,
  AlertTriangle,
  Activity,
  Rocket,
  Cpu,
  BarChart3,
  Lightbulb,
  Repeat,
} from "lucide-react";
import type { EntityType } from "@/types";

export const entityTypeConfig: Record<
  EntityType,
  { icon: typeof CheckSquare; color: string; bg: string }
> = {
  task: { icon: CheckSquare, color: "text-blue-600", bg: "bg-blue-100" },
  commit_pr: { icon: GitPullRequest, color: "text-purple-600", bg: "bg-purple-100" },
  person: { icon: User, color: "text-emerald-600", bg: "bg-emerald-100" },
  goal: { icon: Target, color: "text-amber-600", bg: "bg-amber-100" },
  document: { icon: FileText, color: "text-slate-600", bg: "bg-slate-100" },
  incident: { icon: AlertTriangle, color: "text-red-600", bg: "bg-red-100" },
  error_event: { icon: AlertTriangle, color: "text-orange-600", bg: "bg-orange-100" },
  deploy: { icon: Rocket, color: "text-cyan-600", bg: "bg-cyan-100" },
  feature: { icon: Lightbulb, color: "text-yellow-600", bg: "bg-yellow-100" },
  project: { icon: Cpu, color: "text-indigo-600", bg: "bg-indigo-100" },
  metric_snapshot: { icon: BarChart3, color: "text-pink-600", bg: "bg-pink-100" },
  decision: { icon: Activity, color: "text-teal-600", bg: "bg-teal-100" },
  sprint: { icon: Repeat, color: "text-violet-600", bg: "bg-violet-100" },
};

export const entityTypeRoute: Partial<Record<EntityType, string>> = {
  task: "/tasks",
  goal: "/goals",
  project: "/projects",
  person: "/people",
};

export function getEntityRoute(type: EntityType, id: string): string {
  const base = entityTypeRoute[type];
  return base ? `${base}/${id}` : `/entities/${id}`;
}
