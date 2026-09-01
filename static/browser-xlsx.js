(function () {
  "use strict";

  const MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
  const OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
  const PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships";
  const XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  const parser = new DOMParser();
  const serializer = new XMLSerializer();

  function parseXml(text, label) {
    const document = parser.parseFromString(text, "application/xml");
    const error = document.getElementsByTagName("parsererror")[0];
    if (error) throw new Error(`${label} 不是有效的 Excel XML`);
    return document;
  }

  function normalizeZipPath(path) {
    const result = [];
    String(path).replace(/\\/g, "/").split("/").forEach((part) => {
      if (!part || part === ".") return;
      if (part === "..") result.pop();
      else result.push(part);
    });
    return result.join("/");
  }

  function columnNumber(cellReference) {
    const match = String(cellReference || "").match(/^[A-Z]+/);
    let value = 0;
    for (const character of match ? match[0] : "") value = value * 26 + character.charCodeAt(0) - 64;
    return value;
  }

  function directChild(element, localName) {
    return [...element.children].find((child) => child.localName === localName) || null;
  }

  function cellText(cell, sharedStrings) {
    if (!cell) return "";
    const type = cell.getAttribute("t");
    if (type === "inlineStr") {
      return [...cell.getElementsByTagNameNS(MAIN_NS, "t")].map((node) => node.textContent || "").join("");
    }
    const value = directChild(cell, "v")?.textContent ?? "";
    if (type === "s") return sharedStrings[Number(value)] ?? "";
    return value;
  }

  async function sharedStringsFromZip(zip) {
    const entry = zip.file("xl/sharedStrings.xml");
    if (!entry) return [];
    const document = parseXml(await entry.async("string"), "共享字符串");
    return [...document.getElementsByTagNameNS(MAIN_NS, "si")].map((item) =>
      [...item.getElementsByTagNameNS(MAIN_NS, "t")].map((node) => node.textContent || "").join("")
    );
  }

  async function firstSheetPath(zip) {
    const workbook = parseXml(await zip.file("xl/workbook.xml").async("string"), "工作簿");
    const firstSheet = workbook.getElementsByTagNameNS(MAIN_NS, "sheet")[0];
    if (!firstSheet) throw new Error("模板中没有工作表");
    const relationId = firstSheet.getAttributeNS(OFFICE_REL_NS, "id") || firstSheet.getAttribute("r:id");
    const relationships = parseXml(await zip.file("xl/_rels/workbook.xml.rels").async("string"), "工作簿关系");
    const relation = [...relationships.getElementsByTagNameNS(PACKAGE_REL_NS, "Relationship")]
      .find((item) => item.getAttribute("Id") === relationId);
    if (!relation) throw new Error("无法定位模板主工作表");
    const target = relation.getAttribute("Target") || "";
    return target.startsWith("/") ? normalizeZipPath(target) : normalizeZipPath(`xl/${target}`);
  }

  function findCell(row, reference) {
    return [...row.getElementsByTagNameNS(MAIN_NS, "c")]
      .find((cell) => cell.getAttribute("r") === reference) || null;
  }

  function findOrCreateCell(document, row, reference) {
    const existing = findCell(row, reference);
    if (existing) return existing;
    const cell = document.createElementNS(MAIN_NS, "c");
    cell.setAttribute("r", reference);
    const wanted = columnNumber(reference);
    const laterCell = [...row.children].find((child) => child.localName === "c" && columnNumber(child.getAttribute("r")) > wanted);
    if (laterCell) row.insertBefore(cell, laterCell);
    else row.appendChild(cell);
    return cell;
  }

  function clearCell(cell) {
    cell.removeAttribute("t");
    while (cell.firstChild) cell.removeChild(cell.firstChild);
  }

  function setInlineText(document, cell, value) {
    clearCell(cell);
    if (!value) return;
    cell.setAttribute("t", "inlineStr");
    const inline = document.createElementNS(MAIN_NS, "is");
    const text = document.createElementNS(MAIN_NS, "t");
    text.textContent = value;
    inline.appendChild(text);
    cell.appendChild(inline);
  }

  function setNumber(document, cell, value, formula) {
    clearCell(cell);
    if (formula) {
      const formulaNode = document.createElementNS(MAIN_NS, "f");
      formulaNode.textContent = formula;
      cell.appendChild(formulaNode);
    }
    const valueNode = document.createElementNS(MAIN_NS, "v");
    valueNode.textContent = String(value);
    cell.appendChild(valueNode);
  }

  function chineseDate(isoDate) {
    const [, month, day] = String(isoDate).split("-").map(Number);
    return `${month}月${day}日`;
  }

  async function parseRoster(buffer) {
    const zip = await JSZip.loadAsync(buffer.slice(0));
    const sharedStrings = await sharedStringsFromZip(zip);
    const sheetPath = await firstSheetPath(zip);
    const sheetEntry = zip.file(sheetPath);
    if (!sheetEntry) throw new Error("模板缺少主工作表文件");
    const sheet = parseXml(await sheetEntry.async("string"), "主工作表");
    const roster = [];
    for (const row of sheet.getElementsByTagNameNS(MAIN_NS, "row")) {
      const rowNumber = Number(row.getAttribute("r"));
      if (rowNumber < 3) continue;
      const values = {};
      for (const cell of row.getElementsByTagNameNS(MAIN_NS, "c")) {
        values[columnNumber(cell.getAttribute("r"))] = cellText(cell, sharedStrings).trim();
      }
      const name = values[2] || "";
      const className = values[3] || "";
      const studentId = values[4] || "";
      if (!name || !className || !studentId) continue;
      const classCode = className.match(/25\d{2}/)?.[0] || "";
      roster.push({
        row: rowNumber,
        serial: roster.length + 1,
        name,
        class_name: className,
        class_code: classCode,
        student_id: studentId,
        group: className.includes("数学类") ? "数学类" : "中外",
      });
    }
    if (!roster.length) throw new Error("未找到名单：请确认第2行为表头，第3行起是学生名单");
    return roster;
  }

  async function buildWorkbook(buffer, roster, events, settings) {
    const zip = await JSZip.loadAsync(buffer.slice(0));
    const sheetPath = await firstSheetPath(zip);
    const sheet = parseXml(await zip.file(sheetPath).async("string"), "主工作表");
    const rows = new Map([...sheet.getElementsByTagNameNS(MAIN_NS, "row")]
      .map((row) => [Number(row.getAttribute("r")), row]));
    const byStudent = new Map(roster.map((student) => [student.student_id, { 缺勤: new Set(), 早退: new Set() }]));
    for (const event of events) {
      if (!["缺勤", "早退"].includes(event.type) || !byStudent.has(event.student_id)) continue;
      if (!/^20\d{2}-\d{2}-\d{2}$/.test(event.date || "")) continue;
      byStudent.get(event.student_id)[event.type].add(event.date);
    }

    const mathDays = Math.max(1, Number(settings.math_days) || 1);
    const intlDays = Math.max(1, Number(settings.intl_days) || 1);
    const grade = String(settings.grade || "25级").trim() || "25级";
    const title = `数统${grade}晚自习${settings.month}月${settings.period}公示表（本轮晚自习数学类${mathDays}天 中外${intlDays}天）`;
    const titleRow = rows.get(1);
    if (titleRow) setInlineText(sheet, findOrCreateCell(sheet, titleRow, "A1"), title);

    for (const student of roster) {
      const row = rows.get(student.row);
      if (!row) continue;
      const days = student.group === "数学类" ? mathDays : intlDays;
      const absenceDates = [...byStudent.get(student.student_id).缺勤].sort();
      const earlyDates = [...byStudent.get(student.student_id).早退].sort();
      const absenceCount = absenceDates.length;
      const earlyCount = earlyDates.length;
      const abnormal = Math.min(1, (absenceCount + earlyCount) / days);
      const attendance = Math.max(0, 1 - abnormal);
      const rowNumber = student.row;
      setNumber(sheet, findOrCreateCell(sheet, row, `E${rowNumber}`), attendance, `MAX(0,1-F${rowNumber})`);
      setNumber(sheet, findOrCreateCell(sheet, row, `F${rowNumber}`), abnormal, `MIN(1,(G${rowNumber}+H${rowNumber})/${days})`);
      setNumber(sheet, findOrCreateCell(sheet, row, `G${rowNumber}`), absenceCount);
      setNumber(sheet, findOrCreateCell(sheet, row, `H${rowNumber}`), earlyCount);
      setInlineText(sheet, findOrCreateCell(sheet, row, `I${rowNumber}`), absenceDates.map(chineseDate).join("，"));
      setInlineText(sheet, findOrCreateCell(sheet, row, `J${rowNumber}`), earlyDates.map(chineseDate).join("，"));
    }
    zip.file(sheetPath, `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>${serializer.serializeToString(sheet.documentElement)}`);

    const workbook = parseXml(await zip.file("xl/workbook.xml").async("string"), "工作簿");
    let calcPr = workbook.getElementsByTagNameNS(MAIN_NS, "calcPr")[0];
    if (!calcPr) {
      calcPr = workbook.createElementNS(MAIN_NS, "calcPr");
      workbook.documentElement.appendChild(calcPr);
    }
    calcPr.setAttribute("calcMode", "auto");
    calcPr.setAttribute("fullCalcOnLoad", "1");
    calcPr.setAttribute("forceFullCalc", "1");
    zip.file("xl/workbook.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>${serializer.serializeToString(workbook.documentElement)}`);
    zip.remove("xl/calcChain.xml");

    return zip.generateAsync({ type: "blob", compression: "DEFLATE", compressionOptions: { level: 6 }, mimeType: XLSX_MIME });
  }

  function openTemplateDatabase() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open("evening-study-generator", 1);
      request.onupgradeneeded = () => request.result.createObjectStore("files");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async function saveTemplate(buffer) {
    const database = await openTemplateDatabase();
    await new Promise((resolve, reject) => {
      const transaction = database.transaction("files", "readwrite");
      transaction.objectStore("files").put(buffer.slice(0), "template");
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error);
    });
    database.close();
  }

  async function loadSavedTemplate() {
    const database = await openTemplateDatabase();
    const result = await new Promise((resolve, reject) => {
      const request = database.transaction("files", "readonly").objectStore("files").get("template");
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
    database.close();
    return result;
  }

  window.BrowserXlsx = { parseRoster, buildWorkbook, saveTemplate, loadSavedTemplate, XLSX_MIME };
})();
