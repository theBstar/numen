import { MarketingLayout } from "./components/MarketingLayout";
import { Hero } from "./components/Hero";
import { Problem } from "./components/Problem";
import { PersonaViews } from "./components/PersonaViews";
import { Features } from "./components/Features";
import { FAQ } from "./components/FAQ";

export function Home() {
  return (
    <MarketingLayout>
      <Hero />
      <Problem />
      <PersonaViews />
      <Features />
      <FAQ />
    </MarketingLayout>
  );
}
