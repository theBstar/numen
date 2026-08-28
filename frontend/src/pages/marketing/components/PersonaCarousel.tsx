import { useState } from "react";

interface BriefItem {
  title: string;
  badge?: string;
  badgeColor?: string;
  reason: string;
}

interface Persona {
  role: string;
  name: string;
  color: string;
  items: BriefItem[];
}

const personas: Persona[] = [
  {
    role: "CTO",
    name: "Alex Rivera",
    color: "#6366F1",
    items: [
      { title: "2 goals at risk this quarter", badge: "Critical", badgeColor: "bg-red-500/15 text-red-400", reason: "Retention +15% - 62% complete, 8 days left. API Latency <200ms - blocked by infra team capacity." },
      { title: "Cross-team blocker: payments \u2192 mobile \u2192 checkout", reason: "3-team blocking chain. PR #807 stale 4 days. Historically your org escalates within 2 hours." },
      { title: "Engineering velocity down 18% org-wide this sprint", reason: "Correlated with 3 concurrent incidents last week. Recommend sprint buffer for payments team." },
    ],
  },
  {
    role: "VP Engineering",
    name: "Sarah Kim",
    color: "#818CF8",
    items: [
      { title: "Payments team at capacity - no buffer for incidents", badge: "Watch", badgeColor: "bg-amber-500/15 text-amber-400", reason: "5 active tickets, 2 PRs in review, 0 incident buffer. Historical P1 rate: 1 per 3 weeks." },
      { title: "Mobile team blocked on payments for 4 days", reason: "PR #807 is the bottleneck. 3 downstream tasks waiting. Sprint commitment at risk." },
      { title: "New hire onboarding: 2 engineers unassigned", reason: "Joined Monday, no sprint work assigned. Suggest pairing with Sofia on checkout-v2." },
    ],
  },
  {
    role: "Eng Manager",
    name: "Priya Sharma",
    color: "#34D399",
    items: [
      { title: "Team workload: 3 tickets closing Friday, 0 incidents", reason: "Sofia has capacity Monday. Phase 2 PRD stale 9 days - suggest closing by Thursday." },
      { title: "1:1 with James - prep ready", reason: "Topics: blocked on auth-flow scope, sprint velocity down 12%, new hire onboarding status." },
      { title: "Sprint health: 78% on track, 1 at risk", reason: "ENG-4530 depends on API team. Escalation recommended if no movement by Wednesday." },
    ],
  },
  {
    role: "Product Manager",
    name: "James Park",
    color: "#A78BFA",
    items: [
      { title: "Saved Filters: 0.4% adoption after 3 weeks", badge: "Signal", badgeColor: "bg-[#6366F1]/15 text-[#818CF8]", reason: "Feature shipped but near-zero usage. PostHog data. You specced this feature." },
      { title: "3 open decisions blocking engineers", reason: "Scope questions on payments-v2, auth-flow, onboarding-redesign. Average wait: 2.5 days." },
      { title: "Checkout v2 goal: 62% complete, 8 days left", reason: "3 tasks remaining, 1 blocked. On track if PR #807 merges this week." },
    ],
  },
  {
    role: "Engineer",
    name: "Sofia Chen",
    color: "#60A5FA",
    items: [
      { title: "Review PR #807 - latency fix", badge: "Urgent", badgeColor: "bg-red-500/15 text-red-400", reason: "Blocking 3 teams. Stale 4 days. Goal: Ship Checkout v2 by April 3." },
      { title: "ENG-4521 unblocked - ready to start", reason: "Dependency resolved yesterday. Sprint item. Goal: Retention +15%." },
      { title: "Bug: checkout.js error spike +340%", reason: "Auto-detected from Sentry x Amplitude correlation. No ticket filed yet." },
    ],
  },
];

export function PersonaCarousel() {
  const [active, setActive] = useState(0);
  const persona = personas[active]!;

  return (
    <div>
      <div className="flex gap-2 overflow-x-auto pb-2 -mx-1 px-1">
        {personas.map((p, i) => (
          <button
            key={p.role}
            onClick={() => setActive(i)}
            className={`shrink-0 px-4 py-2 rounded-full text-xs font-medium transition-all ${
              i === active
                ? "bg-[#6366F1] text-white"
                : "bg-[#1E293B] text-[#94A3B8] hover:text-[#F5F5F0] border border-[#334155]"
            }`}
          >
            {p.role}
          </button>
        ))}
      </div>

      <div className="mt-5 rounded-2xl border border-[#334155] overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 bg-[#0F0F23] border-b border-[#334155]">
          <div className="flex items-center gap-2.5">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: persona.color }} />
            <span className="text-xs font-medium text-[#F5F5F0]">{persona.role} - {persona.name}</span>
          </div>
          <span className="text-[10px] text-[#64748B]">8:00 AM - Today's Brief</span>
        </div>

        <div className="p-4 space-y-3 bg-[#0F0F23]">
          {persona.items.map((item, i) => (
            <div key={i} className="p-3.5 rounded-xl bg-[#1A1A2E] border border-[#1E293B]">
              <div className="flex items-start justify-between gap-3">
                <span className="text-[13px] font-medium text-[#F5F5F0] leading-snug">{item.title}</span>
                {item.badge && (
                  <span className={`shrink-0 px-2 py-0.5 rounded-lg text-[9px] font-semibold ${item.badgeColor}`}>
                    {item.badge}
                  </span>
                )}
              </div>
              <p className="mt-1.5 text-[11px] text-[#64748B] leading-relaxed">{item.reason}</p>
            </div>
          ))}
        </div>

        <div className="px-5 py-3 bg-[#0F0F23] border-t border-[#334155]">
          <p className="text-[10px] text-[#334155]">
            Each item shows why Numen surfaced it - Scores personalised per role - Connected to business goals
          </p>
        </div>
      </div>
    </div>
  );
}
