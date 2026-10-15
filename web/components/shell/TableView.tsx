"use client";

// A block read as a table (D-44): the same facts in rows and columns, each column sortable, a filter box, and the table as CSV. It is
// built from `tablesOf`, so it shows nothing the block does not. Sorting and filtering are local to the pane and change no data.

import { useMemo, useState } from "react";

import { toCsv, type Table } from "@/lib/tables";

type Sort = { column: number; direction: "ascending" | "descending" } | null;

const compare = (a: string | number, b: string | number) =>
  typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b), undefined, { numeric: true });

function One({ table }: { table: Table }) {
  const [sort, setSort] = useState<Sort>(null);
  const [filter, setFilter] = useState("");
  const rows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const kept = needle ? table.rows.filter((r) => r.some((c) => String(c).toLowerCase().includes(needle))) : [...table.rows];
    if (sort) {
      kept.sort((a, b) => (sort.direction === "ascending" ? 1 : -1) * compare(a[sort.column] ?? "", b[sort.column] ?? ""));
    }
    return kept;
  }, [table.rows, filter, sort]);

  const download = () => {
    const url = URL.createObjectURL(new Blob([toCsv(table)], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${table.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "table"}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const toggle = (column: number) =>
    setSort((s) =>
      s && s.column === column
        ? s.direction === "ascending"
          ? { column, direction: "descending" }
          : null
        : { column, direction: "ascending" },
    );

  return (
    <section aria-label={table.title} className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-xs font-medium uppercase tracking-wide text-stone-500">{table.title}</h3>
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter rows"
          aria-label={`Filter ${table.title}`}
          className="min-w-0 flex-1 rounded border border-stone-300 px-2 py-0.5 text-xs"
        />
        <button type="button" onClick={download} className="rounded border border-stone-300 px-2 py-0.5 text-xs text-stone-700">
          Download CSV
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-xs">
          <thead>
            <tr>
              {table.columns.map((name, i) => (
                <th
                  key={name}
                  scope="col"
                  aria-sort={sort?.column === i ? sort.direction : "none"}
                  className="border-b border-stone-300 bg-stone-50 px-2 py-1 font-medium text-stone-700"
                >
                  <button type="button" onClick={() => toggle(i)} className="text-left font-medium hover:underline">
                    {name}
                    {sort?.column === i && <span aria-hidden="true">{sort.direction === "ascending" ? " ▲" : " ▼"}</span>}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, r) => (
              <tr key={r} className="odd:bg-white even:bg-stone-50">
                {row.map((cell, c) => (
                  <td key={c} className="border-b border-stone-200 px-2 py-1 align-top text-stone-800">
                    {String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-stone-500" role="status">
        {rows.length} of {table.rows.length} {table.rows.length === 1 ? "row" : "rows"}
      </p>
    </section>
  );
}

export function TableView({ tables }: { tables: Table[] }) {
  return (
    <div className="space-y-5">
      {tables.map((t) => (
        <One key={t.title} table={t} />
      ))}
    </div>
  );
}
