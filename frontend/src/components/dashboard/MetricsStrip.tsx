import {
  CheckSquare,
  GitPullRequest,
  AlertTriangle,
  Target,
  Users,
  Clock,
  TrendingUp,
  BarChart3,
  Shield,
  Eye,
  Layers,
  Zap,
} from "lucide-react";
import { MetricCard } from "./MetricCard";
import { RoleType } from "@/types";
import type { DashboardSummary } from "@/types";

interface MetricsStripProps {
  summary: DashboardSummary;
}

interface CardConfig {
  label: string;
  value: number;
  icon: import("lucide-react").LucideIcon;
  color: "default" | "red" | "amber" | "green" | "blue";
  href?: string;
}

export function MetricsStrip({ summary }: MetricsStripProps) {
  const cards = getCardsForRole(summary);

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {cards.map((card) => (
        <MetricCard
          key={card.label}
          label={card.label}
          value={card.value}
          icon={card.icon}
          color={card.color}
          href={card.href}
        />
      ))}
    </div>
  );
}

function getCardsForRole(s: DashboardSummary): CardConfig[] {
  const role = s.role;

  switch (role) {
    case RoleType.ENGINEER:
      return [
        { label: "Active Tasks", value: s.my_tasks.active, icon: CheckSquare, color: "blue" as const, href: "/tasks" },
        { label: "PRs to Review", value: s.pr_reviews_pending, icon: GitPullRequest, color: "amber" as const },
        { label: "Blocked Items", value: s.my_tasks.blocked, icon: AlertTriangle, color: "red" as const },
        { label: "In Review", value: s.my_tasks.in_review, icon: Eye, color: "green" as const },
      ];

    case RoleType.PM:
      return [
        { label: "Active Tasks", value: s.my_tasks.active, icon: CheckSquare, color: "blue" as const, href: "/tasks" },
        { label: "Blocked Items", value: s.my_tasks.blocked, icon: AlertTriangle, color: "red" as const },
        { label: "Goal Progress", value: s.goals_summary?.on_track ?? 0, icon: Target, color: "green" as const, href: "/goals" },
        { label: "At-Risk Goals", value: s.goals_summary?.at_risk ?? 0, icon: AlertTriangle, color: "amber" as const, href: "/goals" },
      ];

    case RoleType.EM:
      return [
        { label: "Team Members", value: s.team_size, icon: Users, color: "blue" as const, href: "/people" },
        { label: "Blocked Items", value: s.my_tasks.blocked, icon: AlertTriangle, color: "red" as const },
        { label: "Stalled PRs", value: s.stalled_prs_count, icon: Clock, color: "amber" as const },
        { label: "Team Tasks", value: s.my_tasks.total, icon: Layers, color: "default" as const },
      ];

    case RoleType.CTO:
      return [
        { label: "At-Risk Goals", value: s.goals_summary?.at_risk ?? 0, icon: AlertTriangle, color: "red" as const, href: "/goals" },
        { label: "Delayed Projects", value: s.delayed_projects?.length ?? 0, icon: Clock, color: "amber" as const, href: "/projects" },
        { label: "Cross-Team Blocks", value: s.cross_team_blocks, icon: Shield, color: "red" as const },
        { label: "Goal Coverage", value: s.goals_summary?.total ?? 0, icon: Target, color: "blue" as const, href: "/goals" },
      ];

    case RoleType.VP_ENG:
      return [
        { label: "At-Risk Goals", value: s.goals_summary?.at_risk ?? 0, icon: AlertTriangle, color: "red" as const, href: "/goals" },
        { label: "Delayed Projects", value: s.delayed_projects?.length ?? 0, icon: Clock, color: "amber" as const, href: "/projects" },
        { label: "Incidents (7d)", value: s.recent_incidents_count, icon: Zap, color: "red" as const },
        { label: "Stalled PRs", value: s.stalled_prs_count, icon: GitPullRequest, color: "amber" as const },
      ];

    case RoleType.VP_PRODUCT:
      return [
        { label: "Goal Coverage", value: s.goals_summary?.total ?? 0, icon: Target, color: "blue" as const, href: "/goals" },
        { label: "No Coverage", value: s.goals_summary?.no_coverage ?? 0, icon: AlertTriangle, color: "red" as const, href: "/goals" },
        { label: "Delayed Projects", value: s.delayed_projects?.length ?? 0, icon: Clock, color: "amber" as const, href: "/projects" },
        { label: "On Track", value: s.goals_summary?.on_track ?? 0, icon: TrendingUp, color: "green" as const },
      ];

    case RoleType.DESIGNER:
      return [
        { label: "Active Tasks", value: s.my_tasks.active, icon: CheckSquare, color: "blue" as const, href: "/tasks" },
        { label: "In Review", value: s.my_tasks.in_review, icon: Eye, color: "amber" as const },
        { label: "PRs to Review", value: s.pr_reviews_pending, icon: GitPullRequest, color: "default" as const },
        { label: "Todo", value: s.my_tasks.todo, icon: BarChart3, color: "default" as const },
      ];

    default:
      return [
        { label: "Active Tasks", value: s.my_tasks.active, icon: CheckSquare, color: "blue" as const },
        { label: "PRs to Review", value: s.pr_reviews_pending, icon: GitPullRequest, color: "amber" as const },
        { label: "Blocked Items", value: s.my_tasks.blocked, icon: AlertTriangle, color: "red" as const },
        { label: "Total Tasks", value: s.my_tasks.total, icon: Layers, color: "default" as const },
      ];
  }
}
