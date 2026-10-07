import type { LayoutSpec, PanelSpec } from "@arcana/schema";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { layout } from "@/test/fixtures";

import { LayoutSwitch } from "./LayoutSwitch";
import { Shell } from "./Shell";

const panels = { sources: { main: <p>S</p> }, chat: { main: <p>C</p> }, studio: { main: <p>T</p> } };
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

describe("Shell regions", () => {
  const studio = (spec: Partial<PanelSpec>): PanelSpec => ({
    id: "studio",
    width: 35,
    direction: "rows",
    regions: [
      { id: "main", size: 60 },
      { id: "shelf", size: 40 },
    ],
    ...spec,
  });
  const split = (spec: Partial<PanelSpec> = {}) =>
    layout([], {
      panels: [
        { id: "sources", width: 20, direction: "rows", regions: [{ id: "main", size: 100 }] },
        { id: "chat", width: 45, direction: "columns", regions: [{ id: "main", size: 100 }] },
        studio(spec),
      ],
    });
  const withShelf = {
    ...panels,
    studio: { main: <p>Graph</p>, shelf: <p>Saved</p> },
  };

  it("divides a panel into its regions, each with its size as a flex-grow value, in the layout's order", () => {
    render(<Shell layout={split()} header={<span>Arcana</span>} panels={withShelf} />);
    const regions = Array.from(document.querySelectorAll('[data-panel="studio"] [data-region]'));
    expect(regions.map((r) => r.getAttribute("data-region"))).toEqual(["main", "shelf"]);
    expect(regions[0]).toHaveStyle({ flexGrow: "60" });
    expect(regions[1]).toHaveStyle({ flexGrow: "40" });
    expect(regions[0]).toHaveTextContent("Graph");
    expect(regions[1]).toHaveTextContent("Saved");
  });

  it("stacks regions for rows and puts them side by side for columns", () => {
    const { unmount } = render(<Shell layout={split()} header={<span>A</span>} panels={withShelf} />);
    expect(document.querySelector('[data-panel="studio"]')).toHaveClass("flex-col");
    unmount();
    render(<Shell layout={split({ direction: "columns" })} header={<span>A</span>} panels={withShelf} />);
    expect(document.querySelector('[data-panel="studio"]')).toHaveClass("flex-row");
  });

  it("names a region as a landmark only when its panel is split", () => {
    render(<Shell layout={split()} header={<span>A</span>} panels={withShelf} />);
    expect(screen.getByRole("region", { name: "Outputs" })).toHaveTextContent("Saved");
    expect(screen.getByRole("region", { name: "Main area" })).toHaveTextContent("Graph");
    expect(document.querySelector('[data-panel="chat"] [data-region]')).not.toHaveAttribute("role");
  });

  it("draws a listed region with no content as an empty area, and does not draw one the layout leaves out", () => {
    render(<Shell layout={split()} header={<span>A</span>} panels={{ ...panels, studio: { main: <p>Graph</p> } }} />);
    expect(document.querySelector('[data-panel="studio"] [data-region="shelf"]')).toBeEmptyDOMElement();
    render(
      <Shell
        layout={split({ regions: [{ id: "main", size: 100 }] })}
        header={<span>A</span>}
        panels={{ ...panels, studio: { main: <p>Graph</p>, shelf: <p>Hidden by the layout</p> } }}
      />,
    );
    expect(screen.queryByText("Hidden by the layout")).not.toBeInTheDocument();
  });

  it("collapses a region of size 0: aria-hidden and inert", () => {
    render(
      <Shell
        layout={split({ regions: [{ id: "main", size: 0 }, { id: "shelf", size: 100 }] })}
        header={<span>A</span>}
        panels={withShelf}
      />,
    );
    const main = document.querySelector('[data-panel="studio"] [data-region="main"]')!;
    expect(main).toHaveAttribute("aria-hidden", "true");
    expect(main).toHaveAttribute("inert");
    expect(document.querySelector('[data-panel="studio"] [data-region="shelf"]')).not.toHaveAttribute("inert");
  });

  it("contains hidden text and long titles inside each region, and animates a change of share unless motion is reduced", () => {
    render(<Shell layout={split()} header={<span>A</span>} panels={withShelf} />);
    for (const region of Array.from(document.querySelectorAll("[data-region]"))) {
      expect(region).toHaveClass("relative", "overflow-y-auto", "[overflow-wrap:anywhere]");
      expect(region).toHaveClass("transition-[flex-grow]", "motion-reduce:transition-none");
    }
    expect(document.querySelector('[data-panel="studio"]')).toHaveClass("transition-[flex-grow]", "motion-reduce:transition-none");
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
