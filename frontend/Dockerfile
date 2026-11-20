FROM node:24-slim AS build
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN corepack pnpm install --frozen-lockfile
COPY next.config.ts postcss.config.mjs tsconfig.json next-env.d.ts ./
COPY src ./src
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXUS_ATENDE_STANDALONE=1 \
    NEXUS_ATENDE_API_URL=http://api:8000
RUN corepack pnpm build

FROM node:24-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
USER node
CMD ["node", "server.js"]
