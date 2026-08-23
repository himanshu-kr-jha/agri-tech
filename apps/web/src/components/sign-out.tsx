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
      className="rounded-md px-2 py-1 text-xs text-neutral-500 ring-1 ring-inset ring-neutral-300 hover:bg-neutral-100 disabled:opacity-50 dark:ring-neutral-700 dark:hover:bg-neutral-800"
    >
      {pending ? "…" : "Sign out"}
    </button>
  );
}
