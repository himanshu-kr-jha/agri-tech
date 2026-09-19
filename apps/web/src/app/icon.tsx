/**
 * Branded favicon, generated the same way as opengraph-image.tsx — see that file for why
 * colors are hard-coded literals instead of CSS custom properties.
 */

import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

const FOREST = "#1A3826";
const GOLD = "#C7A03D";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: FOREST,
          borderRadius: 6,
        }}
      >
        <div style={{ width: 14, height: 14, borderRadius: "50%", backgroundColor: GOLD }} />
      </div>
    ),
    { ...size },
  );
}
