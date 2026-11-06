"""
软著登记自动化智能体 - 完整演示（v2）

创建示例源程序 + 说明书 → 自动提取信息 → 自动填充环境描述 → 生成 PDF → 字段校验
"""

import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from soft_copyright import (
    SoftwareInfo, CopyrightHolder, RightInfo,
    DevelopmentInfo, FeatureInfo, SoftCopyrightApplication,
    SourceCodeProcessor, ManualProcessor, InfoExtractor,
    SoftCopyrightValidator, PDFGenerator,
)
from main import auto_fill_dev_info, auto_fill_feature_info, _app_to_dict


def make_demo_project(base_dir):
    src = os.path.join(base_dir, "src")
    mdir = os.path.join(base_dir, "manual")
    os.makedirs(src, exist_ok=True)
    os.makedirs(mdir, exist_ok=True)

    # --- 示例源程序（约 232 行） ---
    files = {
        'main.py': '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智能管理系统 - 主入口 版本 V1.0"""
import sys
from app.core import Application
from app.config import Config

def main():
    print("启动智能管理系统...")
    config = Config.load("config.yaml")
    app = Application(config)
    app.initialize()
    try:
        app.run()
    except KeyboardInterrupt:
        print("收到退出信号...")
        app.shutdown()
    return 0

if __name__ == "__main__":
    sys.exit(main())
''',
        'app/__init__.py': '"""智能管理系统应用包"""\n__version__ = "1.0.0"\n',
        'app/core.py': '''# -*- coding: utf-8 -*-
"""应用核心模块"""
import logging
from typing import Optional
from .services import DataService, UserService
from .utils import Logger

class Application:
    def __init__(self, config):
        self.config = config
        self.logger = Logger.get_logger("Application")
        self.user_service = None
        self.data_service = None
        self.running = False

    def initialize(self):
        self.logger.info("初始化应用组件...")
        self.user_service = UserService(self.config.get("database"))
        self.data_service = DataService(self.config.get("database"))
        self.logger.info("初始化完成")

    def run(self):
        self.running = True
        self.logger.info("应用已启动")
        while self.running:
            self._process_requests()
            self._check_status()

    def shutdown(self):
        self.logger.info("正在关闭...")
        self.running = False
        if self.user_service: self.user_service.cleanup()
        if self.data_service: self.data_service.cleanup()

    def _process_requests(self): pass
    def _check_status(self): pass
''',
        'app/config.py': '''# -*- coding: utf-8 -*-
"""配置管理"""
import os
import yaml
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class Config:
    database: Dict[str, Any] = field(default_factory=dict)
    server: Dict[str, Any] = field(default_factory=dict)
    features: Dict[str, bool] = field(default_factory=dict)

    @classmethod
    def load(cls, path):
        config = cls()
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                config.database = data.get("database", {})
                config.server = data.get("server", {})
                config.features = data.get("features", {})
        return config

    def get(self, key, default=None):
        return getattr(self, key, default)
''',
        'app/services.py': '''# -*- coding: utf-8 -*-
"""服务层"""
from typing import List, Optional
from .models import User, DataModel

class BaseService:
    def __init__(self, db_config):
        self.db_config = db_config
        self._initialized = False
    def initialize(self): self._initialized = True
    def cleanup(self): self._initialized = False

class UserService(BaseService):
    def get_user(self, user_id):
        return User(id=user_id, username=f"user_{user_id}", email=f"user_{user_id}@example.com")
    def list_users(self, page=1, page_size=20):
        return [self.get_user(i) for i in range(1, page_size + 1)]
    def create_user(self, username, email, role="user"):
        return User(id=1, username=username, email=email, role=role)

class DataService(BaseService):
    def get_data(self, data_id):
        return DataModel(id=data_id, name=f"数据_{data_id}", content="示例内容")
    def list_data(self, category=None):
        return [self.get_data(i) for i in range(1, 11)]
    def save_data(self, data): return True
    def delete_data(self, data_id): return True
''',
        'app/models.py': '''# -*- coding: utf-8 -*-
"""数据模型"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

@dataclass
class User:
    id: int
    username: str
    email: str
    role: str = "user"
    created_at: Optional[datetime] = None
    is_active: bool = True
    def to_dict(self):
        return {"id": self.id, "username": self.username, "email": self.email,
                "role": self.role, "is_active": self.is_active}

@dataclass
class DataModel:
    id: int
    name: str
    content: str
    category: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    def add_tag(self, tag):
        if tag not in self.tags: self.tags.append(tag)
    def remove_tag(self, tag):
        if tag in self.tags: self.tags.remove(tag)
''',
        'app/utils.py': '''# -*- coding: utf-8 -*-
"""工具模块"""
import logging, hashlib
from datetime import datetime
from typing import Any

class Logger:
    _loggers = {}
    @classmethod
    def get_logger(cls, name):
        if name not in cls._loggers:
            logger = logging.getLogger(name)
            logger.setLevel(logging.INFO)
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            logger.addHandler(handler)
            cls._loggers[name] = logger
        return cls._loggers[name]

def hash_password(password, salt=""):
    combined = f"{salt}{password}"
    return hashlib.sha256(combined.encode()).hexdigest()

def format_datetime(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def safe_get(obj, key, default=None):
    if isinstance(obj, dict): return obj.get(key, default)
    return default
''',
    }

    for rel, content in files.items():
        full = os.path.join(src, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w', encoding='utf-8') as f:
            f.write(content)

    # --- 示例说明书 ---
    manual = '''# 智能管理系统 使用说明书

## 软件名称
智能管理系统 版本 V1.0

---

## 目录
1. 软件概述
2. 系统架构
3. 开发运行环境
4. 主要功能
5. 技术特点
6. 安装部署
7. 操作指南

---

## 1. 软件概述
智能管理系统是一套面向中小企业的综合管理平台，帮助企业提高运营效率、优化管理流程。
集成用户管理、数据管理、报表统计、权限控制等核心功能，支持多角色协同工作。

## 2. 系统架构
采用分层架构：表现层、业务逻辑层、数据访问层、基础设施层。
后端：Python + FastAPI，数据库：MySQL/PostgreSQL，前端：Vue.js。

## 3. 开发运行环境
开发机: x86_64 架构，4核CPU，8GB以上内存，256GB SSD。
操作系统: Windows 10/11、macOS 12+、Ubuntu 20.04+。
运行环境: Python 3.10+，MySQL 8.0+。

## 4. 主要功能

### 4.1 用户管理
- 用户注册、登录、认证
- 角色权限管理（管理员、普通用户、只读用户）
- 密码安全策略与重置流程
- 登录日志记录与审计

### 4.2 数据管理
- 多源数据接入与统一存储
- 数据录入、编辑、分类、搜索
- 批量导入导出（Excel/CSV格式）
- 数据清洗与版本控制

### 4.3 报表统计
- 多维度数据统计与分析
- 实时数据可视化图表
- 自定义报表设计器
- 报表导出（PDF/Excel/图片）
- 定时报表推送

### 4.4 系统管理
- 系统参数配置中心
- 操作日志完整记录
- 数据备份与恢复
- 性能监控与告警

## 5. 技术特点
- 高性能：异步 I/O，数据库查询优化，智能缓存
- 高可用：健康检查，故障转移，多副本备份
- 安全性：数据加密存储，传输加密，细粒度权限
- 易用性：直观 UI，完善文档，快捷键支持

## 6. 安装部署
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
```

## 7. 操作指南
1. 访问系统地址，输入用户名密码登录
2. 进入数据管理模块进行数据录入
3. 进入报表模块查看和生成报表
4. 管理员可进入系统配置进行参数调整

---
文档版本: V1.0 | 编制日期: 2025-01-15
'''
    mpath = os.path.join(mdir, "manual.md")
    with open(mpath, 'w', encoding='utf-8') as f:
        f.write(manual)

    return src, mpath


def main():
    print("\n" + "=" * 70)
    print("  软著登记自动化智能体 v2 - 完整演示")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmp:
        src_dir, manual_path = make_demo_project(tmp)
        out_dir = os.path.join(tmp, "output")
        os.makedirs(out_dir, exist_ok=True)

        app = SoftCopyrightApplication(
            software=SoftwareInfo(
                full_name="智能管理系统", version="V1.0", category_code="B01",
                develop_date="2025-01-15", publish_status="unpublished",
                development_type="independent", software_type="original",
            ),
            copyright_holder=CopyrightHolder(name="北京某某科技有限公司", category="legal"),
            source_code_dir=src_dir,
            manual_path=manual_path,
            output_dir=out_dir,
        )

        sp = SourceCodeProcessor("智能管理系统", "V1.0")
        mp = ManualProcessor("智能管理系统", "V1.0")

        # Step 1: 源程序
        print("\n【Step 1】处理源程序...")
        s = sp.process(src_dir, out_dir)
        print(f"  {s['total_files']} 文件 → {s['total_lines_clean']} 行 → {s['submit_pages']} 页提交")

        # Step 2: 说明书
        print("\n【Step 2】处理说明书...")
        ms = mp.process(manual_path, out_dir)
        print(f"  {ms['clean_lines']} 行 → {ms['submit_pages']} 页提交")

        # Step 3: 自动填充（环境描述 + 功能描述）
        print("\n【Step 3】自动填充 dev + feature 字段...")
        auto_fill_dev_info(app, s['detected_languages'])
        auto_fill_feature_info(app, s['total_lines_clean'], mp.read_manual(manual_path))

        print(f"  dev.dev_hardware_env: '{app.dev.dev_hardware_env}'")
        print(f"  dev.languages: {app.dev.languages}")
        print(f"  feature.source_code_lines: {app.feature.source_code_lines}")
        print(f"  feature.main_functions 字数: {len(app.feature.main_functions)}")
        print(f"  feature.tech_tags: {app.feature.tech_tags}")

        # Step 4: 生成 PDF
        print("\n【Step 4】生成 PDF...")
        all_lines, _ = sp.merge_source_code(sp.scan_source_files(src_dir))
        src_pages = sp.select_submission_pages(sp.paginate(all_lines))
        mcontent = mp.read_manual(manual_path)
        m_pages = mp.select_submission_pages(mp.paginate(mp.clean_text(mcontent)))

        try:
            pdfs = PDFGenerator(app.software.full_name, app.software.version) \
                .generate_all(src_pages, m_pages, out_dir)
            app._source_pdf = pdfs['source_code_pdf']
            app._manual_pdf = pdfs['manual_pdf']
            for p in pdfs.values():
                print(f"  ✓ {os.path.basename(p)}")
        except Exception as e:
            print(f"  ⚠️ PDF跳过: {e}")

        # Step 5: 字段校验
        print("\n【Step 5】字段校验...")
        r = SoftCopyrightValidator().validate_all(app)
        SoftCopyrightValidator().print_report(r)

        # Step 6: 保存 JSON
        info_path = os.path.join(out_dir, "application_info.json")
        with open(info_path, 'w', encoding='utf-8') as f:
            json.dump(_app_to_dict(app), f, ensure_ascii=False, indent=2)
        print(f"\n📄 申请数据: {info_path}")

        print("\n" + "=" * 70)
        print("  ✅ 演示完成！")
        print("=" * 70)


if __name__ == '__main__':
    main()
