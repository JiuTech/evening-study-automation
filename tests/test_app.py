import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

import server


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not server.TEMPLATE_PATH.exists():
            raise unittest.SkipTest("本地真实模板未提供；公开仓库不会包含名单模板")
        cls.roster = server.load_roster()

    def test_roster_shape(self):
        self.assertEqual(len(self.roster), 249)
        self.assertEqual(sum(item["group"] == "数学类" for item in self.roster), 110)
        self.assertEqual(sum(item["group"] == "中外" for item in self.roster), 139)

    def test_parser_last_report_wins_and_leave_is_kept(self):
        math_students = [student for student in self.roster if student["group"] == "数学类"]
        kept, replaced = math_students[0], math_students[1]
        leave_student = next(student for student in math_students if student["class_code"] != kept["class_code"])
        text = f"""12月1日
数学类
缺勤
{kept['class_code']}{kept['name']}
{replaced['class_code']}{replaced['name']}
12月1日
数学类
缺勤
{kept['class_code']}{kept['name']}
12月14日
数学类
请假
{leave_student['class_code']}{leave_student['name']}
"""
        result = server.parse_chat_text(text, self.roster, 2025, 12)
        names = [(item["name"], item["type"]) for item in result["events"]]
        self.assertIn((kept["name"], "缺勤"), names)
        self.assertNotIn((replaced["name"], "缺勤"), names)
        self.assertIn((leave_student["name"], "请假"), names)

    def test_export_contains_formulas_and_dates(self):
        student = next(item for item in self.roster if item["group"] == "数学类")
        events = [{**student, "date": "2025-12-01", "type": "缺勤"}]
        content = server.build_workbook(events, {"year": 2025, "month": 12, "period": "上半月", "grade": "25级", "math_days": 9, "intl_days": 8})
        with zipfile.ZipFile(BytesIO(content)) as archive:
            xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn(f"G{student['row']}", xml)
        self.assertIn("12月1日", xml)
        self.assertIn("MAX(0,1-F", xml)


if __name__ == "__main__":
    unittest.main()
