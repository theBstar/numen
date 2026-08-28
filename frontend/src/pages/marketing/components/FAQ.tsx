const faqs = [
  {
    question: "What is a context graph?",
    answer: "A context graph captures not just what things are, but how they connect, how decisions were made, and why. Unlike a knowledge graph which stores static entities and semantic relationships, a context graph carries temporal validity (when relationships were active), provenance (which system produced data), confidence scores (inferred vs confirmed), and decision traces (what the graph looked like when someone acted). These properties make it useful for AI reasoning, proactive surfacing, and organisational learning.",
  },
  {
    question: "How is Numen different from a dashboard?",
    answer: "Dashboards show you data and wait for you to interpret it. Numen reads continuously across all your tools - Linear, GitHub, Slack, and more - and tells each person what to focus on, with the reasoning shown. It is proactive (you do not ask it questions), personalised (the same data surfaces differently per role), and goal-connected (every item is annotated with the business goal it connects to).",
  },
  {
    question: "What tools does Numen connect to?",
    answer: "In v1, Numen connects to Linear, GitHub, and Slack via read-only OAuth. The roadmap includes Datadog, Sentry, PagerDuty (observability), Amplitude, Mixpanel, PostHog (product analytics), Jira, Notion, Figma, and Confluence. Each connector maps to core entity types - adding a new tool means adding a connector, not changing the graph schema.",
  },
  {
    question: "Is Numen read-only?",
    answer: "In v1, yes. Numen reads from your tools and surfaces insights. Claude dispatch can generate drafts - PR summaries, briefing narratives, bug reports - but never acts on source systems without human approval. Every output is a draft for review. Write capabilities with an approval flow are planned for v2.",
  },
  {
    question: "What is an MCP server and how does Numen use it?",
    answer: "Model Context Protocol (MCP) is a standard that lets AI coding agents query external systems for context. Numen exposes its context graph as an MCP server, so agents like Cursor, Claude Code, and Devin can ask questions like 'should I refactor or ship a quick fix?' and receive the team's sprint state, the goal's urgency, the module's incident history, and the org's historical tolerance for tech debt.",
  },
  {
    question: "How does urgency scoring work?",
    answer: "Each item is scored per person, not globally. The same PR has a different urgency for its author, reviewer, and PM. Scoring components include: blocking others (30% weight), staleness in days (20%), downstream blocked count (10%), goal criticality (10%), recent mention count (8%), sprint membership (5%), precedent severity (10%), and historical response time (7%). The precedent components draw from accumulated Decision entities - the institutional memory of how this specific org responds to similar patterns.",
  },
];

export function FAQ() {
  return (
    <section id="faq" className="py-16 sm:py-24">
      <div className="max-w-2xl mx-auto px-6">
        <h2 className="font-serif text-3xl sm:text-4xl font-normal text-ws-50 leading-tight text-center">
          Frequently asked questions
        </h2>

        <div className="mt-10 space-y-3">
          {faqs.map((faq) => (
            <details key={faq.question} className="group rounded-2xl bg-ws-700 border border-ws-500">
              <summary className="flex items-center justify-between cursor-pointer p-5 text-ws-50 text-sm font-medium list-none [&::-webkit-details-marker]:hidden">
                <span>{faq.question}</span>
                <svg
                  className="w-4 h-4 text-ws-300 transition-transform group-open:rotate-180 flex-shrink-0 ml-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={1.5}
                  aria-hidden="true"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
                </svg>
              </summary>
              <div className="px-5 pb-5 text-xs text-ws-300 leading-relaxed">
                {faq.answer}
              </div>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
