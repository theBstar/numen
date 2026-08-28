import { useParams, Link, Navigate } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import Markdown from "react-markdown";
import { MarketingLayout } from "./components/MarketingLayout";
import { blogPosts } from "@/content/blog";

function getReadingTime(body: string): number {
  const words = body.split(/\s+/).length;
  return Math.max(1, Math.ceil(words / 200));
}

export function BlogPost() {
  const { slug } = useParams<{ slug: string }>();
  const post = blogPosts.find((p) => p.slug === slug && !p.draft);

  if (!post) {
    return <Navigate to="/blog" replace />;
  }

  const dateStr = post.publishDate.toISOString().split("T")[0];
  const updatedStr = post.updatedDate?.toISOString().split("T")[0];
  const displayDate = post.publishDate.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  const readingTime = getReadingTime(post.body);
  const canonicalURL = `https://www.numen.team/blog/${post.slug}/`;

  const blogPostingSchema = {
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    headline: post.title,
    description: post.description,
    datePublished: post.publishDate.toISOString(),
    dateModified: (post.updatedDate ?? post.publishDate).toISOString(),
    author: {
      "@type": "Organization",
      name: "Numen",
      url: "https://www.numen.team",
    },
    publisher: {
      "@type": "Organization",
      name: "Numen",
      url: "https://www.numen.team",
      logo: "https://www.numen.team/favicon.svg",
    },
    mainEntityOfPage: canonicalURL,
    keywords: post.tags,
  };

  return (
    <MarketingLayout
      title={`${post.title} - Numen Blog`}
      description={post.description}
      ogType="article"
      ogDescription={post.description}
      articleDate={dateStr}
      articleModifiedDate={updatedStr ?? dateStr}
      noFaqSchema
      extraHead={
        <Helmet>
          <meta property="article:tag" content={post.tags.join(", ")} />
          <script type="application/ld+json">{JSON.stringify(blogPostingSchema)}</script>
        </Helmet>
      }
    >
      <div className="pt-32 pb-16">
        <article className="max-w-3xl mx-auto px-6">
          {/* Article header */}
          <header className="mb-12">
            <div className="flex flex-wrap items-center gap-2 mb-4">
              {post.tags.map((tag) => (
                <span key={tag} className="bg-brand-muted text-brand-light text-[10px] font-medium rounded-full px-2.5 py-0.5">
                  {tag}
                </span>
              ))}
            </div>
            <h1 className="font-serif text-3xl sm:text-4xl lg:text-5xl font-normal text-ws-50 leading-tight mb-4">
              {post.title}
            </h1>
            <p className="text-sm text-ws-300 mb-2">{post.description}</p>
            <div className="flex items-center gap-3 text-[11px] text-ws-400 mt-4">
              <span>{displayDate}</span>
              <span className="text-ws-500">&middot;</span>
              <span>{readingTime} min read</span>
              <span className="text-ws-500">&middot;</span>
              <span>{post.author}</span>
            </div>
          </header>

          {/* Article body */}
          <div className="ws-prose">
            <Markdown>{post.body}</Markdown>
          </div>
        </article>

        {/* CTA */}
        <div className="max-w-3xl mx-auto px-6 mt-16 pt-12 border-t border-ws-500/30">
          <div className="text-center">
            <p className="font-serif text-xl sm:text-2xl text-ws-50 mb-2">
              See context graphs in action.
            </p>
            <p className="text-xs text-ws-300 mb-6">
              Numen builds a live context graph from your engineering and product tools.
            </p>
            <Link
              to="/login"
              className="inline-block px-6 py-2.5 bg-brand text-white text-xs font-medium rounded-full transition-colors hover:bg-brand-dark"
            >
              Get Started
            </Link>
          </div>
        </div>

        {/* Back to blog */}
        <div className="max-w-3xl mx-auto px-6 mt-12">
          <Link
            to="/blog"
            className="text-xs text-ws-400 hover:text-ws-200 transition-colors"
          >
            &larr; All articles
          </Link>
        </div>
      </div>
    </MarketingLayout>
  );
}
