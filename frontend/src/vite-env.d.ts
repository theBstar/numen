/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  /** "true" serves the numen.team landing page and blog from this build. */
  readonly VITE_MARKETING_SITE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
