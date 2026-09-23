import base64
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(
    page_title="26级晚自习公示生成器",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def read_static_file(filename: str) -> str:
    path = STATIC_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"找不到静态资源：{path}")
    return path.read_text(encoding="utf-8")


index_html = read_static_file("index.html")
styles = read_static_file("styles.css")
vendor_js = read_static_file("vendor/jszip.min.js")
xlsx_js = read_static_file("browser-xlsx.js")
app_js = read_static_file("app.js")
template_base64 = base64.b64encode((STATIC_DIR / "roster-template.xlsx").read_bytes()).decode("ascii")

html = index_html
html = html.replace('<link rel="stylesheet" href="./styles.css">', f"<style>{styles}</style>")
html = html.replace('<script src="./vendor/jszip.min.js"></script>', f"<script>{vendor_js}</script>")
html = html.replace(
    '<script src="./browser-xlsx.js"></script>',
    f'<script>window.BUILT_IN_TEMPLATE_BASE64="{template_base64}";</script><script>{xlsx_js}</script>',
)
html = html.replace('<script src="./app.js" defer></script>', f"<script>{app_js}</script>")

components.html(html, height=1560, scrolling=True)
