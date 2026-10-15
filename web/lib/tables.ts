// The tables a block can be read as, for a pane's Table view (D-44). A pure function of the block's own data: nothing is computed that
// the server did not send, so a table is the same facts as the block laid out in rows and columns, sortable and exportable. A block
// type with no table of its own gives none and its pane has no Table view.

import type { Citation, UIBlock } from "@arcana/schema";

export interface Table {
  title: string;
  columns: string[];
  rows: (string | number)[][];
}

const quote = (byId: Map<string, Citation>, id: string) => byId.get(id)?.quote ?? "";
const where = (c: Citation | undefined) => (c ? `${c.docTitle}${c.page != null ? `, page ${c.page}` : ""}` : "");

function sourcesTable(citations: Citation[]): Table {
  return {
    title: "Sources",
    columns: ["Id", "Document", "Page", "Quote"],
    rows: citations.map((c) => [c.id, c.docTitle, c.page ?? "", c.quote]),
  };
}

/** What each block type is called above its pane. A type not listed is shown under its own name. */
const WORDS: Partial<Record<UIBlock["type"], string>> = {
  CitedSummary: "Answer",
  SourceList: "Sources",
  GraphView: "Connection graph",
  TraversalView: "Search path",
  ComparisonGrid: "Document comparison",
  ConceptMap: "Connection path",
  ConceptPage: "Concept page",
  NotesGraph: "Notes graph",
  QuizCard: "Quiz",
  VerifiedLab: "Lab",
  WritingDraft: "Draft",
  StudySet: "Study set",
  StudyPlan: "Review schedule",
  DocBrief: "Document brief",
  CheatSheet: "Cheat sheet",
  LearningInsights: "Learning insights",
};

export function blockTitle(block: UIBlock): string {
  if (block.type === "WritingDraft" && block.data.title) return block.data.title;
  if (block.type === "DocBrief" && block.data.docTitle) return `Brief: ${block.data.docTitle}`;
  return WORDS[block.type] ?? block.type;
}

export function tablesOf(block: UIBlock): Table[] {
  switch (block.type) {
    case "CitedSummary":
      return block.data.citations.length > 0 ? [sourcesTable(block.data.citations)] : [];
    case "SourceList":
      return block.data.documents.length > 0
        ? [{ title: "Documents", columns: ["Document", "Passages"], rows: block.data.documents.map((d) => [d.title, d.chunkCount]) }]
        : [];
    case "ComparisonGrid": {
      const byId = new Map(block.data.citations.map((c) => [c.id, c]));
      return block.data.rows.length > 0
        ? [
            {
              title: "Comparison",
              columns: ["Document", ...block.data.dimensions.map((d) => d.label)],
              rows: block.data.rows.map((row) => [
                row.docTitle,
                ...block.data.dimensions.map((d) => {
                  const cell = row.cells.find((c) => c.dimensionId === d.id);
                  return cell ? quote(byId, cell.citationId) : "";
                }),
              ]),
            },
          ]
        : [];
    }
    case "WritingDraft":
      return [
        ...(block.data.citations.length > 0 ? [sourcesTable(block.data.citations)] : []),
        ...(block.data.bibliography.length > 0
          ? [{ title: "References", columns: ["Document", "APA", "IEEE"], rows: block.data.bibliography.map((b) => [b.docId, b.apa, b.ieee]) }]
          : []),
      ];
    case "StudyPlan":
      return block.data.items.length > 0
        ? [
            {
              title: "Review schedule",
              columns: ["Page", "Due", "Mastery %", "Ratings", "Days since rated"],
              rows: block.data.items.map((i) => [i.pageLabel, i.due, Math.round(i.score * 100), i.events, i.daysSince]),
            },
          ]
        : [];
    case "LearningInsights":
      return [
        ...(block.data.weakest.length > 0
          ? [
              {
                title: "Weakest pages",
                columns: ["Page", "Mastery %", "Ratings"],
                rows: block.data.weakest.map((w) => [w.pageLabel, Math.round(w.score * 100), w.events]),
              },
            ]
          : []),
        ...(block.data.activity.length > 0
          ? [{ title: "Activity", columns: ["Day", "Ratings"], rows: block.data.activity.map((d) => [d.date, d.count]) }]
          : []),
        ...(block.data.workload.length > 0
          ? [{ title: "Review workload", columns: ["Day", "Pages due"], rows: block.data.workload.map((d) => [d.date, d.due]) }]
          : []),
      ];
    case "DocBrief": {
      const byId = new Map(block.data.citations.map((c) => [c.id, c]));
      return [
        ...(block.data.keyPoints.length > 0
          ? [
              {
                title: "Key points",
                columns: ["Sentence", "Names", "Source"],
                rows: block.data.keyPoints.map((p) => [quote(byId, p.citationId), p.pageLabels.join(", "), where(byId.get(p.citationId))]),
              },
            ]
          : []),
        ...(block.data.terms.length > 0
          ? [{ title: "Key terms", columns: ["Term", "Definition"], rows: block.data.terms.map((t) => [t.pageLabel, quote(byId, t.citationId)]) }]
          : []),
        ...(block.data.actions.length > 0
          ? [{ title: "Next steps", columns: ["Step", "Page", "Why"], rows: block.data.actions.map((a) => [a.kind, a.pageLabel, a.reason]) }]
          : []),
      ];
    }
    case "CheatSheet": {
      const byId = new Map(block.data.citations.map((c) => [c.id, c]));
      const label = new Map(block.data.entries.map((e) => [e.pageId, e.pageLabel]));
      return [
        ...(block.data.entries.length > 0
          ? [
              {
                title: "Concepts",
                columns: ["Concept", "Kind", "Sentence", "Source"],
                rows: block.data.entries.map((e) => [e.pageLabel, e.kind ?? "", quote(byId, e.citationId), where(byId.get(e.citationId))]),
              },
            ]
          : []),
        ...(block.data.edges.length > 0
          ? [
              {
                title: "Connections",
                columns: ["From", "Relation", "To"],
                rows: block.data.edges.map((e) => [label.get(e.src) ?? e.src, e.relation ?? "appears with", label.get(e.dst) ?? e.dst]),
              },
            ]
          : []),
      ];
    }
    default:
      return [];
  }
}

/**
 * A table as CSV (RFC 4180). A cell that a spreadsheet would run as a formula (it starts with =, +, - or @, or a tab or carriage return)
 * is written with a leading apostrophe: the text is a stranger's document, and opening an export must not execute it.
 */
export function toCsv(table: Table): string {
  const cell = (value: string | number): string => {
    let text = String(value);
    if (typeof value === "string" && /^[=+\-@\t\r]/.test(text)) text = `'${text}`;
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  return [table.columns, ...table.rows].map((r) => r.map(cell).join(",")).join("\r\n") + "\r\n";
}
