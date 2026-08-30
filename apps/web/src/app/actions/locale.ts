"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";

import { LOCALE_COOKIE, isLocale, type Locale } from "@/lib/locale";

/**
 * Persist the reader's language and rebuild the tree in it.
 *
 * A Server Action rather than a client-side store because the pages that read this are
 * Server Components: the language has to be settled before the HTML exists. `revalidatePath`
 * with the `layout` scope is what makes the switch apply to the shell as well as the page —
 * without it the nav keeps the old language until the next hard navigation.
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
  revalidatePath("/", "layout");
}
