import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { OrgProvider } from "@/contexts/OrgContext";
import { AnalyticsProvider } from "@/analytics/AnalyticsProvider";
import { setAccessToken } from "@/services/api";
import App from "./App";
import "./index.css";

// Restore JWT token from localStorage before any component mounts
const savedToken = localStorage.getItem("numen_access_token");
if (savedToken) setAccessToken(savedToken);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});

const root = document.getElementById("root");
if (!root) throw new Error("Root element not found");

createRoot(root).render(
  <StrictMode>
    <HelmetProvider>
      <QueryClientProvider client={queryClient}>
        <OrgProvider>
          <BrowserRouter>
            <AnalyticsProvider>
              <App />
            </AnalyticsProvider>
          </BrowserRouter>
        </OrgProvider>
      </QueryClientProvider>
    </HelmetProvider>
  </StrictMode>,
);
