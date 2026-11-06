"""
软著登记自动化智能体 - 配置与常量定义

基于中国版权保护中心软著登记平台（R11软件著作权登记申请）的真实字段结构。
平台步骤条：选择办理身份 → 软件申请信息 → 软件开发信息 → 软件功能与特点 → 确认信息
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import date


# ================ 平台字段长度限制（来自PDF截图） ================
# 所有 "*" 开头的字段为必填项
FIELD_LENGTHS = {
    # 软件开发信息页（第2步）
    "dev_hardware_env": 50,          # *开发的硬件环境  0/50
    "run_hardware_env": 50,          # *运行的硬件环境  0/50
    "dev_os": 50,                    # *开发该软件的操作系统  0/50
    "dev_environment": 50,           # *软件开发环境/开发工具  0/50
    "run_platform": 50,              # *该软件的运行平台/操作系统  0/50
    "support_env": 50,               # *软件运行支撑环境/支持软件  0/50
    "languages_custom": 120,         # *编程语言（自定义补充）  0/120

    # 软件功能与特点页（第3步）
    "purpose": 50,                   # *开发目的  0/50
    "target_industry": 50,           # *面向领域/行业  0/50
    "main_functions": (500, 1300),     # *软件的主要功能  0/500~1300
    "tech_tags": 100,                # *软件的技术特点（标签描述）  0/100
}


# ================ 平台编程语言多选列表（来自PDF截图） ================
# 平台界面上直接可点选的按钮列表
PLATFORM_LANGUAGE_BUTTONS = [
    "Assembly language", "C", "C#", "C++", "Delphi/Object Pascal",
    "Go", "HTML", "Java", "JavaScript", "MATLAB", "Objective-C",
    "Pascal", "Perl", "PHP", "PL/SQL", "Python", "R", "Ruby",
    "Scala", "SQL", "Swift", "T-SQL", "TypeScript", "Visual Basic",
]

# 内部标准化名称到平台显示名的映射
LANGUAGE_DISPLAY_MAP = {
    "Python": "Python",
    "Java": "Java",
    "C": "C",
    "C++": "C++",
    "C#": "C#",
    "JavaScript": "JavaScript",
    "TypeScript": "TypeScript",
    "Go": "Go",
    "Rust": None,           # Rust 不在默认列表，需要自定义输入
    "Ruby": "Ruby",
    "PHP": "PHP",
    "Swift": "Swift",
    "Kotlin": None,         # 需要自定义输入
    "Objective-C": "Objective-C",
    "HTML": "HTML",
    "CSS": None,            # 需要自定义输入
    "SQL": "SQL",
    "Shell": None,
    "Lua": None,
    "Scala": "Scala",
    "Perl": "Perl",
    "R": "R",
    "MATLAB": "MATLAB",
    "Delphi": "Delphi/Object Pascal",
    "Visual Basic": "Visual Basic",
    "Assembly": "Assembly language",
    "Pascal": "Pascal",
}


# ================ 平台软件技术特点分类标签（来自PDF截图） ================
TECH_FEATURE_TAGS = [
    "APP", "游戏软件", "教育软件", "金融软件", "医疗软件",
    "地理信息软件", "云计算软件", "信息安全软件", "大数据软件",
    "人工智能软件", "VR软件", "5G软件", "小程序", "物联网软件",
    "智慧城市软件",
]


# ================ 鉴别材料类型 ================
SUBMISSION_TYPES = {
    "normal": "一般交存",
    "exception": "例外交存",
}


# ================ 软著平台鉴别材料规范 ================
SPEC = {
    "SOURCE_CODE_MIN_LINES_PER_PAGE": 50,
    "DOC_MIN_LINES_PER_PAGE": 30,
    "FRONT_PAGES": 30,
    "BACK_PAGES": 30,
    "TOTAL_PAGES_THRESHOLD": 60,
    "VERSION_PATTERN": r"^V?\d+\.\d+$",
    "SOFTWARE_NAME_MAX_LEN": 50,
    "HEADER_FONT": "Helvetica",
    "HEADER_FONT_SIZE": 9,
    "CODE_FONT": "Courier",
    "CODE_FONT_SIZE": 9,
    "CODE_LINE_HEIGHT": 11,
    "PAGE_MARGIN_LEFT": 45,
    "PAGE_MARGIN_RIGHT": 45,
    "PAGE_MARGIN_TOP": 50,
    "PAGE_MARGIN_BOTTOM": 50,
}


# 软件分类号（GB/T13702）
SOFTWARE_CATEGORIES = {
    "A": "基础软件", "A01": "操作系统", "A02": "数据库系统",
    "A03": "中间件", "A04": "编程语言",
    "B": "应用软件", "B01": "管理软件", "B02": "办公软件",
    "B03": "辅助设计软件", "B04": "教育软件", "B05": "金融软件",
    "B06": "医疗软件",
    "C": "行业应用软件", "D": "嵌入式软件", "E": "游戏软件",
}


# 开发方式
DEVELOPMENT_TYPES = {
    "independent": "单独开发",
    "cooperative": "合作开发",
    "commissioned": "委托开发",
    "task": "下达任务开发",
}


# 权利取得方式
RIGHT_TYPES = {
    "original": "原始取得",
    "transfer": "受让",
    "inheritance": "继承",
    "succession": "承受",
}


# 源文件扩展名到编程语言映射
EXTENSION_LANGUAGE_MAP = {
    ".py": "Python", ".java": "Java", ".c": "C", ".h": "C",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++",
    ".cs": "C#", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go",
    ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
    ".kt": "Kotlin", ".m": "Objective-C", ".mm": "Objective-C",
    ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".sql": "SQL",
    ".sh": "Shell", ".bash": "Shell", ".lua": "Lua", ".scala": "Scala",
    ".pl": "Perl", ".r": "R", ".mex": "MATLAB", ".pas": "Delphi",
    ".vb": "Visual Basic", ".asm": "Assembly", ".s": "Assembly",
}


# 源文件注释风格
LANGUAGE_COMMENT_STYLES = {
    "Python": {"single": "#", "block": ("'''", "'''")},
    "C": {"single": "//", "block": ("/*", "*/")},
    "C++": {"single": "//", "block": ("/*", "*/")},
    "Java": {"single": "//", "block": ("/*", "*/")},
    "C#": {"single": "//", "block": ("/*", "*/")},
    "JavaScript": {"single": "//", "block": ("/*", "*/")},
    "TypeScript": {"single": "//", "block": ("/*", "*/")},
    "Go": {"single": "//", "block": ("/*", "*/")},
    "Rust": {"single": "//", "block": ("/*", "*/")},
    "Ruby": {"single": "#", "block": ("=begin", "=end")},
    "PHP": {"single": "//", "block": ("/*", "*/")},
    "Swift": {"single": "//", "block": ("/*", "*/")},
    "Kotlin": {"single": "//", "block": ("/*", "*/")},
    "Shell": {"single": "#", "block": None},
    "SQL": {"single": "--", "block": ("/*", "*/")},
    "Lua": {"single": "--", "block": ("--[[", "]]")},
}


# ================ 数据类定义 ================

@dataclass
class SoftwareInfo:
    """软件申请信息（第1步）"""
    full_name: str = ""                    # *软件全称
    short_name: str = ""                   # 软件简称（可选）
    version: str = ""                      # *版本号（Vx.x 或 x.x）
    category_code: str = ""                # 分类号
    develop_date: str = ""                 # *开发完成日期 YYYY-MM-DD
    publish_status: str = "unpublished"    # published / unpublished
    publish_date: str = ""                 # 首次发表日期（已发表时必填）
    publish_location: str = ""             # 首次发表地点
    development_type: str = "independent"  # 开发方式
    software_type: str = "original"        # original(原创) / modified(修改)
    modify_desc: str = ""                  # 修改说明
    original_reg_no: str = ""              # 原登记号


@dataclass
class CopyrightHolder:
    """著作权人信息"""
    name: str = ""                         # *姓名/名称
    category: str = "legal"                # natural / legal / illegal
    id_type: str = ""                      # 证件类型
    id_number: str = ""                    # 证件号码
    nationality: str = "中国"
    province: str = ""
    city: str = ""


@dataclass
class RightInfo:
    """权利说明"""
    acquire_type: str = "original"
    scope: str = "all"
    partial_rights: List[str] = field(default_factory=list)


@dataclass
class DevelopmentInfo:
    """
    软件开发信息（第2步）
    
    对应平台7个独立输入框，每个最多50字，外加编程语言多选。
    这是之前版本最缺失的部分——把 hardware_env / software_env 拆成了6个独立字段。
    """
    dev_hardware_env: str = ""             # *开发的硬件环境  0/50
    run_hardware_env: str = ""             # *运行的硬件环境  0/50
    dev_os: str = ""                       # *开发该软件的操作系统  0/50
    dev_environment: str = ""              # *软件开发环境/开发工具  0/50
    run_platform: str = ""                 # *该软件的运行平台/操作系统  0/50
    support_env: str = ""                  # *软件运行支撑环境/支持软件  0/50
    languages: List[str] = field(default_factory=list)   # *编程语言（从平台按钮列表选择）
    languages_custom: str = ""             # 编程语言自定义补充（0/120）


@dataclass
class FeatureInfo:
    """
    软件功能与特点（第3步）
    
    对应平台：源程序量 + 开发目的 + 面向领域 + 主要功能(500-1300字) + 技术特点(分类标签+描述) + 鉴别材料类型
    """
    source_code_lines: int = 0             # *源程序量（行）
    purpose: str = ""                      # *开发目的  0/50
    target_industry: str = ""              # *面向领域/行业  0/50
    main_functions: str = ""                # *软件的主要功能  0/500~1300
    tech_tags: List[str] = field(default_factory=list)   # *软件的技术特点（分类标签）
    tech_desc: str = ""                    # 技术特点补充描述  0/100
    program_submit_type: str = "normal"    # 程序鉴别材料 normal/exception
    doc_submit_type: str = "normal"        # 文档鉴别材料 normal/exception


@dataclass
class AgentCredentials:
    """软著平台账号凭据"""
    username: str = ""
    password: str = ""
    url: str = "https://ccopyright.com.cn"


@dataclass
class SoftCopyrightApplication:
    """完整的软著登记申请表数据"""
    software: SoftwareInfo = field(default_factory=SoftwareInfo)
    copyright_holder: CopyrightHolder = field(default_factory=CopyrightHolder)
    right: RightInfo = field(default_factory=RightInfo)
    dev: DevelopmentInfo = field(default_factory=DevelopmentInfo)
    feature: FeatureInfo = field(default_factory=FeatureInfo)
    source_code_dir: str = ""
    manual_path: str = ""
    output_dir: str = "./output"

    # 兼容旧字段的快捷访问
    @property
    def tech(self):
        """向后兼容旧的 tech 属性"""
        class _CompatTech:
            def __init__(self, app):
                self._app = app
                self.hardware_env = f"{app.dev.dev_hardware_env} | {app.dev.run_hardware_env}"
                self.software_env = f"{app.dev.dev_os} / {app.dev.run_platform}"
                self.languages = app.dev.languages
                self.source_code_lines = app.feature.source_code_lines
                self.main_features = app.feature.main_functions
        return _CompatTech(self)
