"use client";

import { useState } from "react";

import { translator } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

const WEB3FORMS_ENDPOINT = "https://api.web3forms.com/submit";

type Status = "idle" | "sending" | "success" | "error";

export function FooterFeedbackForm({ locale }: { locale: Locale }) {
  const t = translator(locale);
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<Status>("idle");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setStatus("sending");
    try {
      const res = await fetch(WEB3FORMS_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          access_key: process.env.NEXT_PUBLIC_WEB3FORMS_KEY,
          subject: "New suggestion from the AgriVardhak footer",
          from_name: "AgriVardhak footer form",
          email,
          message,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || body.success === false) throw new Error(body.message ?? "submit failed");
      setStatus("success");
      setEmail("");
      setMessage("");
    } catch {
      setStatus("error");
    }
  }

  const field =
    "w-full rounded-md border border-footer-border/60 bg-footer-foreground/5 px-3 py-2.5 text-sm text-footer-foreground placeholder:text-footer-muted/60 transition-colors focus:border-footer-muted/60 focus:outline-none";

  return (
    <form onSubmit={submit} className="space-y-2.5">
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder={t("footer.feedbackEmailPlaceholder")}
        required
        className={field}
      />
      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder={t("footer.feedbackMessagePlaceholder")}
        required
        rows={3}
        className={`${field} resize-none`}
      />
      <button
        type="submit"
        disabled={status === "sending"}
        className="rounded-md border border-footer-border/60 px-4 py-2 text-xs text-footer-foreground transition-colors hover:bg-footer-foreground/5 disabled:opacity-60"
      >
        {status === "sending" ? t("footer.feedbackSending") : t("footer.feedbackSubmit")}
      </button>
      {status === "success" && (
        <p role="status" className="text-xs text-footer-foreground/85">
          {t("footer.feedbackSuccess")}
        </p>
      )}
      {status === "error" && (
        <p role="alert" className="text-xs text-destructive">
          {t("footer.feedbackError")}
        </p>
      )}
    </form>
  );
}
