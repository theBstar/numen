import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { startGoogleLogin } from "@/services/googleLogin";

export function Navigation() {
  const navRef = useRef<HTMLElement>(null);
  const [loading, setLoading] = useState(false);

  async function onLogin() {
    setLoading(true);
    try {
      await startGoogleLogin();
    } catch {
      setLoading(false);
    }
  }

  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    const onScroll = () => {
      if (window.scrollY > 40) {
        nav.classList.add("bg-ws-800/90", "backdrop-blur-lg", "border-b", "border-ws-500/30");
      } else {
        nav.classList.remove("bg-ws-800/90", "backdrop-blur-lg", "border-b", "border-ws-500/30");
      }
    };
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <nav ref={navRef} className="fixed top-0 left-0 right-0 z-50 transition-all duration-300">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link to="/" className="font-serif text-2xl font-medium text-ws-50 tracking-tight">
          numen
        </Link>
        <div className="flex items-center gap-6">
          <Link to="/blog" className="text-xs font-medium text-ws-200 hover:text-ws-50 transition-colors">
            Blog
          </Link>
          <button
            type="button"
            onClick={onLogin}
            disabled={loading}
            className="px-5 py-2 bg-brand text-white text-xs font-medium rounded-full transition-colors hover:bg-brand-dark disabled:opacity-60"
          >
            {loading ? "Signing in..." : "Login"}
          </button>
        </div>
      </div>
    </nav>
  );
}
