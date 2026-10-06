import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TITLE, conceptMap, envelope } from "@/test/fixtures";

import { ConceptMap } from "./ConceptMap";

describe("ConceptMap: the wire states", () => {
  it("loading: a busy status and no steps", () => {
    render(<ConceptMap block={conceptMap("loading")} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("list", { name: "Steps" })).not.toBeInTheDocument();
  });

  it("empty: says no connection was found, not styled or announced as a failure", () => {
    render(<ConceptMap block={conceptMap("empty")} />);
    expect(screen.getByText("No connection found.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("error: shows the reason from meta.error as an alert", () => {
    render(<ConceptMap block={conceptMap("error", {}, envelope({ message: "The path could not be traced." }))} />);
    expect(within(screen.getByRole("alert")).getByText("The path could not be traced.")).toBeInTheDocument();
  });

  it("partial: shows the steps and says it is not final", () => {
    render(<ConceptMap block={conceptMap("partial")} />);
    expect(screen.getByRole("list", { name: "Steps" })).toBeInTheDocument();
    expect(screen.getByText(/not final/i)).toBeInTheDocument();
  });
});

describe("ConceptMap: ready", () => {
  it("is an ordered list of steps with its quote and source link on each", () => {
    render(<ConceptMap block={conceptMap("ready")} />);
    const steps = within(screen.getByRole("list", { name: "Steps" })).getAllByRole("listitem");
    expect(steps).toHaveLength(3);
    expect(steps[0]).toHaveTextContent("Step 1");
    expect(steps[0]).toHaveTextContent("Alpha Method");
    expect(steps[0]).toHaveTextContent("Alpha Method builds on Beta Index for fast lookup.");
    expect(within(steps[2]!).getByRole("link", { name: `Source c3: ${TITLE}, page 3` })).toHaveAttribute(
      "href",
      "#turn-1-concept-map-c3",
    );
    expect(document.getElementById("turn-1-concept-map-c3")).toHaveTextContent("feeds the Delta Store");
  });

  it("a partial map with a single step still renders it, with the not-final note", () => {
    const map = conceptMap("partial");
    map.data.steps = map.data.steps.slice(0, 1);
    render(<ConceptMap block={map} />);
    expect(screen.getAllByRole("listitem").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("(1 step)", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/not final/i)).toBeInTheDocument();
  });

  it("summarises the whole path, start to end, with a step count", () => {
    render(<ConceptMap block={conceptMap("ready")} />);
    expect(screen.getByText(/Alpha Method/, { selector: "p" })).toHaveTextContent("Alpha Method → to Delta Store (3 steps)");
  });

  it("writes a reversed hop's claim the way the document states it, and says so", () => {
    const map = conceptMap("ready");
    map.data.steps[1] = { ...map.data.steps[1]!, reversed: true };
    render(<ConceptMap block={map} />);
    const step = screen.getAllByRole("listitem")[1]!;
    expect(step).toHaveTextContent("Beta Index → to Gamma Cache"); // path order stays as walked
    expect(step).toHaveTextContent("Gamma Cache compared with Beta Index (stated in the opposite direction)");
  });

  it("says plainly if a step's citation is missing, rather than showing an ungrounded step", () => {
    const map = conceptMap("ready");
    map.data.citations = map.data.citations.filter((c) => c.id !== "c2");
    render(<ConceptMap block={map} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Evidence for this step is unavailable.");
  });

  it("renders labels, relations and quotes as text, never as markup", () => {
    const hostile = "<img src=x onerror=alert(1)>";
    const map = conceptMap("ready", {
      steps: [
        { source: hostile, target: "B", relation: "<b>bold</b>", reversed: false, citationId: "c1" },
        { source: "B", target: "C", relation: "uses", reversed: false, citationId: "c1" },
      ],
      citations: [{ id: "c1", chunkId: "k", docId: "d", docTitle: "<script>x</script>", page: 1, quote: `${hostile} B C` }],
    });
    const { container } = render(<ConceptMap block={map} />);
    expect(container.querySelector("img, b, script")).toBeNull();
    expect(screen.getAllByText(/<img src=x onerror=alert\(1\)>/).length).toBeGreaterThan(0);
  });
});
