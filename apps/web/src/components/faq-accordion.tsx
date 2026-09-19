"use client";

/**
 * One FAQ open at a time — opening an item closes whichever one was open, rather than
 * letting them stack into a long scroll of answers.
 */

import { useState } from "react";

import { IconChevronDown } from "@/components/icons";

export type FaqItem = { q: string; a: string };

export function FaqAccordion({ items, qLabel, aLabel }: { items: FaqItem[]; qLabel: string; aLabel: string }) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  return (
    <div className="mt-10 space-y-3">
      {items.map(({ q, a }, index) => {
        const isOpen = openIndex === index;
        const panelId = `faq-panel-${index}`;

        return (
          <div key={q} className="panel !p-0">
            <button
              type="button"
              className="flex w-full items-center justify-between gap-4 px-6 py-5 text-left"
              aria-expanded={isOpen}
              aria-controls={panelId}
              onClick={() => setOpenIndex(isOpen ? null : index)}
            >
              <span className="title-panel text-[15px]">
                <span className="text-secondary">{qLabel}:</span> {q}
              </span>
              <IconChevronDown
                size={18}
                className={`shrink-0 text-muted-foreground transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
              />
            </button>
            {isOpen && (
              <p id={panelId} className="px-6 pb-5 text-sm leading-relaxed text-muted-foreground">
                <span className="font-medium text-secondary">{aLabel}:</span> {a}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
