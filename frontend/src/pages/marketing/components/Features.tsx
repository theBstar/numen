const features = [
  {
    title: "Decisions are first-class entities",
    desc: "Every action is recorded with context, rationale, and outcome. After 18 months, you have institutional memory no competitor can replicate.",
  },
  {
    title: "Personalised urgency scoring",
    desc: "The same PR scores differently for its author, reviewer, and PM. Weights: blocking (30%), staleness (20%), goal criticality (10%), org precedent (17%).",
  },
  {
    title: "Agent-ready via MCP",
    desc: "Cursor, Claude Code, and Devin query the context graph. An agent asking 'refactor or quick fix?' gets sprint state, goal urgency, and incident history.",
  },
  {
    title: "Read-only. Always a draft.",
    desc: "Numen never writes to your tools. Claude dispatch generates drafts - PR summaries, briefing narratives - but never acts without human approval.",
  },
];

export function Features() {
  return (
    <section id="features" className="py-16 sm:py-24">
      <div className="max-w-6xl mx-auto px-6">
        <h2 className="font-serif text-3xl sm:text-4xl font-normal text-ws-50 leading-tight">
          Why it compounds.
        </h2>

        <div className="mt-10 grid sm:grid-cols-2 gap-4">
          {features.map((feature) => (
            <article key={feature.title} className="p-5 rounded-2xl bg-ws-700 border border-ws-500">
              <h3 className="text-sm font-medium text-ws-50">{feature.title}</h3>
              <p className="mt-2 text-xs text-ws-300 leading-relaxed">{feature.desc}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
