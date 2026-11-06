"""
软著登记自动化智能体 - 主入口 CLI

基于：中国版权保护中心 R11软件著作权登记申请 平台

用法:
    python main.py prepare --config config.yaml
    python main.py validate --config config.yaml
    python main.py run --config config.yaml --username xxx --password xxx
"""

import os
import re
import sys
import json
import asyncio
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from soft_copyright import (
    SoftwareInfo, CopyrightHolder, RightInfo,
    DevelopmentInfo, FeatureInfo,
    SoftCopyrightApplication,
    SourceCodeProcessor, ManualProcessor, InfoExtractor,
    SoftCopyrightValidator,
    PDFGenerator, CopyrightPlatformAgent,
)


def load_config(path: str) -> dict:
    try:
        import yaml
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except ImportError:
        raise ImportError("pip install PyYAML")


def build_application(cfg: dict) -> SoftCopyrightApplication:
    """
    从 YAML 配置构建申请对象
    
    支持新版配置（software + dev + feature）和旧版兼容（tech 自动拆分）。
    """
    app = SoftCopyrightApplication()
    app.source_code_dir = cfg.get('source_code_dir', '')
    app.manual_path = cfg.get('manual_path', '')
    app.output_dir = cfg.get('output_dir', './output')

    # Software
    sw = cfg.get('software', {})
    app.software = SoftwareInfo(**{k: sw.get(k, '') for k in
        ['full_name', 'short_name', 'version', 'category_code',
         'develop_date', 'publish_status', 'publish_date', 'publish_location',
         'development_type', 'software_type', 'modify_desc', 'original_reg_no']})

    # Copyright Holder
    h = cfg.get('copyright_holder', {})
    app.copyright_holder = CopyrightHolder(**{k: h.get(k, '') for k in
        ['name', 'category', 'id_type', 'id_number', 'nationality', 'province', 'city']})

    # Right
    r = cfg.get('right', {})
    app.right = RightInfo(acquire_type=r.get('acquire_type', 'original'),
                          scope=r.get('scope', 'all'),
                          partial_rights=r.get('partial_rights', []))

    # Development Info（第2步，新版）
    if 'dev' in cfg:
        d = cfg['dev']
        app.dev = DevelopmentInfo(
            dev_hardware_env=d.get('dev_hardware_env', ''),
            run_hardware_env=d.get('run_hardware_env', ''),
            dev_os=d.get('dev_os', ''),
            dev_environment=d.get('dev_environment', ''),
            run_platform=d.get('run_platform', ''),
            support_env=d.get('support_env', ''),
            languages=d.get('languages', []),
            languages_custom=d.get('languages_custom', ''),
        )
    else:
        # 旧版兼容：从 tech.hardware_env / software_env 自动拆分
        tech = cfg.get('tech', {})
        hw = tech.get('hardware_env', cfg.get('hardware_env', 'x86_64/8GB内存'))
        sw_env = tech.get('software_env', cfg.get('software_env', 'Python开发环境'))
        app.dev = DevelopmentInfo(
            dev_hardware_env=f"开发机: {hw}"[:50],
            run_hardware_env=f"部署环境: {hw}"[:50],
            dev_os="Windows 10 / macOS 12 / Ubuntu 20.04",
            dev_environment="Python 3.10+, VS Code, Git",
            run_platform="跨平台: Linux / macOS / Windows",
            support_env=sw_env[:50],
            languages=tech.get('languages', []),
        )

    # Feature Info（第3步，新版）
    if 'feature' in cfg:
        feat = cfg['feature']
        app.feature = FeatureInfo(
            source_code_lines=feat.get('source_code_lines', 0),
            purpose=feat.get('purpose', ''),
            target_industry=feat.get('target_industry', ''),
            main_functions=feat.get('main_functions', ''),
            tech_tags=feat.get('tech_tags', []),
            tech_desc=feat.get('tech_desc', ''),
            program_submit_type=feat.get('program_submit_type', 'normal'),
            doc_submit_type=feat.get('doc_submit_type', 'normal'),
        )
    else:
        # 旧版兼容
        tech = cfg.get('tech', {})
        app.feature = FeatureInfo(
            source_code_lines=tech.get('source_code_lines', 0),
            purpose='',
            target_industry='',
            main_functions=tech.get('main_features', '') or tech.get('main_functions', ''),
            tech_tags=tech.get('tech_tags', []),
        )

    return app


# ==================== 自动生成环境描述（当用户未提供时） ====================

def auto_fill_dev_info(app: SoftCopyrightApplication, detected_languages: list):
    """
    当用户未填写 dev 字段时，根据检测到的语言自动生成合理默认值。
    每个字段 0/50 字上限。
    """
    if not app.dev.dev_hardware_env:
        app.dev.dev_hardware_env = "x86_64架构，4核CPU，8GB以上内存，256GB SSD"
    if not app.dev.run_hardware_env:
        app.dev.run_hardware_env = "x86_64架构，2核以上CPU，4GB以上内存"
    if not app.dev.dev_os:
        app.dev.dev_os = "Windows 10/11、macOS 12+、Ubuntu 20.04+"
    if not app.dev.dev_environment:
        lang_list = ", ".join(detected_languages) if detected_languages else "多语言混合"
        app.dev.dev_environment = f"{lang_list} 开发环境，VS Code / JetBrains IDE，Git 版本管理"
    if not app.dev.run_platform:
        app.dev.run_platform = "跨平台运行，支持 Linux / macOS / Windows 操作系统"
    if not app.dev.support_env:
        app.dev.support_env = "支持 Python 3.10+、Node.js 18+ 等运行时环境"

    # 编程语言：自动选中检测到的语言，在平台按钮列表内的直接选
    from soft_copyright.config import PLATFORM_LANGUAGE_BUTTONS, LANGUAGE_DISPLAY_MAP
    if not app.dev.languages:
        auto_selected = []
        for lang in detected_languages:
            # 直接匹配
            if lang in PLATFORM_LANGUAGE_BUTTONS:
                auto_selected.append(lang)
            # 通过显示名映射
            else:
                display = LANGUAGE_DISPLAY_MAP.get(lang)
                if display and display in PLATFORM_LANGUAGE_BUTTONS:
                    auto_selected.append(display)
                elif display is None:
                    # 不在平台列表，放入自定义
                    if lang not in (app.dev.languages_custom or ''):
                        app.dev.languages_custom = (app.dev.languages_custom + ", " + lang).strip(", ")
        app.dev.languages = auto_selected if auto_selected else ["Python"]


# 描述性能力词：用于判断说明书某句是否在"描述系统功能"
_FUNC_HINTS = (
    "提供", "支持", "用于", "实现", "包含", "涵盖", "识别", "管理", "展示",
    "记录", "配置", "查询", "分析", "帮助", "自动", "处理", "统计", "监控",
    "维护", "导入", "导出", "生成", "计算", "检测", "诊断", "上传", "浏览",
    "筛选", "搜索", "绑定", "登录", "注册", "切换", "追溯", "对照", "推荐",
)

# 软件名里的通用词，剔除后剩下的才是"领域核心词"
_GENERIC_WORDS = ("系统", "软件", "平台", "管理", "智能", "识别", "应用", "服务", "工具", "综合")

# 主要功能抽取时需排除的"UI 排版/布局"描述行（属实现细节，非功能能力）
_LAYOUT_MARKERS = ("侧边栏", "布局", "面包屑", "锚点", "头部栏", "左侧", "右侧", "顶部", "页面为")
_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]")

# 面向领域关键词（命中越多越相关，最多取前 2 个领域）
_DOMAIN_KEYWORDS = {
    "农业、智慧农业与农业信息化": ["农业", "作物", "种植", "病虫害", "农田", "农技", "畜牧", "水产", "土壤", "灌溉", "植保"],
    "医疗健康": ["医疗", "医院", "患者", "诊断", "健康", "诊疗", "临床", "护理", "药品"],
    "金融": ["金融", "银行", "支付", "理财", "保险", "信贷", "风控", "交易"],
    "教育": ["教育", "学习", "课程", "考试", "教学", "培训", "学生", "题库"],
    "工业与智能制造": ["工业", "制造", "设备", "生产", "工厂", "工艺", "数控", "车间", "产线"],
    "电子商务": ["电商", "商城", "购物", "商品", "订单", "购物车", "门店"],
    "物流与供应链": ["物流", "供应链", "仓储", "配送", "运输", "库存"],
    "政务与公共服务": ["政务", "政府", "公共服务", "审批", "办事"],
    "能源": ["能源", "电力", "电网", "光伏", "风电", "储能"],
    "交通": ["交通", "出行", "车辆", "导航", "路况"],
    "人力资源": ["人力资源", "人事", "招聘", "考勤", "薪酬", "员工"],
    "零售": ["零售", "门店", "快消", "销售", "会员", "库存"],
}


def _name_core_tokens(name: str) -> list:
    """从软件名中剔除通用词后抽取领域核心词（2~4 字子串），用于判断句子相关性"""
    core = re.sub("|".join(_GENERIC_WORDS), "", name or "")
    toks = set()
    for n in (2, 3, 4):
        for i in range(len(core) - n + 1):
            toks.add(core[i:i + n])
    return [t for t in toks if len(t) >= 2]


def _is_noise_line(s: str) -> bool:
    """判定是否为目录/图注/路由/章节标题等非正文描述行"""
    s = s.strip()
    if not s:
        return True
    # 目录行：编号开头 + 制表符 + 页码
    if "\t" in s and re.match(r"^\d+(\.\d+)*\s+\S", s):
        return True
    # 图注：图 N
    if re.match(r"^图\s*\d+", s):
        return True
    # 路由映射：xxx.html —— 名称
    if "——" in s and ".html" in s:
        return True
    # 章节标题：编号开头且较短
    if re.match(r"^\d+(\.\d+)*\s+\S", s) and len(s) <= 18:
        return True
    return False


def _ensure_sentence(line: str) -> str:
    s = line.strip().strip("•·-–— ").strip()
    if not s:
        return ""
    if s[-1] not in "。！？；：，、,.!?;:":
        s = s + "。"
    return s


def _infer_domain(name: str, manual: str) -> str:
    """按名称(强信号)+说明书关键词推断面向领域；次级领域需说明书命中≥3 个关键词，避免误判"""
    name = name or ""
    manual = manual or ""
    scored = []
    for domain, kws in _DOMAIN_KEYWORDS.items():
        n_hits = sum(1 for k in kws if k in name)
        m_hits = sum(1 for k in kws if k in manual)
        if n_hits or m_hits:
            scored.append((n_hits, m_hits, domain))
    if not scored:
        return "行业应用、业务处理与数据管理领域"
    primary = max(scored, key=lambda x: (x[0], x[1]))
    result = [primary[2]]
    for n_hits, m_hits, domain in sorted(scored, key=lambda x: (-x[0], -x[1])):
        if domain == primary[2]:
            continue
        if m_hits >= 3:
            result.append(domain)
        if len(result) >= 2:
            break
    return ("、".join(result) + "领域")[:50]


def _infer_purpose(name: str, domain: str, manual_lines: list) -> str:
    """优先抓"X 是…系统/平台"定义句，其次找用途句，找不到则按领域+软件名组织"""
    for line in manual_lines:
        s = line.strip()
        if _is_noise_line(s):
            continue
        first = re.split(r"[。！？]", s)[0].strip()
        if 10 <= len(first) <= 50 and re.search(r"是.{4,}(系统|平台|软件)$", first):
            return first[:50]
    ui_markers = ("板块", "导航", "按钮", "标签", "布局", "页面", "侧边栏", "头部", "面包屑", "卡片", "锚点")
    for line in manual_lines:
        s = line.strip()
        if _is_noise_line(s) or len(s) < 15 or len(s) > 45:
            continue
        if any(m in s for m in ui_markers):
            continue
        if any(k in s for k in ("旨在", "致力于", "目标是", "用于", "面向")):
            return s[:50]
    domain_short = domain.replace("领域", "")
    core = re.sub("|".join(_GENERIC_WORDS), "", name or "") or (name or "本系统")
    return f"面向{domain_short}领域，为使用者提供{core}以支撑相关业务"[:50]


def _infer_tech_desc(tags: list, name: str, manual: str) -> str:
    """结合技术标签生成技术特点描述"""
    parts = []
    if "人工智能软件" in tags:
        parts.append("基于深度学习/机器学习模型进行智能分析与识别")
    if "大数据软件" in tags:
        parts.append("支持多源数据的汇聚、统计与可视化")
    if "云计算软件" in tags:
        parts.append("采用分布式/云化架构，支持弹性扩展")
    if "信息安全软件" in tags:
        parts.append("内置身份认证与权限控制，保障数据安全")
    if "APP" in tags:
        parts.append("提供移动端与 Web 多端访问")
    if "小程序" in tags:
        parts.append("基于小程序/移动端轻量化访问")
    if "物联网软件" in tags:
        parts.append("对接物联网设备，实现数据采集与联动")
    if not parts:
        parts.append("采用分层架构，模块职责清晰、松耦合")
    return ("，".join(parts[:2]) + "，具备良好的扩展性与稳定性")[:100]


# 技术特点标签关键词：(强区分词, 弱通用词)。
# 强区分词命中才算该技术的可靠信号；弱通用词（数据/安全/权限/设备/云等）几乎每个系统都有，仅作加权、不能单独触发。
_TECH_TAG_KEYWORDS = {
    "人工智能软件": (
        ["ai", "人工智能", "深度学习", "机器学习", "神经网络", "算法", "大模型", "智能识别", "图像识别", "自然语言"],
        ["智能", "模型", "识别", "分析"]),
    "APP": (
        ["app", "移动端", "客户端", "h5", "ios", "安卓", "android", "iphone", "移动应用"],
        ["手机", "移动"]),
    "大数据软件": (
        ["大数据", "数据仓库", "数据湖", "hadoop", "spark", "数据挖掘", "数据中台", "etl"],
        ["数据", "统计", "报表", "可视化"]),
    "云计算软件": (
        ["云计算", "cloud", "分布式", "微服务", "容器", "docker", "kubernetes", "云原生", "k8s"],
        ["云", "部署", "集群"]),
    "信息安全软件": (
        ["信息安全", "加密算法", "密钥管理", "防火墙", "漏洞", "等保", "身份认证", "鉴权", "渗透测试", "安全审计"],
        ["安全", "权限", "认证", "加密"]),
    "物联网软件": (
        ["物联网", "iot", "传感器", "边缘计算", "设备联网", "物联网设备", "mqtt"],
        ["设备", "采集", "联网", "传感"]),
    "地理信息软件": (
        ["gis", "地图", "定位", "地理信息", "遥感", "gps", "北斗"],
        ["定位", "地图"]),
    "教育软件": (
        ["在线学习", "课程", "题库", "教学", "考试系统", "教育平台", "在线课程"],
        ["教育", "学习", "培训", "考试"]),
    "金融软件": (
        ["金融", "支付", "风控", "信贷", "交易系统", "证券", "保险", "银行", "理财"],
        ["财务", "支付"]),
    "医疗软件": (
        ["医疗", "医院", "诊断", "病历", "诊疗", "电子处方", "医疗影像", "pacs"],
        ["健康"]),
    "游戏软件": (
        ["游戏", "game", "游戏引擎", "关卡", "游戏角色", "实时渲染", "npc"], []),
    "VR软件": (
        ["vr", "ar", "虚拟现实", "增强现实", "三维重建", "3d", "metaverse", "元宇宙"], []),
    "5G软件": (
        ["5g", "5g网络", "5g通信", "毫米波"], []),
    "小程序": (
        ["小程序", "微信小程序", "uniapp", "taro"], ["微信"]),
    "智慧城市软件": (
        ["智慧城市", "城市大脑", "政务", "城市管理", "一网通办"], ["城市", "政务"]),
}


_ASCII_KW_CACHE = {}


def _kw_regex(kw: str):
    """纯 ASCII 关键词用词边界正则，避免 'ar'/'ai'/'5g'/'3d' 匹配到英文单词内部（var/param/25g）"""
    if not kw.isascii():
        return None
    if kw not in _ASCII_KW_CACHE:
        _ASCII_KW_CACHE[kw] = re.compile(r"(?<![0-9a-z])" + re.escape(kw) + r"(?![0-9a-z])")
    return _ASCII_KW_CACHE[kw]


def _kw_hit(text_l: str, kw: str) -> bool:
    rx = _kw_regex(kw)
    return (rx.search(text_l) is not None) if rx else (kw in text_l)


def _kw_count(text_l: str, kw: str) -> int:
    rx = _kw_regex(kw)
    return len(rx.findall(text_l)) if rx else text_l.count(kw)


def _infer_tech_tags(name: str, manual: str) -> list:
    """按强区分词命中推断技术特点标签（最多 3 个）；通用词（数据/安全/权限/设备等）单独不触发，避免误判"""
    name_l = (name or "").lower()
    man_l = (manual or "").lower()

    def _counts(strong, weak):
        n_s = sum(1 for k in strong if _kw_hit(name_l, k))
        n_w = sum(1 for k in weak if _kw_hit(name_l, k))
        m_s = sum(min(_kw_count(man_l, k), 8) for k in strong if _kw_hit(man_l, k))
        m_w = sum(min(_kw_count(man_l, k), 5) for k in weak if _kw_hit(man_l, k))
        return n_s, n_w, m_s, m_w

    scored = []
    for tag, (strong, weak) in _TECH_TAG_KEYWORDS.items():
        n_s, n_w, m_s, m_w = _counts(strong, weak)
        score = n_s * 10 + n_w * 2 + m_s * 1.5 + m_w * 0.2
        # 门槛：名称含强词，或说明书强词累计 ≥4 次（标准登录/权限等弱信号不触发）
        if n_s > 0 or m_s >= 4:
            scored.append((score, tag))
    scored.sort(key=lambda x: -x[0])
    matched = [t for _, t in scored[:3]]

    if not matched:
        # 无强信号时放宽为"名称命中或说明书强词≥1"，取最相关 1 个
        relaxed = []
        for tag, (strong, weak) in _TECH_TAG_KEYWORDS.items():
            n_s, n_w, m_s, _ = _counts(strong, weak)
            if n_s or n_w or m_s:
                relaxed.append((n_s * 10 + n_w * 2 + m_s * 1.5, tag))
        relaxed.sort(key=lambda x: -x[0])
        matched = [relaxed[0][1]] if relaxed else []

    if not matched:
        matched = ["APP"]
        print("  ⚠️ 未能从名称/说明书中识别技术特点标签，已默认选择「APP」，请人工确认")
    return matched


def auto_fill_feature_info(app: SoftCopyrightApplication, total_lines: int = 0,
                           manual_content: str = ""):
    """
    基于说明书真实内容自动生成开发目的、面向领域、主要功能、技术特点（按平台字数限制）。
    """
    if app.feature.source_code_lines <= 0 and total_lines > 0:
        app.feature.source_code_lines = total_lines

    manual_lines = [l.strip() for l in manual_content.split('\n') if l.strip()] if manual_content else []

    # 面向领域（0/50）：从名称+说明书推断行业
    if not app.feature.target_industry:
        app.feature.target_industry = _infer_domain(app.software.full_name, manual_content)

    # 开发目的（0/50）
    if not app.feature.purpose:
        app.feature.purpose = _infer_purpose(
            app.software.full_name, app.feature.target_industry, manual_lines)

    # 主要功能（500-1300）：从说明书抽取真实功能描述
    from soft_copyright.config import FIELD_LENGTHS
    min_fn, max_fn = FIELD_LENGTHS["main_functions"]
    if not app.feature.main_functions or len(app.feature.main_functions) < min_fn:
        generated = _build_main_functions(app.software.full_name, manual_lines, 800)
        if app.feature.main_functions.strip():
            origin_len = len(app.feature.main_functions.strip())
            merged = (app.feature.main_functions.strip() + generated)[:max_fn - 50]
            app.feature.main_functions = merged
            print(f"  ⚠️ 主要功能原文 {origin_len} 字，"
                  f"已自动补充到 {len(merged)} 字（平台要求 ≥{min_fn}），请人工复核")
        else:
            app.feature.main_functions = generated

    # 技术特点标签（强区分词门槛，避免通用词误判）
    if not app.feature.tech_tags:
        app.feature.tech_tags = _infer_tech_tags(
            app.software.full_name, manual_content)

    # 技术特点描述（0/100）：结合技术标签
    if not app.feature.tech_desc:
        app.feature.tech_desc = _infer_tech_desc(
            app.feature.tech_tags, app.software.full_name, manual_content)


def _build_main_functions(sw_name: str, manual_lines: list, target_len: int = 800) -> str:
    """
    基于说明书真实内容构建 500-1300 字的主要功能描述。
    抽取描述系统功能的句子（按相关度排序后按原文顺序拼接），避免套用与软件无关的通用模板。
    """
    core_toks = _name_core_tokens(sw_name)

    def rel_score(s: str) -> int:
        sc = sum(1 for h in _FUNC_HINTS if h in s)
        if core_toks and any(t in s for t in core_toks):
            sc += 2
        if "系统" in s and ("提供" in s or "面向" in s or "支持" in s):
            sc += 1
        return sc

    # 收集候选句：{idx: (score, sentence)}
    cand = {}
    for idx, line in enumerate(manual_lines):
        if _is_noise_line(line):
            continue
        s = _EMOJI_RE.sub("", _ensure_sentence(line)).strip()
        if not s or len(s) < 25:
            continue
        if any(m in s for m in _LAYOUT_MARKERS):
            continue
        cand[idx] = (rel_score(s), s)

    if not cand:
        if sw_name:
            return (f"{sw_name} 围绕核心业务提供完整的功能模块，覆盖从输入处理、"
                    f"结果呈现到数据管理的全流程，兼顾易用性、稳定性与可扩展性，"
                    f"满足日常业务处理需求。")[:1300]
        return ""

    ranked = sorted(cand.items(), key=lambda kv: (-kv[1][0], kv[0]))

    # 先选高相关句
    chosen, total = [], 0
    for idx, (sc, s) in ranked:
        chosen.append(idx)
        total += len(s)
        if total >= 600 or len(chosen) >= 14:
            break
    # 不足则继续按相关度补足
    if total < 400:
        for idx, (sc, s) in ranked:
            if idx in chosen:
                continue
            chosen.append(idx)
            total += len(s)
            if total >= 600 or len(chosen) >= 20:
                break

    # 按原文顺序拼接，保持连贯
    result = "".join(cand[i][1] for i in sorted(chosen))

    # 字数不足继续补足
    if len(result) < 500:
        for idx, (sc, s) in ranked:
            if len(result) >= 500:
                break
            if idx in chosen:
                continue
            result += s
            chosen.append(idx)

    # 说明书过短时，追加保留软件名的收尾
    if len(result) < 500 and sw_name:
        result += (f"{sw_name} 各功能模块相互衔接，围绕核心业务形成完整闭环，"
                   f"覆盖从输入处理、结果呈现到数据管理的全流程，兼顾易用性、稳定性与可扩展性。")

    # 去除开头的承接片段（如"识别之外，"），使首句更完整
    result = re.sub(r"^\s*[^，。！？]{0,8}(?:之外|此外|另外|同时|其中)[，。]", "", result).lstrip()
    if result and result[-1] not in "。！？；":
        result += "。"
    return result[:1300]


# ==================== CLI 子命令 ====================

def cmd_prepare(args):
    print("\n" + "=" * 60)
    print("  软著登记自动化智能体 - Step 1/2: 准备鉴别材料")
    print("=" * 60)

    cfg = load_config(args.config) if args.config else None
    app = build_application(cfg) if cfg else SoftCopyrightApplication(
        source_code_dir=args.source or '',
        manual_path=args.manual or '',
        output_dir=args.output or './output',
    )
    if not cfg:
        if args.software_name:
            app.software.full_name = args.software_name
        if args.version:
            app.software.version = args.version
        if not app.software.develop_date:
            from datetime import date
            app.software.develop_date = date.today().strftime('%Y-%m-%d')

    os.makedirs(app.output_dir, exist_ok=True)
    source_processor = SourceCodeProcessor(app.software.full_name, app.software.version)
    manual_processor = ManualProcessor(app.software.full_name, app.software.version)
    extractor = InfoExtractor()

    source_stats = None
    manual_stats = None
    manual_content = ""

    # 1. 源程序
    if app.source_code_dir and os.path.isdir(app.source_code_dir):
        source_stats = source_processor.process(app.source_code_dir, app.output_dir)
        print(f"\n【源程序】{source_stats['total_files']} 个文件 → "
              f"{source_stats['total_lines_clean']} 行 → {source_stats['submit_pages']} 页提交")
        detected = source_stats['detected_languages']
        total_lines = source_stats['total_lines_clean']
        app.feature.source_code_lines = app.feature.source_code_lines or total_lines
    else:
        print("\n【源程序】⚠️ 目录未指定或不存在")
        detected, total_lines = [], 0

    # 2. 说明书
    if app.manual_path and os.path.isfile(app.manual_path):
        manual_stats = manual_processor.process(app.manual_path, app.output_dir)
        manual_content = manual_processor.read_manual(app.manual_path)
        print(f"【说明书】{manual_stats['clean_lines']} 行 → {manual_stats['submit_pages']} 页提交")
    else:
        print("【说明书】⚠️ 未指定或不存在")

    # 3. 自动填充 dev + feature
    print("\n【自动填充】环境描述 & 功能描述...")
    auto_fill_dev_info(app, detected)
    auto_fill_feature_info(app, total_lines, manual_content)

    # 4. 生成 PDF
    print("\n【生成PDF】")
    source_pages = _get_source_pages(source_processor, app.source_code_dir) if source_stats else []
    manual_pages = _get_manual_pages(manual_processor, app.manual_path) if manual_stats else []

    if source_pages or manual_pages:
        try:
            pdfs = PDFGenerator(app.software.full_name, app.software.version) \
                .generate_all(source_pages, manual_pages, app.output_dir)
            app._source_pdf = pdfs.get('source_code_pdf', '')
            app._manual_pdf = pdfs.get('manual_pdf', '')
            print(f"  ✓ {os.path.basename(app._source_pdf)}")
            print(f"  ✓ {os.path.basename(app._manual_pdf)}")
        except Exception as e:
            print(f"  ⚠️ PDF生成跳过: {e}")

    # 5. 保存 JSON
    out = os.path.join(app.output_dir, "application_info.json")
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(_app_to_dict(app), f, ensure_ascii=False, indent=2)
    print(f"\n📄 申请数据: {out}")

    return app


def _get_source_pages(proc, source_dir):
    all_lines, _ = proc.merge_source_code(proc.scan_source_files(source_dir))
    return proc.select_submission_pages(proc.paginate(all_lines))


def _get_manual_pages(proc, manual_path):
    content = proc.read_manual(manual_path)
    return proc.select_submission_pages(proc.paginate(proc.clean_text(content)))


def _app_to_dict(app: SoftCopyrightApplication) -> dict:
    d = {
        'software': {k: getattr(app.software, k) for k in
                     ['full_name', 'short_name', 'version', 'category_code',
                      'develop_date', 'publish_status', 'publish_date', 'publish_location',
                      'development_type', 'software_type']},
        'dev': {k: getattr(app.dev, k) for k in
                ['dev_hardware_env', 'run_hardware_env', 'dev_os',
                 'dev_environment', 'run_platform', 'support_env',
                 'languages', 'languages_custom']},
        'feature': {k: getattr(app.feature, k) for k in
                    ['source_code_lines', 'purpose', 'target_industry',
                     'main_functions', 'tech_tags', 'tech_desc',
                     'program_submit_type', 'doc_submit_type']},
        'copyright_holder': {k: getattr(app.copyright_holder, k) for k in
                              ['name', 'category', 'id_type', 'id_number',
                               'nationality', 'province', 'city']},
        'right': {'acquire_type': app.right.acquire_type,
                  'scope': app.right.scope},
        'generated_files': {
            'source_code_pdf': getattr(app, '_source_pdf', ''),
            'manual_pdf': getattr(app, '_manual_pdf', ''),
        },
    }
    return d


def cmd_validate(args):
    print("\n" + "=" * 60)
    print("  软著登记自动化智能体 - Step 2/2: 字段校验")
    print("=" * 60)

    if args.app_info and os.path.isfile(args.app_info):
        with open(args.app_info, 'r', encoding='utf-8') as f:
            data = json.load(f)
        app = _dict_to_app(data)
    elif args.config:
        app = build_application(load_config(args.config))
    else:
        print("⚠️ 请指定 --config 或 --app-info")
        return

    result = SoftCopyrightValidator().validate_all(app)
    SoftCopyrightValidator().print_report(result)
    return result


def _dict_to_app(data: dict) -> SoftCopyrightApplication:
    """从 JSON dict 重建 application"""
    app = SoftCopyrightApplication()
    if 'software' in data:
        app.software = SoftwareInfo(**data['software'])
    if 'dev' in data:
        app.dev = DevelopmentInfo(**data['dev'])
    if 'feature' in data:
        app.feature = FeatureInfo(**data['feature'])
    if 'copyright_holder' in data:
        app.copyright_holder = CopyrightHolder(**data['copyright_holder'])
    if 'right' in data:
        app.right = RightInfo(**data['right'])
    return app


async def cmd_run(args):
    app = cmd_prepare(args)

    print("\n")
    v_result = SoftCopyrightValidator().validate_all(app)
    SoftCopyrightValidator().print_report(v_result)

    if not v_result['valid']:
        print("\n⚠️ 存在校验错误，请修正后再继续！")
        return

    if args.auto_submit and args.username and args.password:
        from soft_copyright import AgentCredentials
        creds = AgentCredentials(username=args.username, password=args.password)
        source_pdf = getattr(app, '_source_pdf', '') or args.source_pdf
        manual_pdf = getattr(app, '_manual_pdf', '') or args.manual_pdf

        print("\n🚀 启动自动填报 Agent（5步流程）...")
        agent = CopyrightPlatformAgent(creds, headless=False)
        run_result = await agent.run_full(app, source_pdf, manual_pdf,
                                           auto_submit=args.auto_submit,
                                           pause_at_step4=True)
        if run_result['success']:
            print(f"\n✅ 全部 {run_result['steps_completed']} 步完成！")
        else:
            print(f"\n⚠️ 状态: {run_result}")
            await agent.save_screenshot(os.path.join(app.output_dir, "agent_state.png"))


def main():
    p = argparse.ArgumentParser(description="软著登记自动化智能体（R11）")
    sp = p.add_subparsers(dest='command')

    for name, help_ in [('prepare', 'Step 1: 准备鉴别材料'),
                        ('validate', 'Step 2: 校验字段'),
                        ('run', '全自动: prepare + validate + 自动填报')]:
        sub = sp.add_parser(name, help=help_)
        sub.add_argument('--config', '-c')
        sub.add_argument('--source', '-s')
        sub.add_argument('--manual', '-m')
        sub.add_argument('--software-name', '-n')
        sub.add_argument('--version', '-v')
        sub.add_argument('--output', '-o')
        if name == 'validate':
            sub.add_argument('--app-info', '-a', help='prepare 生成的 application_info.json')
        if name == 'run':
            sub.add_argument('--username', '-u')
            sub.add_argument('--password', '-p')
            sub.add_argument('--auto-submit', action='store_true')
            sub.add_argument('--source-pdf')
            sub.add_argument('--manual-pdf')

    args = p.parse_args()
    if args.command == 'prepare':
        cmd_prepare(args)
    elif args.command == 'validate':
        cmd_validate(args)
    elif args.command == 'run':
        asyncio.run(cmd_run(args))
    else:
        p.print_help()


if __name__ == '__main__':
    main()
