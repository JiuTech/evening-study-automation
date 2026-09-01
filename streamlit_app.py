import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path


# ============================================================
# Streamlit 页面配置
# ============================================================

st.set_page_config(
    page_title="半月晚自习公示自动生成器",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# 读取项目本地静态资源
#
# 不再从 raw.githubusercontent.com 加载 CSS / JS
# 这样部署到 Streamlit Cloud 后也能正常加载样式和功能
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def read_static_file(filename: str) -> str:
    path = STATIC_DIR / filename

    if not path.exists():
        raise FileNotFoundError(
            f"找不到静态资源：{path}\n"
            f"请确认 GitHub 仓库中存在 static/{filename}"
        )

    return path.read_text(encoding="utf-8")


CSS = read_static_file("styles.css")
BROWSER_XLSX_JS = read_static_file("browser-xlsx.js")
APP_JS = read_static_file("app.js")


# ============================================================
# HTML 页面
# ============================================================

HTML = f"""
<!DOCTYPE html>

<html lang="zh-CN">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1, maximum-scale=1"
>

<meta
    name="theme-color"
    content="#0f5036"
>

<title>半月晚自习公示自动生成器</title>


<style>

/* ==========================================================
   Streamlit iframe 基础处理
   ========================================================== */

html,
body {{
    margin: 0;
    padding: 0;
    width: 100%;
    min-height: 100%;
}}

body {{
    overflow-x: hidden;
    background: #f3f5ef;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        "Microsoft YaHei",
        "PingFang SC",
        sans-serif;
}}


/* ==========================================================
   防止 iframe 中出现奇怪的默认边距
   ========================================================== */

* {{
    box-sizing: border-box;
}}


/* ==========================================================
   原项目完整 CSS
   ========================================================== */

{CSS}

</style>

</head>


<body>


<!-- ========================================================
     顶部导航
     ======================================================== -->

<header class="topbar">

    <div class="brand">

        <div class="brand-mark">
            数统
        </div>

        <div>

            <h1>
                半月晚自习公示自动生成器
            </h1>

            <p>
                粘贴群聊记录 · 人工核对 · 一键生成 Excel
            </p>

        </div>

    </div>


    <div class="header-actions">

        <button
            id="installBtn"
            class="install-button hidden"
        >
            安装应用
        </button>


        <div
            id="rosterBadge"
            class="roster-badge"
        >
            请先选择名单模板
        </div>

    </div>

</header>


<!-- ========================================================
     主体
     ======================================================== -->

<main class="layout">


    <!-- ====================================================
         左侧步骤导航
         ==================================================== -->

    <aside class="steps">


        <button
            class="step active"
            data-step="1"
        >

            <span>
                1
            </span>

            <div>

                <b>
                    粘贴记录
                </b>

                <small>
                    设置公示周期
                </small>

            </div>

        </button>


        <button
            class="step"
            data-step="2"
        >

            <span>
                2
            </span>

            <div>

                <b>
                    识别与校对
                </b>

                <small>
                    处理撤回和请假
                </small>

            </div>

        </button>


        <button
            class="step"
            data-step="3"
        >

            <span>
                3
            </span>

            <div>

                <b>
                    生成公示表
                </b>

                <small>
                    下载原格式 Excel
                </small>

            </div>

        </button>


        <div class="privacy-note">

            <b>
                数据留在本机
            </b>

            <p>
                模板、群聊、姓名和学号只在当前设备浏览器中处理，
                不上传 GitHub 或服务器。
            </p>

        </div>

    </aside>


    <!-- ====================================================
         右侧工作区
         ==================================================== -->

    <section class="workspace">


        <!-- =================================================
             STEP 1
             ================================================= -->

        <div
            class="panel"
            id="step1"
        >


            <div class="panel-heading">


                <div>

                    <span class="eyebrow">
                        STEP 01
                    </span>

                    <h2>
                        粘贴半个月的群聊文字
                    </h2>

                </div>


                <div class="heading-actions">


                    <label
                        class="button ghost file-button"
                    >

                        导入聊天文本

                        <input
                            id="textFileInput"
                            type="file"
                            accept=".txt,text/plain"
                        >

                    </label>


                    <button
                        id="sampleBtn"
                        class="button ghost"
                    >
                        载入格式示例
                    </button>


                </div>

            </div>


            <!-- =================================================
                 Excel 模板
                 ================================================= -->

            <div
                class="template-card"
                id="templateCard"
            >


                <div class="template-icon">
                    XLSX
                </div>


                <div class="template-copy">

                    <b>
                        第一步：选择当前名单模板
                    </b>

                    <span id="templateSummary">
                        尚未选择模板
                    </span>

                    <small>
                        文件只保存在这台手机或电脑的浏览器中。
                    </small>

                </div>


                <label
                    class="button template-button"
                >

                    选择 Excel 模板

                    <input
                        id="templateInputTop"
                        type="file"
                        accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    >

                </label>

            </div>


            <!-- =================================================
                 参数
                 ================================================= -->

            <div class="settings-grid">


                <label>

                    学年

                    <input
                        id="yearInput"
                        type="number"
                        min="2020"
                        max="2100"
                    >

                </label>


                <label>

                    年级

                    <input
                        id="gradeInput"
                        value="25级"
                        maxlength="8"
                    >

                </label>


                <label>

                    月份

                    <input
                        id="monthInput"
                        type="number"
                        min="1"
                        max="12"
                        value="12"
                    >

                </label>


                <label>

                    周期

                    <select id="periodInput">

                        <option>
                            上半月
                        </option>

                        <option>
                            下半月
                        </option>

                    </select>

                </label>


                <label>

                    数学类检查天数

                    <input
                        id="mathDaysInput"
                        type="number"
                        min="1"
                        max="31"
                        value="9"
                    >

                </label>


                <label>

                    中外检查天数

                    <input
                        id="intlDaysInput"
                        type="number"
                        min="1"
                        max="31"
                        value="8"
                    >

                </label>


            </div>


            <!-- =================================================
                 群聊文本
                 ================================================= -->

            <label class="textarea-label">

                群聊记录

            </label>


            <textarea
                id="chatInput"
                placeholder="把工作群里这半个月的文字直接粘贴到这里……"
            ></textarea>


            <div class="hint-row">

                <span>
                    提示：撤回后重新发送的同日同类别记录，以后一次为准。
                </span>

                <span id="charCount">
                    0 字
                </span>

            </div>


            <div class="actions">

                <button
                    id="parseBtn"
                    class="button primary"
                >
                    开始识别 →
                </button>

            </div>


        </div>


        <!-- =================================================
             STEP 2
             ================================================= -->

        <div
            class="panel hidden"
            id="step2"
        >


            <div class="panel-heading">


                <div>

                    <span class="eyebrow">
                        STEP 02
                    </span>

                    <h2>
                        核对识别结果
                    </h2>

                    <p>
                        这里的修改会直接反映到最终公示表。
                    </p>

                </div>


                <button
                    id="backBtn"
                    class="button ghost"
                >
                    返回修改原文
                </button>


            </div>


            <!-- =================================================
                 数据统计
                 ================================================= -->

            <div class="stats">


                <div>

                    <span>
                        识别记录
                    </span>

                    <strong id="recognisedStat">
                        0
                    </strong>

                </div>


                <div class="danger">

                    <span>
                        缺勤
                    </span>

                    <strong id="absenceStat">
                        0
                    </strong>

                </div>


                <div class="warning">

                    <span>
                        早退
                    </span>

                    <strong id="earlyStat">
                        0
                    </strong>

                </div>


                <div class="neutral">

                    <span>
                        请假（不计入）
                    </span>

                    <strong id="leaveStat">
                        0
                    </strong>

                </div>


            </div>


            <div
                id="warningBox"
                class="warning-box hidden"
            ></div>


            <!-- =================================================
                 筛选
                 ================================================= -->

            <div class="toolbar">


                <div class="filters">


                    <button
                        class="filter active"
                        data-filter="全部"
                    >
                        全部
                    </button>


                    <button
                        class="filter"
                        data-filter="数学类"
                    >
                        数学类
                    </button>


                    <button
                        class="filter"
                        data-filter="中外"
                    >
                        中外
                    </button>


                    <button
                        class="filter"
                        data-filter="请假"
                    >
                        只看请假
                    </button>


                </div>


                <button
                    id="addEventBtn"
                    class="button ghost"
                >
                    ＋ 添加一条
                </button>


            </div>


            <!-- =================================================
                 识别结果表
                 ================================================= -->

            <div class="table-wrap">


                <table>

                    <thead>

                        <tr>

                            <th>
                                日期
                            </th>

                            <th>
                                类别
                            </th>

                            <th>
                                班级
                            </th>

                            <th>
                                姓名
                            </th>

                            <th>
                                情况
                            </th>

                            <th>
                                操作
                            </th>

                        </tr>

                    </thead>


                    <tbody id="eventsBody"></tbody>


                </table>


                <div
                    id="emptyState"
                    class="empty-state hidden"
                >
                    没有符合当前筛选条件的记录。
                </div>


            </div>


            <div
                class="coverage"
                id="coverageText"
            ></div>


            <div class="actions">

                <button
                    id="toExportBtn"
                    class="button primary"
                >
                    确认无误，进入导出 →
                </button>

            </div>


        </div>


        <!-- =================================================
             STEP 3
             ================================================= -->

        <div
            class="panel hidden"
            id="step3"
        >


            <div class="success-icon">
                ✓
            </div>


            <span class="eyebrow">
                STEP 03
            </span>


            <h2>
                公示表已准备好
            </h2>


            <p class="success-copy">

                将保留原表名单、学号、边框和排版，
                自动填写缺勤/早退次数、日期与比例公式。

            </p>


            <div
                class="export-summary"
                id="exportSummary"
            ></div>


            <button
                id="downloadBtn"
                class="button primary large"
            >
                下载 Excel 公示表
            </button>


            <button
                id="againBtn"
                class="button text"
            >
                继续生成另一份
            </button>


            <details class="template-settings">


                <summary>
                    以后换新一届名单怎么办？
                </summary>


                <p>
                    准备一个与当前模板相同列结构的 Excel，
                    第2行为表头，第3行起为名单。
                </p>


                <label class="upload-button">

                    选择新名单模板

                    <input
                        id="templateInput"
                        type="file"
                        accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    >

                </label>


                <span id="templateStatus"></span>


            </details>


        </div>


    </section>

</main>


<!-- ========================================================
     Toast
     ======================================================== -->

<div
    id="toast"
    class="toast"
    role="status"
></div>


<!-- ========================================================
     本地 JSZip
     ========================================================

     注意：
     这里仍然使用 jszip CDN。

     如果你的 browser-xlsx.js 已经自带 JSZip，
     可以去掉下面这一行。
     当前版本沿用原项目结构。
     ======================================================== -->

<script
    src="https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js"
></script>


<!-- ========================================================
     原项目 Excel 处理代码
     ======================================================== -->

<script>

{BROWSER_XLSX_JS}

</script>


<!-- ========================================================
     原项目核心业务代码
     ======================================================== -->

<script>

{APP_JS}

</script>


</body>

</html>
"""


# ============================================================
# 渲染
# ============================================================

components.html(
    HTML,
    height=1650,
    scrolling=True,
)
