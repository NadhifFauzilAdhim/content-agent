# --- web (Next.js) -----------------------------------------------------------
# The dashboard imports the Remotion compositions directly (the `@video/*` path alias points at
# services/media-engine/remotion/src), so the Player previews exactly the code that renders.
FROM node:22-alpine AS deps
WORKDIR /repo
COPY apps/web/package.json apps/web/package-lock.json ./apps/web/
RUN cd apps/web && npm ci

FROM node:22-alpine AS build
WORKDIR /repo
COPY --from=deps /repo/apps/web/node_modules ./apps/web/node_modules
COPY apps/web ./apps/web
# Composition sources shared with the renderer.
COPY services/media-engine/remotion/src ./services/media-engine/remotion/src
COPY services/media-engine/remotion/tsconfig.json ./services/media-engine/remotion/tsconfig.json
# The shared sources resolve react/remotion from their own directory, so the engine's packages go
# there too. Only what the compositions import is needed at build time — not the CLI, bundler or
# renderer — which keeps this layer small. Versions are pinned to match the engine's package.json.
COPY services/media-engine/remotion/package.json ./services/media-engine/remotion/package.json
RUN cd services/media-engine/remotion \
    && npm install --no-audit --no-fund --ignore-scripts --no-package-lock \
         remotion@4.0.541 @remotion/media@4.0.541 react@19.3.1 react-dom@19.3.1 \
    && npm install --no-audit --no-fund --ignore-scripts --no-package-lock --save-dev \
         @types/react@19.3.0 @types/react-dom@19.3.0 typescript@5.9.3
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN cd apps/web && npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=build /repo/apps/web/.next ./.next
COPY --from=build /repo/apps/web/public ./public
COPY --from=build /repo/apps/web/node_modules ./node_modules
COPY --from=build /repo/apps/web/package.json ./package.json
EXPOSE 3000
USER node
CMD ["npm", "start", "--", "-p", "3000"]
