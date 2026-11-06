import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Tailwind v4 is applied by the Turbopack CSS plugin (no PostCSS config needed).
  turbopack: { rules: { "*.css": { loaders: ["@tailwindcss/turbopack"] } } },
  // All operational data is per-user and must never be cached or prefetched with stale data.
  cacheComponents: false,
  // Remotion compositions are shared verbatim with the renderer (services/media-engine/remotion),
  // so the in-dashboard Player previews exactly the code that will be rendered server-side.
  transpilePackages: ["remotion", "@remotion/player", "@remotion/media"],  experimental: {
    // Provider assets are served by the API (local storage or R2 in production).
    serverActions: { bodySizeLimit: "4mb" },
  },
};

export default nextConfig;
