import type { EventName, EventProperties, GroupTraits, TrackerProvider, UserTraits } from "../types";

export class MultiProvider implements TrackerProvider {
  constructor(private providers: TrackerProvider[]) {}

  private run(fn: (p: TrackerProvider) => void): void {
    for (const p of this.providers) {
      try {
        fn(p);
      } catch (e) {
        console.warn("[analytics] provider error (swallowed)", e);
      }
    }
  }

  init(): void {
    this.run((p) => p.init());
  }

  identify(memberId: string, traits: UserTraits): void {
    this.run((p) => p.identify(memberId, traits));
  }

  group(orgId: string, traits: GroupTraits): void {
    this.run((p) => p.group(orgId, traits));
  }

  track(event: EventName, properties?: EventProperties): void {
    this.run((p) => p.track(event, properties));
  }

  page(name?: string, properties?: EventProperties): void {
    this.run((p) => p.page(name, properties));
  }

  reset(): void {
    this.run((p) => p.reset());
  }
}
