import re
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "static" / "roster-template.xlsx"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def cell_value(cell, shared_strings):
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(f".//{{{MAIN_NS}}}t"))
    value = cell.find(f"{{{MAIN_NS}}}v")
    text = value.text if value is not None and value.text is not None else ""
    return shared_strings[int(text)] if cell_type == "s" and text else text


class Streamlit2026Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(TEMPLATE) as archive:
            if "xl/sharedStrings.xml" in archive.namelist():
                shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                cls.shared = ["".join(t.text or "" for t in item.findall(f".//{{{MAIN_NS}}}t")) for item in shared_root]
            else:
                cls.shared = []
            cls.sheet_xml = archive.read("xl/worksheets/sheet1.xml")
        root = ET.fromstring(cls.sheet_xml)
        cls.rows = root.findall(f".//{{{MAIN_NS}}}row")

    def test_builtin_roster_is_complete_and_unique(self):
        students = []
        for row in self.rows:
            if int(row.attrib["r"]) < 3:
                continue
            values = {re.match(r"[A-Z]+", cell.attrib["r"])[0]: cell_value(cell, self.shared) for cell in row.findall(f"{{{MAIN_NS}}}c")}
            if values.get("B") and values.get("D"):
                students.append((values["B"], values["C"], values["D"]))
        self.assertEqual(len(students), 257)
        self.assertEqual(len({student[2] for student in students}), 257)
        self.assertEqual(len({student[0] for student in students}), 257)
        self.assertTrue(all(re.fullmatch(r"2026\d{5}", student[2]) for student in students))
        self.assertEqual(sum("数学类" in student[1] for student in students), 112)
        self.assertEqual(sum("数学与应用数学" in student[1] for student in students), 145)

    def test_output_layout_and_formula_tail(self):
        text = self.sheet_xml.decode("utf-8")
        self.assertIn("数统26级晚自习", text)
        self.assertIn('r="E259"', text)
        self.assertIn("MAX(0,1-F259)", text)
        self.assertIn("MIN(1,(G259+H259)/1)", text)

    def test_upload_roster_controls_are_removed(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("templateInputTop", html + app)
        self.assertNotIn("templateInput", html + app)
        self.assertIn("loadBuiltInTemplate", app)
        self.assertIn("dateInSelectedPeriod", app)


if __name__ == "__main__":
    unittest.main()
