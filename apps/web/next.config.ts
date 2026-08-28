import type { NextConfig } from "next";

// Next.js 16 blocks cross-origin requests to the dev server (static chunks, HMR
// websocket) unless the requesting origin is listed here. Prefer opening
// http://localhost:3000 — that always works with no config. If you need to reach
// the dev server from another device on your LAN (e.g. testing on a phone), set
// DEV_ALLOWED_ORIGINS in apps/web/.env.local (gitignored, per-developer) to a
// comma-separated list of hostnames/IPs, e.g. DEV_ALLOWED_ORIGINS=192.168.0.121
const nextConfig: NextConfig = {
  /* config options here */
  reactCompiler: true,
  allowedDevOrigins: process.env.DEV_ALLOWED_ORIGINS?.split(",")
    .map((origin) => origin.trim())
    .filter(Boolean),
};

export default nextConfig;
