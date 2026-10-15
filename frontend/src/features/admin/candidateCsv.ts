import type { AdminCandidateWrite } from "../../types/admin";

/** Parse quoted CSV fields, escaped quotes, CRLF, and embedded newlines without executing content. */
export function candidateCsv(text: string): AdminCandidateWrite[] {
  if (text.length > 1_000_000)
    throw new Error(
      "CSV is too large. Import at most 500 candidates at a time.",
    );
  const rows: string[][] = [];
  let row: string[] = [];
  let value = "";
  let quoted = false;
  let ended = false;
  const field = () => {
    row.push(value);
    value = "";
    ended = false;
  };
  const line = () => {
    field();
    if (row.some((item) => item.trim())) rows.push(row);
    row = [];
  };
  const input = text.replace(/^\uFEFF/, "");
  for (let index = 0; index < input.length; index++) {
    const char = input[index];
    if (quoted) {
      if (char === '"') {
        if (input[index + 1] === '"') {
          value += '"';
          index++;
        } else {
          quoted = false;
          ended = true;
        }
      } else value += char;
    } else if (char === "," || char === "\n" || char === "\r") {
      if (char === ",") field();
      else {
        line();
        if (char === "\r" && input[index + 1] === "\n") index++;
      }
    } else if (char === '"') {
      if (value || ended)
        throw new Error(
          "Invalid CSV quoting. Quote the entire field and escape quotes with two quotes.",
        );
      quoted = true;
    } else {
      if (ended) throw new Error("Unexpected text after a quoted CSV field.");
      value += char;
    }
  }
  if (quoted) throw new Error("The CSV ends inside a quoted field.");
  if (value || row.length || ended) line();
  const headers = rows.shift()?.map((item) => item.trim().toLowerCase()) || [];
  const required = ["full_name", "roll_number"];
  if (
    new Set(headers).size !== headers.length ||
    required.some((header) => !headers.includes(header)) ||
    headers.some(
      (header) => ![...required, "father_name", "email", "google_subject", "status"].includes(header),
    )
  ) {
    throw new Error(
      "Use unique CSV headers: roll_number,full_name,father_name,email,google_subject,status. Roll number and full name are required.",
    );
  }
  if (!rows.length || rows.length > 500)
    throw new Error("Import between 1 and 500 candidates.");
  const emails = new Set<string>();
  const rolls = new Set<string>();
  return rows.map((cells, index) => {
    if (cells.length !== headers.length)
      throw new Error(`Row ${index + 2} has an unexpected number of fields.`);
    const record = Object.fromEntries(
      headers.map((key, column) => [key, cells[column].trim()]),
    );
    const status = record.status || "APPROVED";
    if (status !== "APPROVED" && status !== "DISABLED")
      throw new Error(`Row ${index + 2}: status must be APPROVED or DISABLED.`);
    const email = record.email?.toLowerCase() || null;
    if (!record.full_name || !record.roll_number || (!record.father_name && !email))
      throw new Error(
        `Row ${index + 2}: full name, roll number, and father’s name are required for candidate login.`,
      );
    if ((email && emails.has(email)) || rolls.has(record.roll_number.toLowerCase()))
      throw new Error(
        `Row ${index + 2}: duplicate email or roll number in this file.`,
      );
    if (email) emails.add(email);
    rolls.add(record.roll_number.toLowerCase());
    return {
      email,
      full_name: record.full_name,
      father_name: record.father_name || null,
      roll_number: record.roll_number,
      google_subject: record.google_subject || null,
      status,
    };
  });
}
