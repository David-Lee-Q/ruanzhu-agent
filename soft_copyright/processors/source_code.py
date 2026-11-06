"""
软著登记自动化智能体 - 源程序文件处理器

功能：
1. 扫描目录下的所有源文件
2. 自动识别编程语言
3. 去除空行和注释
4. 合并为单一文件
5. 按每页50行格式生成
6. 添加页眉（软件名称+版本号）和页码
7. 截取前30页和后30页
"""

import os
import re
from typing import List, Tuple, Optional
from pathlib import Path

from ..config import (
    SPEC,
    EXTENSION_LANGUAGE_MAP,
    LANGUAGE_COMMENT_STYLES,
)


class SourceCodeProcessor:
    """源程序文件处理器"""

    def __init__(self, software_name: str = "", version: str = "",
                 lines_per_page: int = None):
        self.software_name = software_name
        self.version = version
        self.lines_per_page = lines_per_page or SPEC["SOURCE_CODE_MIN_LINES_PER_PAGE"]
        self.detected_languages = set()

    def scan_source_files(self, directory: str, exclude_dirs: List[str] = None) -> List[str]:
        """
        扫描目录中的所有源文件

        Args:
            directory: 源程序根目录
            exclude_dirs: 要排除的目录（如 node_modules, .git 等）

        Returns:
            源文件路径列表
        """
        exclude_dirs = exclude_dirs or [
            ".git", ".svn", "__pycache__", "node_modules",
            "dist", "build", ".idea", ".vscode", ".venv", "venv",
            ".tox", ".eggs", "target", "bin", "obj",
        ]

        source_files = []
        directory = os.path.abspath(directory)

        for root, dirs, files in os.walk(directory):
            # 排除指定目录
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for filename in sorted(files):
                ext = os.path.splitext(filename)[1].lower()
                if ext in EXTENSION_LANGUAGE_MAP:
                    source_files.append(os.path.join(root, filename))
                    self.detected_languages.add(EXTENSION_LANGUAGE_MAP[ext])

        return sorted(source_files)

    def detect_languages(self, source_files: List[str]) -> List[str]:
        """
        检测编程语言

        Args:
            source_files: 源文件路径列表

        Returns:
            检测到的编程语言列表
        """
        languages = set()
        for filepath in source_files:
            ext = os.path.splitext(filepath)[1].lower()
            lang = EXTENSION_LANGUAGE_MAP.get(ext)
            if lang:
                languages.add(lang)
        return sorted(languages)

    def read_file_content(self, filepath: str, encoding: str = None) -> str:
        """
        读取文件内容，自动尝试多种编码

        Args:
            filepath: 文件路径
            encoding: 强制指定编码

        Returns:
            文件内容
        """
        if encoding:
            with open(filepath, 'r', encoding=encoding, errors='replace') as f:
                return f.read()

        # 尝试多种编码
        encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'utf-16', 'latin-1']
        for enc in encodings:
            try:
                with open(filepath, 'r', encoding=enc) as f:
                    return f.read()
            except (UnicodeDecodeError, UnicodeError):
                continue

        # 兜底方案
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()

    def strip_comments(self, content: str, language: str) -> str:
        """
        去除注释

        Args:
            content: 源代码内容
            language: 编程语言

        Returns:
            去除注释后的代码
        """
        styles = LANGUAGE_COMMENT_STYLES.get(language, {})
        result = content

        # 去除块注释
        block_style = styles.get("block")
        if block_style:
            start, end = block_style
            pattern = re.escape(start) + r'.*?' + re.escape(end)
            result = re.sub(pattern, '', result, flags=re.DOTALL)

        # 去除行注释
        single_comment = styles.get("single")
        if single_comment:
            lines = result.split('\n')
            cleaned_lines = []
            for line in lines:
                # 保留字符串内的内容，但这会导致一些边界问题
                # 简化处理：去除从注释标记到行尾的内容
                if single_comment in line:
                    idx = line.index(single_comment)
                    cleaned_lines.append(line[:idx])
                else:
                    cleaned_lines.append(line)
            result = '\n'.join(cleaned_lines)

        return result

    def clean_source_code(self, content: str, language: str = None) -> List[str]:
        """
        清洗源代码：去注释 -> 去空行 -> 去尾部空格

        Args:
            content: 原始代码内容
            language: 编程语言（用于去注释）

        Returns:
            清洗后的代码行列表
        """
        if language:
            content = self.strip_comments(content, language)

        # 分割为行
        lines = content.split('\n')

        # 去尾部空格、去空行
        cleaned = []
        for line in lines:
            stripped = line.rstrip()
            if stripped:
                cleaned.append(stripped)

        return cleaned

    def merge_source_code(self, source_files: List[str]) -> Tuple[List[str], dict]:
        """
        合并所有源文件为单一代码行列表

        Args:
            source_files: 源文件路径列表

        Returns:
            (所有代码行列表, 统计信息)
        """
        all_lines = []
        stats = {
            'total_files': len(source_files),
            'total_lines_raw': 0,
            'total_lines_clean': 0,
            'files_by_language': {},
        }

        for filepath in source_files:
            ext = os.path.splitext(filepath)[1].lower()
            language = EXTENSION_LANGUAGE_MAP.get(ext, 'Unknown')

            # 读取并清洗
            raw_content = self.read_file_content(filepath)
            stats['total_lines_raw'] += len(raw_content.split('\n'))

            cleaned_lines = self.clean_source_code(raw_content, language)
            all_lines.extend(cleaned_lines)
            stats['total_lines_clean'] += len(cleaned_lines)

            # 按语言统计
            if language not in stats['files_by_language']:
                stats['files_by_language'][language] = {'files': 0, 'lines': 0}
            stats['files_by_language'][language]['files'] += 1
            stats['files_by_language'][language]['lines'] += len(cleaned_lines)

        return all_lines, stats

    def paginate(self, lines: List[str], lines_per_page: int = None) -> List[List[str]]:
        """
        将代码行分页

        Args:
            lines: 代码行列表
            lines_per_page: 每页行数

        Returns:
            页列表，每页是一组代码行
        """
        if not lines_per_page:
            lines_per_page = self.lines_per_page

        pages = []
        for i in range(0, len(lines), lines_per_page):
            pages.append(lines[i:i + lines_per_page])

        # 处理最后一页不足的情况 - 用空行补齐至每页50行
        if pages and len(pages[-1]) < lines_per_page:
            last_page = pages[-1]
            # 为了软著审查通过，最后一页的最后一行应为代码
            # 不强制补齐空行，让最后一页保持原样
            pass

        return pages

    def select_submission_pages(self, pages: List[List[str]],
                                 front_count: int = None,
                                 back_count: int = None) -> List[List[str]]:
        """
        选择提交的页码（前30页 + 后30页）

        Args:
            pages: 所有页面
            front_count: 前N页
            back_count: 后N页

        Returns:
            提交的页面列表
        """
        front_count = front_count or SPEC["FRONT_PAGES"]
        back_count = back_count or SPEC["BACK_PAGES"]
        threshold = SPEC["TOTAL_PAGES_THRESHOLD"]

        total = len(pages)

        if total <= threshold:
            # 不足60页，全部提交
            return pages

        # 取前front_count页 + 后back_count页，去重
        selected = pages[:front_count]

        start_back = max(front_count, total - back_count)
        back_pages = pages[start_back:]
        selected.extend(back_pages)

        return selected

    def process(self, source_dir: str, output_dir: str = "./output") -> dict:
        """
        完整处理流程

        Args:
            source_dir: 源程序目录
            output_dir: 输出目录

        Returns:
            处理结果统计信息
        """
        os.makedirs(output_dir, exist_ok=True)

        # 1. 扫描源文件
        source_files = self.scan_source_files(source_dir)
        if not source_files:
            raise ValueError(f"在目录 {source_dir} 中未找到任何源文件！")

        # 2. 合并与清洗
        all_lines, stats = self.merge_source_code(source_files)
        stats['detected_languages'] = self.detect_languages(source_files)

        # 3. 分页
        all_pages = self.paginate(all_lines)
        stats['total_pages'] = len(all_pages)

        # 4. 选择提交页
        submit_pages = self.select_submission_pages(all_pages)
        stats['submit_pages'] = len(submit_pages)

        # 5. 保存合并后的代码（原始合并版，便于人工检查）
        merged_path = os.path.join(output_dir, "source_code_merged.txt")
        with open(merged_path, 'w', encoding='utf-8') as f:
            for i, page in enumerate(all_pages):
                f.write(f"\n{'='*60}\n")
                f.write(f"# Page {i+1}\n")
                f.write(f"{'='*60}\n")
                for line in page:
                    f.write(line + '\n')

        stats['merged_file'] = merged_path

        # 6. 保存提交用代码
        submit_path = os.path.join(output_dir, "source_code_submit.txt")
        with open(submit_path, 'w', encoding='utf-8') as f:
            for i, page in enumerate(submit_pages):
                f.write(f"\n{'='*60}\n")
                f.write(f"# Submit Page {i+1} (original page {all_pages.index(page)+1 if page in all_pages else '?'})\n")
                f.write(f"{'='*60}\n")
                for line in page:
                    f.write(line + '\n')

        stats['submit_file'] = submit_path
        stats['submit_pages_list'] = [all_pages.index(p) + 1 for p in submit_pages if p in all_pages]

        return stats

    def get_submission_lines(self, source_dir: str) -> List[str]:
        """
        获取用于提交的代码行（前30页+后30页，按每页50行计算）

        Returns:
            提交用代码行列表
        """
        source_files = self.scan_source_files(source_dir)
        all_lines, _ = self.merge_source_code(source_files)
        all_pages = self.paginate(all_lines)
        submit_pages = self.select_submission_pages(all_pages)

        result = []
        for page in submit_pages:
            result.extend(page)
        return result

    def get_total_line_count(self, source_dir: str) -> int:
        """
        获取源程序总行数（清洗后）

        Args:
            source_dir: 源程序目录

        Returns:
            代码行数
        """
        source_files = self.scan_source_files(source_dir)
        all_lines, _ = self.merge_source_code(source_files)
        return len(all_lines)
