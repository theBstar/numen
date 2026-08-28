import { useState } from "react";
import { useParams, useLocation } from "react-router-dom";
import { Loader2 } from "lucide-react";
import {
  useWikiLanding,
  useWikiFeature,
  useWikiConcept,
  useGenerateWiki,
  useUpdateWikiFeature,
} from "@/hooks/wikiQueries";
import { ThreeColumnLayout } from "@/components/layouts/ThreeColumnLayout";
import { WikiFeatureSidebar } from "@/components/wiki/WikiFeatureSidebar";
import { WikiLanding } from "@/components/wiki/WikiLanding";
import { WikiFeatureDetail } from "@/components/wiki/WikiFeatureDetail";
import { WikiConceptDetail } from "@/components/wiki/WikiConceptDetail";
import { WikiStatsPanel } from "@/components/wiki/WikiStatsPanel";

type ContentMode = "landing" | "feature" | "concept";

function useContentMode(): { mode: ContentMode; slug?: string } {
  const location = useLocation();
  const params = useParams<{ slug: string }>();

  if (location.pathname.includes("/wiki/features/") && params.slug) {
    return { mode: "feature", slug: params.slug };
  }
  if (location.pathname.includes("/wiki/concepts/") && params.slug) {
    return { mode: "concept", slug: params.slug };
  }
  return { mode: "landing" };
}

export function Wiki() {
  const { mode, slug } = useContentMode();
  const [search, setSearch] = useState("");

  // Queries
  const { data: landing, isLoading: landingLoading } = useWikiLanding();
  const { data: featureDetail, isLoading: featureLoading } = useWikiFeature(
    mode === "feature" ? slug : undefined,
  );
  const { data: conceptDetail, isLoading: conceptLoading } = useWikiConcept(
    mode === "concept" ? slug : undefined,
  );

  // Mutations
  const generateWiki = useGenerateWiki();
  const updateFeature = useUpdateWikiFeature();

  const features = landing?.features ?? [];

  // Left sidebar
  const sidebar = (
    <WikiFeatureSidebar
      features={features}
      search={search}
      onSearchChange={setSearch}
    />
  );

  // Main content
  let mainContent: React.ReactNode;

  if (mode === "landing") {
    if (landingLoading) {
      mainContent = (
        <div className="flex items-center justify-center py-16 text-surface-400">
          <Loader2 size={20} className="animate-spin mr-2" />
          <span className="text-sm">Loading wiki...</span>
        </div>
      );
    } else {
      mainContent = (
        <WikiLanding
          summary={landing?.summary ?? { summary: "", feature_count: 0, prd_count: 0, generated_at: null }}
          features={features}
          stats={landing?.stats ?? { total_features: 0, active: 0, planned: 0, manual_edits: 0, concept_count: 0 }}
          isGenerating={generateWiki.isPending}
          onGenerate={() => generateWiki.mutate()}
        />
      );
    }
  } else if (mode === "feature") {
    if (featureLoading) {
      mainContent = (
        <div className="flex items-center justify-center py-16 text-surface-400">
          <Loader2 size={20} className="animate-spin mr-2" />
          <span className="text-sm">Loading feature...</span>
        </div>
      );
    } else if (featureDetail) {
      mainContent = (
        <WikiFeatureDetail
          feature={featureDetail}
          onUpdate={(data) => {
            if (slug) {
              updateFeature.mutate({ slug, data });
            }
          }}
          isUpdating={updateFeature.isPending}
        />
      );
    } else {
      mainContent = (
        <div className="flex items-center justify-center py-16 text-surface-400">
          <span className="text-sm">Feature not found</span>
        </div>
      );
    }
  } else if (mode === "concept") {
    if (conceptLoading) {
      mainContent = (
        <div className="flex items-center justify-center py-16 text-surface-400">
          <Loader2 size={20} className="animate-spin mr-2" />
          <span className="text-sm">Loading concept...</span>
        </div>
      );
    } else if (conceptDetail) {
      mainContent = <WikiConceptDetail concept={conceptDetail} />;
    } else {
      mainContent = (
        <div className="flex items-center justify-center py-16 text-surface-400">
          <span className="text-sm">Concept not found</span>
        </div>
      );
    }
  }

  // Right panel
  const rightPanel = landing ? (
    <WikiStatsPanel stats={landing.stats} />
  ) : null;

  return (
    <ThreeColumnLayout
      sidebar={sidebar}
      rightPanel={rightPanel}
    >
      {mainContent}
    </ThreeColumnLayout>
  );
}
