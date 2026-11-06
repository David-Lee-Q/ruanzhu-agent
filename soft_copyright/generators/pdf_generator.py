"""
软著登记自动化智能体 - PDF生成器

功能：
1. 源程序PDF生成（每页50行，含页眉页码）
2. 说明书PDF生成（每页30行，含页眉页码）
3. 页眉格式：软件全称 + 版本号（与申请表一致）
4. 页脚格式：居中页码
"""

import os
from typing import List, Optional

from ..config import SPEC


class SourceCodePDFGenerator:
    """源程序PDF生成器"""

    def __init__(self, software_name: str = "", version: str = ""):
        self.software_name = software_name
        self.version = version

    def generate(self, pages: List[List[str]], output_path: str,
                 lines_per_page: int = None) -> str:
        """
        生成源程序PDF

        Args:
            pages: 分页后的代码行列表
            output_path: 输出PDF路径
            lines_per_page: 每页行数（校验用）

        Returns:
            输出文件路径
        """
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import mm
            from reportlab.pdfgen import canvas
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        except ImportError:
            raise ImportError("生成PDF需要安装 reportlab: pip install reportlab")

        lines_per_page = lines_per_page or SPEC["SOURCE_CODE_MIN_LINES_PER_PAGE"]

        # 注册中文字体
        try:
            pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
            font_name = 'STSong-Light'
            font_encoding = 'UnicodeCIDFont'
        except:
            font_name = 'Helvetica'

        # 创建PDF
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        c = canvas.Canvas(output_path, pagesize=A4)
        width, height = A4

        # 边距设置
        left = SPEC["PAGE_MARGIN_LEFT"]
        right = width - SPEC["PAGE_MARGIN_RIGHT"]
        top = height - SPEC["PAGE_MARGIN_TOP"]
        bottom = SPEC["PAGE_MARGIN_BOTTOM"]

        line_height = SPEC["CODE_LINE_HEIGHT"]
        code_font_size = SPEC["CODE_FONT_SIZE"]

        for page_idx, page_lines in enumerate(pages):
            # === 绘制页眉 ===
            c.setFont(font_name, SPEC["HEADER_FONT_SIZE"])
            header_text = f"{self.software_name}  Version {self.version}"
            c.drawString(left, top + 10, header_text)

            # 页眉分隔线
            c.setStrokeColorRGB(0.7, 0.7, 0.7)
            c.line(left, top + 5, right, top + 5)
            c.setStrokeColorRGB(0, 0, 0)

            # === 绘制代码 ===
            current_y = top - 15
            c.setFont(font_name, code_font_size)

            for line_idx, line in enumerate(page_lines):
                if current_y < bottom:
                    # 换页
                    c.showPage()

                    # 新页页眉
                    c.setFont(font_name, SPEC["HEADER_FONT_SIZE"])
                    c.drawString(left, top + 10, header_text)
                    c.line(left, top + 5, right, top + 5)
                    c.setFont(font_name, code_font_size)
                    current_y = top - 15

                # 处理超长行 - 截断或分行
                if len(line) > 120:
                    line = line[:117] + "..."

                c.drawString(left, current_y, line)
                current_y -= line_height

            # === 绘制页脚（页码） ===
            page_num = page_idx + 1
            c.setFont(font_name, 8)
            c.drawCentredString(width / 2, bottom - 15, f"- {page_num} -")

            c.showPage()

        c.save()
        return output_path


class ManualPDFGenerator:
    """说明书PDF生成器"""

    def __init__(self, software_name: str = "", version: str = ""):
        self.software_name = software_name
        self.version = version

    def generate(self, pages: List[List[str]], output_path: str,
                 lines_per_page: int = None) -> str:
        """
        生成说明书PDF

        Args:
            pages: 分页后的文本行列表
            output_path: 输出PDF路径
            lines_per_page: 每页行数（校验用）

        Returns:
            输出文件路径
        """
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import mm
            from reportlab.pdfgen import canvas
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        except ImportError:
            raise ImportError("生成PDF需要安装 reportlab: pip install reportlab")

        lines_per_page = lines_per_page or SPEC["DOC_MIN_LINES_PER_PAGE"]

        # 注册中文字体
        try:
            pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
            font_name = 'STSong-Light'
        except:
            font_name = 'Helvetica'

        # 创建PDF
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        c = canvas.Canvas(output_path, pagesize=A4)
        width, height = A4

        # 边距设置
        left = SPEC["PAGE_MARGIN_LEFT"]
        right = width - SPEC["PAGE_MARGIN_RIGHT"]
        top = height - SPEC["PAGE_MARGIN_TOP"]
        bottom = SPEC["PAGE_MARGIN_BOTTOM"]

        line_height = 16  # 说明书行高更大
        text_font_size = 11  # 说明书字号更大

        for page_idx, page_lines in enumerate(pages):
            # === 绘制页眉 ===
            c.setFont(font_name, SPEC["HEADER_FONT_SIZE"])
            header_text = f"{self.software_name}  Version {self.version}"
            c.drawString(left, top + 10, header_text)

            # 页眉分隔线
            c.setStrokeColorRGB(0.7, 0.7, 0.7)
            c.line(left, top + 5, right, top + 5)
            c.setStrokeColorRGB(0, 0, 0)

            # === 绘制文本 ===
            current_y = top - 15
            c.setFont(font_name, text_font_size)

            for line_idx, line in enumerate(page_lines):
                if current_y < bottom:
                    c.showPage()
                    c.setFont(font_name, SPEC["HEADER_FONT_SIZE"])
                    c.drawString(left, top + 10, header_text)
                    c.line(left, top + 5, right, top + 5)
                    c.setFont(font_name, text_font_size)
                    current_y = top - 15

                # 处理超长行 - 简单的自动换行
                while len(line) > 70:
                    c.drawString(left, current_y, line[:68] + "-")
                    line = line[68:]
                    current_y -= line_height
                    if current_y < bottom:
                        c.showPage()
                        c.setFont(font_name, SPEC["HEADER_FONT_SIZE"])
                        c.drawString(left, top + 10, header_text)
                        c.line(left, top + 5, right, top + 5)
                        c.setFont(font_name, text_font_size)
                        current_y = top - 15

                c.drawString(left, current_y, line)
                current_y -= line_height

            # === 绘制页脚（页码） ===
            page_num = page_idx + 1
            c.setFont(font_name, 9)
            c.drawCentredString(width / 2, bottom - 15, f"- {page_num} -")

            c.showPage()

        c.save()
        return output_path


class PDFGenerator:
    """统一PDF生成器接口"""

    def __init__(self, software_name: str, version: str):
        self.software_name = software_name
        self.version = version
        self.source_gen = SourceCodePDFGenerator(software_name, version)
        self.manual_gen = ManualPDFGenerator(software_name, version)

    def generate_all(self, source_pages: List[List[str]], manual_pages: List[List[str]],
                     output_dir: str) -> dict:
        """
        生成所有提交用PDF

        Args:
            source_pages: 源程序提交页
            manual_pages: 说明书提交页
            output_dir: 输出目录

        Returns:
            生成文件路径字典
        """
        os.makedirs(output_dir, exist_ok=True)

        source_pdf_path = os.path.join(output_dir, "source_code_submit.pdf")
        manual_pdf_path = os.path.join(output_dir, "manual_submit.pdf")

        print(f"  生成源程序PDF: {source_pdf_path}")
        self.source_gen.generate(source_pages, source_pdf_path)

        print(f"  生成说明书PDF: {manual_pdf_path}")
        self.manual_gen.generate(manual_pages, manual_pdf_path)

        return {
            'source_code_pdf': source_pdf_path,
            'manual_pdf': manual_pdf_path,
        }
