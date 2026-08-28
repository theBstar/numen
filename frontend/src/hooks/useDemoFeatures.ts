import { useOrgContext } from "@/contexts/OrgContext";

type FeatureMatrix =
  | "orgSwitching"
  | "roleSwitching"
  | "mockConnectorStatus"
  | "sampleBriefings"
  | "userViewSwitcher";

/**
 * Returns true if the given feature should be enabled.
 * Demo-only features are gated behind the current org's is_demo flag.
 */
export function useDemoFeatures(feature: FeatureMatrix): boolean {
  const { isDemo } = useOrgContext();

  switch (feature) {
    case "orgSwitching":
    case "roleSwitching":
    case "mockConnectorStatus":
    case "sampleBriefings":
    case "userViewSwitcher":
      return isDemo;
    default:
      return false;
  }
}
