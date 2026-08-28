import { useEffect, useRef, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { useOrgContext } from "@/contexts/OrgContext";
import { analytics } from "./index";

export function AnalyticsProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { orgId, orgName, memberId, memberEmail, role, isDemo } = useOrgContext();
  const lastIdentified = useRef<string | null>(null);
  const lastGrouped = useRef<string | null>(null);
  const lastPath = useRef<string | null>(null);

  useEffect(() => {
    analytics.init();
  }, []);

  useEffect(() => {
    analytics.setUserContext({ memberId, orgId, role, isDemo });

    if (memberId && memberId !== lastIdentified.current) {
      analytics.identify(memberId, { email: memberEmail, role });
      lastIdentified.current = memberId;
    }

    if (orgId && orgId !== lastGrouped.current) {
      analytics.group(orgId, { name: orgName, is_demo: isDemo });
      lastGrouped.current = orgId;
    }
  }, [memberId, memberEmail, orgId, orgName, role, isDemo]);

  useEffect(() => {
    const path = location.pathname + location.search;
    if (path === lastPath.current) return;
    lastPath.current = path;
    analytics.page(undefined, { path: location.pathname, referrer: document.referrer || null });
    analytics.track("page.viewed", { path: location.pathname });
  }, [location.pathname, location.search]);

  return <>{children}</>;
}
