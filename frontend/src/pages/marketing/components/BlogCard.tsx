import { Link } from "react-router-dom";

interface BlogCardProps {
  title: string;
  description: string;
  slug: string;
  publishDate: Date;
  tags: string[];
  readingTime: number;
}

export function BlogCard({ title, description, slug, publishDate, tags, readingTime }: BlogCardProps) {
  const displayDate = publishDate.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  return (
    <Link to={`/blog/${slug}`} className="group block">
      <article className="rounded-2xl border border-ws-500 bg-ws-700 p-6 transition-colors hover:border-brand/40 h-full flex flex-col">
        <div className="flex flex-wrap gap-1.5 mb-3">
          {tags.slice(0, 3).map((tag) => (
            <span key={tag} className="bg-brand-muted text-brand-light text-[10px] font-medium rounded-full px-2 py-0.5">
              {tag}
            </span>
          ))}
        </div>
        <h2 className="font-serif text-xl text-ws-50 leading-snug mb-2 group-hover:text-brand-light transition-colors">
          {title}
        </h2>
        <p className="text-xs text-ws-300 leading-relaxed mb-4 flex-1">
          {description}
        </p>
        <div className="flex items-center gap-2 text-[11px] text-ws-400">
          <span>{displayDate}</span>
          <span className="text-ws-500">&middot;</span>
          <span>{readingTime} min read</span>
        </div>
      </article>
    </Link>
  );
}
