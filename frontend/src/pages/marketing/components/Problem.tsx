const pains = [
  {
    num: "01",
    title: "Tool sprawl",
    desc: "Linear, GitHub, Slack, Datadog, Notion - context lives in 12 tools, connected nowhere.",
  },
  {
    num: "02",
    title: "Lost decisions",
    desc: "Why was this built? Who decided? The answer died in a Slack thread three months ago.",
  },
  {
    num: "03",
    title: "Morning scramble",
    desc: "30 minutes catching up across 5 tabs before any real work. Engineers finish tickets faster but the right work runs out.",
  },
];

export function Problem() {
  return (
    <section id="problem" className="py-16 sm:py-24">
      <div className="max-w-6xl mx-auto px-6">
        <h2 className="font-serif text-3xl sm:text-4xl font-normal text-ws-50 leading-tight">
          Context is the new bottleneck.
        </h2>
        <p className="mt-4 text-sm sm:text-base text-ws-200 leading-relaxed max-w-lg">
          AI made execution fast. But knowing what to execute on - that layer hasn't kept up.
        </p>

        <div className="mt-10 space-y-3 sm:grid sm:grid-cols-3 sm:gap-5 sm:space-y-0">
          {pains.map((pain) => (
            <article key={pain.num} className="flex gap-4 p-5 rounded-2xl bg-ws-700 border border-ws-500">
              <span className="font-serif text-3xl font-light text-brand-light shrink-0">{pain.num}</span>
              <div>
                <h3 className="text-sm font-medium text-ws-50">{pain.title}</h3>
                <p className="mt-1.5 text-xs text-ws-300 leading-relaxed">{pain.desc}</p>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
