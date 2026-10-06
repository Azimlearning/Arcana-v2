import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { envelope, jsonResponse, trace } from "@/test/fixtures";

import { TracePanel } from "./TracePanel";

afterEach(cleanup);

const fetching = (response: () => Response | Promise<Response>) => vi.fn<typeof fetch>(async () => response());
/** The hops only: the composition record below them is a list too. */
const hops = async () => within(await screen.findByRole("list", { name: "Steps" })).getAllByRole("listitem");
const open = () => fireEvent.click(screen.getByRole("button", { name: /how this was answered/i }));

describe("TracePanel", () => {
  it("is closed and has fetched nothing until it is opened", () => {
    const fetchImpl = fetching(() => jsonResponse(trace()));
    render(<TracePanel turnId="turn-1" fetchImpl={fetchImpl} />);
    expect(screen.getByRole("button", { name: "Show how this was answered" })).toHaveAttribute("aria-expanded", "false");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("lists every hop with its agent, outcome in words, tokens and time", async () => {
    render(<TracePanel turnId="turn-1" fetchImpl={fetching(() => jsonResponse(trace()))} />);
    open();
    const steps = await hops();
    expect(steps).toHaveLength(3);
    expect(steps[0]).toHaveTextContent("1. orchestrator");
    expect(steps[0]).toHaveTextContent("completed");
    expect(steps[0]).toHaveTextContent("1,200 tokens");
    expect(steps[0]).toHaveTextContent("40 ms");
    expect(within(steps[2]!).getByText(/fact checker/)).toBeInTheDocument(); // underscores are not shown
    expect(steps[2]).toHaveTextContent("partly completed");
    expect(steps[2]).toHaveTextContent("(removed 1 of 3 segments)");
    expect(screen.getByText(/3 steps, 1,200 tokens: answered/)).toBeInTheDocument();
  });

  it("asks for the right trace, by the turn id, once", async () => {
    const fetchImpl = fetching(() => jsonResponse(trace()));
    render(<TracePanel turnId="turn-9" fetchImpl={fetchImpl} />);
    open();
    await hops();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(String(fetchImpl.mock.calls[0]?.[0])).toMatch(/\/turns\/turn-9\/trace$/);
    fireEvent.click(screen.getByRole("button", { name: /hide/i })); // close and reopen: no second request
    open();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(await hops()).toHaveLength(3);
  });

  it("says a refused hop was not run, rather than showing it as a success", async () => {
    const refused = trace({
      steps: [{ hop: 0, agent: "orchestrator", status: "refused", tokens: 0, latencyMs: 0, note: "hop budget reached" }],
      hopsUsed: 1,
      outcome: "error",
    });
    render(<TracePanel turnId="turn-1" fetchImpl={fetching(() => jsonResponse(refused))} />);
    open();
    const [step] = await hops();
    expect(step).toHaveTextContent("not run (limit reached)");
    expect(screen.getByText(/1 step, .*ended with an error/)).toBeInTheDocument();
  });

  it("shows the server's message when there is no trace for the turn", async () => {
    const notFound = fetching(() => jsonResponse(envelope({ code: "not_found", message: "No trace for that turn.", retryable: false }), 404));
    render(<TracePanel turnId="turn-1" fetchImpl={notFound} />);
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("No trace for that turn.");
  });

  it("says so when the server cannot be reached", async () => {
    render(<TracePanel turnId="turn-1" fetchImpl={vi.fn(async () => { throw new TypeError("down"); })} />);
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
  });

  it("refuses a body that is not a trace instead of rendering it", async () => {
    render(<TracePanel turnId="turn-1" fetchImpl={fetching(() => jsonResponse({ turnId: "turn-1", steps: "nope" }))} />);
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("The server sent an unreadable response.");
  });

  it("shows a loading status while the trace is on its way", async () => {
    let release: (r: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => (release = resolve));
    render(<TracePanel turnId="turn-1" fetchImpl={vi.fn(() => pending)} />);
    open();
    expect(await screen.findByRole("status")).toHaveTextContent("Loading the trace");
    release(jsonResponse(trace()));
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
  });

  it("closes and forgets the old trace when the turn changes", async () => {
    const fetchImpl = fetching(() => jsonResponse(trace()));
    const { rerender } = render(<TracePanel key="turn-1" turnId="turn-1" fetchImpl={fetchImpl} />);
    open();
    await hops();
    rerender(<TracePanel key="turn-2" turnId="turn-2" fetchImpl={fetchImpl} />);
    await waitFor(() => expect(screen.queryByRole("list", { name: "Steps" })).not.toBeInTheDocument());
    open();
    await hops();
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(String(fetchImpl.mock.calls[1]?.[0])).toMatch(/turn-2\/trace$/);
  });

  describe("the composition record", () => {
    const sections = async () => {
      render(<TracePanel turnId="turn-1" fetchImpl={fetching(() => jsonResponse(trace()))} />);
      open();
      return {
        offered: await screen.findByRole("region", { name: "Offered" }),
        refused: await screen.findByRole("region", { name: "Not offered" }),
      };
    };

    it("lists what was offered and, separately, what was not and why, in plain sentences", async () => {
      const { offered, refused } = await sections();
      expect(within(offered).getByText("Answer")).toBeInTheDocument();
      expect(within(offered).getByText("Source list")).toBeInTheDocument();
      expect(within(offered).queryByText("Connection graph")).not.toBeInTheDocument();
      const items = within(refused).getAllByRole("listitem");
      expect(items).toHaveLength(3);
      expect(items[0]).toHaveTextContent("Connection graph: no stated relationship had a quote naming both concepts");
      expect(items[1]).toHaveTextContent("Document comparison: the documents do not share enough concepts to compare");
      expect(items[2]).toHaveTextContent("Connection path: the concepts are directly linked");
    });

    it("never shows a raw reason code", async () => {
      const { refused } = await sections();
      expect(refused.textContent).not.toMatch(/no_grounded_edge|single_hop|_/);
    });

    it("explains an empty answer that was still offered", async () => {
      const empty = trace({ composition: [{ component: "CitedSummary", offered: true, reasons: ["no_grounded_answer"] }] });
      render(<TracePanel turnId="turn-1" fetchImpl={fetching(() => jsonResponse(empty))} />);
      open();
      const offered = await screen.findByRole("region", { name: "Offered" });
      expect(offered).toHaveTextContent("Answer (nothing in your documents could support an answer)");
    });

    it("falls back to a generic sentence for a code from a newer server, and shows an unknown component by its name", async () => {
      const newer = trace({
        composition: [
          { component: "TimelineRibbon", offered: false, reasons: ["needs_a_timeline" as never] },
          { component: "GraphView", offered: false, reasons: [] },
        ],
      });
      render(<TracePanel turnId="turn-1" fetchImpl={fetching(() => jsonResponse(newer))} />);
      open();
      const refused = await screen.findByRole("region", { name: "Not offered" });
      expect(refused).toHaveTextContent("TimelineRibbon: a reason this version of the app does not describe");
      expect(refused).toHaveTextContent("Connection graph: no reason was recorded");
      expect(refused.textContent).not.toContain("needs_a_timeline");
    });

    it("says so when nothing was refused or nothing was offered", async () => {
      const all = trace({ composition: [{ component: "CitedSummary", offered: true, reasons: [] }] });
      const { unmount } = render(<TracePanel turnId="turn-1" fetchImpl={fetching(() => jsonResponse(all))} />);
      open();
      expect(await screen.findByText("Everything that could be shown was shown.")).toBeInTheDocument();
      unmount();
      cleanup();
      const none = trace({ composition: [{ component: "CitedSummary", offered: false, reasons: ["answer_unavailable"] }] });
      render(<TracePanel turnId="turn-2" fetchImpl={fetching(() => jsonResponse(none))} />);
      open();
      expect(await screen.findByText("Nothing was offered.")).toBeInTheDocument();
      expect(screen.getByRole("region", { name: "Not offered" })).toHaveTextContent("the answer could not be produced or checked");
    });

    it("shows no composition section for a trace with an empty record", async () => {
      render(<TracePanel turnId="turn-1" fetchImpl={fetching(() => jsonResponse(trace({ composition: [] })))} />);
      open();
      await hops();
      expect(screen.queryByRole("region", { name: "Offered" })).not.toBeInTheDocument();
    });

    it("refuses a trace whose composition is malformed, as an error and not a half-rendered trace", async () => {
      const broken = { ...trace(), composition: [{ component: 3 }] };
      render(<TracePanel turnId="turn-1" fetchImpl={fetching(() => jsonResponse(broken))} />);
      open();
      expect(await screen.findByRole("alert")).toHaveTextContent("unreadable response");
    });
  });
});
