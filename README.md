# 软著登记自动化智能体

面向中国版权保护中心 **R11 软件著作权登记申请** 平台的自动化辅助工具。上传源程序与说明书后，自动生成合规的鉴别材料 PDF、从说明书真实内容中抽取并填充申请字段、校验平台字数/格式要求，并可选用浏览器自动填报。

## 核心功能

- **鉴别材料生成**：源程序按"前 30 页 + 后 30 页、每页 ≥ 50 行"截取，说明书按"每页 ≥ 30 行"分页，页眉自动带软件名与版本号，输出 PDF。
- **多形态源程序输入**：源码文件夹、单个源码文件、`.zip` 压缩包，或已生成好的源程序 PDF（自动直通并按页截取）。
- **说明书智能抽取**：解析 `.docx` / `.pdf` 说明书，自动生成开发目的、面向领域、主要功能、技术特点标签与技术描述。
  - 主要功能从说明书真实正文抽取（过滤目录、图注、路由、UI 排版等噪声），不再套用通用模板。
  - 技术特点标签采用"强区分词门槛 + 弱通用词降权 + 英文词边界匹配"打分，避免"数据/安全/权限"等通用词误判。
- **字段校验**：按平台真实字段与字数限制校验，输出报告。
- **浏览器自动填报**（可选）：基于 Playwright 驱动中国版权保护中心平台自动填报，需本机带图形界面运行。
- **Web UI + CLI 双入口**：图形化上传与一键生成，或命令行批处理。

## 目录结构

```
.
├── main.py                  # CLI 入口（prepare / validate / run）
├── demo.py                  # 端到端本地演示
├── config.example.yaml      # 配置文件示例
├── requirements.txt         # 依赖清单
├── start.sh                 # 生产启动脚本（gunicorn）
├── soft_copyright/
│   ├── config.py            # 常量、字数限制、数据类
│   ├── processors/
│   │   ├── source_code.py   # 源程序处理（分页 / 截取 / 语言识别）
│   │   ├── manual.py        # 说明书处理
│   │   └── extractor.py     # 信息提取
│   ├── generators/
│   │   └── pdf_generator.py # 鉴别材料 PDF 生成
│   ├── validators/
│   │   └── fields.py        # 字段校验
│   └── agent/
│       └── platform_agent.py# 平台自动填报（Playwright）
└── web/
    ├── app.py               # Flask 后端
    └── index.html           # 前端页面
```

## 环境要求

- Python 3.10+
- 生产部署建议使用 gunicorn（`requirements.txt` 之外单独安装）
- 自动填报功能需本机带图形界面并安装 Playwright 的 Chromium

## 安装

```bash
# 安装依赖
pip3 install --break-system-packages -r requirements.txt

# 生产环境额外安装 gunicorn
pip3 install --break-system-packages gunicorn

# 仅在需要「浏览器自动填报」时安装 Chromium
playwright install chromium
```

## 快速开始

### 方式一：Web UI（推荐）

```bash
# 生产启动（单 worker 多线程，绑定 0.0.0.0:8000）
./start.sh

# 或本地调试启动（默认 127.0.0.1:8000）
python3 web/app.py --port 8000
```

启动后访问 `http://localhost:8000/`，按页面步骤：上传源程序与说明书 → 点击「生成并校验」→ 查看自动填充的字段与 warnings → 下载鉴别材料 PDF。

> 生产必须使用单 worker：任务状态保存在进程内存字典中，多 worker 会导致上传与生成请求落到不同进程而丢失任务。`start.sh` 已固定 `--workers 1 --threads 8`。

### 方式二：命令行 CLI

```bash
# Step 1：准备鉴别材料（生成 PDF + 自动补全字段）
python3 main.py prepare -s ./source_code -m ./manual.docx -n "软件全称" -v "V1.0" -o ./output

# 使用配置文件
python3 main.py prepare -c config.yaml

# Step 2：校验字段
python3 main.py validate -a ./output/application_info.json

# 全自动：准备 + 校验 + 浏览器自动填报（需本机图形界面）
python3 main.py run -c config.yaml -u <账号> -p <密码>
```

常用参数：`--config/-c`、`--source/-s`、`--manual/-m`、`--software-name/-n`、`--version/-v`、`--output/-o`；`run` 子命令另支持 `--username/-u`、`--password/-p`、`--auto-submit`、`--source-pdf`、`--manual-pdf`。

### 方式三：本地演示

```bash
# 生成示例源码与说明书，走完整流程并输出校验报告
python3 demo.py
```

## 配置说明

复制 `config.example.yaml` 为 `config.yaml` 后按需修改。关键字段字数限制（与平台一致）：

| 字段 | 限制 |
| --- | --- |
| `dev_hardware_env` / `run_hardware_env` / `dev_os` / `dev_environment` / `run_platform` / `support_env` | 各 0–50 字 |
| `languages_custom`（平台列表外的语言） | 0–120 字 |
| `purpose`（开发目的） | 0–50 字 |
| `target_industry`（面向领域） | 0–50 字 |
| `main_functions`（主要功能） | 500–1300 字 |
| `tech_desc`（技术特点描述） | 0–100 字 |
| `tech_tags`（技术特点标签） | 从下方 15 项中选，自动推荐最多 3 个 |

技术特点标签可选：`APP`、`游戏软件`、`教育软件`、`金融软件`、`医疗软件`、`地理信息软件`、`云计算软件`、`信息安全软件`、`大数据软件`、`人工智能软件`、`VR软件`、`5G软件`、`小程序`、`物联网软件`、`智慧城市软件`。

## Web 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/scapi/meta` | 获取字段限制、标签列表、语言按钮等元数据 |
| POST | `/scapi/task` | 创建任务，返回 `task_id` |
| POST | `/scapi/task/<id>/file` | 逐个上传源程序（`kind=source`）或说明书（`kind=manual`） |
| POST | `/scapi/task/<id>/prepare` | 生成鉴别材料 + 字段校验 |
| GET | `/scapi/download/<id>/<kind>` | 下载 PDF / JSON |
| POST | `/scapi/agent` | 启动浏览器自动填报 |
| GET | `/scapi/agent/<id>` | 查询自动填报状态 |

> 接口前缀固定为 `/scapi`。部分 IDE/沙箱的预览代理会占用 `/api` 前缀（返回 404），使用 `/api` 会导致页面能打开但请求被拦截。

上传与生成产物保存在 `web/workspace/<task_id>/` 下。

## 自动填报说明

「自动填报」通过 Playwright 弹出**可见**浏览器窗口访问中国版权保护中心平台，登录时最长等待 90 秒由用户手动补验证码，因此只能在**本机带图形界面**的环境运行。

- 云端/容器环境通常没有 `DISPLAY`，该功能无法运行。此时 `/scapi/agent` 会预检环境并直接返回 400，提示在本机运行，避免抛出 `ModuleNotFoundError`。
- 本机运行方式：`pip install -r requirements.txt && playwright install chromium && python3 web/app.py`。

## 技术栈

- Python 3.10+
- Flask（Web 后端）、gunicorn（生产服务）
- reportlab（PDF 生成）、pypdf / pdfminer.six（PDF 解析）、python-docx（Word 解析）
- Pillow、PyYAML、click
- Playwright（浏览器自动填报）

## 常见问题

**Q：页面能打开但所有接口 404？**
A：确认使用 `/scapi` 前缀；`/api` 会被预览代理占用。

**Q：生成后任务丢失 / 404「任务已失效」？**
A：必须单 worker 运行。多 worker 下任务状态分散在不同进程，请用 `./start.sh`。

**Q：主要功能字数不足 500？**
A：说明书中可抽取的正文过少。请提供更完整的说明书，或先在页面上手工补充主要功能后再生成。

**Q：源程序每页行数或页数不符合要求？**
A：平台要求每页 ≥ 50 行、共提交前 30 + 后 30 页。直接上传已生成的源程序 PDF 时会按页截取，warnings 会提示不足的页。

**Q：技术特点标签识别不准？**
A：自动推荐仅为初值，可在页面上手动增减后再提交。标签识别优先依赖名称与说明书中的强区分词。
