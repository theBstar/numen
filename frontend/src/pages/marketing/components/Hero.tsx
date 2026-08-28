import { useState } from "react";
import { HeroBrief } from "./HeroBrief";
import { startGoogleLogin } from "@/services/googleLogin";

export function Hero() {
  const [loading, setLoading] = useState(false);

  async function onLogin() {
    setLoading(true);
    try {
      await startGoogleLogin();
    } catch {
      setLoading(false);
    }
  }

  return (
    <section id="hero" className="pt-20 pb-0">
      <div className="max-w-6xl mx-auto px-6 py-8 sm:py-16">
        {/* Badge */}
        <div className="inline-flex items-center px-4 py-1.5 rounded-full border border-ws-400 mb-6">
          <span className="text-[9px] font-medium text-brand-light tracking-[2px] uppercase">Now onboarding design partners</span>
        </div>

        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-start">
          {/* Left: Copy */}
          <div>
            <h1 className="font-serif text-4xl sm:text-5xl lg:text-[56px] font-normal text-ws-50 leading-[1.05] tracking-tight">
              Know what needs your attention before standup
            </h1>
            <p className="mt-6 text-base sm:text-lg text-ws-200 leading-relaxed max-w-lg">
              Numen connects across Linear, GitHub, Slack, Datadog, and Amplitude and surfaces a personalized daily brief of what matters most - for every person on your engineering team.
            </p>
            <div className="mt-8">
              <button
                type="button"
                onClick={onLogin}
                disabled={loading}
                className="inline-flex items-center justify-center px-6 py-3 bg-brand text-white text-sm font-medium rounded-full transition-colors hover:bg-brand-dark disabled:opacity-60"
              >
                {loading ? "Signing in..." : "Login"}
              </button>
            </div>
            <p className="mt-3 text-[11px] text-ws-300">
              Free for teams under 20. No credit card required.
            </p>
          </div>

          {/* Right: Auto-rotating briefing per role */}
          <HeroBrief />
        </div>
      </div>

      {/* Trust strip */}
      <div className="bg-ws-700 py-6 mt-8 px-6">
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 sm:gap-8">
          <span className="text-[9px] font-medium text-ws-300 tracking-[3px] uppercase">Built for fast-moving teams</span>
          <span className="hidden sm:block text-ws-500">|</span>
          <div className="flex flex-wrap items-center justify-center gap-4 sm:gap-8">
            <span className="flex items-center gap-2 text-xs font-medium text-ws-300"><span className="text-brand-light">&#9672;</span> Immediate value</span>
            <span className="flex items-center gap-2 text-xs font-medium text-ws-300"><span className="text-brand-light">&#9672;</span> 10+ integrations</span>
            <span className="flex items-center gap-2 text-xs font-medium text-ws-300"><span className="text-brand-light">&#9672;</span> Cross-team visibility</span>
          </div>
        </div>
      </div>
    </section>
  );
}
