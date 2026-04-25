# syntax=docker/dockerfile:1.9
# Build with: docker build -f apps/web/Dockerfile -t deployai/web:dev .
# (from repository root; Dockerfile needs the full workspace context to copy lockfile + workspace manifests)
#
# Story 1.7: honor the pnpm workspace graph. `apps/web` imports
# `@deployai/design-tokens/tailwind`, `@deployai/authz`, and `@deployai/shared-ui` (Epic 7+);
# shared-ui depends on `@deployai/contracts`. The deps stage copies all workspace
# manifests needed for `pnpm install --filter "@deployai/web..."`; the builder runs
# `pnpm turbo run build --filter=@deployai/web` so ^build (contracts, shared-ui, …) runs first.

FROM node:24-alpine AS base
ENV NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /repo

FROM base AS deps
COPY pnpm-lock.yaml package.json pnpm-workspace.yaml tsconfig.base.json turbo.json ./
COPY apps/web/package.json ./apps/web/
COPY packages/authz/package.json ./packages/authz/
COPY packages/design-tokens/package.json ./packages/design-tokens/
COPY packages/contracts/package.json ./packages/contracts/
COPY packages/shared-ui/package.json ./packages/shared-ui/
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile --filter "@deployai/web..."

FROM base AS builder
COPY --from=deps /repo/node_modules ./node_modules
COPY --from=deps /repo/apps/web/node_modules ./apps/web/node_modules
COPY --from=deps /repo/packages/authz/node_modules ./packages/authz/node_modules
COPY --from=deps /repo/packages/design-tokens/node_modules ./packages/design-tokens/node_modules
COPY --from=deps /repo/packages/contracts/node_modules ./packages/contracts/node_modules
COPY --from=deps /repo/packages/shared-ui/node_modules ./packages/shared-ui/node_modules
COPY pnpm-lock.yaml package.json pnpm-workspace.yaml tsconfig.base.json turbo.json ./
COPY packages/authz ./packages/authz
COPY packages/design-tokens ./packages/design-tokens
COPY packages/contracts ./packages/contracts
COPY packages/shared-ui ./packages/shared-ui
COPY apps/web ./apps/web
RUN pnpm turbo run build --filter=@deployai/web

FROM node:24-alpine AS runner
WORKDIR /app
RUN addgroup -S nextjs && adduser -S -G nextjs nextjs
COPY --from=builder --chown=nextjs:nextjs /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=nextjs:nextjs /repo/apps/web/public ./apps/web/public
USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0 NEXT_TELEMETRY_DISABLED=1
CMD ["node", "apps/web/server.js"]
