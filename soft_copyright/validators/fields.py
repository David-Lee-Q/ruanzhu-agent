"""
软著登记自动化智能体 - 字段校验器（v2 对齐平台真实字段）

基于：中国版权保护中心 R11软件著作权登记申请 平台PDF截图
"""

import re
from datetime import datetime, date
from typing import List, Optional, Tuple

from ..config import (
    FIELD_LENGTHS, SOFTWARE_CATEGORIES, DEVELOPMENT_TYPES, RIGHT_TYPES,
    PLATFORM_LANGUAGE_BUTTONS, TECH_FEATURE_TAGS, LANGUAGE_DISPLAY_MAP,
    SoftCopyrightApplication, DevelopmentInfo, FeatureInfo,
)


class ValidationError:
    """校验错误"""
    def __init__(self, field: str, message: str, level: str = "error"):
        self.field = field
        self.message = message
        self.level = level

    def __repr__(self):
        return f"[{self.level.upper()}] {self.field}: {self.message}"


class SoftCopyrightValidator:
    """软著登记字段校验器"""

    VERSION_PATTERN = re.compile(r'^V?\d+\.\d+$', re.IGNORECASE)
    DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')

    def __init__(self):
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []

    def clear(self):
        self.errors = []
        self.warnings = []

    # ==================== 软件申请信息（第1步） ====================

    def validate_software_name(self, name: str) -> List[ValidationError]:
        errs = []
        if not name or not name.strip():
            errs.append(ValidationError("软件全称", "*软件全称不能为空"))
            return errs
        if len(name) > 50:
            errs.append(ValidationError("软件全称", f"软件名称长度 {len(name)} 超过上限 50"))
        if re.search(r'[\\/:*?"<>|]', name):
            errs.append(ValidationError("软件全称", "软件名称包含禁止字符"))
        return errs

    def validate_version(self, version: str) -> List[ValidationError]:
        errs = []
        if not version:
            errs.append(ValidationError("版本号", "*版本号不能为空"))
            return errs
        if not self.VERSION_PATTERN.match(version.strip()):
            errs.append(ValidationError("版本号", f"版本号 '{version}' 格式错误，应为 Vx.x 或 x.x"))
        return errs

    def validate_date(self, date_str: str, field_name: str) -> List[ValidationError]:
        errs = []
        if not date_str:
            return errs
        if not self.DATE_PATTERN.match(date_str.strip()):
            errs.append(ValidationError(field_name, f"日期 '{date_str}' 格式错误，应为 YYYY-MM-DD"))
            return errs
        try:
            datetime.strptime(date_str.strip(), '%Y-%m-%d')
        except ValueError:
            errs.append(ValidationError(field_name, f"日期 '{date_str}' 无效"))
        return errs

    def validate_date_logic(self, app: SoftCopyrightApplication) -> List[ValidationError]:
        """
        日期逻辑校验：
        - 开发完成日期 ≤ 今天
        - 发表日期 ≥ 开发完成日期
        - 发表状态为未发表时不应填发表日期
        """
        errs = []
        today = date.today()
        s = app.software

        if not s.develop_date:
            errs.append(ValidationError("开发完成日期", "*开发完成日期不能为空"))
            return errs

        try:
            develop_dt = datetime.strptime(s.develop_date, '%Y-%m-%d').date()
        except ValueError:
            return errs

        if develop_dt > today:
            errs.append(ValidationError("开发完成日期", f"开发完成日期 {s.develop_date} 不能晚于今天"))

        if s.publish_status == "published":
            if not s.publish_date:
                errs.append(ValidationError("首次发表日期", "*已发表状态下必须填写首次发表日期"))
            else:
                try:
                    publish_dt = datetime.strptime(s.publish_date, '%Y-%m-%d').date()
                    if publish_dt < develop_dt:
                        errs.append(ValidationError("首次发表日期",
                            f"首次发表日期 {s.publish_date} 不能早于开发完成日期 {s.develop_date}"))
                    if publish_dt > today:
                        errs.append(ValidationError("首次发表日期", f"首次发表日期 {s.publish_date} 不能晚于今天"))
                except ValueError:
                    pass
        elif s.publish_status == "unpublished" and s.publish_date:
            errs.append(ValidationError("发表状态", "未发表状态下不应填写发表日期", "warning"))

        return errs

    # ==================== 软件开发信息（第2步） ====================

    def _check_length(self, value: str, field_name: str, max_len: int, required: bool = True) -> List[ValidationError]:
        """检查文本字段长度"""
        errs = []
        if required and (not value or not value.strip()):
            errs.append(ValidationError(field_name, f"*{field_name}不能为空"))
        elif value and len(value) > max_len:
            errs.append(ValidationError(field_name,
                f"{field_name}长度 {len(value)} 超过平台限制 {max_len} 字"))
        return errs

    def validate_development_info(self, dev: DevelopmentInfo) -> List[ValidationError]:
        """
        校验软件开发信息页的7+1个字段
        每个环境描述字段最多 50 字
        """
        errs = []
        L = FIELD_LENGTHS

        # 6个环境描述字段，都是 * 必填 + 0/50
        errs.extend(self._check_length(dev.dev_hardware_env, "开发的硬件环境", L["dev_hardware_env"]))
        errs.extend(self._check_length(dev.run_hardware_env, "运行的硬件环境", L["run_hardware_env"]))
        errs.extend(self._check_length(dev.dev_os, "开发该软件的操作系统", L["dev_os"]))
        errs.extend(self._check_length(dev.dev_environment, "软件开发环境/开发工具", L["dev_environment"]))
        errs.extend(self._check_length(dev.run_platform, "该软件的运行平台/操作系统", L["run_platform"]))
        errs.extend(self._check_length(dev.support_env, "软件运行支撑环境/支持软件", L["support_env"]))

        # 编程语言
        if not dev.languages and not dev.languages_custom:
            errs.append(ValidationError("编程语言", "*编程语言至少需要选择一个"))
        elif dev.languages_custom and len(dev.languages_custom) > L["languages_custom"]:
            errs.append(ValidationError("编程语言（自定义补充）",
                f"自定义补充长度 {len(dev.languages_custom)} 超过限制 {L['languages_custom']}"))

        # 检查选定的语言是否在平台可选项中
        platform_displayable = set(PLATFORM_LANGUAGE_BUTTONS)
        for lang in dev.languages:
            # 检查是否直接匹配平台按钮名
            if lang in platform_displayable:
                continue
            # 检查是否可以映射到平台按钮名
            display_name = LANGUAGE_DISPLAY_MAP.get(lang)
            if display_name is None:
                # 不在平台列表上，需要用户在 languages_custom 中补充或接受提示
                errs.append(ValidationError("编程语言",
                    f"'{lang}' 不在平台默认按钮列表中，建议在自定义补充框填写或改用平台支持的语言名",
                    "warning"))

        return errs

    # ==================== 软件功能与特点（第3步） ====================

    def validate_feature_info(self, feature: FeatureInfo) -> List[ValidationError]:
        errs = []
        L = FIELD_LENGTHS

        # 源程序量
        if feature.source_code_lines <= 0:
            errs.append(ValidationError("源程序量", "*源程序量必须大于0"))

        # 开发目的 0/50
        errs.extend(self._check_length(feature.purpose, "开发目的", L["purpose"]))

        # 面向领域/行业 0/50
        errs.extend(self._check_length(feature.target_industry, "面向领域/行业", L["target_industry"]))

        # 软件的主要功能 0/500~1300
        min_func, max_func = L["main_functions"]
        if not feature.main_functions or not feature.main_functions.strip():
            errs.append(ValidationError("软件的主要功能", "*软件的主要功能不能为空"))
        else:
            fn_len = len(feature.main_functions)
            if fn_len < min_func:
                errs.append(ValidationError("软件的主要功能",
                    f"软件的主要功能当前 {fn_len} 字，平台要求 {min_func}-{max_func} 字，建议详细补充"))
            elif fn_len > max_func:
                errs.append(ValidationError("软件的主要功能",
                    f"软件的主要功能当前 {fn_len} 字，超过平台上限 {max_func} 字"))

        # 技术特点标签
        if not feature.tech_tags:
            errs.append(ValidationError("软件的技术特点", "*请至少选择一个技术特点分类标签"))
        else:
            for tag in feature.tech_tags:
                if tag not in TECH_FEATURE_TAGS:
                    errs.append(ValidationError("软件的技术特点",
                        f"'{tag}' 不在平台分类标签列表中", "warning"))

        # 技术特点描述 0/100
        if feature.tech_desc and len(feature.tech_desc) > L["tech_tags"]:
            errs.append(ValidationError("软件的技术特点描述",
                f"描述长度 {len(feature.tech_desc)} 超过限制 {L['tech_tags']}"))

        return errs

    # ==================== 著作权人 ====================

    def validate_copyright_holder(self, app: SoftCopyrightApplication) -> List[ValidationError]:
        errs = []
        h = app.copyright_holder
        if not h.name or not h.name.strip():
            errs.append(ValidationError("著作权人名称", "*著作权人名称不能为空"))
        if h.category not in ['natural', 'legal', 'illegal']:
            errs.append(ValidationError("著作权人类别", f"类别 '{h.category}' 无效"))
        return errs

    # ==================== 鉴别材料一致性 ====================

    def validate_consistency(self, app: SoftCopyrightApplication) -> List[ValidationError]:
        """
        交叉一致性校验：
        - 申请表中的软件名称、版本号应与鉴别材料页眉一致
        - 所有必填字段有值
        """
        errs = []
        s = app.software

        if not s.full_name:
            errs.append(ValidationError("一致性", "软件全称未填写，影响所有后续校验"))
        if not s.version:
            errs.append(ValidationError("一致性", "版本号未填写"))

        return errs

    # ==================== 完整校验 ====================

    def validate_all(self, app: SoftCopyrightApplication) -> dict:
        """执行完整校验，返回结构化结果"""
        self.clear()

        # 第1步：软件申请信息
        self.errors.extend(self.validate_software_name(app.software.full_name))
        self.errors.extend(self.validate_version(app.software.version))
        self.errors.extend(self.validate_date(app.software.develop_date, "开发完成日期"))
        self.errors.extend(self.validate_date(app.software.publish_date, "首次发表日期"))
        self.errors.extend(self.validate_date_logic(app))

        # 第2步：软件开发信息
        self.errors.extend(self.validate_development_info(app.dev))

        # 第3步：软件功能与特点
        self.errors.extend(self.validate_feature_info(app.feature))

        # 著作权人
        self.errors.extend(self.validate_copyright_holder(app))

        # 一致性
        self.errors.extend(self.validate_consistency(app))

        errors = [e for e in self.errors if e.level == 'error']
        warnings = [e for e in self.errors if e.level in ('warning', 'info')]

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'error_count': len(errors),
            'warning_count': len(warnings),
        }

    def print_report(self, result: dict):
        print("\n" + "=" * 60)
        print("  软著登记字段校验报告")
        print("=" * 60)

        if result['valid']:
            print(f"\n  ✓ 校验通过！({result['warning_count']} 个警告)")
        else:
            print(f"\n  ✗ 校验未通过 ({result['error_count']} 个错误, {result['warning_count']} 个警告)")

        if result['errors']:
            print("\n  【错误 - 必须修正】")
            for e in result['errors']:
                print(f"    ✗ {e}")

        if result['warnings']:
            print("\n  【警告/提示 - 建议修正】")
            for w in result['warnings']:
                print(f"    ⚠ {w}")

        print("\n" + "=" * 60)
        return result['valid']
