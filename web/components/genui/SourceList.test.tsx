import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TITLE, envelope, sourceList } from "@/test/fixtures";

import { SourceList } from "./SourceList";

describe("SourceList: the wire states", () => {
  it("loading: a busy status and no documents", () => {
    render(<SourceList block={sourceList("loading")} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByText(TITLE)).not.toBeInTheDocument();
  });

  it("empty: says there are no documents, not styled or announced as a failure", () => {
    render(<SourceList block={sourceList("empty")} />);
    expect(screen.getByText("No documents yet.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("error: shows the reason from meta.error as an alert", () => {
    const reason = envelope({ message: "The store could not be read.", retryable: false });
    render(<SourceList block={sourceList("error", [], reason)} />);
    expect(within(screen.getByRole("alert")).getByText("The store could not be read.")).toBeInTheDocument();
  });

  it("partial: shows what is there and says it is not final", () => {
    render(<SourceList block={sourceList("partial")} />);
    expect(screen.getByText(TITLE)).toBeInTheDocument();
    expect(screen.getByText(/not final/i)).toBeInTheDocument();
  });

  it("ready: lists every document with its passage count, singular for one", () => {
    render(<SourceList block={sourceList("ready")} />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]!).getByText("12 passages")).toBeInTheDocument();
    expect(within(items[1]!).getByText("1 passage")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Documents \(2\)/ })).toBeInTheDocument();
  });

  it("renders a title as text, never as markup", () => {
    const hostile = [{ docId: "x", title: "<img src=x onerror=alert(1)>", chunkCount: 3 }];
    const { container } = render(<SourceList block={sourceList("ready", hostile)} />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
  });
});
