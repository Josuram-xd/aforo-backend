// CSV helpers with formula-injection protection (OWASP "CSV Injection").
const FORMULA_PREFIX = /^[=+\-@\t\r]/;

export function csvCell(value: unknown): string {
  let text = value === null || value === undefined ? "" : String(value);
  const guarded = FORMULA_PREFIX.test(text);
  if (guarded) text = "'" + text;
  if (guarded || /[",\r\n]/.test(text)) {
    text = '"' + text.replaceAll('"', '""') + '"';
  }
  return text;
}

export function csvRow(values: unknown[]): string {
  return values.map(csvCell).join(",") + "\r\n";
}

const bogotaFormat = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "America/Bogota",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

/** "2026-10-13 08:30:00" in America/Bogota. */
export function formatBogota(iso: string): string {
  return bogotaFormat.format(new Date(iso));
}
