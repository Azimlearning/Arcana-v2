import { render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LAB_CSP, LAB_SANDBOX, LAB_TEMPLATE_VERSION, buildFrame, sha256Hex } from "@/lib/labFrame";
import { LAB_SHA256, LAB_SOURCE, envelope, verifiedLab } from "@/test/fixtures";

const TEMPLATE_FINGERPRINT = "9fa43ed30289529bb9ecc07de788e9c08040870874f8a5531c9aeba5f0681c0d";

import { VerifiedLab } from "./VerifiedLab";

describe("VerifiedLab: the wire states", () => {
  it("loading: a busy status and no frame", () => {
    render(<VerifiedLab block={verifiedLab("loading")} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(document.querySelector("iframe")).toBeNull();
  });

  it("empty: says no passage states the formula, not announced as a failure", () => {
    render(<VerifiedLab block={verifiedLab("empty")} />);
    expect(screen.getByText("No lab could be made.")).toBeInTheDocument();
    expect(screen.getByText(/None of the stored passages states this lab's formula/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(document.querySelector("iframe")).toBeNull();
  });

  it("error: shows the reason from meta.error as an alert and carries no frame", () => {
    render(<VerifiedLab block={verifiedLab("error", {}, envelope({ message: "reference_cases: the formula gives another number." }))} />);
    expect(within(screen.getByRole("alert")).getByText(/the formula gives another number/)).toBeInTheDocument();
    expect(document.querySelector("iframe")).toBeNull();
  });

  it("partial: a lab is delivered whole, so a partial one is never shown", () => {
    render(<VerifiedLab block={{ ...verifiedLab("ready"), meta: { status: "partial", error: null } }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("only shown when it is complete and verified");
    expect(document.querySelector("iframe")).toBeNull();
  });
});

describe("VerifiedLab: ready", () => {
  it("renders the code only in an iframe whose sandbox is exactly allow-scripts, after the hash matches", async () => {
    render(<VerifiedLab block={verifiedLab("ready")} />);
    await waitFor(() => expect(document.querySelector("iframe")).not.toBeNull());
    const frame = document.querySelector("iframe")!;
    expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
    expect(LAB_SANDBOX).toBe("allow-scripts");
    expect(frame.getAttribute("sandbox")).not.toMatch(/same-origin|allow-forms|allow-popups|allow-top-navigation|allow-modals/);
    expect(frame.getAttribute("referrerpolicy")).toBe("no-referrer");
    expect(frame.getAttribute("src")).toBeNull(); // no address to load: only our own srcdoc
    const doc = frame.getAttribute("srcdoc")!;
    expect(doc).toContain(`<meta http-equiv="Content-Security-Policy" content="${LAB_CSP}">`);
    expect(doc).toContain(LAB_SOURCE);
    expect(doc).not.toMatch(/https?:\/\//); // the template loads nothing from anywhere
  });

  it("says what the lab is, what was checked and that it is not a proof, and cites the sentence as text", async () => {
    render(<VerifiedLab block={verifiedLab("ready")} />);
    const region = screen.getByRole("region", { name: "Lab" });
    expect(within(region).getByRole("heading", { name: "RankNet pairwise loss for one pair of passages" })).toBeInTheDocument();
    expect(region).toHaveTextContent("4 reference cases, on 5 properties, on every one of the 4,225 settings the sliders can reach, and on 200 other inputs");
    expect(region).toHaveTextContent("not a proof that it is right for every input, only for these");
    expect(region).toHaveTextContent("The formula is stated in A Ranking Paper · page 16");
    expect(within(region).getByRole("group", { name: "Parameters" })).toHaveTextContent("score of the passage ranked first: from -4 to 4, starting at 0");
    await waitFor(() => expect(document.querySelector("iframe")).not.toBeNull());
  });

  it("refuses a lab whose code does not match the verified hash: an alert, no frame", async () => {
    render(<VerifiedLab block={verifiedLab("ready", { source: LAB_SOURCE.replace("log1p", "log") })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("does not match the hash the server verified");
    expect(document.querySelector("iframe")).toBeNull();
  });

  it("refuses a lab verified for another template version", async () => {
    render(<VerifiedLab block={verifiedLab("ready", { templateVersion: LAB_TEMPLATE_VERSION + 1 })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("another version of the lab template");
    expect(document.querySelector("iframe")).toBeNull();
  });

  it("shows the checking status first, never the frame, while the hash is being checked", () => {
    render(<VerifiedLab block={verifiedLab("ready")} />);
    expect(screen.getByRole("status")).toHaveTextContent("Checking the lab's code against its hash");
    expect(document.querySelector("iframe")).toBeNull();
  });
});

describe("the lab frame", () => {
  it("hashes text the way the server does (SHA-256 of the UTF-8 text)", async () => {
    expect(await sha256Hex(LAB_SOURCE)).toBe(LAB_SHA256);
    expect(await sha256Hex("")).toBe("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  });

  it("builds nothing for a source that holds a markup sequence that could close the script, even if its hash matches", async () => {
    for (const source of [`${LAB_SOURCE}\n// </script><script>alert(1)</script>`, `${LAB_SOURCE}<!--`, `${LAB_SOURCE}-->`, `${LAB_SOURCE}</SCRIPT>`]) {
      const data = verifiedLab("ready", { source, sourceSha256: await sha256Hex(source) }).data;
      const built = await buildFrame(data);
      expect(built.ok).toBe(false);
    }
  });

  it("puts the lab's text in the document as data that cannot close the script element", async () => {
    const data = verifiedLab("ready", { title: "A </script><b>title</b>" }).data;
    const built = await buildFrame(data);
    expect(built.ok).toBe(true);
    if (built.ok) {
      expect(built.srcdoc).not.toContain("</script><b>");
      expect(built.srcdoc).toContain("\\u003c/script>\\u003cb>title");
      expect(built.srcdoc.match(/<script>/g)).toHaveLength(1);
      expect(built.srcdoc.match(/<\/script>/g)).toHaveLength(1);
    }
  });

  it("is a fixed template: the same lab gives the same document", async () => {
    const data = verifiedLab("ready").data;
    const a = await buildFrame(data);
    const b = await buildFrame(data);
    expect(a).toEqual(b);
  });
});

describe("the template is pinned", () => {
  // If this fails you changed the template text. That can change what a verified function does in the browser: bump LAB_TEMPLATE_VERSION (and
  // the server's TEMPLATE_VERSION), then update this fingerprint on purpose.
  it("has the fingerprint recorded for its version", async () => {
    const built = await buildFrame(verifiedLab("ready").data);
    expect(built.ok).toBe(true);
    if (built.ok) expect({ version: LAB_TEMPLATE_VERSION, sha256: await sha256Hex(built.srcdoc) }).toEqual({ version: 2, sha256: TEMPLATE_FINGERPRINT });
  });
});

