import { useState, useEffect } from "react";

interface BriefItem {
  title: string;
  badge: string;
  badgeColor: string;
  reason: string;
}

interface Persona {
  role: string;
  name: string;
  items: BriefItem[];
}

const personas: Persona[] = [
  {
    role: "CTO",
    name: "Alex Rivera",
    items: [
      { title: "2 goals at risk this quarter", badge: "Critical", badgeColor: "bg-red-500/10 text-red-400", reason: "Retention +15% - 62% complete, 8 days left. API Latency <200ms - blocked by infra capacity. 3 teams affected." },
      { title: "Cross-team blocker: payments \u2192 mobile", badge: "0.92", badgeColor: "bg-indigo-500/10 text-indigo-400", reason: "3-team blocking chain. PR #807 stale 4 days. Historically your org escalates within 2 hours." },
      { title: "Silent bug: checkout funnel dropped 8%", badge: "Auto", badgeColor: "bg-amber-500/10 text-amber-400", reason: "Sentry x Amplitude cross-signal: 340% error spike correlates with funnel drop. No ticket filed." },
    ],
  },
  {
    role: "VP Engineering",
    name: "Sarah Kim",
    items: [
      { title: "Payments team at capacity - no incident buffer", badge: "Watch", badgeColor: "bg-amber-500/10 text-amber-400", reason: "5 active tickets, 2 PRs in review, 0 incident buffer. Historical P1 rate: 1 per 3 weeks." },
      { title: "Mobile team blocked on payments for 4 days", badge: "0.88", badgeColor: "bg-indigo-500/10 text-indigo-400", reason: "PR #807 is the bottleneck. 3 downstream tasks waiting. Sprint commitment at risk." },
      { title: "New hire onboarding: 2 engineers unassigned", badge: "Action", badgeColor: "bg-emerald-500/10 text-emerald-400", reason: "Joined Monday, no sprint work assigned. Suggest pairing with Sofia on checkout-v2." },
    ],
  },
  {
    role: "Eng Manager",
    name: "Priya Sharma",
    items: [
      { title: "3 tickets closing Friday, team has capacity", badge: "Capacity", badgeColor: "bg-emerald-500/10 text-emerald-400", reason: "Sofia has capacity Monday. Phase 2 PRD stale 9 days - suggest closing by Thursday." },
      { title: "1:1 with James - prep ready", badge: "Prep", badgeColor: "bg-indigo-500/10 text-indigo-400", reason: "Topics: blocked on auth-flow scope, sprint velocity down 12%, new hire onboarding status." },
      { title: "Sprint health: 78% on track, 1 at risk", badge: "0.78", badgeColor: "bg-amber-500/10 text-amber-400", reason: "ENG-4530 depends on API team. Escalation recommended if no movement by Wednesday." },
    ],
  },
  {
    role: "Product Manager",
    name: "James Park",
    items: [
      { title: "Saved Filters: 0.4% adoption after 3 weeks", badge: "Signal", badgeColor: "bg-indigo-500/10 text-indigo-400", reason: "Feature shipped but near-zero usage. PostHog data. You specced this feature." },
      { title: "3 open decisions blocking engineers", badge: "Urgent", badgeColor: "bg-red-500/10 text-red-400", reason: "Scope questions on payments-v2, auth-flow, onboarding-redesign. Avg wait: 2.5 days." },
      { title: "Checkout v2 goal: 62% complete, 8 days left", badge: "0.62", badgeColor: "bg-amber-500/10 text-amber-400", reason: "3 tasks remaining, 1 blocked. On track if PR #807 merges this week." },
    ],
  },
  {
    role: "Engineer",
    name: "Sofia Chen",
    items: [
      { title: "Review PR #807 - latency fix", badge: "Urgent", badgeColor: "bg-red-500/10 text-red-400", reason: "Blocking 3 teams. Stale 4 days. Goal: Ship Checkout v2 by April 3." },
      { title: "ENG-4521 unblocked - ready to start", badge: "Ready", badgeColor: "bg-emerald-500/10 text-emerald-400", reason: "Dependency resolved yesterday. Sprint item. Goal: Retention +15%." },
      { title: "Bug: checkout.js error spike +340%", badge: "Auto", badgeColor: "bg-amber-500/10 text-amber-400", reason: "Auto-detected from Sentry x Amplitude correlation. No ticket filed yet." },
    ],
  },
];

export function HeroBrief() {
  const [active, setActive] = useState(0);
  const [fading, setFading] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setFading(true);
      setTimeout(() => {
        setActive((prev) => (prev + 1) % personas.length);
        setFading(false);
      }, 300);
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const persona = personas[active]!;

  return (
    <div className="rounded-2xl border border-[#334155] overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-[#334155] bg-[#0A0A1A]">
        <span className="text-[11px] font-medium text-[#94A3B8] tracking-wide">
          Today's Brief - {persona.name}, {persona.role}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-[10px] font-medium text-emerald-400">Live</span>
        </span>
      </div>

      <div
        className={`p-4 space-y-4 bg-[#0A0A1A] h-[260px] overflow-hidden transition-opacity duration-300 ${fading ? "opacity-0" : "opacity-100"}`}
      >
        {persona.items.map((item, i) => (
          <div key={i}>
            {i > 0 && <div className="h-px bg-[#1E293B] mb-4" />}
            <div className="flex items-start justify-between gap-2">
              <span className="text-[13px] font-medium text-[#F5F5F0] leading-snug">{item.title}</span>
              <span className={`shrink-0 px-2 py-0.5 rounded-lg text-[10px] font-semibold ${item.badgeColor}`}>
                {item.badge}
              </span>
            </div>
            <p className="mt-1.5 text-[11px] text-[#475569] leading-relaxed line-clamp-2">{item.reason}</p>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-center gap-3 px-5 py-3 bg-[#0A0A1A] border-t border-[#1E293B]">
        {personas.map((p, i) => (
          <button
            key={p.role}
            onClick={() => { setActive(i); setFading(false); }}
            className="p-2 -m-2 group"
            aria-label={`View ${p.role} brief`}
          >
            <span className={`block rounded-full transition-all ${
              i === active ? "w-5 h-1.5 bg-[#6366F1]" : "w-2 h-1.5 bg-[#334155] group-hover:bg-[#475569]"
            }`} />
          </button>
        ))}
      </div>
    </div>
  );
}
