import type { LayoutSpec } from "@arcana/schema";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { layout } from "@/test/fixtures";

import { LayoutSwitch } from "./LayoutSwitch";
import { Shell } from "./Shell";

const panels = { sources: <p>S</p>, chat: <p>C</p>, studio: <p>T</p> };
const shell = (spec: LayoutSpec) => render(<Shell layout={spec} header={<span>Arcana</span>} panels={panels} />);

describe("Shell", () => {
  it("gives each panel its layout width as a flex-grow value, in the layout's order", () => {
    shell(layout([], { panels: [{ id: "chat", width: 55, direction: "rows" as const, regions: [{ id: "main" as const, size: 100 }] }, { id: "sources", width: 15, direction: "rows" as const, regions: [{ id: "main" as const, size: 100 }] }, { id: "studio", width: 30, direction: "rows" as const, regions: [{ id: "main" as const, size: 100 }] }] }));
    const order = Array.from(document.querySelectorAll("[data-panel]")).map((p) => p.getAttribute("data-panel"));
    expect(order).toEqual(["chat", "sources", "studio"]);
    expect(document.querySelector('[data-panel="chat"]')).toHaveStyle({ flexGrow: "55" });
    expect(document.querySelector('[data-panel="sources"]')).toHaveStyle({ flexGrow: "15" });
    expect(document.querySelector('[data-panel="studio"]')).toHaveStyle({ flexGrow: "30" });
  });

  it("collapses a panel of width 0: aria-hidden and inert, so nothing in it can be reached", () => {
    shell(layout([], { panels: [{ id: "sources", width: 0, direction: "rows" as const, regions: [{ id: "main" as const, size: 100 }] }, { id: "chat", width: 100, direction: "rows" as const, regions: [{ id: "main" as const, size: 100 }] }, { id: "studio", width: 0, direction: "rows" as const, regions: [{ id: "main" as const, size: 100 }] }] }));
    for (const id of ["sources", "studio"]) {
      const panel = document.querySelector(`[data-panel="${id}"]`)!;
      expect(panel).toHaveAttribute("aria-hidden", "true");
      expect(panel).toHaveAttribute("inert"); // React 19.3 renders the attribute
    }
    const chat = screen.getByRole("main", { name: "Chat" });
    expect(chat).not.toHaveAttribute("aria-hidden");
    expect(chat).not.toHaveAttribute("inert");
  });

  it("contains absolutely positioned text inside its panel, so a panel's hidden text cannot make the page scroll, and lets long unbroken titles wrap", () => {
    shell(layout([]));
    for (const id of ["sources", "chat", "studio"]) {
      expect(document.querySelector(`[data-panel="${id}"]`)).toHaveClass("relative", "overflow-y-auto", "[overflow-wrap:anywhere]");
    }
  });

  it("uses a landmark for each panel and says which layout is in force", () => {
    shell(layout([]));
    expect(screen.getByRole("complementary", { name: "Sources" })).toBeInTheDocument();
    expect(screen.getByRole("main", { name: "Chat" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Studio" })).toBeInTheDocument();
    expect(document.querySelector("[data-layout-origin]")).toHaveAttribute("data-layout-origin", "adaptive");
  });
});

describe("LayoutSwitch", () => {
  it("states which layout is chosen and reports a choice", () => {
    const onChoose = vi.fn();
    render(<LayoutSwitch choice="basic" adaptiveAvailable onChoose={onChoose} />);
    expect(screen.getByRole("button", { name: "Basic" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Adaptive" })).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(screen.getByRole("button", { name: "Adaptive" }));
    expect(onChoose).toHaveBeenCalledWith("adaptive");
  });

  it("disables Adaptive with a stated reason until one exists", () => {
    const onChoose = vi.fn();
    render(<LayoutSwitch choice="basic" adaptiveAvailable={false} onChoose={onChoose} />);
    const adaptive = screen.getByRole("button", { name: "Adaptive" });
    expect(adaptive).toBeDisabled();
    expect(adaptive).toHaveAccessibleDescription("Adaptive is available after your first answer.");
    fireEvent.click(adaptive);
    expect(onChoose).not.toHaveBeenCalled();
  });
});
