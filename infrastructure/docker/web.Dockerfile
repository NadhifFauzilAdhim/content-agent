# --- web (Next.js standalone) ------------------------------------------------
FROM node:22-alpine AS deps
WORKDIR /repo
COPY apps/web/package.json apps/web/package-lock.json ./apps/web/
RUN cd apps/web && npm ci

FROM node:22-alpine AS build
WORKDIR /repo
COPY --from=deps /repo/apps/web/node_modules ./apps/web/node_modules
COPY apps/web ./apps/web
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN cd apps/web && npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /repo/apps/web/.next ./.next
COPY --from=build /repo/apps/web/public ./public
COPY --from=build /repo/apps/web/node_modules ./node_modules
COPY --from=build /repo/apps/web/package.json ./package.json
EXPOSE 3000
USER node
CMD ["npm", "start", "--", "-p", "3000"]
