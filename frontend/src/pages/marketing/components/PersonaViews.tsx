import { PersonaCarousel } from "./PersonaCarousel";

export function PersonaViews() {
  return (
    <section id="personas" className="py-16 sm:py-24 bg-ws-700">
      <div className="max-w-3xl mx-auto px-6">
        <h2 className="font-serif text-3xl sm:text-4xl font-normal text-ws-50 leading-tight">
          One graph. Every role's view.
        </h2>
        <p className="mt-4 text-sm sm:text-base text-ws-200 leading-relaxed max-w-lg">
          The same context graph surfaces different insights per role. A CTO sees goal risk and cross-team blockers. An engineer sees their prioritised queue. Switch tabs to see each view.
        </p>

        <div className="mt-8">
          <PersonaCarousel />
        </div>
      </div>
    </section>
  );
}
