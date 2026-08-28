import { Link } from "react-router-dom";

export function Footer() {
  return (
    <footer className="py-8 border-t border-ws-500/30">
      <div className="max-w-6xl mx-auto px-6 flex flex-col items-center gap-3">
        <span className="font-serif text-xl font-medium text-ws-50">numen</span>
        <span className="text-[11px] text-ws-300">The context graph for organisations.</span>
        <div className="flex items-center gap-4">
          <Link to="/blog" className="text-[11px] text-ws-300 hover:text-ws-50 transition-colors">Blog</Link>
        </div>
        <span className="text-[10px] text-ws-400">&copy; {new Date().getFullYear()} Numen. All rights reserved.</span>
      </div>
    </footer>
  );
}
