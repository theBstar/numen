# Numen — Product Vision

## The Core Thesis

AI can now execute fast. Cursor, Copilot, and Claude handle the doing. But **knowing what to execute on, in what order, and why** — that piece is still missing. Companies are hitting this wall.

Numen is the operating system that holds business goals, live work signals, production observability, and product analytics together in one context graph — and tells every person in the org, in their own language, where to put their energy today.

## The Problem

Every engineering organisation is buying AI coding tools. Execution speed has never been higher. But execution speed has exposed a new bottleneck: **the knowing-what-to-do layer has not kept up.**

The pattern companies are hitting:
- Engineers finish tickets faster but the queue of correctly-prioritised work runs out
- AI agents write code but have no access to the business context that determines what to build
- Product decisions are made in Slack threads that vanish, never connecting to the work
- Observability and product analytics sit in separate tools, unread and disconnected from planning
- Goals are set in OKR tools during planning and not consulted until the next quarter

## What Numen Is

Numen is a **proactive work intelligence platform**. It connects to every tool in a product and engineering organisation, builds a living context graph, and tells each person — CTO, VP Product, Engineering Manager, PM, Engineer, Designer — exactly what to work on now and why it matters.

- **Not reactive** — you do not ask it questions. It reads continuously and surfaces to you.
- **Not role-specific** — it covers the whole org from CTO to IC with one shared graph and personalised views.
- **Not a dashboard** — it does not show you data. It tells you what to do, with the reasoning shown.
- **Not disconnected from execution** — Claude dispatch lets you act immediately, with human approval on every output.

### The One-Line Pitch

> Numen reads your entire product and engineering organisation and tells every person where to put their energy today — connected to the business goals you are actually trying to hit.

## The Four Signal Layers

Numen ingests from four distinct signal sources. The power comes from reasoning across all four simultaneously — something no existing tool can do.

| Signal Layer | Tools | What It Adds |
|---|---|---|
| **Work signals** | Linear, Jira, GitHub, Slack, Notion, Figma | Task ownership, blockers, dependencies, decisions, PR state, design state |
| **Observability** | Datadog, Sentry, PagerDuty, Grafana | Error rates, latency, incident health, deploy outcomes |
| **Product analytics** | Amplitude, Mixpanel, PostHog | Feature adoption, funnel completion, retention cohorts |
| **Business goals** | OKR layer, roadmap docs, Notion/Confluence | Objectives, key results, initiatives — the 'why' layer |

## Cross-Signal Capabilities

These insights are impossible in any single tool today:

**Latency fix confirming a retention goal**: Datadog shows p95 latency dropped 180ms after PR #807. Amplitude shows D7 retention up 3.2% in the same cohort. Goal: Retention +15%. This work is measurably moving the number.

**Silent bug auto-detected from funnel drop**: Amplitude shows checkout completion dropped 8% starting Tuesday. Sentry shows a 340% spike in a checkout.js error. No ticket filed. Numen auto-surfaces a draft bug report.

**Feature shipped, near-zero adoption**: PostHog shows 'saved filters' (shipped 3 weeks ago) has 0.4% weekly active usage. The PM who specced it doesn't know. Numen surfaces this proactively.

**Bandwidth opening: PRD urgency alert**: Payments team has 3 tickets closing Friday, 0 incidents in 30 days. Phase 2 PRD is 80% complete, stale for 9 days. Surface to EM: 'Sofia should close the PRD by Thursday — team has capacity Monday.'

## The Role Map

Same context graph. Personalised view per role.

| Role | Their Question | What Numen Shows | Claude Can Do |
|---|---|---|---|
| **CTO** | Where does my attention create the most leverage? | Leverage map: bottlenecks, at-risk goals, cross-team gaps | Summarise RFC, draft goal status brief |
| **VP Engineering** | Which teams are healthy? | Team health: sprint state, incident rate, WIP load | Draft cross-team dependency brief |
| **VP Product** | Is the roadmap covering all goals? | Goal coverage map: goals with no owner, launch blockers | Draft scope recommendation |
| **Eng Manager** | Are my ICs unblocked? | IC blockers, stalled PRs, 1:1 prep | Prepare 1:1 brief, draft unblock message |
| **PM** | What decisions do engineers need from me? | Open decisions, funnel drops, spec gaps | Draft spec section, stakeholder update |
| **Engineer** | What is the most important thing to start on? | Prioritised briefing: PRs, bugs, unblocked tickets | Summarise PR diff, trace bug root cause |
| **Designer** | Are there conflicting requirements? | Conflicting specs, overdue reviews, handoffs ready | Brief PMs on conflict |

## Architecture (5 Layers)

| Layer | Name | Responsibility |
|---|---|---|
| L1 | Ingestion & Sync | Connect to source tools via OAuth/API. Pull incremental changes every 5 min. Normalise into canonical entities. |
| L2 | Context Graph | Property graph of entities (people, tasks, decisions, features, goals) and typed edges. Updated continuously. |
| L3 | Inference Engine | Score urgency per item per person. Detect anomalies and cross-signal correlations. Forecast capacity. |
| L4 | Briefing Generation | Compose personalised daily briefings per role. Rank by urgency. Annotate with goal connections. |
| L5 | Claude Dispatch | Grounded prompts to Claude API. Always returns drafts for human review. Never acts without approval. |

## V1 Scope (Phase 1)

- **Connectors**: Linear + GitHub + Slack (read-only)
- **Scoring**: Urgency formula with hardcoded weights
- **Briefings**: Daily email at 8am, Engineer + PM roles
- **Goals**: Manual input via web form
- **Claude dispatch**: Single action — summarize PR diff
- **Target**: 3 design partner companies, 5-10 users each
- **Success metric**: >40% open rate with click-through on 3 consecutive days

## Build Roadmap

| Phase | Weeks | Goal |
|---|---|---|
| 1. Validate the briefing | 1-6 | Linear + GitHub + Slack, daily email briefing, Engineer + PM |
| 2. Add observability | 7-14 | Datadog + Sentry + PagerDuty, anomaly detection, web app, EM + CTO roles |
| 3. Product analytics | 15-22 | Amplitude + PostHog, feature adoption, capacity forecasting, VP + Designer roles |
| 4. Write capabilities | 23-32 | Agentic dispatch with approval flow, write to GitHub/Linear/Slack, native goal tracking |

## Why Existing Tools Don't Solve This

The market is fragmented across disconnected layers. Each tool solves one layer and is blind to the others. No tool reasons across work management, observability, product analytics, and business goals simultaneously. Numen is the integration layer that connects all four and tells you what matters.
