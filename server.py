from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import shutil
import threading
import urllib.parse
import webbrowser
import zipfile
from collections import defaultdict
from datetime import date, datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
TEMPLATE_PATH = DATA_DIR / "晚自习公示模板.xlsx"

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
ET.register_namespace("", NS_MAIN)
ET.register_namespace("r", NS_REL)


def qname(namespace: str, tag: str) -> str:
    return f"{{{namespace}}}{tag}"


def column_number(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref or "")
    value = 0
    for char in letters.group(0) if letters else "":
        value = value * 26 + ord(char) - 64
    return value


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    strings: list[str] = []
    for si in root.findall(qname(NS_MAIN, "si")):
        strings.append("".join(node.text or "" for node in si.iter(qname(NS_MAIN, "t"))))
    return strings


def _first_sheet_path(archive: zipfile.ZipFile) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    sheet = workbook.find(f"{qname(NS_MAIN, 'sheets')}/{qname(NS_MAIN, 'sheet')}")
    if sheet is None:
        raise ValueError("模板中没有工作表")
    relation_id = sheet.attrib.get(qname(NS_REL, "id"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    for rel in rels.findall(qname(NS_PKG_REL, "Relationship")):
        if rel.attrib.get("Id") == relation_id:
            target = rel.attrib["Target"].replace("\\", "/")
            if target.startswith("/"):
                return target.lstrip("/")
            return "xl/" + target.lstrip("/")
    raise ValueError("无法定位模板主工作表")


def _cell_text(cell: ET.Element | None, shared_strings: list[str]) -> str:
    if cell is None:
        return ""
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(qname(NS_MAIN, "t")))
    value = cell.find(qname(NS_MAIN, "v"))
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        try:
            return shared_strings[int(value.text)]
        except (ValueError, IndexError):
            return ""
    return value.text


def load_roster(template_path: Path = TEMPLATE_PATH) -> list[dict]:
    if not template_path.exists():
        raise FileNotFoundError(f"找不到模板：{template_path}")
    with zipfile.ZipFile(template_path) as archive:
        shared = _read_shared_strings(archive)
        sheet_root = ET.fromstring(archive.read(_first_sheet_path(archive)))

    rows: list[dict] = []
    sheet_data = sheet_root.find(qname(NS_MAIN, "sheetData"))
    if sheet_data is None:
        raise ValueError("模板主工作表没有数据")
    for row in sheet_data.findall(qname(NS_MAIN, "row")):
        row_number = int(row.attrib.get("r", "0"))
        if row_number < 3:
            continue
        values: dict[int, str] = {}
        for cell in row.findall(qname(NS_MAIN, "c")):
            values[column_number(cell.attrib.get("r", ""))] = _cell_text(cell, shared)
        name = values.get(2, "").strip()
        class_name = values.get(3, "").strip()
        student_id = values.get(4, "").strip()
        if not name or not class_name or not student_id:
            continue
        group = "数学类" if "数学类" in class_name else "中外"
        class_code_match = re.search(r"(25\d{2})", class_name)
        rows.append(
            {
                "row": row_number,
                "serial": len(rows) + 1,
                "name": name,
                "class_name": class_name,
                "class_code": class_code_match.group(1) if class_code_match else "",
                "student_id": student_id,
                "group": group,
            }
        )
    if not rows:
        raise ValueError("模板中没有找到名单；请确认第2行为表头，第3行起是名单")
    return rows


DATE_RE = re.compile(
    r"(?:(?P<year>20\d{2})\s*[年/.-]\s*)?(?P<month>\d{1,2})\s*[月/.-]\s*(?P<day>\d{1,2})\s*日?"
)
REPORTISH_RE = re.compile(r"25\d{2}\s*[-—_:：]?\s*[\u4e00-\u9fff·]{2,6}|[\u4e00-\u9fff·]{2,6}\s*25\d{2}")


def _normalise_line(line: str) -> str:
    translation = str.maketrans({"Ｉ": "1", "I": "1", "Ｏ": "0", "O": "0", "：": ":", "，": ","})
    return re.sub(r"[\u200b\ufeff]", "", line.translate(translation)).strip()


def _looks_like_sender(line: str) -> bool:
    return bool(
        re.search(r"(?:数学类|中外|应数)\s*25\d{2}.*[-—_].*[\u4e00-\u9fff]{2,5}$", line)
        or "工作群" in line
        or line.startswith(("群主", "群成员", "撤回了一条"))
    )


def parse_chat_text(text: str, roster: list[dict], default_year: int, default_month: int) -> dict:
    names = sorted({student["name"] for student in roster}, key=len, reverse=True)
    by_name: dict[str, list[dict]] = defaultdict(list)
    for student in roster:
        by_name[student["name"]].append(student)

    current_date: date | None = None
    current_group: str | None = None
    current_type = "缺勤"
    sequence = 0
    reports: dict[tuple[str, str, str], dict] = {}
    report_days: dict[str, set[str]] = {"数学类": set(), "中外": set()}
    warnings: list[str] = []

    def report_bucket(event_type: str) -> dict | None:
        if current_date is None or current_group is None:
            return None
        key = (current_date.isoformat(), current_group, event_type)
        existing = reports.get(key)
        if existing is None or existing["sequence"] < sequence:
            existing = {"sequence": sequence, "events": []}
            reports[key] = existing
        return existing

    for original_line in text.replace("\r", "\n").split("\n"):
        line = _normalise_line(original_line)
        if not line:
            continue

        date_match = DATE_RE.search(line)
        if date_match:
            year = int(date_match.group("year") or default_year)
            month = int(date_match.group("month") or default_month)
            day = int(date_match.group("day"))
            try:
                current_date = date(year, month, day)
                sequence += 1
                current_type = "缺勤"
                current_group = None
            except ValueError:
                warnings.append(f"日期无法识别：{line}")
                current_date = None

        group_found = False
        if "数学类" in line:
            current_group = "数学类"
            group_found = True
        elif "中外" in line:
            current_group = "中外"
            group_found = True

        if group_found and current_date and current_group:
            report_days[current_group].add(current_date.isoformat())

        if any(token in line for token in ("无人缺勤", "无人旷课", "全勤", "无缺勤")):
            current_type = "缺勤"
            bucket = report_bucket(current_type)
            if bucket is not None:
                bucket["events"] = []
            continue
        if "早退" in line:
            current_type = "早退"
        elif "请假" in line:
            current_type = "请假"
        elif "缺勤" in line or "旷课" in line:
            current_type = "缺勤"

        if _looks_like_sender(line) and not date_match and not any(x in line for x in ("缺勤", "早退", "请假")):
            continue

        matched_names = [name for name in names if name in line]
        if not matched_names:
            if REPORTISH_RE.search(line) and not _looks_like_sender(line):
                warnings.append(f"疑似名单但未匹配：{line}")
            continue
        if current_date is None or current_group is None:
            warnings.append(f"缺少日期或类别，已跳过：{line}")
            continue

        class_match = re.search(r"25\d{2}", line)
        class_code = class_match.group(0) if class_match else None
        for name in matched_names:
            candidates = [student for student in by_name[name] if student["group"] == current_group]
            if class_code:
                narrowed = [student for student in candidates if student["class_code"] == class_code]
                if narrowed:
                    candidates = narrowed
                elif candidates:
                    warnings.append(
                        f"班级与名单不一致，已按姓名匹配：{line}（名单为{candidates[0]['class_code']}）"
                    )
            if len(candidates) != 1:
                warnings.append(f"姓名需要人工确认：{line}")
                continue
            student = candidates[0]
            bucket = report_bucket(current_type)
            if bucket is None:
                continue
            event = {
                "date": current_date.isoformat(),
                "group": current_group,
                "type": current_type,
                "name": student["name"],
                "class_name": student["class_name"],
                "class_code": student["class_code"],
                "student_id": student["student_id"],
                "roster_row": student["row"],
                "source": line,
            }
            identity = (event["date"], event["type"], event["student_id"])
            if not any((item["date"], item["type"], item["student_id"]) == identity for item in bucket["events"]):
                bucket["events"].append(event)

    events = []
    for report in reports.values():
        events.extend(report["events"])
    events.sort(key=lambda item: (item["date"], item["group"], item["type"], item["class_code"], item["name"]))
    leave_count = sum(1 for item in events if item["type"] == "请假")
    return {
        "events": events,
        "warnings": list(dict.fromkeys(warnings)),
        "report_days": {group: sorted(days) for group, days in report_days.items()},
        "summary": {
            "absence": sum(1 for item in events if item["type"] == "缺勤"),
            "early": sum(1 for item in events if item["type"] == "早退"),
            "leave": leave_count,
            "recognised": len(events),
        },
    }


def _find_or_create_cell(row: ET.Element, cell_ref: str) -> ET.Element:
    cells = row.findall(qname(NS_MAIN, "c"))
    for cell in cells:
        if cell.attrib.get("r") == cell_ref:
            return cell
    new_cell = ET.Element(qname(NS_MAIN, "c"), {"r": cell_ref})
    wanted = column_number(cell_ref)
    insert_at = len(cells)
    for index, cell in enumerate(cells):
        if column_number(cell.attrib.get("r", "")) > wanted:
            insert_at = index
            break
    row.insert(insert_at, new_cell)
    return new_cell


def _clear_cell(cell: ET.Element) -> None:
    cell.attrib.pop("t", None)
    for child in list(cell):
        cell.remove(child)


def _set_inline_text(cell: ET.Element, value: str) -> None:
    _clear_cell(cell)
    if not value:
        return
    cell.attrib["t"] = "inlineStr"
    inline = ET.SubElement(cell, qname(NS_MAIN, "is"))
    text = ET.SubElement(inline, qname(NS_MAIN, "t"))
    text.text = value


def _set_number(cell: ET.Element, value: int | float, formula: str | None = None) -> None:
    _clear_cell(cell)
    if formula:
        formula_node = ET.SubElement(cell, qname(NS_MAIN, "f"))
        formula_node.text = formula
    value_node = ET.SubElement(cell, qname(NS_MAIN, "v"))
    value_node.text = str(value)


def _format_chinese_date(iso_date: str) -> str:
    value = date.fromisoformat(iso_date)
    return f"{value.month}月{value.day}日"


def build_workbook(
    events: list[dict],
    settings: dict,
    template_path: Path = TEMPLATE_PATH,
) -> bytes:
    roster = load_roster(template_path)
    by_student: dict[str, dict[str, set[str]]] = {
        student["student_id"]: {"缺勤": set(), "早退": set()} for student in roster
    }
    for event in events:
        event_type = event.get("type")
        student_id = str(event.get("student_id", ""))
        event_date = str(event.get("date", ""))
        if event_type in ("缺勤", "早退") and student_id in by_student:
            try:
                date.fromisoformat(event_date)
            except ValueError:
                continue
            by_student[student_id][event_type].add(event_date)

    math_days = max(1, int(settings.get("math_days", 1)))
    intl_days = max(1, int(settings.get("intl_days", 1)))
    year = int(settings.get("year", datetime.now().year))
    month = int(settings.get("month", datetime.now().month))
    period = settings.get("period", "上半月")
    grade = str(settings.get("grade", "25级")).strip() or "25级"
    title = f"数统{grade}晚自习{month}月{period}公示表（本轮晚自习数学类{math_days}天 中外{intl_days}天）"

    with zipfile.ZipFile(template_path, "r") as source:
        files = {name: source.read(name) for name in source.namelist()}
        sheet_path = _first_sheet_path(source)
    sheet_root = ET.fromstring(files[sheet_path])
    sheet_data = sheet_root.find(qname(NS_MAIN, "sheetData"))
    if sheet_data is None:
        raise ValueError("模板主工作表没有数据")
    rows_by_number = {int(row.attrib["r"]): row for row in sheet_data.findall(qname(NS_MAIN, "row"))}

    title_row = rows_by_number.get(1)
    if title_row is not None:
        _set_inline_text(_find_or_create_cell(title_row, "A1"), title)

    for student in roster:
        row_number = student["row"]
        row = rows_by_number.get(row_number)
        if row is None:
            continue
        days = math_days if student["group"] == "数学类" else intl_days
        absence_dates = sorted(by_student[student["student_id"]]["缺勤"])
        early_dates = sorted(by_student[student["student_id"]]["早退"])
        absence_count = len(absence_dates)
        early_count = len(early_dates)
        abnormal = min(1, (absence_count + early_count) / days)
        attendance = max(0, 1 - abnormal)

        _set_number(
            _find_or_create_cell(row, f"E{row_number}"),
            attendance,
            f"MAX(0,1-F{row_number})",
        )
        _set_number(
            _find_or_create_cell(row, f"F{row_number}"),
            abnormal,
            f"MIN(1,(G{row_number}+H{row_number})/{days})",
        )
        _set_number(_find_or_create_cell(row, f"G{row_number}"), absence_count)
        _set_number(_find_or_create_cell(row, f"H{row_number}"), early_count)
        _set_inline_text(
            _find_or_create_cell(row, f"I{row_number}"),
            "，".join(_format_chinese_date(value) for value in absence_dates),
        )
        _set_inline_text(
            _find_or_create_cell(row, f"J{row_number}"),
            "，".join(_format_chinese_date(value) for value in early_dates),
        )

    files[sheet_path] = ET.tostring(sheet_root, encoding="utf-8", xml_declaration=True)

    workbook_root = ET.fromstring(files["xl/workbook.xml"])
    calc_pr = workbook_root.find(qname(NS_MAIN, "calcPr"))
    if calc_pr is None:
        calc_pr = ET.SubElement(workbook_root, qname(NS_MAIN, "calcPr"))
    calc_pr.attrib.update({"calcMode": "auto", "fullCalcOnLoad": "1", "forceFullCalc": "1"})
    files["xl/workbook.xml"] = ET.tostring(workbook_root, encoding="utf-8", xml_declaration=True)
    files.pop("xl/calcChain.xml", None)

    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for name, content in files.items():
            target.writestr(name, content)
    return output.getvalue()


def validate_template(raw: bytes) -> list[dict]:
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        names = set(archive.namelist())
        if "xl/workbook.xml" not in names:
            raise ValueError("这不是有效的 Excel .xlsx 文件")
    temp_path = DATA_DIR / ".template-validation.xlsx"
    temp_path.write_bytes(raw)
    try:
        return load_roster(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)


class AppHandler(SimpleHTTPRequestHandler):
    server_version = "EveningStudyGenerator/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def _json_response(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 10 * 1024 * 1024:
            raise ValueError("提交内容过大")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/health":
            self._json_response({"ok": True, "version": "1.0.0"})
            return
        if parsed.path == "/api/roster":
            try:
                roster = load_roster()
                groups = defaultdict(int)
                for student in roster:
                    groups[student["group"]] += 1
                self._json_response({"roster": roster, "counts": dict(groups), "total": len(roster)})
            except Exception as error:
                self._json_response({"error": str(error)}, 500)
            return
        if parsed.path == "/api/sample":
            sample_path = DATA_DIR / "12月截图文本整理.txt"
            self._json_response({"text": sample_path.read_text(encoding="utf-8")})
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/parse":
                payload = self._read_json()
                result = parse_chat_text(
                    str(payload.get("text", "")),
                    load_roster(),
                    int(payload.get("year", datetime.now().year)),
                    int(payload.get("month", datetime.now().month)),
                )
                self._json_response(result)
                return
            if parsed.path == "/api/export":
                payload = self._read_json()
                content = build_workbook(payload.get("events", []), payload.get("settings", {}))
                settings = payload.get("settings", {})
                filename = f"数统{settings.get('month', '')}月{settings.get('period', '半月')}晚自习公示表.xlsx"
                encoded = urllib.parse.quote(filename)
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{encoded}")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            if parsed.path == "/api/template":
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 20 * 1024 * 1024:
                    raise ValueError("模板文件为空或超过20MB")
                raw = self.rfile.read(length)
                roster = validate_template(raw)
                backup_dir = DATA_DIR / "backups"
                backup_dir.mkdir(parents=True, exist_ok=True)
                if TEMPLATE_PATH.exists():
                    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    shutil.copy2(TEMPLATE_PATH, backup_dir / f"晚自习公示模板-{timestamp}.xlsx")
                TEMPLATE_PATH.write_bytes(raw)
                self._json_response({"ok": True, "total": len(roster), "message": "新名单模板已启用，旧模板已备份"})
                return
            self._json_response({"error": "接口不存在"}, 404)
        except (ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as error:
            self._json_response({"error": str(error)}, 400)
        except Exception as error:
            self._json_response({"error": f"处理失败：{error}"}, 500)


def run_server(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), AppHandler)
    url = f"http://{host}:{port}"
    print(f"晚自习公示自动生成器已启动：{url}")
    print("使用结束后，可直接关闭这个窗口。")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="半月晚自习公示自动生成器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    arguments = parser.parse_args()
    run_server(arguments.host, arguments.port, not arguments.no_browser)
