const state = {
  templateBuffer: null,
  roster: [],
  events: [],
  warnings: [],
  reportDays: { 数学类: [], 中外: [] },
  filter: "全部",
};
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 3000);
}

function settings() {
  return {
    year: Number($("#yearInput").value),
    grade: $("#gradeInput").value.trim(),
    month: Number($("#monthInput").value),
    period: $("#periodInput").value,
    math_days: Number($("#mathDaysInput").value),
    intl_days: Number($("#intlDaysInput").value),
  };
}

function goTo(step) {
  [1, 2, 3].forEach((number) => {
    $(`#step${number}`).classList.toggle("hidden", number !== step);
    $(`.step[data-step="${number}"]`).classList.toggle("active", number === step);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[character]));
}

function normaliseLine(line) {
  return String(line)
    .replace(/[\u200b\ufeff]/g, "")
    .replace(/[ＩI]/g, "1")
    .replace(/[ＯO]/g, "0")
    .replace(/：/g, ":")
    .replace(/，/g, ",")
    .trim();
}

function looksLikeSender(line) {
  return /(?:数学类|中外|应数)\s*25\d{2}.*[-—_].*[\u4e00-\u9fff]{2,5}$/.test(line)
    || line.includes("工作群")
    || /^(群主|群成员|撤回了一条)/.test(line);
}

function validIsoDate(year, month, day) {
  const value = new Date(Date.UTC(year, month - 1, day));
  if (value.getUTCFullYear() !== year || value.getUTCMonth() !== month - 1 || value.getUTCDate() !== day) return null;
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function parseChatText(text) {
  const config = settings();
  const names = [...new Set(state.roster.map((student) => student.name))].sort((a, b) => b.length - a.length);
  const byName = new Map();
  state.roster.forEach((student) => {
    if (!byName.has(student.name)) byName.set(student.name, []);
    byName.get(student.name).push(student);
  });
  let currentDate = null;
  let currentGroup = null;
  let currentType = "缺勤";
  let sequence = 0;
  const reports = new Map();
  const reportDays = { 数学类: new Set(), 中外: new Set() };
  const warnings = [];

  function reportBucket(eventType) {
    if (!currentDate || !currentGroup) return null;
    const key = `${currentDate}|${currentGroup}|${eventType}`;
    let report = reports.get(key);
    if (!report || report.sequence < sequence) {
      report = { sequence, events: [] };
      reports.set(key, report);
    }
    return report;
  }

  for (const originalLine of String(text).replace(/\r/g, "\n").split("\n")) {
    const line = normaliseLine(originalLine);
    if (!line) continue;
    const dateMatch = line.match(/(?:(20\d{2})\s*[年/.-]\s*)?(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?/);
    if (dateMatch) {
      const year = Number(dateMatch[1] || config.year);
      const month = Number(dateMatch[2] || config.month);
      const day = Number(dateMatch[3]);
      currentDate = validIsoDate(year, month, day);
      sequence += 1;
      currentType = "缺勤";
      currentGroup = null;
      if (!currentDate) warnings.push(`日期无法识别：${line}`);
    }

    let groupFound = false;
    if (line.includes("数学类")) {
      currentGroup = "数学类";
      groupFound = true;
    } else if (line.includes("中外")) {
      currentGroup = "中外";
      groupFound = true;
    }
    if (groupFound && currentDate) reportDays[currentGroup].add(currentDate);

    if (["无人缺勤", "无人旷课", "全勤", "无缺勤"].some((token) => line.includes(token))) {
      currentType = "缺勤";
      const bucket = reportBucket(currentType);
      if (bucket) bucket.events = [];
      continue;
    }
    if (line.includes("早退")) currentType = "早退";
    else if (line.includes("请假")) currentType = "请假";
    else if (line.includes("缺勤") || line.includes("旷课")) currentType = "缺勤";

    if (looksLikeSender(line) && !dateMatch && !["缺勤", "早退", "请假"].some((token) => line.includes(token))) continue;
    const matchedNames = names.filter((name) => line.includes(name));
    if (!matchedNames.length) {
      if (/(?:25\d{2}\s*[-—_:：]?\s*[\u4e00-\u9fff·]{2,6}|[\u4e00-\u9fff·]{2,6}\s*25\d{2})/.test(line) && !looksLikeSender(line)) {
        warnings.push(`疑似名单但未匹配：${line}`);
      }
      continue;
    }
    if (!currentDate || !currentGroup) {
      warnings.push(`缺少日期或类别，已跳过：${line}`);
      continue;
    }

    const classCode = line.match(/25\d{2}/)?.[0] || null;
    for (const name of matchedNames) {
      let candidates = (byName.get(name) || []).filter((student) => student.group === currentGroup);
      if (classCode) {
        const narrowed = candidates.filter((student) => student.class_code === classCode);
        if (narrowed.length) candidates = narrowed;
        else if (candidates.length) warnings.push(`班级与名单不一致，已按姓名匹配：${line}（名单为${candidates[0].class_code}）`);
      }
      if (candidates.length !== 1) {
        warnings.push(`姓名需要人工确认：${line}`);
        continue;
      }
      const student = candidates[0];
      const bucket = reportBucket(currentType);
      if (!bucket) continue;
      const event = {
        date: currentDate,
        group: currentGroup,
        type: currentType,
        name: student.name,
        class_name: student.class_name,
        class_code: student.class_code,
        student_id: student.student_id,
        roster_row: student.row,
        source: line,
      };
      const identity = `${event.date}|${event.type}|${event.student_id}`;
      if (!bucket.events.some((item) => `${item.date}|${item.type}|${item.student_id}` === identity)) bucket.events.push(event);
    }
  }

  const events = [...reports.values()].flatMap((report) => report.events);
  events.sort((a, b) => `${a.date}|${a.group}|${a.type}|${a.class_code}|${a.name}`.localeCompare(`${b.date}|${b.group}|${b.type}|${b.class_code}|${b.name}`, "zh-CN"));
  return {
    events,
    warnings: [...new Set(warnings)],
    reportDays: { 数学类: [...reportDays.数学类].sort(), 中外: [...reportDays.中外].sort() },
  };
}

function rosterOptions(event) {
  return state.roster
    .filter((student) => student.group === event.group && (!event.class_code || student.class_code === event.class_code))
    .map((student) => `<option value="${escapeHtml(student.student_id)}" ${student.student_id === event.student_id ? "selected" : ""}>${escapeHtml(student.name)}</option>`)
    .join("");
}

function classOptions(event) {
  const classes = [...new Set(state.roster.filter((student) => student.group === event.group).map((student) => student.class_code))].sort();
  return classes.map((value) => `<option ${value === event.class_code ? "selected" : ""}>${value}</option>`).join("");
}

function filteredEvents() {
  if (state.filter === "全部") return state.events;
  if (state.filter === "请假") return state.events.filter((event) => event.type === "请假");
  return state.events.filter((event) => event.group === state.filter);
}

function updateStats() {
  $("#recognisedStat").textContent = state.events.length;
  $("#absenceStat").textContent = state.events.filter((event) => event.type === "缺勤").length;
  $("#earlyStat").textContent = state.events.filter((event) => event.type === "早退").length;
  $("#leaveStat").textContent = state.events.filter((event) => event.type === "请假").length;
}

function renderEvents() {
  const events = filteredEvents();
  $("#eventsBody").innerHTML = events.map((event) => {
    const index = state.events.indexOf(event);
    return `<tr data-index="${index}">
      <td><input class="event-date" type="date" value="${escapeHtml(event.date)}"></td>
      <td><select class="event-group"><option ${event.group === "数学类" ? "selected" : ""}>数学类</option><option ${event.group === "中外" ? "selected" : ""}>中外</option></select></td>
      <td><select class="event-class">${classOptions(event)}</select></td>
      <td><select class="event-name name-select">${rosterOptions(event)}</select></td>
      <td><select class="event-type"><option ${event.type === "缺勤" ? "selected" : ""}>缺勤</option><option ${event.type === "早退" ? "selected" : ""}>早退</option><option ${event.type === "请假" ? "selected" : ""}>请假</option></select></td>
      <td><button class="delete-row" title="删除">×</button></td>
    </tr>`;
  }).join("");
  $("#emptyState").classList.toggle("hidden", events.length > 0);
  updateStats();
}

function syncStudent(event, studentId) {
  const student = state.roster.find((item) => item.student_id === studentId);
  if (!student) return;
  Object.assign(event, {
    student_id: student.student_id,
    name: student.name,
    class_name: student.class_name,
    class_code: student.class_code,
    roster_row: student.row,
    group: student.group,
  });
}

function addEvent() {
  if (!state.roster.length) return showToast("请先选择名单模板");
  const group = ["数学类", "中外"].includes(state.filter) ? state.filter : "数学类";
  const student = state.roster.find((item) => item.group === group);
  const config = settings();
  const day = config.period === "上半月" ? 1 : 16;
  state.events.push({
    date: `${config.year}-${String(config.month).padStart(2, "0")}-${String(day).padStart(2, "0")}`,
    group,
    type: "缺勤",
    name: student.name,
    class_name: student.class_name,
    class_code: student.class_code,
    student_id: student.student_id,
    roster_row: student.row,
    source: "人工添加",
  });
  renderEvents();
}

function updateRosterDisplay() {
  if (!state.roster.length) {
    $("#rosterBadge").textContent = "请先选择名单模板";
    $("#templateSummary").textContent = "尚未选择模板";
    $("#templateCard").classList.remove("ready");
    return;
  }
  const mathCount = state.roster.filter((student) => student.group === "数学类").length;
  const intlCount = state.roster.filter((student) => student.group === "中外").length;
  $("#rosterBadge").textContent = `当前名单 ${state.roster.length} 人 · 数学类 ${mathCount} · 中外 ${intlCount}`;
  $("#templateSummary").textContent = `名单已就绪：${state.roster.length} 人（数学类 ${mathCount}，中外 ${intlCount}）`;
  $("#templateCard").classList.add("ready");
}

async function useTemplateBuffer(buffer, persist = true) {
  const roster = await BrowserXlsx.parseRoster(buffer);
  state.templateBuffer = buffer.slice(0);
  state.roster = roster;
  if (persist) await BrowserXlsx.saveTemplate(buffer);
  updateRosterDisplay();
  return roster;
}

async function handleTemplateFile(file) {
  if (!file || !file.name.toLowerCase().endsWith(".xlsx")) throw new Error("请选择 .xlsx 名单模板");
  if (file.size > 20 * 1024 * 1024) throw new Error("模板不能超过 20MB");
  const roster = await useTemplateBuffer(await file.arrayBuffer(), true);
  showToast(`模板已保存在本设备，共 ${roster.length} 人`);
}

async function parseText() {
  if (!state.roster.length) return showToast("请先选择当前名单 Excel 模板");
  const text = $("#chatInput").value.trim();
  if (!text) return showToast("请先粘贴或导入群聊文字");
  const button = $("#parseBtn");
  button.disabled = true;
  button.textContent = "正在本机识别…";
  try {
    const result = parseChatText(text);
    state.events = result.events;
    state.warnings = result.warnings;
    state.reportDays = result.reportDays;
    const warningBox = $("#warningBox");
    warningBox.classList.toggle("hidden", !state.warnings.length);
    warningBox.textContent = state.warnings.length
      ? `需要人工确认的内容（${state.warnings.length}）：\n${state.warnings.slice(0, 8).join("\n")}${state.warnings.length > 8 ? "\n…" : ""}`
      : "";
    $("#coverageText").textContent = `从文字中识别到检查日期：数学类 ${state.reportDays.数学类.length} 天，中外 ${state.reportDays.中外.length} 天。最终比例以第一步填写的检查天数为准。`;
    state.filter = "全部";
    $$(".filter").forEach((item) => item.classList.toggle("active", item.dataset.filter === "全部"));
    renderEvents();
    goTo(2);
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = "开始识别 <span>→</span>";
  }
}

function prepareExport() {
  const counted = state.events.filter((event) => event.type !== "请假");
  const uniqueStudents = new Set(counted.map((event) => event.student_id)).size;
  const config = settings();
  $("#exportSummary").innerHTML = `<b>${config.year} 年 ${config.month} 月${escapeHtml(config.period)}</b><br>数学类 ${config.math_days} 天 · 中外 ${config.intl_days} 天 · 涉及 ${uniqueStudents} 名学生 · ${counted.length} 条计入记录`;
  goTo(3);
}

async function downloadWorkbook() {
  if (!state.templateBuffer) return showToast("名单模板已丢失，请重新选择");
  const button = $("#downloadBtn");
  button.disabled = true;
  button.textContent = "正在本机生成…";
  try {
    const config = settings();
    const blob = await BrowserXlsx.buildWorkbook(state.templateBuffer, state.roster, state.events, config);
    const filename = `数统${config.month}月${config.period}晚自习公示表.xlsx`;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    showToast("Excel 已在本设备生成并开始下载");
  } catch (error) {
    showToast(`生成失败：${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = "下载 Excel 公示表";
  }
}

function loadFormatExample() {
  if (!state.roster.length) return showToast("请先选择模板，示例会使用名单中的姓名");
  const math = state.roster.find((student) => student.group === "数学类");
  const intl = state.roster.find((student) => student.group === "中外");
  const month = settings().month;
  $("#chatInput").value = `${month}月1日\n数学类\n缺勤\n${math.class_code} ${math.name}\n\n${month}月1日\n中外\n无人缺勤\n\n${month}月2日\n中外\n早退\n${intl.class_code} ${intl.name}`;
  $("#chatInput").dispatchEvent(new Event("input"));
  showToast("已载入格式示例；姓名来自本设备模板");
}

$("#chatInput").addEventListener("input", (event) => $("#charCount").textContent = `${event.target.value.length} 字`);
$("#sampleBtn").addEventListener("click", loadFormatExample);
$("#textFileInput").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    $("#chatInput").value = await file.text();
    $("#chatInput").dispatchEvent(new Event("input"));
    showToast("聊天文本已导入");
  } catch (error) { showToast(error.message); }
  event.target.value = "";
});
$("#templateInputTop").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try { await handleTemplateFile(file); } catch (error) { showToast(error.message); }
  event.target.value = "";
});
$("#templateInput").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const status = $("#templateStatus");
  status.textContent = "正在本机检查模板…";
  try {
    const roster = await handleTemplateFile(file);
    status.textContent = `新模板已启用，共 ${roster.length} 人`;
  } catch (error) { status.textContent = error.message; }
  event.target.value = "";
});
$("#parseBtn").addEventListener("click", parseText);
$("#backBtn").addEventListener("click", () => goTo(1));
$("#addEventBtn").addEventListener("click", addEvent);
$("#toExportBtn").addEventListener("click", prepareExport);
$("#downloadBtn").addEventListener("click", downloadWorkbook);
$("#againBtn").addEventListener("click", () => goTo(1));

$("#eventsBody").addEventListener("change", (event) => {
  const row = event.target.closest("tr");
  if (!row) return;
  const item = state.events[Number(row.dataset.index)];
  if (event.target.classList.contains("event-date")) item.date = event.target.value;
  if (event.target.classList.contains("event-type")) item.type = event.target.value;
  if (event.target.classList.contains("event-name")) { syncStudent(item, event.target.value); renderEvents(); }
  if (event.target.classList.contains("event-group")) {
    item.group = event.target.value;
    const student = state.roster.find((candidate) => candidate.group === item.group);
    if (student) syncStudent(item, student.student_id);
    renderEvents();
  }
  if (event.target.classList.contains("event-class")) {
    item.class_code = event.target.value;
    const student = state.roster.find((candidate) => candidate.group === item.group && candidate.class_code === item.class_code);
    if (student) syncStudent(item, student.student_id);
    renderEvents();
  }
  updateStats();
});
$("#eventsBody").addEventListener("click", (event) => {
  if (!event.target.classList.contains("delete-row")) return;
  state.events.splice(Number(event.target.closest("tr").dataset.index), 1);
  renderEvents();
});
$(".filters").addEventListener("click", (event) => {
  const button = event.target.closest(".filter");
  if (!button) return;
  state.filter = button.dataset.filter;
  $$(".filter").forEach((item) => item.classList.toggle("active", item === button));
  renderEvents();
});

let deferredInstallPrompt = null;
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredInstallPrompt = event;
  $("#installBtn").classList.remove("hidden");
});
$("#installBtn").addEventListener("click", async () => {
  if (!deferredInstallPrompt) return;
  deferredInstallPrompt.prompt();
  await deferredInstallPrompt.userChoice;
  deferredInstallPrompt = null;
  $("#installBtn").classList.add("hidden");
});

$("#yearInput").value = new Date().getFullYear();
updateRosterDisplay();
BrowserXlsx.loadSavedTemplate()
  .then((buffer) => buffer && useTemplateBuffer(buffer, false))
  .catch(() => showToast("未能读取本设备保存的模板，请重新选择"));
if ("serviceWorker" in navigator) window.addEventListener("load", () => navigator.serviceWorker.register("./service-worker.js"));
