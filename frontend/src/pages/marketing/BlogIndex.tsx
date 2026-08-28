import { Helmet } from "react-helmet-async";
import { MarketingLayout } from "./components/MarketingLayout";
import { BlogCard } from "./components/BlogCard";
import { blogPosts } from "@/content/blog";

const blogSchema = {
  "@context": "https://schema.org",
  "@type": "Blog",
  name: "Numen Blog",
  description: "Insights on context graphs, engineering intelligence, and the future of AI-powered organisational awareness.",
  url: "https://www.numen.team/blog/",
  publisher: {
    "@type": "Organization",
    name: "Numen",
    url: "https://www.numen.team",
  },
};

function getReadingTime(body: string): number {
  const words = body.split(/\s+/).length;
  return Math.max(1, Math.ceil(words / 200));
}

export function BlogIndex() {
  const posts = blogPosts.filter((p) => !p.draft);

  return (
    <MarketingLayout
      title="Blog - Numen"
      description="Insights on context graphs, engineering intelligence, and the future of AI-powered organisational awareness."
      noFaqSchema
      extraHead={
        <Helmet>
          <script type="application/ld+json">{JSON.stringify(blogSchema)}</script>
        </Helmet>
      }
    >
      <div className="pt-32 pb-16">
        <div className="max-w-6xl mx-auto px-6">
          <div className="mb-12">
            <h1 className="font-serif text-3xl sm:text-4xl font-normal text-ws-50 mb-3">
              Blog
            </h1>
            <p className="text-sm text-ws-300 max-w-xl">
              Context graphs, engineering intelligence, and how organisations can surface what matters before anyone asks.
            </p>
          </div>

          {posts.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {posts.map((post) => (
                <BlogCard
                  key={post.slug}
                  title={post.title}
                  description={post.description}
                  slug={post.slug}
                  publishDate={post.publishDate}
                  tags={post.tags}
                  readingTime={getReadingTime(post.body)}
                />
              ))}
            </div>
          ) : (
            <p className="text-ws-400 text-sm">No articles yet. Check back soon.</p>
          )}
        </div>
      </div>
    </MarketingLayout>
  );
}
