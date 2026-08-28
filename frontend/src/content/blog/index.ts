export interface BlogPost {
  slug: string;
  title: string;
  description: string;
  publishDate: Date;
  updatedDate?: Date;
  author: string;
  tags: string[];
  draft: boolean;
  body: string;
}

export const blogPosts: BlogPost[] = [
  {
    slug: "what-is-a-context-graph",
    title: "What Is a Context Graph?",
    description:
      "A context graph captures not just what things are, but how decisions were made and why. Here is what makes it different from a knowledge graph, why it matters for AI, and where the industry is headed.",
    publishDate: new Date("2026-03-29"),
    author: "Numen Team",
    tags: ["context graphs", "AI infrastructure", "engineering intelligence"],
    draft: false,
    body: `
Every organisation runs on context. Not just data - context. Who decided what, when, and why. Which task is blocking three other teams. Which decision from last quarter is the reason this deploy is structured this way.

That context lives in people's heads, scattered across Slack threads, Linear comments, GitHub reviews, and half-remembered standups. AI has made execution fast. But knowing what to execute on - that layer has not kept up.

A context graph is the data structure designed to fix this.

## The definition

A context graph is a dynamic network that connects entities (people, tasks, decisions, deploys, goals) with typed, weighted relationships - and critically, tracks **when** those relationships were active, **who** established them, and **how confident** the system is in each connection.

Unlike a static database or even a traditional knowledge graph, a context graph answers temporal questions: What did the graph look like when we made that decision? Which relationships have decayed? What changed between Tuesday and today?

Every node and edge carries metadata:

- **Temporal validity** - \`valid_from\` and \`valid_to\` timestamps, enabling point-in-time queries
- **Provenance** - which system or person produced the data
- **Confidence scores** - inferred connections score below 1.0, confirmed ones score 1.0
- **Decision traces** - records of governance actions, certifications, and operational decisions made about a data asset

This is what the Atlan team calls "reification" - treating edges as first-class objects with their own attributes, so that "Alice approved PR #412 on March 3rd" becomes a queryable node, not just a line between two entities.

## Why not just a knowledge graph?

Knowledge graphs are powerful. They map semantic relationships between entities - "Alice owns the payments service", "PR #412 depends on the auth refactor". Google's Knowledge Graph, for instance, powers the info boxes you see in search results.

But knowledge graphs are fundamentally **noun-centric**. They map what things *are*. A context graph is **verb-centric** - it maps how decisions *work*. (We dig deeper into this distinction in [Context Graph vs Knowledge Graph: What's Actually Different?](/blog/context-graph-vs-knowledge-graph/).)

The practical difference:

| Property | Knowledge Graph | Context Graph |
|----------|----------------|---------------|
| Temporal awareness | Limited | Native - every edge has a time window |
| Decision memory | None | First-class - traces of who decided what and when |
| Update model | Periodic batch | Real-time streaming |
| Confidence tracking | Usually absent | Scored per relationship |
| AI agent readiness | Partial (good for RAG) | Native - designed for agent reasoning |

A knowledge graph tells you that a task exists. A context graph tells you that the task has been stale for 6 days, is blocking 3 downstream items, was discussed in Slack 14 times this week, and the last time a similar pattern occurred the team shipped a hotfix within 24 hours.

That second kind of information is what humans use to make decisions. And it is what AI agents need to make recommendations that do not sound hollow.

## What goes into a context graph?

The nodes are operational entities - the things your organisation actually works with:

- **People** - engineers, PMs, designers, with their roles and team memberships
- **Tasks** - tickets, issues, stories from your project management tool
- **Code artifacts** - PRs, commits, branches, deploys
- **Incidents and errors** - from observability tools
- **Decisions** - architectural choices, prioritisation calls, scope changes
- **Goals** - OKRs, milestones, quarterly targets
- **Documents** - specs, RFCs, design docs

The edges are typed relationships:

- OWNS, BLOCKS, DEPENDS_ON, AUTHORED
- MENTIONED_IN, SHIPS_TO, MEASURES
- CAUSED_BY, CONFLICTS_WITH

Each edge carries a weight (which decays over time) and confidence score. An edge inferred from a Slack mention has lower confidence than one confirmed by a Linear dependency link. Both are useful; the system just knows which is which.

## Why now?

Three forces have converged to make context graphs suddenly relevant:

**1. Production AI hit a wall.** Demos work great. Production deployments plateau at 50-65% accuracy because the AI lacks organisational context - it does not know which tables to join, what terms mean in your specific org, or who owns what. RAG (retrieval-augmented generation) helped, but it is hitting diminishing returns at scale.

**2. Context engineering became a discipline.** Andrej Karpathy's framing - that "context engineering is the delicate art and science of filling the context window with just the right information" - shifted the industry's attention from model capabilities to input quality. The model is not the bottleneck. The context is.

**3. Agents need structured context, not documents.** AI agents that can take multi-step actions need more than a vector search over documents. They need to understand relationships, temporal ordering, and organisational structure. A context graph provides exactly this. (See [How Context Graphs Power AI Agents](/blog/context-graphs-for-ai-agents/) for concrete use cases.)

Gartner predicts that by 2028, over 50% of enterprise AI agent systems will incorporate context graphs. Foundation Capital has called it "AI's trillion-dollar opportunity". The W3C formed a Context Graphs Community Group in February 2026 with 62 members working on interchange format standards.

This is not theoretical infrastructure. It is the missing layer between "AI can generate text" and "AI can actually help my team ship." We explore the full momentum story in [Why Everyone Is Talking About Context Graphs Right Now](/blog/why-context-graphs-now/).

## How Numen uses context graphs

Numen builds a live context graph from your engineering and product tools - Linear, GitHub, Slack, and more. It normalises entities across sources, resolves identities (matching the same person across different tools), and computes personalised urgency scores.

The same PR has a different urgency for its author, its reviewer, and the PM tracking the feature. The same goal shows different signals to the CTO and the engineer working on it. The context graph makes this personalisation possible because it encodes not just the data, but the *relationships that give data meaning*.

Every insight Numen surfaces comes with provenance - "Why Numen surfaced this" - linking back to the specific graph connections and temporal signals that made it relevant to you, right now.

---

*Context graphs are the infrastructure layer that makes AI useful inside organisations - not just capable, but aware. If you are building for a world where agents need to understand how your team actually works, this is the primitive to build on.*

*Numen is building the context graph for engineering and product teams. [Join the waitlist](/#waitlist) to be first to see it.*
`,
  },
  {
    slug: "context-graph-vs-knowledge-graph",
    title: "Context Graph vs Knowledge Graph: What's Actually Different?",
    description:
      "Knowledge graphs, data catalogs, and context graphs are often conflated. Here is what each one does, when you need which, and why context graphs are emerging as the layer AI agents actually require.",
    publishDate: new Date("2026-03-28"),
    author: "Numen Team",
    tags: ["context graphs", "knowledge graphs", "data infrastructure"],
    draft: false,
    body: `
The terms get blurred. Vendors relabel knowledge graphs as context graphs. Analysts bundle them together. Engineers wonder if this is just rebranding.

It is not. The distinction matters - and it is the difference between AI that can answer questions and AI that can make decisions.

## Three paradigms, one sentence each

**Knowledge graph**: maps what things *are*. Entities and their semantic relationships.

**Data catalog**: maps where things *live*. Assets, their metadata, lineage, and ownership.

**Context graph**: maps how decisions *work*. Actions, temporal traces, confidence scores, and institutional memory. (For a full definition, see [What Is a Context Graph?](/blog/what-is-a-context-graph/).)

The metaphor that clarifies it: a knowledge graph is the org chart. A data catalog is the filing cabinet. A context graph is the institutional memory of everyone who has ever worked there - how decisions actually get made, what patterns recur, and what the current state of play is across every team.

## Knowledge graphs in depth

Knowledge graphs model semantic relationships between entities. "Alice is a senior engineer." "The payments service depends on the auth module." "PR #412 was authored by Bob."

They are **noun-centric** - built from declared schemas and ontologies. Google's Knowledge Graph powers the info panels in search. Enterprise knowledge graphs power recommendation systems, search, and entity resolution.

Strengths:
- Excellent for structured queries over well-defined domains
- Mature tooling (RDF, OWL, SPARQL, Neo4j)
- Good for RAG pipelines where you need entity context

Limitations:
- **Static snapshots** - a knowledge graph tells you the current state, not the trajectory
- **No decision memory** - it records that a decision exists, not the context in which it was made
- **Batch updates** - typically refreshed periodically, not in real-time
- **No confidence tracking** - a relationship either exists or it does not

When a knowledge graph says "Task A blocks Task B", it is a binary fact. It cannot tell you that this blocking relationship was established 8 days ago, that 3 people have mentioned it in Slack since Tuesday, or that the last time a similar blocker lasted this long the team escalated to the VP of Engineering.

## Data catalogs in depth

Data catalogs inventory your data assets - table names, column descriptions, data owners, quality metrics, lineage graphs. They are **asset-centric**, answering "where does this data live and who manages it?"

Tools like Atlan, Alation, and Collibra have built large businesses here. They solve a real problem: in any organisation with more than a handful of data sources, nobody knows where everything is.

Strengths:
- Essential for data governance and compliance
- Good for onboarding new team members ("where do I find X?")
- Lineage tracking helps with impact analysis

Limitations:
- **Metadata, not operational context** - a catalog knows a table exists, not how teams actually use it for decisions
- **Static descriptions** - column descriptions get stale fast
- **No temporal context** - when was this table last relevant to a decision?
- **No cross-tool correlation** - catalogs track data assets, not the relationships between code, tasks, people, and goals

## Context graphs: what's actually new

A context graph starts where knowledge graphs and data catalogs stop. It captures operational metadata and decision traces - the *how* and *when* and *why*, not just the *what*.

Key properties that distinguish context graphs:

### Temporal validity

Every node and edge has a time window. You can ask: "What did the dependency graph look like on March 15th?" or "How has the blocking chain evolved over the past week?" This is not a log - it is a queryable temporal model.

### Decision traces

When someone approves a PR, changes a task status, reassigns a ticket, or makes a scope decision, the context graph records not just the action but the graph state at the time. This creates institutional memory - the system knows that the last time a similar pattern occurred, the team responded in a particular way.

### Confidence scores

Not all relationships are equally certain. A dependency link in Linear is high confidence. A person-to-task relationship inferred from a Slack mention is lower confidence. Both are useful, but the system (and any AI agent querying it) knows the difference.

### Real-time streaming

Context graphs ingest events as they happen - webhook payloads, API polls, message events. They are not refreshed on a schedule; they reflect the current state of work as it evolves.

### Personalisation

The same graph looks different to different people. The same PR has a different urgency for the author, the reviewer, and the PM tracking the feature. Context graphs encode enough relational structure to compute per-person relevance.

## The comparison table

| Dimension | Knowledge Graph | Data Catalog | Context Graph |
|-----------|----------------|--------------|---------------|
| **Focus** | Semantic relationships | Asset metadata | Operational decisions |
| **Orientation** | Noun-centric (entities) | Asset-centric (tables) | Verb-centric (actions) |
| **Temporal** | Limited | Static snapshots | Native time-travel |
| **Decision memory** | None | None | First-class traces |
| **Confidence** | Binary (exists/not) | Quality scores on assets | Per-relationship scores |
| **Update model** | Periodic batch | Snapshot-based | Real-time streaming |
| **AI agent use** | Good for RAG | Good for discovery | Designed for agent reasoning |
| **Personalisation** | Generic | Role-based access | Per-person relevance |

## When you need which

**Use a knowledge graph when** you have a well-defined domain with stable entities and relationships. Product catalogs, medical ontologies, corporate org structures. The entities do not change much; the relationships are definitional.

**Use a data catalog when** you need to inventory and govern your data assets. Compliance requirements, data discovery for analysts, lineage tracking for impact analysis.

**Use a context graph when** you need AI to understand how your organisation actually works - not just what exists, but what is happening, what is changing, what is urgent, and what patterns recur. Engineering intelligence, proactive surfacing, agent-powered decision support.

## The convergence thesis

These are not mutually exclusive. In practice, a context graph subsumes the other two. It contains entity relationships (like a knowledge graph) and can track data lineage (like a catalog), but adds the temporal, confidence, and decision-trace layers that neither provides.

The interesting question is not "which one should I use?" but "which layer is missing?" If you already have a knowledge graph, what you are probably missing is the temporal and operational context that turns it from a static reference into a live intelligence layer.

That is the gap context graphs fill. Not replacing what exists - extending it with the context that makes AI actually useful. For a balanced look at the limitations, read [The Honest Case for Context Graphs](/blog/context-graph-honest-assessment/).

---

*Numen builds a context graph from your engineering and product tools - connecting tasks, code, people, decisions, and goals into a live graph that surfaces what matters to each person. [Join the waitlist](/#waitlist) to see it in action.*
`,
  },
  {
    slug: "why-context-graphs-now",
    title: "Why Everyone Is Talking About Context Graphs Right Now",
    description:
      "From Gartner predictions to Aaron Levie's tweets, context graphs went from obscure infrastructure to the most discussed AI architecture in months. Here is what changed and why it matters.",
    publishDate: new Date("2026-03-27"),
    author: "Numen Team",
    tags: ["context graphs", "AI trends", "context engineering"],
    draft: false,
    body: `
Six months ago, "context graph" was a term you would find in academic papers and W3C mailing lists. Today, it is on the roadmap of every major enterprise AI company, in Gartner's predictions for agentic systems, and on the lips of CEOs at Box, HubSpot, and Glean.

What changed? Not the technology - the realisation.

## The RAG ceiling

Retrieval-augmented generation was supposed to solve the grounding problem. Give the model access to your documents, let it retrieve relevant chunks, and it will generate accurate answers.

For demos, it works. For production at scale, it plateaus.

The problem is not retrieval quality - it is that documents are the wrong unit of context. When an AI agent needs to understand whether to escalate a bug, it does not need the incident runbook. It needs to know: Who owns this service? What is the current sprint state? Is this blocking a release? How did the team handle a similar pattern last quarter? What is the goal this feature connects to?

That is not a document retrieval problem. That is a graph traversal problem.

RAG gives you relevant text. A context graph gives you relevant *understanding*. (Not sure what a context graph actually is? Start with [What Is a Context Graph?](/blog/what-is-a-context-graph/).)

## The Karpathy inflection

In 2025, Andrej Karpathy reframed the AI engineering discipline. He argued that "context engineering is the delicate art and science of filling the context window with just the right information for the next step."

This was a quiet paradigm shift. The industry had been obsessing over model capabilities - bigger models, better benchmarks, more parameters. Karpathy redirected attention to the input side: the model is not the bottleneck. The context is.

Once you accept that framing, the question becomes: where does the context come from? And the answer - for any non-trivial organisational use case - is a structured, temporal, relationship-aware data layer. A context graph.

## The accuracy gap

Here is the number that matters: enterprise AI tools in production achieve roughly 50-65% accuracy. Production-grade agents need 95%+.

That gap is not a model problem. It is a context problem.

The AI does not know which tables to join. It does not know what "revenue" means in your specific org (gross? net? ARR?). It does not know that the fiscal year starts in April. It does not know that the "payments" team was reorganised last quarter and half of what used to be "payments" is now "billing".

This is tribal knowledge - the accumulated institutional context that lives in people's heads and nowhere else. A context graph is the first data structure designed to capture it systematically: not as documents, but as typed, temporal, confidence-scored relationships.

## The industry pivot

The momentum is hard to ignore:

**Gartner** predicted that by 2028, over 50% of enterprise AI agent systems will incorporate context graphs, calling them "the new essential infrastructure for agentic systems."

**Foundation Capital** termed it "AI's trillion-dollar opportunity" - arguing that the context layer is the infrastructure play of this decade, not the model layer.

**Aaron Levie** (Box CEO) has been publicly vocal about context graphs as the architecture that makes enterprise AI actually work. Not because they are a new idea, but because they are suddenly necessary - agents need structured context, not document search.

**Glean** is building their entire AI platform around a context graph that connects people, documents, and actions across enterprise tools. Their approach: model actions as first-class entities, not just the objects they act upon.

**Chroma** (the vector database company) has explicitly positioned around the "context layer" thesis - arguing that "every Fortune 5000 company in the next 3 years will build a context layer and transform their businesses with AI. If they don't - they will die." Strong claim. But the direction is clear.

The **W3C** formed a Context Graphs Community Group in February 2026 with 62 members from knowledge representation, semantic web, and enterprise AI domains. They are standardising interchange formats and vocabulary - the kind of standards work that signals a technology is crossing from experimental to foundational.

## Models come and go. Data is forever.

There is a deeper reason the industry is gravitating toward context graphs. It is the same reason databases outlasted application frameworks: data infrastructure persists.

Every 18 months, the leading model changes. GPT-4 gave way to Claude 3 gave way to whatever ships next quarter. The model layer is a commodity - increasingly powerful, decreasingly differentiated.

But your organisation's context - how teams work, how decisions get made, what patterns recur, what institutional memory has accumulated - that is a durable asset. It compounds over time. A context graph that has been ingesting signals for six months is dramatically more useful than one that started yesterday.

This is why Chroma's founder said "models will come and go, but data is forever." The value is not in the AI. The value is in the structured, temporal, relationship-rich context that makes the AI useful.

## What this means for engineering teams

If you are an engineering leader, the practical implication is straightforward: the tools you use to ship software are generating signals that, when connected, produce dramatically more insight than any single tool provides alone.

Your project management tool knows about tasks. Your code platform knows about PRs. Your chat tool knows about conversations. But none of them knows the relationships between tasks, PRs, conversations, goals, incidents, and the people working on all of it.

A context graph connects those signals. And once connected, it becomes possible to:

- Surface what matters to each person before they ask
- Score urgency based on blocking chains, goal criticality, and historical patterns
- Give AI agents the [structured context they need](/blog/context-graphs-for-ai-agents/) to make useful recommendations
- Build institutional memory that persists beyond any individual's tenure

This is not a future promise. Organisations are building this now. The question is not whether context graphs will become standard infrastructure - it is how quickly your team gets there.

---

*Numen is building the context graph for engineering and product teams. We connect Linear, GitHub, Slack, and more into a live graph that surfaces what matters to each person. [Join the waitlist](/#waitlist) to be part of the first cohort.*
`,
  },
  {
    slug: "context-graphs-for-ai-agents",
    title: "How Context Graphs Power AI Agents",
    description:
      "AI agents are brilliant but amnesiac. Context graphs give them the structured, temporal organisational knowledge they need to move from impressive demos to production-grade decision support.",
    publishDate: new Date("2026-03-26"),
    author: "Numen Team",
    tags: ["AI agents", "context graphs", "MCP", "engineering intelligence"],
    draft: false,
    body: `
AI agents can write code, summarise documents, draft emails, and orchestrate multi-step workflows. What they cannot do - without help - is understand your organisation.

They do not know that the payments service was refactored last quarter. They do not know that the person who usually reviews auth PRs is on leave. They do not know that the feature you are building connects to a Q2 revenue goal that the CEO tracks weekly.

This is the agent context problem: powerful reasoning capabilities operating on impoverished context. The result is recommendations that are technically competent but organisationally naive.

Context graphs solve this by giving agents a structured, queryable model of how your organisation actually works. (New to the concept? See [What Is a Context Graph?](/blog/what-is-a-context-graph/) for the fundamentals.)

## What agents need that documents cannot provide

When an AI coding agent encounters a question like "should I refactor this module or ship a quick fix?", the answer depends on context that lives outside the codebase:

- **Sprint state** - Is the team mid-sprint with a release tomorrow, or in a planning week?
- **Blocking chains** - Is this module blocking other teams? How many downstream items are waiting?
- **Goal urgency** - Does this connect to a high-priority goal with a tight deadline?
- **Historical patterns** - How has this team handled similar trade-offs before?
- **Incident history** - Has this module caused production incidents recently?
- **Ownership** - Who owns this area? Who needs to be looped in?

None of this is in the code. None of it is in a document. It exists as relationships between entities - people, tasks, goals, deploys, incidents - evolving over time.

A context graph encodes exactly this structure. And when exposed via a protocol like MCP (Model Context Protocol), any AI agent can query it.

## Use case: Engineering intelligence

This is what Numen builds. The context graph connects engineering and product tools - Linear, GitHub, Slack - and computes personalised urgency scores for every entity.

The same PR looks different to different people:

- **For the author**: urgency is based on review wait time, whether it blocks other PRs, and sprint deadline proximity
- **For the reviewer**: urgency is based on the author's blocked status, the PR's goal connection, and how many reviews they already have queued
- **For the PM**: urgency is based on whether this PR is on the critical path for a feature tied to a quarterly goal

This personalisation is only possible because the context graph encodes the relationships between the person, the task, the goal, the sprint, and the historical patterns. No single tool has this picture. The graph does.

An agent connected to this graph can answer questions that would take a human 30 minutes of context-gathering across three tools:

- "What is blocking the v2.3 release?"
- "Which team members have the most blocked downstream work?"
- "What changed since yesterday that I should know about?"

## Use case: Customer support agents

Merge's architecture for context-graph-powered support agents operates across three data tiers:

**Live data** - recently modified tickets, current account status, active escalations. Fetched in real-time from CRM and ticketing systems.

**Cached context** - account history, past interactions, product configuration. Refreshed periodically, available with low latency.

**Derived summaries** - pre-computed customer health scores, interaction summaries, pattern analysis. Lightweight enough for rapid inclusion in agent context.

When a support rep handles a dissatisfied customer, the agent does not just retrieve the current ticket. It assembles the full context: the customer's history, related tickets, product usage patterns, and the resolution outcomes of similar cases. The context graph connects all of these - and the agent knows which connections are high-confidence (explicit CRM links) versus inferred (similarity-based matching).

## Use case: Sales enablement

The same architecture applies to sales workflows. Before a quarterly business review, an agent can assemble:

- Recent meeting notes and email threads (live data)
- Deal stage, pipeline value, and stakeholder map (cached context)
- Conversation summaries and relationship strength scores (derived)

The context graph provides the relationships between people, deals, communications, and outcomes. The agent uses these relationships to generate a briefing that is not just a data dump but a narrative grounded in actual interaction history.

## Use case: Agentic analytics

Promethium describes an "agentic analytics fabric" - an architecture where AI agents can query distributed data sources through a context layer that provides:

- **Federated data access** - live queries across databases, warehouses, and SaaS tools
- **Contextual intelligence** - business rules, metric definitions, and institutional knowledge
- **Personalised agents** - domain-specific intent interpretation and memory
- **Governance** - fine-grained access controls from user level to data level

The context graph is the layer that makes federation useful. Without it, federated access just gives you more data to be confused by. With it, the agent knows which data matters for this specific question from this specific person.

## The technical architecture

Building a context graph for agent consumption involves four layers:

### 1. Deep connectors

Integrations that capture not just current state but change events. A task tracker connector should capture not only "Task A is in progress" but "Task A moved from review to in-progress at 14:32 by Alice." The event stream is the raw material for temporal edges.

### 2. Entity resolution

The same person appears differently across tools - "alice@company.com" in GitHub, "Alice Chen" in Linear, "@alice" in Slack. Entity resolution matches these identities and creates canonical references. Glean describes this as building a "unified knowledge graph" where machine learning infers higher-level entities (projects, teams, products) from lower-level signals.

### 3. Graph construction

Entities become nodes. Relationships become typed, weighted, temporal edges. Confidence scores distinguish confirmed connections from inferred ones. The graph supports recursive queries - "find all items transitively blocked by Task A" - which is critical for urgency scoring and impact analysis.

### 4. Agent interface

The graph needs an API layer that agents can query. MCP (Model Context Protocol) is emerging as the standard for this - it lets AI agents like Cursor, Claude Code, and Devin ask structured questions and receive graph-grounded responses.

Numen exposes its context graph as an MCP server. An agent building a feature can query: "What is the sprint state for this team? What goal does this feature connect to? How urgent is the deadline?" The response includes provenance - the agent knows *why* each piece of information was surfaced and how confident the system is in each relationship.

## Agent execution as a feedback loop

Glean describes an elegant closing of the loop: agent runs become new traces in the context graph. When an agent takes an action - querying data, generating a summary, making a recommendation - the sequence of tool calls, inputs, outputs, and user feedback becomes training data.

Successful runs get replayed as reinforcement learning signals. Failed runs identify anti-patterns. Over time, the context graph learns not just how the organisation works, but how agents can best serve it.

This is the compounding effect. A context graph that has been running for six months knows more than one that started yesterday - not because it has more data, but because it has more *decision traces* showing what worked.

## The path forward

The trajectory is clear: AI agents are becoming the primary interface for organisational work. But agents without context are like brilliant new hires on their first day - technically capable but operationally blind.

Context graphs are the onboarding layer. They give agents the structured, temporal, relationship-rich understanding they need to be genuinely useful - not just impressive. For a frank look at what is and is not deliverable today, read [The Honest Case for Context Graphs](/blog/context-graph-honest-assessment/).

---

*Numen builds a live context graph from your engineering and product tools and exposes it to AI agents via MCP. [Join the waitlist](/#waitlist) to see how it works.*
`,
  },
  {
    slug: "context-graph-honest-assessment",
    title: "The Honest Case for Context Graphs",
    description:
      "Context graphs are generating real momentum - and real scepticism. Here is a frank look at the promises, the limitations, and what is actually deliverable today.",
    publishDate: new Date("2026-03-25"),
    author: "Numen Team",
    tags: ["context graphs", "analysis", "AI infrastructure"],
    draft: false,
    body: `
We are building a context graph. So you should expect us to be bullish on the concept. We are - but we also think the space benefits from honesty about what context graphs can and cannot do today.

The hype is real. So are the limitations. Here is our attempt at a clear-eyed assessment.

## What the sceptics say

Verdantix, the technology research firm, published an analysis asking whether context graphs represent "transformational architecture or familiar AI hype." Their conclusion was pointed: context graphs are a "transitional technology" offering pragmatic workflow automation improvements rather than fundamentally expanding AI agent capabilities.

Their specific criticisms deserve serious engagement. (For a primer on the concept itself, see [What Is a Context Graph?](/blog/what-is-a-context-graph/). For why the momentum is building now, see [Why Everyone Is Talking About Context Graphs](/blog/why-context-graphs-now/).)

### "It's incremental, not revolutionary"

The argument: context graphs are knowledge graphs with extra metadata. Temporal validity, confidence scores, and decision traces are useful additions, but they do not change the fundamental challenges of data integration, ontology alignment, and governance. The core problems persist while complexity and maintenance costs increase.

**Our take**: This is partially fair. The underlying graph model is not fundamentally new. What is new is the emphasis on temporal dynamics and decision context - and this matters more than it might seem. The difference between "Task A blocks Task B" and "Task A has blocked Task B for 8 days, with 14 Slack mentions this week and a pattern match to a similar blocker that escalated to VP-level last quarter" is not incremental. It is the difference between data and intelligence.

But yes - building and maintaining this is harder than building a static knowledge graph. That cost is real.

### "The capture problem"

The argument: much of the most valuable organisational context is never recorded. It lives in hallway conversations, offhand Slack messages, informal decisions that nobody documents. Return-to-office trends have made this worse - more decisions happen verbally, leaving fewer digital traces.

**Our take**: This is the strongest criticism. A context graph can only work with signals that are digitally captured. For engineering teams using tools like Linear, GitHub, and Slack, the signal density is high - most work happens in these systems. For other functions (sales, marketing, executive decision-making), the capture problem is more severe.

The honest answer is that context graphs work best where digital signal density is high. That is engineering and product work. Extending to other domains requires either cultural change (more documentation) or inference (which introduces confidence trade-offs).

### "Structural bias toward trivial decisions"

The argument: context graphs naturally capture high-frequency, low-stakes decisions (task movements, PR reviews, status updates) but remain sparse on the complex, rare, high-stakes decisions that matter most. The result is a system that knows everything about routine work and little about strategic inflection points.

**Our take**: This is true, and it is a design challenge we think about constantly. The mitigation is two-fold:

First, Numen treats **Decisions as first-class entities**. When someone makes a scope change, an architectural choice, or a prioritisation call, the system captures it as a node with its own edges and temporal context - not just an attribute on a task.

Second, **goal-connected scoring** means that even routine signals get weighted by their connection to strategic outcomes. A PR review is low-stakes on its own. A PR review that blocks a feature tied to a Q2 revenue goal that is already behind schedule - that is surfaced differently.

But the bias exists. Context graphs will always know more about the 95% of routine work than the 5% of strategic decisions that drive outsized outcomes. The goal is to reduce this gap, not pretend it does not exist.

### "Transitional technology"

The argument: context graphs are useful for the current moment - where AI agents are relatively simple and need explicit context - but as models improve and can reason more independently, the explicit context layer may become unnecessary.

**Our take**: This could be true on a long enough timeline. But "long enough" matters. Even if models eventually infer organisational context from raw data streams, that capability is years away. Today - and for the foreseeable planning horizon - agents need structured context. And structured context needs a data structure designed for it.

The analogy: operating systems were arguably "transitional" between hardware and applications. That transition has lasted 50 years and counting.

## What context graphs actually do well today

Setting aside the hype, here is what is concretely deliverable:

### Cross-tool correlation

The single most valuable thing a context graph does is connect signals across tools. No single tool - not your project tracker, not your code platform, not your chat tool - has the full picture. The graph does. "This PR blocks a feature that connects to a goal that is behind schedule" requires traversing relationships across at least three systems.

### Personalised urgency

The same data point is differently urgent to different people. A context graph with per-person edges and role-aware scoring can compute this. A dashboard cannot.

### Temporal awareness

"What changed since yesterday?" is a simple question that most tools answer badly. A context graph with temporal edges makes it a straightforward query. "What was the state of this dependency chain on March 15th?" is even harder for conventional tools and trivial for a temporal graph.

### Agent grounding

When an AI agent has access to a context graph, its recommendations are grounded in organisational reality - not just language patterns. (We explore this in depth in [How Context Graphs Power AI Agents](/blog/context-graphs-for-ai-agents/).) This is the difference between "you might want to review this PR" (generic) and "this PR has been waiting 6 days, blocks 3 downstream tasks in the billing team, and the feature deadline is in 4 days" (grounded).

### Institutional memory

Over time, the accumulated decision traces become genuinely valuable. The system learns: "The last three times a blocking chain exceeded 5 days in this team, someone escalated to the EM." This is not AI magic - it is pattern recognition over structured historical data. But it is the kind of pattern recognition that individual humans lose when they switch teams or leave the company.

## What we cannot do yet

In the interest of honesty:

- **We cannot capture what is not digitised.** If a critical decision happens in a meeting with no follow-up in any tool, we do not know about it.
- **Confidence scoring is imperfect.** Inferring relationships from Slack mentions is useful but noisy. We are transparent about confidence levels, but some inferences will be wrong.
- **Urgency scoring is heuristic-based.** Our v1 formula uses hardcoded weights, not learned ones. It works well for common patterns but may misjudge novel situations.
- **The graph needs time to compound.** A context graph that started yesterday is thin. It takes weeks of continuous ingestion before the temporal and pattern layers become genuinely insightful.
- **Cross-function coverage is limited.** Engineering and product tools are well-covered. Sales, marketing, HR, finance tools are not yet integrated.

## Where this is going

The trajectory we believe in:

**Near term (2026)**: Context graphs become standard infrastructure for engineering-focused AI tools. Entity resolution, temporal edges, and basic decision traces become table stakes. MCP adoption makes these graphs accessible to any AI agent.

**Medium term (2027-2028)**: Cross-function context graphs emerge, connecting engineering, product, sales, and customer success signals. Learned urgency scoring replaces heuristic weights. Simulation capabilities ("what would happen if we reprioritised X?") become feasible.

**Longer term**: The context graph becomes the organisational operating system - the live model of how work happens, how decisions get made, and what matters. Not replacing any individual tool, but connecting all of them into a unified intelligence layer.

Is this ambitious? Yes. Is every step guaranteed? No. But the direction - structured, temporal, relationship-rich context as the foundation for organisational AI - is the right one. And the criticisms, when engaged honestly, make the technology better.

---

*We are building Numen with eyes open about both the potential and the limitations. If you want to see context graphs applied honestly to engineering and product teams, [join the waitlist](/#waitlist).*
`,
  },
];
