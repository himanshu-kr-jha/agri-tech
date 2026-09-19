/**
 * The public shell — ADR-0024.
 *
 * Everything readable without an account lives in this group: the landing page, About us,
 * the FAQ, Privacy, Terms and the sign-in screen. The group has no guard, which is the
 * whole point of it — and the guard must stay out. `/login` is in here, so a `currentUser()`
 * redirect at this level would bounce a signed-in visitor off the very page they were sent
 * to. The two pages that do redirect (`page.tsx` and `login/page.tsx`) each do it themselves.
 *
 * This layout owns three things the six pages used to each own a copy of: the header, the
 * `flex min-h-screen flex-col` column, and the `Footer`.
 *
 * That column is not stylistic. `Footer` escapes its container with
 * `left-1/2 / -translate-x-1/2 / w-screen` to run its green edge to edge, and that only
 * resolves when its parent is itself viewport-width — here, a direct child of
 * `<body className="paper-noise flex min-h-full flex-col">`. The footer also carries
 * `flex-1` so it, rather than the content, absorbs the slack on a short page. Wrapping
 * `{children}` in a centred max-width container would break both. Sections set their own
 * width; the column stays full-bleed.
 */

import { Footer } from "@/components/footer";
import { PublicHeader } from "@/components/public-header";

export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <PublicHeader />
      {children}
      <Footer />
    </div>
  );
}
