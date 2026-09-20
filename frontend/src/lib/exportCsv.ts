interface Column<T> {
  header: string;
  value: (row: T) => string | number | null | undefined;
}

function escapeCsvCell(value: string | number | null | undefined): string {
  const s = value == null ? "" : String(value);
  return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** Экспорт текущей загруженной выборки (с учётом активных фильтров/сортировки) — не всей
 * таблицы на сервере. Достаточно для выгрузки того, что видит пользователь на экране. */
export function exportCsv<T>(filename: string, rows: T[], columns: Column<T>[]): void {
  const lines = [
    columns.map((c) => escapeCsvCell(c.header)).join(";"),
    ...rows.map((row) => columns.map((c) => escapeCsvCell(c.value(row))).join(";")),
  ];
  // BOM — чтобы Excel на Windows сразу определил UTF-8 и не показал кракозябры на кириллице.
  const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
