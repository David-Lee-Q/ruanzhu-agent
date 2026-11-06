"""
软著登记自动化智能体 - 本地启动页（Web UI）

用法:
    python3 web/app.py            # 默认 http://127.0.0.1:8000
    python3 web/app.py --port 9000

接口（分两步，避免单个超大 multipart 请求被网关拦截）：
    POST /scapi/task                     创建任务
    POST /scapi/task/<id>/file           逐个上传源程序/说明书
    POST /scapi/task/<id>/prepare        生成鉴别材料 + 字段校验
    GET  /scapi/download/<id>/<kind>     下载 PDF / JSON
    POST /scapi/agent                    启动浏览器自动填报

注意：接口前缀特意使用 /scapi 而不是 /api。
IDE/沙箱的预览代理会占用 /api 路径（返回 404 "Session api not registered"），
用 /api 会导致页面能打开但所有请求都被代理拦截。
"""

import os
import re
import sys
import json
import uuid
import shutil
import zipfile
import asyncio
import argparse
import threading
import platform
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, send_file, send_from_directory
from werkzeug.exceptions import HTTPException

from soft_copyright import (
    SoftwareInfo, CopyrightHolder, RightInfo,
    DevelopmentInfo, FeatureInfo,
    SoftCopyrightApplication,
    SourceCodeProcessor, ManualProcessor,
    SoftCopyrightValidator, PDFGenerator, CopyrightPlatformAgent,
    AgentCredentials,
)
from soft_copyright.config import (
    FIELD_LENGTHS, TECH_FEATURE_TAGS, PLATFORM_LANGUAGE_BUTTONS,
    EXTENSION_LANGUAGE_MAP,
)
from soft_copyright.generators.pdf_generator import ManualPDFGenerator
from main import auto_fill_dev_info, auto_fill_feature_info

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_ROOT = os.path.join(BASE_DIR, "workspace")
os.makedirs(WORK_ROOT, exist_ok=True)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
app.config["JSON_AS_ASCII"] = False

TASKS = {}
DOWNLOAD_KINDS = {
    "source_pdf": "source_code_submit.pdf",
    "manual_pdf": "manual_submit.pdf",
    "app_json": "application_info.json",
}

SOURCE_CODE_EXTS = set(EXTENSION_LANGUAGE_MAP)
PDF_HEAD_PAGES = 30
PDF_TAIL_PAGES = 30
PDF_MIN_LINES_PER_PAGE = 50


# ==================== 通用 ====================

@app.errorhandler(Exception)
def handle_error(e):
    """任何异常都返回 JSON，避免前端 res.json() 解析 HTML 报错"""
    code = e.code if isinstance(e, HTTPException) else 500
    if code == 413:
        return jsonify({"error": "单个文件过大（上限 200MB）"}), 413
    if code == 500:
        traceback.print_exc()
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500
    return jsonify({"error": getattr(e, "description", str(e))}), code


def _split(value) -> list:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [x.strip() for x in str(value or "").replace("，", ",").split(",") if x.strip()]


def _safe_relpath(filename: str) -> str:
    """保留相对目录结构，剔除绝对路径与 .. 片段"""
    parts = [p for p in str(filename or "").replace("\\", "/").split("/")
             if p not in ("", ".", "..")]
    return os.path.join(*parts) if parts else "unnamed"


def _to_int(value) -> int:
    try:
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())
        return int(digits) if digits else 0
    except Exception:
        return 0


class PipelineInputError(Exception):
    """输入材料不满足处理条件，返回 400 而非 500"""


def _find_files_by_ext(directory: str, exts: set) -> list:
    found = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in {"__MACOSX", "__pycache__", ".git"}]
        for name in sorted(files):
            if os.path.splitext(name)[1].lower() in exts:
                found.append(os.path.join(root, name))
    return sorted(found)


def _extract_zip(zip_path: str, dest_dir: str) -> int:
    """安全解压 zip（防止路径穿越），返回解压出的文件数"""
    base = os.path.abspath(dest_dir)
    count = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = [p for p in info.filename.replace("\\", "/").split("/")
                     if p not in ("", ".", "..")]
            if not parts or "__MACOSX" in parts:
                continue
            target = os.path.abspath(os.path.join(base, *parts))
            if not (target == base or target.startswith(base + os.sep)):
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            count += 1
    return count


_LANG_PATTERNS = {
    "Python": [r"^\s*def \w+\(", r"^\s*from [\w.]+ import ", r"^\s*import \w+",
               r"^\s*class \w+.*:\s*$"],
    "Java": [r"\bpublic class \w+", r"^\s*package [\w.]+;", r"System\.out\.print"],
    "C#": [r"^\s*using System", r"\bnamespace [\w.]+", r"\bpublic void \w+\("],
    "C++": [r"#include\s*<(iostream|vector|string)>", r"\bstd::\w+"],
    "C": [r"#include\s*<(stdio|stdlib|string)\.h>", r"\bprintf\("],
    "JavaScript": [r"\bconsole\.log\(", r"=>\s*\{", r"^\s*(const|let)\s+\w+\s*="],
    "TypeScript": [r":\s*(string|number|boolean)\b", r"\binterface \w+\s*\{"],
    "Go": [r"^\s*package main", r"\bfunc \w+\(", r"\bfmt\.\w+"],
    "PHP": [r"<\?php", r"\$\w+\s*=\s*"],
    "Ruby": [r"^\s*puts\s+", r"^\s*def \w+\s*$"],
}


def _detect_languages_from_text(text: str) -> list:
    scores = {}
    for lang, patterns in _LANG_PATTERNS.items():
        hits = sum(len(re.findall(p, text, re.MULTILINE)) for p in patterns)
        if hits >= 3:
            scores[lang] = hits
    return [lang for lang, _ in sorted(scores.items(),
                                       key=lambda kv: kv[1], reverse=True)[:3]]


def _pdf_page_stats(path: str):
    from pdfminer.high_level import extract_text
    text = extract_text(path) or ""
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    per_page = [sum(1 for line in page.splitlines() if line.strip())
                for page in pages]
    return len(per_page), sum(per_page), per_page, text


def _write_source_pdf(src_path: str, out_path: str) -> dict:
    """将已有源程序 PDF 按前 30 + 后 30 页截取，输出为提交用 PDF"""
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(src_path)
    total = len(reader.pages)
    if total > PDF_HEAD_PAGES + PDF_TAIL_PAGES:
        indices = list(range(PDF_HEAD_PAGES)) + list(
            range(total - PDF_TAIL_PAGES, total))
    else:
        indices = list(range(total))
    writer = PdfWriter()
    for i in indices:
        writer.add_page(reader.pages[i])
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as f:
        writer.write(f)
    return {"total_pages": total, "submitted_pages": len(indices)}


def _validation_json(result: dict) -> dict:
    def conv(items):
        return [{"field": e.field, "message": e.message, "level": e.level}
                for e in items]
    return {
        "valid": result["valid"],
        "error_count": result["error_count"],
        "warning_count": result["warning_count"],
        "errors": conv(result["errors"]),
        "warnings": conv(result["warnings"]),
    }


def _build_application(form) -> SoftCopyrightApplication:
    a = SoftCopyrightApplication()
    a.software = SoftwareInfo(
        full_name=str(form.get("full_name", "")).strip(),
        short_name=str(form.get("short_name", "")).strip(),
        version=str(form.get("version", "")).strip(),
        category_code=str(form.get("category_code", "")).strip(),
        develop_date=str(form.get("develop_date", "")).strip(),
        publish_status=form.get("publish_status", "unpublished"),
        publish_date=str(form.get("publish_date", "")).strip(),
        publish_location=str(form.get("publish_location", "")).strip(),
        development_type=form.get("development_type", "independent"),
        software_type=form.get("software_type", "original"),
    )
    a.copyright_holder = CopyrightHolder(
        name=str(form.get("holder_name", "")).strip(),
        category=form.get("holder_category", "legal"),
        id_type=form.get("holder_id_type", "统一社会信用代码"),
        id_number=str(form.get("holder_id_number", "")).strip(),
        nationality=str(form.get("holder_nationality", "中国")).strip(),
        province=str(form.get("holder_province", "")).strip(),
        city=str(form.get("holder_city", "")).strip(),
    )
    a.right = RightInfo(acquire_type="original", scope="all")
    a.dev = DevelopmentInfo(
        dev_hardware_env=str(form.get("dev_hardware_env", "")).strip(),
        run_hardware_env=str(form.get("run_hardware_env", "")).strip(),
        dev_os=str(form.get("dev_os", "")).strip(),
        dev_environment=str(form.get("dev_environment", "")).strip(),
        run_platform=str(form.get("run_platform", "")).strip(),
        support_env=str(form.get("support_env", "")).strip(),
        languages=_split(form.get("languages", "")),
        languages_custom=str(form.get("languages_custom", "")).strip(),
    )
    a.feature = FeatureInfo(
        source_code_lines=_to_int(form.get("source_code_lines")),
        purpose=str(form.get("purpose", "")).strip(),
        target_industry=str(form.get("target_industry", "")).strip(),
        main_functions=str(form.get("main_functions", "")).strip(),
        tech_tags=_split(form.get("tech_tags", "")),
        tech_desc=str(form.get("tech_desc", "")).strip(),
        program_submit_type=form.get("program_submit_type", "normal"),
        doc_submit_type=form.get("doc_submit_type", "normal"),
    )
    return a


def _app_summary(a: SoftCopyrightApplication) -> dict:
    return {
        "software": vars(a.software),
        "dev": vars(a.dev),
        "feature": vars(a.feature),
        "copyright_holder": vars(a.copyright_holder),
        "right": vars(a.right),
    }


# ==================== 页面 ====================

@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/scapi/meta")
def meta():
    return jsonify({
        "field_lengths": FIELD_LENGTHS,
        "tech_tags": TECH_FEATURE_TAGS,
        "languages": PLATFORM_LANGUAGE_BUTTONS,
    })


# ==================== 任务与上传 ====================

@app.post("/scapi/task")
def create_task():
    task_id = uuid.uuid4().hex[:8]
    task_dir = os.path.join(WORK_ROOT, task_id)
    dirs = {k: os.path.join(task_dir, k) for k in ("src", "manual", "output")}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)

    TASKS[task_id] = {
        "id": task_id,
        **dirs,
        "manual_path": "",
        "source_files": 0,
        "app": None,
        "source_pdf": "",
        "manual_pdf": "",
        "agent": {"status": "idle", "result": None},
    }
    return jsonify({"task_id": task_id})


@app.post("/scapi/task/<task_id>/file")
def upload_file(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        return jsonify({"error": "任务已失效，请刷新页面后重试"}), 404

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "未收到文件"}), 400

    kind = request.form.get("kind", "source")
    relpath = request.form.get("relpath") or f.filename

    if kind == "manual":
        dest = os.path.join(task["manual"], os.path.basename(relpath))
        task["manual_path"] = dest
    else:
        dest = os.path.join(task["src"], _safe_relpath(relpath))
        task["source_files"] += 1

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    f.save(dest)

    extracted = 0
    if kind != "manual" and os.path.splitext(dest)[1].lower() == ".zip":
        try:
            extracted = _extract_zip(dest, task["src"])
        except zipfile.BadZipFile:
            return jsonify({"error": "压缩包无法解压，请确认上传的是有效的 .zip 文件"}), 400
        except Exception as e:
            return jsonify({"error": f"压缩包解压失败：{e}"}), 400

    return jsonify({"ok": True, "name": os.path.basename(dest),
                    "extracted": extracted})


# ==================== 生成 + 校验 ====================

@app.post("/scapi/task/<task_id>/prepare")
def prepare(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        return jsonify({"error": "任务已失效，请刷新页面后重试"}), 404

    form = request.get_json(silent=True) or {}
    try:
        payload = _run_pipeline(task, form)
    except PipelineInputError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(payload)


def _run_pipeline(task: dict, form: dict) -> dict:
    src_dir = task["src"]
    out_dir = task["output"]

    application = _build_application(form)
    application.source_code_dir = src_dir
    application.output_dir = out_dir
    application.manual_path = task["manual_path"]

    warnings = []
    source_stats = None
    manual_stats = None
    detected, total_lines, manual_content = [], 0, ""

    # ---- 源程序 ----
    sp = SourceCodeProcessor(application.software.full_name,
                             application.software.version)
    source_files = sp.scan_source_files(src_dir)
    source_pdfs = _find_files_by_ext(src_dir, {".pdf"})
    pdf_source_path = ""

    if source_files:
        source_stats = sp.process(src_dir, out_dir)
        detected = source_stats["detected_languages"]
        total_lines = source_stats["total_lines_clean"]
        application.feature.source_code_lines = (
            application.feature.source_code_lines or total_lines)
    elif source_pdfs:
        # 已生成好的源程序 PDF：直接作为鉴别材料，按前 30 + 后 30 页截取
        pdf_source_path = os.path.join(out_dir, "source_code_submit.pdf")
        total_pages, pdf_lines, per_page, pdf_text = _pdf_page_stats(source_pdfs[0])
        meta = _write_source_pdf(source_pdfs[0], pdf_source_path)
        detected = _detect_languages_from_text(pdf_text)
        total_lines = pdf_lines
        application.feature.source_code_lines = (
            application.feature.source_code_lines or total_lines)
        source_stats = {
            "total_files": len(source_pdfs),
            "total_lines_clean": total_lines,
            "submit_pages": meta["submitted_pages"],
            "detected_languages": detected,
        }
        warnings.append(
            f"源程序使用已上传的 PDF（共 {meta['total_pages']} 页），"
            f"已截取前 {PDF_HEAD_PAGES} + 后 {PDF_TAIL_PAGES} 页，"
            f"实际提交 {meta['submitted_pages']} 页")
        if meta["total_pages"] < PDF_HEAD_PAGES + PDF_TAIL_PAGES:
            warnings.append("源程序 PDF 不足 60 页，已全部提交，请核对平台页数要求")
        low_pages = [i + 1 for i, n in enumerate(per_page)
                     if n < PDF_MIN_LINES_PER_PAGE]
        if low_pages:
            shown = "、".join(str(i) for i in low_pages[:5])
            warnings.append(
                f"源程序 PDF 第 {shown} 页非空行数少于 "
                f"{PDF_MIN_LINES_PER_PAGE} 行，请核对平台每页行数要求")
    else:
        uploaded = []
        for name in sorted(os.listdir(src_dir)):
            full = os.path.join(src_dir, name)
            if os.path.isfile(full):
                uploaded.append(name)
        detail = f"（已上传：{'、'.join(uploaded[:5])}）" if uploaded else ""
        raise PipelineInputError(
            "源程序中未识别到可解析的源代码文件" + detail +
            "。请上传源码文件夹、源码文件、.zip 压缩包，或已生成的源程序 PDF。")

    # ---- 说明书 ----
    if application.manual_path:
        mp = ManualProcessor(application.software.full_name,
                             application.software.version)
        try:
            manual_stats = mp.process(application.manual_path, out_dir)
            manual_content = mp.read_manual(application.manual_path)
        except Exception as e:
            warnings.append(f"说明书解析失败：{e}")
    else:
        warnings.append("未上传说明书，无法生成文档鉴别材料")

    # ---- 自动补全 ----
    auto_fill_dev_info(application, detected)
    auto_fill_feature_info(application, total_lines, manual_content)

    # ---- 生成 PDF ----
    pdfs = {}
    try:
        src_pages = []
        if source_files:
            lines, _ = sp.merge_source_code(source_files)
            src_pages = sp.select_submission_pages(sp.paginate(lines))

        manual_pages = []
        mp = ManualProcessor(application.software.full_name,
                             application.software.version)
        if application.manual_path and os.path.isfile(application.manual_path):
            content = mp.read_manual(application.manual_path)
            manual_pages = mp.select_submission_pages(
                mp.paginate(mp.clean_text(content)))

        if src_pages:
            generator = PDFGenerator(application.software.full_name,
                                     application.software.version)
            if manual_pages:
                pdfs = generator.generate_all(src_pages, manual_pages, out_dir)
            else:
                source_pdf = os.path.join(out_dir, "source_code_submit.pdf")
                generator.source_gen.generate(src_pages, source_pdf)
                pdfs["source_code_pdf"] = source_pdf
        else:
            if pdf_source_path:
                pdfs["source_code_pdf"] = pdf_source_path
            if manual_pages:
                manual_pdf = os.path.join(out_dir, "manual_submit.pdf")
                ManualPDFGenerator(application.software.full_name,
                                   application.software.version) \
                    .generate(manual_pages, manual_pdf)
                pdfs["manual_pdf"] = manual_pdf
    except Exception as e:
        traceback.print_exc()
        warnings.append(f"PDF 生成失败：{e}")

    validation = _validation_json(
        SoftCopyrightValidator().validate_all(application))

    with open(os.path.join(out_dir, "application_info.json"), "w",
              encoding="utf-8") as f:
        json.dump(_app_summary(application), f, ensure_ascii=False, indent=2)

    task.update({
        "app": application,
        "source_pdf": pdfs.get("source_code_pdf", ""),
        "manual_pdf": pdfs.get("manual_pdf", ""),
        "agent": {"status": "idle", "result": None},
    })

    return {
        "task_id": task["id"],
        "source": {
            "files": source_stats["total_files"] if source_stats else 0,
            "lines": total_lines,
            "pages": source_stats["submit_pages"] if source_stats else 0,
            "languages": detected,
        },
        "manual": {
            "lines": manual_stats["clean_lines"] if manual_stats else 0,
            "pages": manual_stats["submit_pages"] if manual_stats else 0,
        },
        "validation": validation,
        "warnings": warnings,
        "filled": {
            "dev": vars(application.dev),
            "feature": vars(application.feature),
        },
        "files": {
            "source_pdf": bool(pdfs.get("source_code_pdf")),
            "manual_pdf": bool(pdfs.get("manual_pdf")),
        },
    }


# ==================== 下载 / 自动填报 ====================

@app.get("/scapi/download/<task_id>/<kind>")
def download(task_id: str, kind: str):
    task = TASKS.get(task_id)
    if not task or kind not in DOWNLOAD_KINDS:
        return jsonify({"error": "文件不存在"}), 404
    path = os.path.join(task["output"], DOWNLOAD_KINDS[kind])
    if not os.path.isfile(path):
        return jsonify({"error": "文件不存在"}), 404
    return send_file(path, as_attachment=True)


def _browser_env_status():
    """
    检查当前环境能否运行自动填报。
    自动填报依赖一个可见浏览器窗口（登录需人工补验证码），
    因此需要本机图形界面 + playwright + Chromium。

    Returns: (ok: bool, message: str)
    """
    try:
        import playwright.async_api  # noqa: F401
    except ImportError:
        return False, ("未安装 playwright。请在运行机器上执行：pip install playwright"
                       " && playwright install chromium，再启动本服务。")

    # 自动填报必须在能弹出可见浏览器窗口的机器上运行（验证码需人工完成）
    system = platform.system()
    has_display = (system in ("Darwin", "Windows")
                   or bool(os.environ.get("DISPLAY")
                           or os.environ.get("WAYLAND_DISPLAY")))
    if not has_display:
        return False, ("当前为无图形界面的服务器/云端环境，无法弹出浏览器窗口完成登录验证码，"
                       "「自动填报」无法在这里运行。请在自己的电脑上运行该项目："
                       "pip install -r requirements.txt && playwright install chromium"
                       " && python3 web/app.py，然后在本地页面点击启动自动填报。")

    # 有图形界面：确认 Chromium 已安装
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = p.chromium.executable_path
        if not exe or not os.path.exists(exe):
            return False, ("未检测到 Chromium 浏览器。请执行：playwright install chromium。")
    except Exception:
        return False, ("playwright 初始化失败，无法启动浏览器。"
                       "请执行：playwright install chromium。")

    return True, ""


@app.post("/scapi/agent")
def run_agent():
    data = request.get_json(silent=True) or {}
    task = TASKS.get(data.get("task_id", ""))
    if not task or not task.get("app"):
        return jsonify({"error": "任务不存在，请先生成材料"}), 404

    ok, env_msg = _browser_env_status()
    if not ok:
        return jsonify({"error": env_msg}), 400

    if not task["source_pdf"] or not task["manual_pdf"]:
        return jsonify({"error": "鉴别材料 PDF 未生成，无法开始填报"}), 400

    username = data.get("username", "")
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "请填写平台账号与密码"}), 400

    if task["agent"]["status"] == "running":
        return jsonify({"status": "running"})

    task["agent"] = {"status": "running", "result": None}
    creds = AgentCredentials(username=username, password=password,
                             url=data.get("url") or "https://ccopyright.com.cn")
    headless = bool(data.get("headless"))
    auto_submit = bool(data.get("auto_submit"))
    application = task["app"]
    source_pdf, manual_pdf = task["source_pdf"], task["manual_pdf"]

    def worker():
        async def go():
            agent = CopyrightPlatformAgent(creds, headless=headless)
            return await agent.run_full(application, source_pdf, manual_pdf,
                                        auto_submit=auto_submit,
                                        pause_at_step4=True)
        try:
            task["agent"]["result"] = asyncio.run(go())
            task["agent"]["status"] = "done"
        except Exception as e:
            traceback.print_exc()
            task["agent"]["result"] = {"success": False, "error": str(e)}
            task["agent"]["status"] = "error"

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"status": "running"})


@app.get("/scapi/agent/<task_id>")
def agent_status(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(task["agent"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="软著登记自动化智能体启动页")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"启动页已就绪: http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
