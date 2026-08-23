"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

export function SignOutButton() {
  const router = useRouter();
  const [pending, start] = useTransition();

  return (
    <button
      onClick={() =>
        start(async () => {
          await fetch("/api/auth/logout", { method: "POST" });
          router.replace("/login");
          router.refresh();
        })
      }
      disabled={pending}
      className="rounded-md border border-border/70 px-2.5 py-1 text-[11px] uppercase tracking-[0.14em] text-muted-foreground transition-colors hover:border-primary/30 hover:text-foreground disabled:opacity-50"
    >
      {pending ? "…" : "Sign out"}
    </button>
  );
}
