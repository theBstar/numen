import { Helmet } from "react-helmet-async";
import { useLocation } from "react-router-dom";
import { Navigation } from "./Navigation";
import { Footer } from "./Footer";

const SITE_URL = "https://www.numen.team";

const faqSchema = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: [
    {
      "@type": "Question",
      name: "What is a context graph?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "A context graph captures not just what things are, but how they connect, how decisions were made, and why. Unlike a knowledge graph which stores static entities and semantic relationships, a context graph carries temporal validity (when relationships were active), provenance (which system produced data), confidence scores (inferred vs confirmed), and decision traces (what the graph looked like when someone acted). These properties make it useful for AI reasoning, proactive surfacing, and organisational learning.",
      },
    },
    {
      "@type": "Question",
      name: "How is Numen different from a dashboard?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Dashboards show you data and wait for you to interpret it. Numen reads continuously across all your tools - Linear, GitHub, Slack, and more - and tells each person what to focus on, with the reasoning shown. It is proactive (you do not ask it questions), personalised (the same data surfaces differently per role), and goal-connected (every item is annotated with the business goal it connects to).",
      },
    },
    {
      "@type": "Question",
      name: "What tools does Numen connect to?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "In v1, Numen connects to Linear, GitHub, and Slack via read-only OAuth. The roadmap includes Datadog, Sentry, PagerDuty (observability), Amplitude, Mixpanel, PostHog (product analytics), Jira, Notion, Figma, and Confluence. Each connector maps to core entity types - adding a new tool means adding a connector, not changing the graph schema.",
      },
    },
    {
      "@type": "Question",
      name: "Is Numen read-only?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "In v1, yes. Numen reads from your tools and surfaces insights. Claude dispatch can generate drafts - PR summaries, briefing narratives, bug reports - but never acts on source systems without human approval. Every output is a draft for review. Write capabilities with an approval flow are planned for v2.",
      },
    },
    {
      "@type": "Question",
      name: "What is an MCP server and how does Numen use it?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Model Context Protocol (MCP) is a standard that lets AI coding agents query external systems for context. Numen exposes its context graph as an MCP server, so agents like Cursor, Claude Code, and Devin can ask questions like 'should I refactor or ship a quick fix?' and receive the team's sprint state, the goal's urgency, the module's incident history, and the org's historical tolerance for tech debt.",
      },
    },
    {
      "@type": "Question",
      name: "How does urgency scoring work in Numen?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Each item is scored per person, not globally. The same PR has a different urgency for its author, reviewer, and PM. Scoring components include: blocking others (30% weight), staleness in days (20%), downstream blocked count (10%), goal criticality (10%), recent mention count (8%), sprint membership (5%), precedent severity (10%), and historical response time (7%). The precedent components draw from the accumulated Decision entities - the institutional memory of how this specific org responds to similar patterns.",
      },
    },
  ],
};

const orgSchema = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "Numen",
  url: SITE_URL,
  logo: `${SITE_URL}/favicon.svg`,
  description: "The context graph for organisations. Numen connects engineering and product tools into a live graph and surfaces what matters to each person before they ask.",
  foundingDate: "2026",
};

const webSiteSchema = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: "Numen",
  url: SITE_URL,
  description: "The context graph for organisations. How organisations work, decide, and ship - captured in a live graph, surfaced before you ask.",
};

interface MarketingLayoutProps {
  children: React.ReactNode;
  title?: string;
  description?: string;
  ogType?: string;
  ogDescription?: string;
  articleDate?: string;
  articleModifiedDate?: string;
  noFaqSchema?: boolean;
  extraHead?: React.ReactNode;
}

export function MarketingLayout({
  children,
  title = "Numen - The Context Graph for Organisations",
  description = "Numen connects your engineering and product tools into a live context graph, then surfaces what matters to each person before they ask.",
  ogType = "website",
  ogDescription,
  articleDate,
  articleModifiedDate,
  noFaqSchema = false,
  extraHead,
}: MarketingLayoutProps) {
  const location = useLocation();
  const canonicalURL = `${SITE_URL}${location.pathname}`;
  const ogImage = `${SITE_URL}/og-image.png`;
  const displayOgDescription = ogDescription ?? "How organisations work, decide, and ship - captured in a live graph, surfaced before you ask.";
  const dateContent = articleDate ?? "2026-03-28";
  const lastModifiedContent = articleModifiedDate ?? articleDate ?? "2026-03-28";

  return (
    <div className="min-h-screen bg-ws-800 text-ws-200 [&_::selection]:bg-brand/20 [&_::selection]:text-ws-50">
      <Helmet>
        <title>{title}</title>
        <meta name="description" content={description} />
        <meta name="keywords" content="context graph, work intelligence, engineering intelligence, proactive work platform, daily briefings, urgency scoring, MCP server" />
        <link rel="canonical" href={canonicalURL} />

        {/* Open Graph */}
        <meta property="og:type" content={ogType} />
        <meta property="og:url" content={canonicalURL} />
        <meta property="og:title" content={title} />
        <meta property="og:description" content={displayOgDescription} />
        <meta property="og:image" content={ogImage} />
        <meta property="og:site_name" content="Numen" />
        {ogType === "article" && articleDate && (
          <meta property="article:published_time" content={articleDate} />
        )}
        {ogType === "article" && articleModifiedDate && (
          <meta property="article:modified_time" content={articleModifiedDate} />
        )}

        {/* Twitter Card */}
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content={title} />
        <meta name="twitter:description" content={displayOgDescription} />
        <meta name="twitter:image" content={ogImage} />

        {/* Freshness signals */}
        <meta name="date" content={dateContent} />
        <meta name="last-modified" content={lastModifiedContent} />

        {/* JSON-LD */}
        <script type="application/ld+json">{JSON.stringify(orgSchema)}</script>
        <script type="application/ld+json">{JSON.stringify(webSiteSchema)}</script>
        {!noFaqSchema && (
          <script type="application/ld+json">{JSON.stringify(faqSchema)}</script>
        )}
      </Helmet>
      {extraHead}
      <Navigation />
      <main>{children}</main>
      <Footer />
    </div>
  );
}
