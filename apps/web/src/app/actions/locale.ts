"use server";

import { cookies } from "next/headers";

import { LOCALE_COOKIE, isLocale, type Locale } from "@/lib/locale";

/**
 * Persist the reader's language for the next server render.
 *
 * Deliberately no `revalidatePath`. The page on screen is translated in place by the page
 * translator (ADR-0023); rebuilding the tree on the server as well would race it, and React
 * would write the server's text over the translation mid-switch. The cookie matters on the
 * next reload or navigation, where it lets static text arrive already in the right language.
 */
export async function setLocale(next: Locale): Promise<void> {
  if (!isLocale(next)) return;
  const jar = await cookies();
  jar.set(LOCALE_COOKIE, next, {
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
    sameSite: "lax",
    httpOnly: false,
  });
}
