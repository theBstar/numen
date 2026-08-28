import { Routes, Route, Navigate } from "react-router-dom";
import { HotkeysProvider } from "@tanstack/react-hotkeys";
import { Layout } from "@/components/Layout";
import { OnboardingModal } from "@/components/OnboardingModal";
import { Dashboard } from "@/pages/Dashboard";
import { People } from "@/pages/People";
import { PersonDetail } from "@/pages/PersonDetail";
import { EntityDetail } from "@/pages/EntityDetail";
import { Connections } from "@/pages/Connections";
import { ConnectorDetail } from "@/pages/ConnectorDetail";
import { Goals } from "@/pages/Goals";
import { GoalDetail } from "@/pages/GoalDetail";
import { Projects } from "@/pages/Projects";
import { ProjectDetail } from "@/pages/ProjectDetail";
import { Tasks } from "@/pages/Tasks";
import { TaskDetail } from "@/pages/TaskDetail";
import { Settings } from "@/pages/Settings";
import { AccountKeys } from "./pages/AccountKeys";
import { PrdProposals } from "./pages/PrdProposals";
import { McpSetup } from "@/pages/McpSetup";
import { Login } from "@/pages/Login";
import { AuthCallback } from "@/pages/AuthCallback";
import { ConnectorOAuthCallback } from "@/pages/ConnectorOAuthCallback";
import PersonResolutions from "@/pages/PersonResolutions";
import { ContextGraph } from "@/pages/ContextGraph";
import { Prds } from "@/pages/Prds";
import { LivingPrdView } from "@/pages/LivingPrdView";
import { LivingMacAuth } from "@/pages/LivingMacAuth";
import { Wiki } from "@/pages/Wiki";
import { Home } from "@/pages/marketing/Home";
import { BlogIndex } from "@/pages/marketing/BlogIndex";
import { BlogPost } from "@/pages/marketing/BlogPost";

/** numen.team serves the landing page and blog from this same build; a
 *  self-hosted deployment should not. Opt in with VITE_MARKETING_SITE=true. */
const MARKETING_SITE_ENABLED = import.meta.env.VITE_MARKETING_SITE === "true";

function AuthGuard({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem("numen_access_token");
  const needsOnboarding = localStorage.getItem("numen_needs_onboarding") === "true";

  if (!token) {
    const currentPath = window.location.pathname + window.location.search;
    if (currentPath !== "/dashboard" && currentPath !== "/login") {
      localStorage.setItem("numen_redirect_after_login", currentPath);
    }
    return <Navigate to="/login" replace />;
  }

  return (
    <>
      {children}
      {needsOnboarding && <OnboardingModal />}
    </>
  );
}

export default function App() {
  return (
    <HotkeysProvider>
      <Routes>
        {/* Marketing pages (public, no auth). Off unless VITE_MARKETING_SITE
            is enabled: a self-hosted install should land on its own app, not
            on the numen.team landing page. */}
        {MARKETING_SITE_ENABLED ? (
          <>
            <Route path="/" element={<Home />} />
            <Route path="/blog" element={<BlogIndex />} />
            <Route path="/blog/:slug" element={<BlogPost />} />
          </>
        ) : (
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
        )}

        {/* Auth pages */}
        <Route path="/login" element={<Login />} />
        <Route path="/auth/google/callback" element={<AuthCallback />} />
        <Route path="/connections/:connector/callback" element={<ConnectorOAuthCallback />} />

        {/* App pages (protected) */}
        <Route element={<AuthGuard><Layout /></AuthGuard>}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/briefings/:id" element={<Dashboard />} />
          <Route path="/people" element={<People />} />
          <Route path="/people/resolutions" element={<PersonResolutions />} />
          <Route path="/people/:id" element={<PersonDetail />} />
          <Route path="/entities/:id" element={<EntityDetail />} />
          <Route path="/connections" element={<Connections />} />
          <Route path="/connections/:connector" element={<ConnectorDetail />} />
          <Route path="/goals" element={<Goals />} />
          <Route path="/goals/:id" element={<GoalDetail />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/projects/:id" element={<ProjectDetail />} />
          <Route path="/prds" element={<Prds />} />
          <Route path="/prds/:id" element={<Prds />} />
          <Route path="/prd/:id" element={<LivingPrdView />} />
          <Route path="/auth/living-mac" element={<LivingMacAuth />} />
          <Route path="/wiki" element={<Wiki />} />
          <Route path="/wiki/features/:slug" element={<Wiki />} />
          <Route path="/wiki/concepts/:slug" element={<Wiki />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/tasks/:id" element={<TaskDetail />} />
          <Route path="/graph" element={<ContextGraph />} />
          <Route path="/mcp-setup" element={<McpSetup />} />
          <Route path="/account/keys" element={<AccountKeys />} />
          <Route path="/prd-proposals" element={<PrdProposals />} />
          <Route path="/prd-proposals/:id" element={<PrdProposals />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
      </Routes>
    </HotkeysProvider>
  );
}
