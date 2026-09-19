/**
 * Deliberately the inverse of a growth site's robots.txt: only the handful of public pages
 * are crawlable. Everything else is a login-gated console — indexing those URLs would just
 * advertise paths that 403/redirect for anonymous crawlers.
 */

import type { MetadataRoute } from "next";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://agri-tech-gold.vercel.app";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: ["/$", "/login", "/privacy", "/faq", "/about", "/terms"],
      disallow: "/",
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
