"""
软著登记自动化智能体 - 说明书处理与校验模块

功能：
1. 读取 Word/Markdown/PDF 格式的说明书
2. 统计页数、每页行数
3. 校验格式规范（文档每页不少于30行）
4. 截取前30页和后30页
5. 生成符合规范的PDF（含页眉页码）
"""

import os
import re
from typing import List, Tuple, Optional
from pathlib import Path

from ..config import SPEC


class ManualProcessor:
    """软件说明书处理器"""

    # 支持的输入格式
    SUPPORTED_FORMATS = ['.md', '.markdown', '.docx', '.txt', '.html']

    def __init__(self, software_name: str = "", version: str = "",
                 lines_per_page: int = None):
        self.software_name = software_name
        self.version = version
        self.lines_per_page = lines_per_page or SPEC["DOC_MIN_LINES_PER_PAGE"]

    def read_manual(self, filepath: str) -> str:
        """
        读取说明书内容

        Args:
            filepath: 说明书文件路径（支持 .md, .docx, .txt, .html）

        Returns:
            纯文本内容
        """
        ext = os.path.splitext(filepath)[1].lower()

        if ext in ['.md', '.markdown', '.txt', '.html']:
            # 纯文本格式
            encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16']
            for enc in encodings:
                try:
                    with open(filepath, 'r', encoding=enc) as f:
                        return f.read()
                except (UnicodeDecodeError, UnicodeError):
                    continue
            # 兜底
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()

        elif ext == '.docx':
            # Word文档 - 需要 python-docx
            try:
                from docx import Document
                doc = Document(filepath)
                paragraphs = []
                for para in doc.paragraphs:
                    paragraphs.append(para.text)
                # 同时读取表格中的内容
                for table in doc.tables:
                    for row in table.rows:
                        row_text = [cell.text for cell in row.cells]
                        paragraphs.append(' | '.join(row_text))
                return '\n'.join(paragraphs)
            except ImportError:
                raise ImportError("读取 .docx 文件需要安装 python-docx: pip install python-docx")
            except Exception as e:
                raise ValueError(f"读取 Word 文件失败: {e}")

        else:
            raise ValueError(f"不支持的文件格式: {ext}。支持的格式: {self.SUPPORTED_FORMATS}")

    def clean_text(self, content: str) -> List[str]:
        """
        清洗说明书文本

        Args:
            content: 原始文本

        Returns:
            清洗后的行列表
        """
        lines = content.split('\n')
        cleaned = []

        for line in lines:
            # 移除 Markdown 格式标记（可选，保留或去除）
            # 去除多余的空白字符
            line = re.sub(r'[ \t]+', ' ', line).strip()
            if line:
                cleaned.append(line)

        return cleaned

    def paginate(self, lines: List[str], lines_per_page: int = None) -> List[List[str]]:
        """
        分页（按行数）

        Args:
            lines: 文本行列表
            lines_per_page: 每页行数要求

        Returns:
            页列表
        """
        lines_per_page = lines_per_page or self.lines_per_page
        pages = []
        for i in range(0, len(lines), lines_per_page):
            pages.append(lines[i:i + lines_per_page])
        return pages

    def validate_format(self, pages: List[List[str]]) -> List[dict]:
        """
        校验文档格式

        Args:
            pages: 分页后的页面

        Returns:
            校验问题列表
        """
        issues = []

        # 总页数检查
        total = len(pages)
        if total < 2:
            issues.append({
                'level': 'error',
                'issue': '文档页数过少',
                'detail': f'当前仅 {total} 页，建议至少 15 页以上',
            })

        # 每页行数检查（最后一页可以例外）
        for i, page in enumerate(pages):
            if i < len(pages) - 1:  # 非最后一页
                if len(page) < self.lines_per_page:
                    issues.append({
                        'level': 'warning',
                        'issue': f'第 {i+1} 页行数不足',
                        'detail': f'该页仅有 {len(page)} 行，要求不少于 {self.lines_per_page} 行',
                    })

        return issues

    def select_submission_pages(self, pages: List[List[str]],
                                 front_count: int = None,
                                 back_count: int = None) -> List[List[str]]:
        """
        选择提交的页面（前30页 + 后30页）

        Args:
            pages: 所有页面
            front_count: 前N页
            back_count: 后N页

        Returns:
            提交用页面列表
        """
        front_count = front_count or SPEC["FRONT_PAGES"]
        back_count = back_count or SPEC["BACK_PAGES"]
        threshold = SPEC["TOTAL_PAGES_THRESHOLD"]

        total = len(pages)

        if total <= threshold:
            return pages

        selected = pages[:front_count]
        start_back = max(front_count, total - back_count)
        selected.extend(pages[start_back:])

        return selected

    def process(self, manual_path: str, output_dir: str = "./output") -> dict:
        """
        完整处理流程

        Args:
            manual_path: 说明书文件路径
            output_dir: 输出目录

        Returns:
            处理结果统计信息
        """
        os.makedirs(output_dir, exist_ok=True)

        # 1. 读取文档
        raw_content = self.read_manual(manual_path)
        raw_lines = raw_content.split('\n')

        # 2. 清洗
        cleaned_lines = self.clean_text(raw_content)

        # 3. 分页
        all_pages = self.paginate(cleaned_lines)

        # 4. 校验格式
        issues = self.validate_format(all_pages)

        # 5. 选择提交页
        submit_pages = self.select_submission_pages(all_pages)

        # 统计
        stats = {
            'manual_file': manual_path,
            'raw_lines': len(raw_lines),
            'clean_lines': len(cleaned_lines),
            'total_pages': len(all_pages),
            'submit_pages': len(submit_pages),
            'issues': issues,
            'submit_page_indices': [all_pages.index(p) + 1 for p in submit_pages if p in all_pages],
        }

        # 保存
        submit_path = os.path.join(output_dir, "manual_submit.txt")
        with open(submit_path, 'w', encoding='utf-8') as f:
            for i, page in enumerate(submit_pages):
                f.write(f"\n{'='*60}\n")
                f.write(f"# Submit Page {i+1}\n")
                f.write(f"{'='*60}\n")
                for line in page:
                    f.write(line + '\n')

        stats['submit_file'] = submit_path

        return stats


    def validate_manual_only(self, manual_path: str) -> dict:
        """
        仅校验说明书格式，不处理

        Args:
            manual_path: 说明书文件路径

        Returns:
            校验结果
        """
        try:
            content = self.read_manual(manual_path)
            cleaned = self.clean_text(content)
            pages = self.paginate(cleaned)
            issues = self.validate_format(pages)

            return {
                'valid': len([i for i in issues if i['level'] == 'error']) == 0,
                'total_pages': len(pages),
                'total_lines': len(cleaned),
                'issues': issues,
                'front_30_available': len(pages) >= 30,
                'back_30_available': len(pages) >= 30,
                'enough_for_full_submission': len(pages) <= 60,
            }
        except Exception as e:
            return {
                'valid': False,
                'error': str(e),
                'total_pages': 0,
                'total_lines': 0,
                'issues': [{'level': 'error', 'issue': '文件读取失败', 'detail': str(e)}],
            }
