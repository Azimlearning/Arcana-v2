import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { envelope, jsonResponse, trace } from "@/test/fixtures";

import { TracePanel } from "./TracePanel";

afterEach(cleanup);

const fetching = (response: () => Response | Promise<Response>) => vi.fn<typeof fetch>(async () => response());
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
    const steps = await screen.findAllByRole("listitem");
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
    await screen.findAllByRole("listitem");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(String(fetchImpl.mock.calls[0]?.[0])).toMatch(/\/turns\/turn-9\/trace$/);
    fireEvent.click(screen.getByRole("button", { name: /hide/i })); // close and reopen: no second request
    open();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(await screen.findAllByRole("listitem")).toHaveLength(3);
  });

  it("says a refused hop was not run, rather than showing it as a success", async () => {
    const refused = trace({
      steps: [{ hop: 0, agent: "orchestrator", status: "refused", tokens: 0, latencyMs: 0, note: "hop budget reached" }],
      hopsUsed: 1,
      outcome: "error",
    });
    render(<TracePanel turnId="turn-1" fetchImpl={fetching(() => jsonResponse(refused))} />);
    open();
    const step = await screen.findByRole("listitem");
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
    await screen.findAllByRole("listitem");
    rerender(<TracePanel key="turn-2" turnId="turn-2" fetchImpl={fetchImpl} />);
    await waitFor(() => expect(screen.queryAllByRole("listitem")).toHaveLength(0));
    open();
    await screen.findAllByRole("listitem");
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(String(fetchImpl.mock.calls[1]?.[0])).toMatch(/turn-2\/trace$/);
  });
});
