import type { EventName, EventProperties, GroupTraits, TrackerProvider, UserTraits } from "../types";

interface PostHogLike {
  init(key: string, config: Record<string, unknown>): void;
  identify(memberId: string, traits: Record<string, unknown>): void;
  group(type: string, id: string, traits: Record<string, unknown>): void;
  capture(event: string, properties?: Record<string, unknown>): void;
  reset(): void;
}

export class PostHogProvider implements TrackerProvider {
  private apiKey: string;
  private host: string;
  private client: PostHogLike | null = null;
  private ready = false;

  constructor(apiKey: string, host: string) {
    this.apiKey = apiKey;
    this.host = host;
  }

  init(): void {
    if (!this.apiKey) return;
    // Dynamic import keeps posthog-js out of the initial bundle if unused.
    import("posthog-js")
      .then((mod) => {
        const posthog = mod.default as unknown as PostHogLike;
        posthog.init(this.apiKey, {
          api_host: this.host,
          capture_pageview: false,
          persistence: "localStorage",
        });
        this.client = posthog;
        this.ready = true;
      })
      .catch((e: unknown) => {
        console.warn("[analytics] posthog-js failed to load", e);
      });
  }

  identify(memberId: string, traits: UserTraits): void {
    if (!this.ready || !this.client) return;
    try {
      this.client.identify(memberId, traits as Record<string, unknown>);
    } catch (e) {
      console.warn("[analytics] posthog identify failed", e);
    }
  }

  group(orgId: string, traits: GroupTraits): void {
    if (!this.ready || !this.client) return;
    try {
      this.client.group("organization", orgId, traits as Record<string, unknown>);
    } catch (e) {
      console.warn("[analytics] posthog group failed", e);
    }
  }

  track(event: EventName, properties?: EventProperties): void {
    if (!this.ready || !this.client) return;
    try {
      this.client.capture(event, properties as Record<string, unknown> | undefined);
    } catch (e) {
      console.warn("[analytics] posthog track failed", e);
    }
  }

  page(name?: string, properties?: EventProperties): void {
    if (!this.ready || !this.client) return;
    try {
      this.client.capture("$pageview", {
        $current_url: window.location.href,
        name,
        ...(properties as Record<string, unknown> | undefined),
      });
    } catch (e) {
      console.warn("[analytics] posthog page failed", e);
    }
  }

  reset(): void {
    if (!this.ready || !this.client) return;
    try {
      this.client.reset();
    } catch (e) {
      console.warn("[analytics] posthog reset failed", e);
    }
  }
}
