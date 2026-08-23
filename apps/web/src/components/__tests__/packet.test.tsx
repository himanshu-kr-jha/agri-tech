/**
 * The packet renderer, against **partly arrived** packets.
 *
 * These tests exist because of a bug that reached the browser and could not have been caught
 * anywhere else. Sections stream in one at a time and the component re-renders after every
 * frame, so on the first render it holds `situation` and nothing else. Treating the input as
 * a complete Packet threw `Cannot read properties of undefined (reading 'map')` and left the
 * page blank.
 *
 * It was invisible to everything already in place: the API test asserted the sections stream
 * in order, and a script that accumulated every frame before rendering parsed them perfectly.
 * Both were true. Neither ever drew a half-built packet, which is the only state a streaming
 * renderer actually has to survive.
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { PacketView } from "@/components/packet";
import type { Claim, EvidenceRef, Packet } from "@/lib/api";

const REF: EvidenceRef = {
  kind: "external_record",
  id: "01a02b4b-3e88-7c3b-9127-d5fd2453713d",
  label: "Paddy at Prayagraj APMC",
  as_of: "2026-08-22T00:00:00Z",
};

function claim(statement: string): Claim {
  return {
    statement,
    magnitude: null,
    unit: null,
    confidence: 0.7,
    evidence: [REF],
    affected: null,
  };
}

describe("PacketView while the packet is still streaming", () => {
  it("renders the first frame, which carries situation and nothing else", () => {
    render(<PacketView packet={{ situation: [claim("Paddy harvests into its price trough.")] }} />);
    expect(screen.getByText(/price trough/)).toBeDefined();
  });

  it("does not render a heading for a section that has not arrived", () => {
    render(<PacketView packet={{ situation: [claim("Something is happening.")] }} />);
    expect(screen.queryByText("Recommendation")).toBeNull();
    expect(screen.queryByText("Actions")).toBeNull();
  });

  it("survives an entirely empty packet", () => {
    expect(() => render(<PacketView packet={{}} />)).not.toThrow();
  });

  it("survives each section arriving on its own", () => {
    const frames: Partial<Packet>[] = [
      { situation: [claim("a")] },
      { impact: [claim("b")] },
      { recommendation: [] },
      { expected_outcome: [claim("c")] },
      { actions: [] },
      { evidence: [REF] },
      { overrides: [] },
    ];
    for (const frame of frames) {
      expect(() => render(<PacketView packet={frame} />)).not.toThrow();
    }
  });

  it("accumulates as frames land, the way the assistant page builds it", () => {
    let packet: Partial<Packet> = {};
    for (const frame of [
      { situation: [claim("situation claim")] },
      { impact: [claim("impact claim")] },
      { recommendation: [] },
    ]) {
      packet = { ...packet, ...frame };
      expect(() => render(<PacketView packet={packet} />)).not.toThrow();
    }
    expect(screen.getAllByText(/situation claim/).length).toBeGreaterThan(0);
  });
});

describe("PacketView invariants", () => {
  it("drops a claim that arrives with no evidence (FR-804)", () => {
    const unevidenced: Claim = { ...claim("This has no source."), evidence: [] };
    render(<PacketView packet={{ situation: [unevidenced] }} />);
    expect(screen.queryByText(/This has no source/)).toBeNull();
    expect(screen.getByText(/nothing is claimed/i)).toBeDefined();
  });

  it("shows the override banner rather than applying it silently (FR-802)", () => {
    render(
      <PacketView
        packet={{
          overrides: [
            {
              overridden_key: "current_cropping.paddy",
              overridden_module: "status_quo",
              reason: "Two modules disagree about the same crop.",
              prevailing_evidence: [REF],
            },
          ],
        }}
      />,
    );
    expect(screen.getByText(/evidence disagrees with the plan/i)).toBeDefined();
    expect(screen.getByText(/Two modules disagree/)).toBeDefined();
  });

  it("renders a confidence percentage for every claim (UI-02)", () => {
    render(<PacketView packet={{ situation: [claim("A number with a source.")] }} />);
    expect(screen.getByText("70%")).toBeDefined();
  });
});
