import type { Metadata } from "next";
import { Fraunces, Inter_Tight, JetBrains_Mono } from "next/font/google";
import "./globals.css";

/*
 * Three families, three jobs, no overlap.
 *
 * Fraunces carries identity and quantity — titles and every number a human reads as a
 * fact. Inter Tight carries everything functional. JetBrains Mono is for strings that are
 * identifiers rather than words (registration numbers, packet IDs, hashes), where a lookalike
 * 0/O matters.
 *
 * Fraunces ships variable optical sizing; `font-optical-sizing: auto` in globals.css is what
 * keeps a 48px title and a 30px KPI value from looking like the same face scaled.
 */
const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  // No `weight`: that is what loads Fraunces as a variable font, which is the only way the
  // `opsz` axis — and therefore `font-optical-sizing` — has anything to act on.
  axes: ["SOFT", "WONK", "opsz"],
  display: "swap",
});

const interTight = Inter_Tight({
  variable: "--font-inter-tight",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "AgriVardhak",
  description: "AI decision & orchestration platform for farmer collectives",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${fraunces.variable} ${interTight.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="paper-noise flex min-h-full flex-col">{children}</body>
    </html>
  );
}
