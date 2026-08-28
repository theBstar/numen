import type { EventName, EventProperties, GroupTraits, TrackerProvider, UserTraits } from "../types";

export class ConsoleProvider implements TrackerProvider {
  init(): void {
    console.debug("[analytics] console provider initialized");
  }

  identify(memberId: string, traits: UserTraits): void {
    console.debug("[analytics] identify", memberId, traits);
  }

  group(orgId: string, traits: GroupTraits): void {
    console.debug("[analytics] group", orgId, traits);
  }

  track(event: EventName, properties?: EventProperties): void {
    console.debug("[analytics] track", event, properties ?? {});
  }

  page(name?: string, properties?: EventProperties): void {
    console.debug("[analytics] page", name ?? "", properties ?? {});
  }

  reset(): void {
    console.debug("[analytics] reset");
  }
}
