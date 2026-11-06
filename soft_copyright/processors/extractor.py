"""
软著登记自动化智能体 - 信息自动提取器

功能：
1. 从源程序自动提取：编程语言、代码行数
2. 从说明书自动提取：软件名称、版本号、功能特点
3. 生成默认的申请表字段建议
"""

import os
import re
from typing import List, Optional, Tuple

from ..config import (
    EXTENSION_LANGUAGE_MAP,
    SOFTWARE_CATEGORIES,
    SoftCopyrightApplication, SoftwareInfo,
)
from .source_code import SourceCodeProcessor


class InfoExtractor:
    """软著申请信息自动提取器"""

    # 常见的软件版本号正则模式
    VERSION_PATTERNS = [
        re.compile(r'version\s*[:=]?\s*[Vv]?(\d+\.\d+(?:\.\d+)?)'),
        re.compile(r'ver\s*[:=]?\s*[Vv]?(\d+\.\d+(?:\.\d+)?)'),
        re.compile(r'__version__\s*=\s*["\']([\d.Vv]+)["\']'),
        re.compile(r'appVersion\s*[:=]\s*["\']([\d.Vv]+)["\']'),
        re.compile(r'softwareVersion\s*[:=]\s*["\']([\d.Vv]+)["\']'),
        re.compile(r'版本[：:]\s*[Vv]?(\d+\.\d+(?:\.\d+)?)'),
    ]

    # 软件名称模式
    NAME_PATTERNS = [
        re.compile(r'软件名称[：:]\s*([^\n\r，,。.；;]{2,50})'),
        re.compile(r'软件全称[：:]\s*([^\n\r，,。.；;]{2,50})'),
        re.compile(r'Software\s*Name[：:]\s*([^\n\r，,。.；;]{2,50})'),
        re.compile(r'项目名称[：:]\s*([^\n\r，,。.；;]{2,50})'),
        re.compile(r'产品名称[：:]\s*([^\n\r，,。.；;]{2,50})'),
    ]

    # 功能描述关键词
    FEATURE_KEYWORDS = [
        '主要功能', '核心功能', '系统功能', '功能特点', '系统特点',
        '应用场景', '技术架构', '技术特点', '创新点', '业务特点',
    ]

    def __init__(self):
        self.source_processor = SourceCodeProcessor()

    # ==================== 源程序信息提取 ====================

    def extract_from_source(self, source_dir: str) -> dict:
        """
        从源程序目录提取信息

        Returns:
            提取的信息字典
        """
        if not os.path.isdir(source_dir):
            return {}

        source_files = self.source_processor.scan_source_files(source_dir)
        if not source_files:
            return {}

        # 语言统计
        languages = {}
        for filepath in source_files:
            ext = os.path.splitext(filepath)[1].lower()
            lang = EXTENSION_LANGUAGE_MAP.get(ext, 'Unknown')
            languages[lang] = languages.get(lang, 0) + 1

        # 计算代码行数
        all_lines, stats = self.source_processor.merge_source_code(source_files)

        # 查找版本号
        version = self._find_version_in_source(source_files)

        return {
            'languages': list(languages.keys()),
            'languages_detail': languages,
            'source_code_lines': len(all_lines),
            'source_files': source_files,
            'total_files': len(source_files),
            'version_from_source': version,
        }

    def _find_version_in_source(self, source_files: List[str]) -> Optional[str]:
        """
        在源文件中搜索版本号定义
        """
        for filepath in source_files[:20]:  # 限制搜索范围
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()

                for pattern in self.VERSION_PATTERNS:
                    match = pattern.search(content)
                    if match:
                        return match.group(1)
            except:
                continue

        return None

    # ==================== 说明书信息提取 ====================

    def extract_from_manual(self, manual_content: str) -> dict:
        """
        从说明书文本提取信息

        Args:
            manual_content: 说明书纯文本内容

        Returns:
            提取的信息字典
        """
        if not manual_content:
            return {}

        result = {}

        # 搜索软件名称
        for pattern in self.NAME_PATTERNS:
            match = pattern.search(manual_content)
            if match:
                name = match.group(1).strip()
                if len(name) >= 2:
                    result['software_name'] = name
                    break

        # 搜索版本号
        for pattern in self.VERSION_PATTERNS:
            match = pattern.search(manual_content)
            if match:
                result['version'] = match.group(1)
                break

        # 提取功能描述
        features = self._extract_features(manual_content)
        if features:
            result['main_features'] = features

        # 统计字数
        result['manual_word_count'] = len(manual_content)
        result['manual_line_count'] = len(manual_content.split('\n'))

        return result

    def _extract_features(self, content: str, max_length: int = 500) -> str:
        """
        从文档中提取功能描述
        """
        lines = content.split('\n')
        features_lines = []
        capturing = False

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # 检测功能段落开始
            for keyword in self.FEATURE_KEYWORDS:
                if keyword in line_stripped:
                    capturing = True
                    break

            if capturing and line_stripped:
                # 跳过只有标题的行
                if line_stripped in self.FEATURE_KEYWORDS:
                    continue

                # 检测段落结束（遇到下一个标题关键词）
                is_next_section = False
                for keyword in self.FEATURE_KEYWORDS + ['目录', '目录页', '第一章', '第二章', '前言', '概述', '简介']:
                    if keyword in line_stripped and len(line_stripped) < 30:
                        is_next_section = True
                        break

                if is_next_section:
                    capturing = False
                    continue

                features_lines.append(line_stripped)

                if sum(len(l) for l in features_lines) > max_length:
                    break

        if features_lines:
            return '\n'.join(features_lines)

        return ''

    # ==================== 综合提取 ====================

    def extract_all(self, source_dir: str = None, manual_content: str = None) -> dict:
        """
        综合从多个来源提取信息

        Returns:
            完整的提取信息字典
        """
        result = {}

        if source_dir:
            source_info = self.extract_from_source(source_dir)
            result.update({f'source_{k}': v for k, v in source_info.items()})

        if manual_content:
            manual_info = self.extract_from_manual(manual_content)
            result.update({f'manual_{k}': v for k, v in manual_info.items()})

        return result

    def suggest_defaults(self, extracted: dict) -> dict:
        """
        基于提取信息生成默认建议值

        Returns:
            建议的默认值字典
        """
        suggestions = {}

        # 软件名称
        if extracted.get('manual_software_name'):
            suggestions['software_full_name'] = extracted['manual_software_name']
        elif extracted.get('source_version_from_source'):
            suggestions['software_full_name'] = "未命名软件"

        # 版本号
        version = extracted.get('manual_version') or extracted.get('source_version_from_source')
        if version:
            # 规范化版本号格式
            ver_clean = version.lstrip('Vv')
            suggestions['version'] = f"V{ver_clean}" if not version.upper().startswith('V') else version

        # 编程语言
        if extracted.get('source_languages'):
            suggestions['languages'] = extracted['source_languages']
        else:
            suggestions['languages'] = []

        # 源程序量
        if extracted.get('source_source_code_lines'):
            suggestions['source_code_lines'] = extracted['source_source_code_lines']

        # 功能描述
        if extracted.get('manual_main_features'):
            suggestions['main_features'] = extracted['manual_main_features']

        return suggestions


# 便捷函数

def read_manual_content(manual_path: str) -> str:
    """读取说明书内容为纯文本"""
    from .processors.manual import ManualProcessor
    processor = ManualProcessor()
    return processor.read_manual(manual_path)
