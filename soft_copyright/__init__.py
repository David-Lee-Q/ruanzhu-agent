"""
软著登记自动化智能体 (Software Copyright Registration Agent)

基于：中国版权保护中心 R11软件著作权登记申请 平台真实字段结构
"""

__version__ = "2.0.0"
__platform__ = "R11软件著作权登记申请"

from .config import (
    # 常量
    SPEC, SOFTWARE_CATEGORIES, DEVELOPMENT_TYPES, RIGHT_TYPES,
    FIELD_LENGTHS, PLATFORM_LANGUAGE_BUTTONS, LANGUAGE_DISPLAY_MAP,
    TECH_FEATURE_TAGS, SUBMISSION_TYPES,
    # 数据类
    SoftwareInfo, CopyrightHolder, RightInfo,
    DevelopmentInfo, FeatureInfo, AgentCredentials,
    SoftCopyrightApplication,
)

from .processors.source_code import SourceCodeProcessor
from .processors.manual import ManualProcessor
from .processors.extractor import InfoExtractor
from .validators.fields import SoftCopyrightValidator, ValidationError
from .generators.pdf_generator import PDFGenerator
from .agent.platform_agent import CopyrightPlatformAgent
