import { ConsoleProvider } from "./providers/console";
import { MultiProvider } from "./providers/multi";
import { PostHogProvider } from "./providers/posthog";
import type { EventName, EventProperties, GroupTraits, TrackerProvider, UserTraits } from "./types";

type ReservedProps = {
  org_id?: string;
  member_id?: string;
  role?: string;
  is_demo?: boolean;
  source: "web";
  environment: string;
};

function buildProviders(): TrackerProvider[] {
  const raw: string = (import.meta.env.VITE_ANALYTICS_PROVIDERS as string | undefined) || "console";
  const names = raw
    .split(",")
    .map((s: string) => s.trim().toLowerCase())
    .filter(Boolean);

  const providers: TrackerProvider[] = [];
  for (const name of names) {
    if (name === "console") {
      providers.push(new ConsoleProvider());
    } else if (name === "posthog") {
      const key = import.meta.env.VITE_POSTHOG_KEY || "";
      const host = import.meta.env.VITE_POSTHOG_HOST || "https://us.i.posthog.com";
      providers.push(new PostHogProvider(key, host));
    } else {
      console.warn(`[analytics] unknown provider '${name}' (ignored)`);
    }
  }
  if (providers.length === 0) providers.push(new ConsoleProvider());
  return providers;
}

class Analytics {
  private provider: TrackerProvider;
  private initialized = false;
  private context: Partial<ReservedProps> = {
    source: "web",
    environment: import.meta.env.MODE,
  };

  constructor() {
    this.provider = new MultiProvider(buildProviders());
  }

  init(): void {
    if (this.initialized) return;
    this.initialized = true;
    this.provider.init();
  }

  setUserContext(context: { memberId?: string; orgId?: string; role?: string; isDemo?: boolean }): void {
    if (context.memberId !== undefined) this.context.member_id = context.memberId || undefined;
    if (context.orgId !== undefined) this.context.org_id = context.orgId || undefined;
    if (context.role !== undefined) this.context.role = context.role || undefined;
    if (context.isDemo !== undefined) this.context.is_demo = context.isDemo;
  }

  identify(memberId: string, traits: UserTraits): void {
    if (!memberId) return;
    this.provider.identify(memberId, traits);
  }

  group(orgId: string, traits: GroupTraits): void {
    if (!orgId) return;
    this.provider.group(orgId, traits);
  }

  track(event: EventName, properties?: EventProperties): void {
    const merged = { ...this.context, ...(properties ?? {}) };
    this.provider.track(event, merged);
  }

  page(name?: string, properties?: EventProperties): void {
    const merged = { ...this.context, ...(properties ?? {}) };
    this.provider.page(name, merged);
  }

  reset(): void {
    this.context = {
      source: "web",
      environment: import.meta.env.MODE,
    };
    this.provider.reset();
  }
}

export const analytics = new Analytics();
export type { EventName, EventProperties, GroupTraits, UserTraits };
