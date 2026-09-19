/**
 * Shared Open Graph image for every route that doesn't define its own — inherited by
 * `/privacy` and `/faq` automatically. Generated from code rather than a design tool since
 * no logo/hero image asset exists anywhere in the repo.
 *
 * Colors are hard-coded literals, not the `--primary`/`--accent` CSS custom properties from
 * globals.css: Satori (the renderer behind `ImageResponse`) cannot resolve `var(--x)`, so the
 * values are copied here by hand — keep them in sync with globals.css if the palette changes.
 */

import { ImageResponse } from "next/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "AgriVardhak — decision support for FPOs";

const FOREST = "#1A3826";
const PAPER = "#F9F9F6";
const GOLD = "#C7A03D";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "80px",
          backgroundColor: PAPER,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <div
            style={{
              width: 88,
              height: 88,
              borderRadius: 16,
              backgroundColor: FOREST,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <div style={{ width: 36, height: 36, borderRadius: "50%", backgroundColor: GOLD }} />
          </div>
          <span style={{ fontSize: 40, color: FOREST, fontWeight: 500 }}>AgriVardhak</span>
        </div>
        <div
          style={{
            display: "flex",
            marginTop: 48,
            fontSize: 52,
            lineHeight: 1.15,
            color: FOREST,
            maxWidth: 980,
          }}
        >
          Sustainable farmer income, one approved decision at a time.
        </div>
      </div>
    ),
    { ...size },
  );
}
