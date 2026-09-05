# Two targets. `dev` runs the Vite dev server with hot reload for
# docker-compose.yml; `prod` builds static assets and serves them for
# docker-compose.prod.yml. Docker builds the last stage unless a target is
# named, so both compose files name theirs explicitly.

# ── dev ───────────────────────────────────────────────────────────────
FROM node:22-alpine AS dev

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ── build ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .

# Vite inlines VITE_* at build time, so the API URL has to be known here.
# Empty means "same origin", which is what the reverse proxy in front of a
# production deployment provides.
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
ARG VITE_MARKETING_SITE="false"
ENV VITE_MARKETING_SITE=$VITE_MARKETING_SITE

RUN npm run build

# ── prod ──────────────────────────────────────────────────────────────
FROM caddy:2-alpine AS prod

COPY --from=build /app/dist /srv
# A single-page app: unknown paths are client-side routes, not 404s.
RUN printf ':3000 {\n\troot * /srv\n\tencode gzip zstd\n\ttry_files {path} /index.html\n\tfile_server\n}\n' \
    > /etc/caddy/Caddyfile

EXPOSE 3000
