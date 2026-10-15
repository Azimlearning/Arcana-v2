import { describe, expect, it } from "vitest";

import { block, cheatSheet, comparisonGrid, docBrief, graphView, learningInsights, sourceList, studyPlan, writingDraft } from "@/test/fixtures";

import { blockTitle, tablesOf, toCsv } from "./tables";

describe("tablesOf: the same facts as the block, in rows", () => {
  it("an answer has a sources table with every citation's id, document, page and quote", () => {
    const [table] = tablesOf(block("ready"));
    expect(table!.title).toBe("Sources");
    expect(table!.columns).toEqual(["Id", "Document", "Page", "Quote"]);
    expect(table!.rows).toHaveLength(2);
    expect(table!.rows[0]).toEqual(["c1", expect.any(String), 1, "Dense Retrieval embeds passages and queries."]);
  });

  it("a comparison has one row per document and one column per dimension, each cell the cited sentence", () => {
    const grid = comparisonGrid("ready");
    const [table] = tablesOf(grid);
    expect(table!.columns).toEqual(["Document", ...grid.data.dimensions.map((d) => d.label)]);
    expect(table!.rows).toHaveLength(grid.data.rows.length);
    for (const row of table!.rows) expect(row).toHaveLength(table!.columns.length);
  });

  it("the review schedule, the insights, the brief and the sheet each give their own tables", () => {
    expect(tablesOf(studyPlan("ready"))[0]!.columns).toEqual(["Page", "Due", "Mastery %", "Ratings", "Days since rated"]);
    expect(tablesOf(learningInsights("ready")).map((t) => t.title)).toEqual(["Weakest pages", "Activity", "Review workload"]);
    expect(tablesOf(docBrief("ready")).map((t) => t.title)).toEqual(["Key points", "Key terms", "Next steps"]);
    expect(tablesOf(cheatSheet("ready")).map((t) => t.title)).toEqual(["Concepts", "Connections"]);
    expect(tablesOf(writingDraft("ready")).map((t) => t.title)).toEqual(["Sources", "References"]);
    expect(tablesOf(sourceList("ready"))[0]!.columns).toEqual(["Document", "Passages"]);
  });

  it("a block with no tabular facts gives none, and an empty one gives none", () => {
    expect(tablesOf(graphView("ready"))).toEqual([]);
    expect(tablesOf(learningInsights("empty"))).toEqual([]);
    expect(tablesOf(docBrief("empty"))).toEqual([]);
  });

  it("every row is as wide as its columns", () => {
    for (const b of [studyPlan("ready"), learningInsights("ready"), docBrief("ready"), cheatSheet("ready"), writingDraft("ready")]) {
      for (const t of tablesOf(b)) for (const r of t.rows) expect(r).toHaveLength(t.columns.length);
    }
  });
});

describe("blockTitle", () => {
  it("names a draft by its title and a brief by its document, and other blocks by what they are", () => {
    expect(blockTitle(writingDraft("ready"))).toBe("Hybrid retrieval in brief");
    expect(blockTitle(docBrief("ready"))).toMatch(/^Brief: /);
    expect(blockTitle(studyPlan("ready"))).toBe("Review schedule");
    expect(blockTitle(block("ready"))).toBe("Answer");
  });
});

describe("toCsv", () => {
  it("quotes commas, quotes and line breaks and ends each row with CRLF", () => {
    const csv = toCsv({ title: "t", columns: ["a", "b"], rows: [['say "hi", please', "two\nlines"], [1, 2]] });
    expect(csv).toBe('a,b\r\n"say ""hi"", please","two\nlines"\r\n1,2\r\n');
  });

  it("neutralises a cell a spreadsheet would run as a formula (a stranger's document text)", () => {
    const csv = toCsv({ title: "t", columns: ["x"], rows: [["=HYPERLINK(\"http://evil\")"], ["+1+1"], ["-2"], ["@SUM(A1)"], ["plain"], [-5]] });
    const lines = csv.trimEnd().split("\r\n");
    expect(lines[1]).toBe(`"'=HYPERLINK(""http://evil"")"`);
    expect(lines.slice(2, 5)).toEqual(["'+1+1", "'-2", "'@SUM(A1)"]);
    expect(lines[5]).toBe("plain");
    expect(lines[6]).toBe("-5"); // a number is a number, not text to neutralise
  });
});
