import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Studio } from "./Studio";

describe("Studio", () => {
  it("lists the generators it will offer, each saying it is not available yet", () => {
    render(<Studio />);
    const list = screen.getByRole("list");
    const items = within(list).getAllByRole("listitem");
    expect(items.map((i) => i.textContent)).toEqual([
      "SlidesComing with the Studio agent",
      "QuizComing with the Studio agent",
      "FlashcardsComing with the Studio agent",
      "Study sessionComing with the Studio agent",
    ]);
    for (const item of items) expect(item).toHaveAttribute("data-available", "false"); // the words say it; a list item takes no aria-disabled
  });

  it("is inert: nothing in it is a button, a link or a control, and it calls nothing", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const { container } = render(<Studio />);
    expect(screen.queryAllByRole("button")).toEqual([]);
    expect(screen.queryAllByRole("link")).toEqual([]);
    expect(container.querySelector("button, a, input, [tabindex]")).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
