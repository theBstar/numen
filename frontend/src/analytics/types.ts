export type EventName =
  | "auth.login_started"
  | "auth.logged_in"
  | "auth.logged_out"
  | "page.viewed"
  | "briefing.viewed"
  | "task.created"
  | "task.status_changed"
  | "connector.connected"
  | "chat.message_sent"
  | "error.api_request_failed";

export type EventProperties = Record<string, string | number | boolean | null | undefined | string[]>;

export interface UserTraits {
  email?: string;
  role?: string;
  name?: string;
}

export interface GroupTraits {
  name?: string;
  is_demo?: boolean;
}

export interface TrackerProvider {
  init(): void;
  identify(memberId: string, traits: UserTraits): void;
  group(orgId: string, traits: GroupTraits): void;
  track(event: EventName, properties?: EventProperties): void;
  page(name?: string, properties?: EventProperties): void;
  reset(): void;
}
