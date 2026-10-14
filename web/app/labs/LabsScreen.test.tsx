// The labs screen against a mocked server: it lists the labs the documents support, offers a lab only where a passage states its formula, and
// shows a made lab through the registry (the code only in the sandboxed iframe).

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { envelope, jsonResponse, layout, verifiedLab } from "@/test/fixtures";

import { LabsScreen } from "./LabsScreen";

const LIST = {
  labs: [
    { contractId: "ranknet_pairwise_loss", title: "RankNet pairwise loss for one pair of passages", available: true, docTitle: "A Ranking Paper", page: 16, reason: null },
    { contractId: "f1_at_k", title: "F1@k: the harmonic mean of precision and recall", available: false, docTitle: null, page: null, reason: "No stored passage states this formula, so there is nothing to ground the lab in." },
  ],
};

let calls: { url: URL; method: string }[];
let listAnswer: () => Response;

beforeEach(() => {
  calls = [];
  listAnswer = () => jsonResponse(LIST);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const url = new URL(input);
      calls.push({ url, method: init?.method ?? "GET" });
      if (url.pathname === "/labs" && (init?.method ?? "GET") === "GET") return listAnswer();
      if (url.pathname === "/labs") {
        return jsonResponse({ layout: layout([{ blockId: "lab", panel: "studio", region: "main", order: 0 }]), blocks: [verifiedLab("ready")] });
      }
      return jsonResponse(envelope({ code: "not_found" }), 404);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LabsScreen", () => {
  it("lists the labs, says where each is stated, and says why one is unavailable", async () => {
    render(<LabsScreen />);
    const list = await screen.findByRole("list", { name: "Available labs" });
    const [first, second] = within(list).getAllByRole("listitem");
    expect(first).toHaveTextContent("RankNet pairwise loss for one pair of passages");
    expect(first).toHaveTextContent("Stated in A Ranking Paper · page 16");
    expect(within(first!).getByRole("button", { name: "Make this lab" })).toBeEnabled();
    expect(second).toHaveTextContent("No stored passage states this formula");
    expect(within(second!).getByRole("button", { name: "Make this lab" })).toBeDisabled();
  });

  it("makes the chosen lab and shows it through the registry, code only in a sandboxed iframe", async () => {
    render(<LabsScreen />);
    const list = await screen.findByRole("list", { name: "Available labs" });
    fireEvent.click(within(within(list).getAllByRole("listitem")[0]!).getByRole("button", { name: "Make this lab" }));
    expect(await screen.findByRole("region", { name: "Lab" })).toBeInTheDocument();
    await waitFor(() => expect(document.querySelector("iframe")).not.toBeNull());
    expect(document.querySelector("iframe")!.getAttribute("sandbox")).toBe("allow-scripts");
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url.pathname).toBe("/labs");
  });

  it("says so as an alert when the server cannot list the labs", async () => {
    listAnswer = () => jsonResponse(envelope({ code: "internal", message: "The server could not list the labs." }), 500);
    render(<LabsScreen />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The server could not list the labs.");
  });

  it("shows a busy status while the list is being read", () => {
    render(<LabsScreen />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
  });
});
