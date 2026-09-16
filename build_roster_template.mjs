import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [sourcePath, templatePath, outputPath, previewPath] = process.argv.slice(2);
if (!sourcePath || !templatePath || !outputPath || !previewPath) {
  throw new Error("usage: node build_roster_template.mjs <source.xlsx> <template.xlsx> <output.xlsx> <preview.png>");
}

const sourceBook = await SpreadsheetFile.importXlsx(await FileBlob.load(sourcePath));
const roster = [];
for (const sheet of sourceBook.worksheets.items) {
  const values = sheet.getUsedRange(true)?.values || [];
  for (let index = 1; index < values.length; index += 1) {
    const row = values[index] || [];
    const name = String(row[1] ?? "").trim();
    const className = String(row[3] ?? "").trim();
    const studentId = String(row[4] ?? "").replace(/\.0$/, "").trim();
    if (!name && !className && !studentId) continue;
    if (!name || !className || !/^\d{9}$/.test(studentId)) {
      throw new Error(`名单数据不完整：${sheet.name} 第 ${index + 1} 行`);
    }
    roster.push({ name, className, studentId });
  }
}

const ids = new Set();
for (const student of roster) {
  if (ids.has(student.studentId)) throw new Error(`学号重复：${student.studentId}`);
  ids.add(student.studentId);
}
if (roster.length !== 257) throw new Error(`预期 257 人，实际 ${roster.length} 人`);

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(templatePath));
const sheet = workbook.worksheets.getItemAt(0);
const existingLastRow = sheet.getUsedRange(true).rowCount;
const targetLastRow = roster.length + 2;

for (let row = existingLastRow + 1; row <= targetLastRow; row += 1) {
  sheet.getRange(`A${existingLastRow}:J${existingLastRow}`).copyTo(sheet.getRange(`A${row}:J${row}`), "all");
}

sheet.getRange("A1").values = [["数统26级晚自习x月x半月公示表（本轮晚自习数学类x天 中外x天）"]];
sheet.getRange("A2:J2").values = [["序号", "姓名", "班级", "学号", "出勤率", "缺勤早退率", "缺勤次数", "早退次数", "缺勤日期", "早退日期"]];

sheet.getRange(`A3:D${targetLastRow}`).values = roster.map((student, index) => [
  index + 1,
  student.name,
  student.className,
  student.studentId,
]);
sheet.getRange(`E3:F${targetLastRow}`).formulas = roster.map((_, index) => {
  const row = index + 3;
  return [`=MAX(0,1-F${row})`, `=MIN(1,(G${row}+H${row})/1)`];
});
sheet.getRange(`G3:J${targetLastRow}`).values = roster.map(() => [0, 0, "", ""]);
sheet.getRange(`E3:F${targetLastRow}`).format.numberFormat = "0.00%";

if (existingLastRow > targetLastRow) {
  sheet.getRange(`A${targetLastRow + 1}:J${existingLastRow}`).clear({ applyTo: "contents" });
}

workbook.recalculate();
const checks = await workbook.inspect({
  kind: "table,formula,match",
  sheetId: sheet.name,
  range: `A1:J${targetLastRow}`,
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  tableMaxRows: 8,
  tableMaxCols: 10,
  maxChars: 8000,
});
console.log(checks.ndjson);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
const preview = await workbook.render({ sheetName: sheet.name, range: "A1:J22", scale: 1.2, format: "png" });
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
console.log(JSON.stringify({ total: roster.length, outputPath, targetLastRow }, null, 2));
