"""
软著登记自动化智能体 - 软著平台自动填报 Agent（v2）

基于：中国版权保护中心 R11软件著作权登记申请 平台截图

页面步骤条：
  Step 1: 选择办理身份（著作权人自行/委托代理机构）
  Step 2: 软件申请信息（软件名称、版本号、分类号、开发完成日期、发表状态、开发方式等）
  Step 3: 软件开发信息（6个环境描述 + 编程语言多选）
  Step 4: 软件功能与特点（源程序量、开发目的、面向领域、主要功能、技术特点标签、鉴别材料上传）
  Step 5: 确认信息（回显 + 签章确认）

平台表单特征（截图实测）：
  - 每个表单项结构为「*标签文字 + 输入框 + 0/50」，标签不在 placeholder 中
  - 编程语言为多选按钮，第一行默认展示 7 个，其余在「展开更多」内
  - 「程序鉴别材料」「文档鉴别材料」两组都有「一般交存/例外交存」单选 + PDF 上传，
    因此所有点击/上传都必须按区块限定，否则会点错组、传错框
"""

import os
import re
from typing import Optional

from ..config import (
    AgentCredentials, SoftCopyrightApplication,
    DEVELOPMENT_TYPES,
    PLATFORM_LANGUAGE_BUTTONS,
)


class CopyrightPlatformAgent:
    """中国版权保护中心软著登记平台 - 自动化Agent"""

    PLATFORM_URL = "https://ccopyright.com.cn"

    def __init__(self, credentials: AgentCredentials, headless: bool = False):
        self.credentials = credentials
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
        self._pw = None

    async def _init_browser(self):
        try:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            self.browser = await self._pw.chromium.launch(headless=self.headless)
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()
        except ImportError:
            raise ImportError("需要 playwright: pip install playwright && playwright install chromium")

    async def _close_browser(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._pw:
            await self._pw.stop()

    # ==================== 通用定位策略 ====================

    @staticmethod
    def _norm(s: str) -> str:
        """归一化文案：去所有空白，统一全角斜杠与括号，转小写"""
        if not s:
            return ""
        s = s.replace("／", "/").replace("（", "(").replace("）", ")")
        return re.sub(r"\s+", "", s).lower()

    async def _form_fields(self) -> list:
        """
        采集页面上所有可填写 input/textarea 及其所在表单项文案。

        返回 [{index, tag, type, label}]，index 是元素在 `input, textarea`
        全集中的序号，可直接用 `locator("input, textarea").nth(index)` 定位。
        """
        try:
            return await self.page.evaluate("""
            () => {
              const CONTAINERS = '.el-form-item, .ant-form-item, .ivu-form-item, .form-item, tr, li'
                               + ', [class*="form-row"], [class*="field"]';
              const out = [];
              document.querySelectorAll('input, textarea').forEach((el, i) => {
                const type = (el.getAttribute('type') || el.tagName).toLowerCase();
                if (el.disabled || el.readOnly) return;
                if (['hidden','file','radio','checkbox','submit','button','reset'].includes(type)) return;
                const box = el.closest(CONTAINERS) || el.parentElement;
                out.push({
                  index: i,
                  tag: el.tagName.toLowerCase(),
                  type: type,
                  label: box ? (box.innerText || '') : ''
                });
              });
              return out;
            }
            """)
        except Exception:
            return []

    async def _set_input(self, loc, value) -> bool:
        """填写输入框（兼容 Element UI 日期控件等非原生输入）"""
        try:
            await loc.fill(str(value))
            return True
        except Exception:
            pass
        try:
            await loc.evaluate(
                """(el, v) => {
                     el.value = v;
                     el.dispatchEvent(new Event('input', {bubbles: true}));
                     el.dispatchEvent(new Event('change', {bubbles: true}));
                   }""", str(value))
            return True
        except Exception:
            return False

    async def _fill_by_label(self, label_text: str, value) -> bool:
        """
        按字段标签填写。

        先采集全部输入框并取各自「最近表单项」文案，命中标签后选择
        容器文案最短的那个（最贴近的容器），避免填到同组其他字段。
        """
        if value is None or str(value).strip() == "":
            return False

        key = self._norm(label_text)
        fields = await self._form_fields()
        cands = [f for f in fields if key and key in self._norm(f["label"])]
        cands.sort(key=lambda f: len(self._norm(f["label"])))

        for f in cands:
            loc = self.page.locator("input, textarea").nth(f["index"])
            if await self._set_input(loc, value):
                return True

        print(f"    ⚠️ 未找到输入框: {label_text}")
        return False

    async def _click_in_section(self, item_text: str, section_text: str = "") -> bool:
        """
        点击某段文案（单选/复选/标签/按钮），可限定在某表单区块内。

        限定区块时先定位「包含该区块文字的最小容器」，避免
        「程序鉴别材料／文档鉴别材料」下都有「一般交存」时点错组。
        """
        try:
            return await self.page.evaluate("""
            ([section, item]) => {
              const norm = s => (s || '')
                .replace(/\\s+/g, '')
                .replace(/／/g, '/').replace(/（/g, '(').replace(/）/g, ')')
                .toLowerCase();
              const secN = norm(section), itN = norm(item);
              if (!itN) return false;

              let scope = document;
              if (secN) {
                let root = null, best = Infinity;
                for (const el of document.querySelectorAll('div, section, fieldset, tr, li')) {
                  const t = norm(el.innerText);
                  if (t.includes(secN) && t.length < best) { best = t.length; root = el; }
                }
                if (root) scope = root;
              }

              const sel = 'label, .el-radio, .el-checkbox, button, [class*="tag"], '
                        + '[class*="radio"], [class*="check"]';
              for (const el of scope.querySelectorAll(sel)) {
                const t = norm(el.innerText);
                if (t.length < 2) continue;
                if (t === itN || t.startsWith(itN) || itN.includes(t)) {
                  el.click();
                  return true;
                }
              }
              return false;
            }
            """, [section_text or "", item_text])
        except Exception:
            return False

    async def _click_radio_by_label(self, label_patterns: list,
                                    section_text: str = "") -> bool:
        """点击单选/复选按钮，任一候选文案命中即点"""
        for pat in label_patterns:
            if await self._click_in_section(pat, section_text):
                return True
        return False

    async def _click_lang_button(self, lang_name: str) -> bool:
        """点击编程语言多选按钮（默认只展示一行，需先「展开更多」）"""
        if await self._click_in_section(lang_name):
            return True
        for more in ("展开更多", "查看更多", "更多"):
            if await self._click_in_section(more):
                await self.page.wait_for_timeout(300)
                if await self._click_in_section(lang_name):
                    return True
                break
        return False

    async def _click_tech_tag(self, tag_name: str) -> bool:
        """点击技术特点分类标签"""
        return await self._click_in_section(tag_name, "软件的技术特点")

    async def _click_next_step(self) -> bool:
        """点击下一步按钮"""
        for sel in [
            'button:has-text("下一步")',
            'button:has-text("下 一步")',
            '.btn-primary:has-text("下一步")',
            'a.next-btn',
        ]:
            try:
                el = await self.page.wait_for_selector(sel, timeout=3000)
                if el:
                    await el.click()
                    await self.page.wait_for_load_state("networkidle")
                    return True
            except Exception:
                continue
        print("    ⚠️ 未找到下一步按钮")
        return False

    # ==================== 登录 ====================

    async def login(self) -> bool:
        await self._init_browser()
        print(f"  [Agent] 打开平台: {self.credentials.url}")
        await self.page.goto(self.credentials.url)
        await self.page.wait_for_load_state("networkidle")

        # 点击登录入口
        for sel in ['a:has-text("登录")', 'button:has-text("登录")',
                    '.header-login', '.top-login']:
            try:
                el = await self.page.wait_for_selector(sel, timeout=3000)
                if el:
                    await el.click()
                    break
            except Exception:
                continue
        await self.page.wait_for_load_state("networkidle")

        # 填写账号
        for sel in ['input[name="username"]', 'input[placeholder*="账号"]',
                    'input[placeholder*="用户名"]', 'input[type="text"]:visible']:
            try:
                el = await self.page.wait_for_selector(sel, timeout=3000)
                if el:
                    await el.fill(self.credentials.username)
                    break
            except Exception:
                continue

        # 填写密码
        for sel in ['input[name="password"]', 'input[type="password"]:visible']:
            try:
                el = await self.page.wait_for_selector(sel, timeout=3000)
                if el:
                    await el.fill(self.credentials.password)
                    break
            except Exception:
                continue

        # 提交登录（若平台有验证码，先提交再等待人工补填）
        for sel in ['button[type="submit"]', 'button:has-text("登 录")',
                    'button:has-text("登录")']:
            try:
                el = await self.page.wait_for_selector(sel, timeout=3000)
                if el:
                    await el.click()
                    break
            except Exception:
                continue

        # 最长等待 90 秒：用户可在浏览器中补验证码 / 扫码
        print("  ⏸️ 如出现验证码或短信验证，请在浏览器中完成（最长等待 90 秒）...")
        logged_in = False
        for _ in range(90):
            await self.page.wait_for_timeout(1000)
            if "login" not in self.page.url.lower():
                logged_in = True
                break

        print(f"  [Agent] 登录{'成功' if logged_in else '未完成，请手动检查'}")
        return logged_in

    # ==================== 进入登记申请 ====================

    async def navigate_to_registration(self):
        """导航到 R11 软件著作权登记申请"""
        print("  [Agent] 进入软件著作权登记申请...")

        # 方式1: 通过菜单
        for sel in [
            'a:has-text("版权登记")',
            'a:has-text("软件著作权")',
            'a:has-text("R11")',
            '.menu-item:has-text("软件")',
        ]:
            try:
                el = await self.page.wait_for_selector(sel, timeout=3000)
                if el:
                    await el.click()
                    await self.page.wait_for_load_state("networkidle")
                    break
            except Exception:
                continue

        # 方式2: 新建申请
        for sel in [
            'button:has-text("新建申请")',
            'button:has-text("新增申请")',
            'a:has-text("新建")',
        ]:
            try:
                el = await self.page.wait_for_selector(sel, timeout=3000)
                if el:
                    await el.click()
                    await self.page.wait_for_load_state("networkidle")
                    break
            except Exception:
                continue

        # 方式3: 选择 R11 业务
        for sel in [
            'a:has-text("软件著作权登记")',
            'div:has-text("R11")',
            '.business-card:has-text("软件")',
        ]:
            try:
                el = await self.page.wait_for_selector(sel, timeout=3000)
                if el:
                    await el.click()
                    await self.page.wait_for_load_state("networkidle")
                    break
            except Exception:
                continue

    # ==================== Step 1: 选择办理身份 ====================

    async def step1_identity(self, app: SoftCopyrightApplication):
        """选择办理身份：著作权人自行办理"""
        print("  [Step 1] 选择办理身份...")
        await self._click_radio_by_label(["著作权人自行办理", "自行办理", "著作权人"])
        await self._click_next_step()

    # ==================== Step 2: 软件申请信息 ====================

    async def step2_software_info(self, app: SoftCopyrightApplication):
        """填写软件申请信息"""
        print("  [Step 2] 填写软件申请信息...")
        s = app.software

        await self._fill_by_label("软件全称", s.full_name)
        await self._fill_by_label("软件简称", s.short_name)
        await self._fill_by_label("版本号", s.version)

        if s.category_code:
            await self._fill_by_label("软件分类", s.category_code)

        await self._fill_by_label("开发完成日期", s.develop_date)

        # 发表状态
        if s.publish_status == "published":
            await self._click_radio_by_label(["已发表"])
            await self._fill_by_label("首次发表日期", s.publish_date)
            await self._fill_by_label("首次发表地点", s.publish_location)
        else:
            await self._click_radio_by_label(["未发表"])

        # 软件类型（原创/修改）
        await self._click_radio_by_label(["原创软件", "原创"])

        # 开发方式
        dev_text = DEVELOPMENT_TYPES.get(s.development_type, "独立开发")
        await self._click_radio_by_label([dev_text, "单独开发"])

        await self._click_next_step()

    # ==================== Step 3: 软件开发信息 ====================

    async def step3_dev_info(self, app: SoftCopyrightApplication):
        """
        填写软件开发信息（截图实测的 6 个环境字段 + 编程语言多选）

        1. *开发的硬件环境        0/50
        2. *运行的硬件环境        0/50
        3. *开发该软件的操作系统   0/50
        4. *软件开发环境 / 开发工具 0/50
        5. *该软件的运行平台 / 操作系统 0/50
        6. *软件运行支撑环境 / 支持软件 0/50
        7. *编程语言（多选按钮 + 自定义 0/120）
        """
        print("  [Step 3] 填写软件开发信息...")
        d = app.dev

        await self._fill_by_label("开发的硬件环境", d.dev_hardware_env)
        await self._fill_by_label("运行的硬件环境", d.run_hardware_env)
        await self._fill_by_label("开发该软件的操作系统", d.dev_os)
        await self._fill_by_label("软件开发环境", d.dev_environment)
        await self._fill_by_label("该软件的运行平台", d.run_platform)
        await self._fill_by_label("软件运行支撑环境", d.support_env)

        # 编程语言 - 多选按钮
        for lang in d.languages:
            if not await self._click_lang_button(lang):
                print(f"    ⚠️ 未找到语言按钮: {lang}")

        # 不在平台按钮列表内的语言，填入自定义补充框
        extra = [l for l in d.languages if l not in PLATFORM_LANGUAGE_BUTTONS]
        custom_text = ", ".join(extra) if extra else d.languages_custom
        if custom_text:
            await self._fill_by_label("其他编程语言", custom_text)
            await self._fill_by_label("若有需要", custom_text)

        await self._click_next_step()

    # ==================== Step 4: 软件功能与特点 ====================

    async def step4_feature_info(self, app: SoftCopyrightApplication,
                                 source_pdf: str, manual_pdf: str):
        """
        填写软件功能与特点 + 上传鉴别材料（截图实测字段）

        1. *源程序量（行）
        2. *开发目的 0/50
        3. *面向领域 / 行业 0/50
        4. *软件的主要功能 0/500~1300
        5. *软件的技术特点（分类标签多选 + 描述 0/100）
        6. *程序鉴别材料（一般交存/例外交存 + PDF 上传）
        7. *文档鉴别材料（一般交存/例外交存 + PDF 上传）
        """
        print("  [Step 4] 填写软件功能与特点...")
        f = app.feature

        await self._fill_by_label("源程序量", f.source_code_lines)
        await self._fill_by_label("开发目的", f.purpose)
        await self._fill_by_label("面向领域", f.target_industry)
        await self._fill_by_label("软件的主要功能", f.main_functions)

        # 技术特点标签（多选）
        for tag in f.tech_tags:
            if not await self._click_tech_tag(tag):
                print(f"    ⚠️ 未找到技术特点标签: {tag}")

        # 技术特点描述（同一区块内的文本框）
        if f.tech_desc:
            await self._fill_by_label("软件的技术特点", f.tech_desc)

        # 鉴别材料交存方式：必须按区块点击，否则两组「一般交存」会点到同一组
        prog_type = "例外交存" if f.program_submit_type == "exception" else "一般交存"
        doc_type = "例外交存" if f.doc_submit_type == "exception" else "一般交存"
        if not await self._click_radio_by_label([prog_type], "程序鉴别材料"):
            print("    ⚠️ 程序鉴别材料交存方式选择失败")
        if not await self._click_radio_by_label([doc_type], "文档鉴别材料"):
            print("    ⚠️ 文档鉴别材料交存方式选择失败")

        # 上传鉴别材料 PDF（按区块定位文件框，避免两个 PDF 传到同一个框）
        print("  [Step 4] 上传程序鉴别材料 PDF...")
        await self._upload_file_in_section("程序鉴别材料", source_pdf)
        print("  [Step 4] 上传文档鉴别材料 PDF...")
        await self._upload_file_in_section("文档鉴别材料", manual_pdf)

        await self._click_next_step()

    async def _upload_file_in_section(self, section_label: str,
                                      file_path: str) -> bool:
        """上传文件到指定区块内的 file 控件"""
        if not file_path or not os.path.exists(file_path):
            print(f"    ⚠️ 文件不存在: {file_path}")
            return False

        try:
            idx = await self.page.evaluate("""
            (section) => {
              const norm = s => (s || '')
                .replace(/\\s+/g, '')
                .replace(/／/g, '/').replace(/（/g, '(').replace(/）/g, ')')
                .toLowerCase();
              const secN = norm(section);

              let root = null, best = Infinity;
              for (const el of document.querySelectorAll('div, section, fieldset, tr, li')) {
                const t = norm(el.innerText);
                if (t.includes(secN) && t.length < best) { best = t.length; root = el; }
              }
              const scope = root || document;
              const all = [...document.querySelectorAll('input[type=file]')];
              const inside = [...scope.querySelectorAll('input[type=file]')];
              if (!inside.length) return -1;
              return all.indexOf(inside[0]);
            }
            """, section_label)

            if idx is None or idx < 0:
                print(f"    ⚠️ 未找到 {section_label} 上传控件")
                return False

            await self.page.locator('input[type=file]').nth(idx).set_input_files(file_path)
            print(f"    ✓ 已上传到 {section_label}: {os.path.basename(file_path)}")
            return True
        except Exception as e:
            print(f"    ⚠️ 上传失败: {e}")
            return False

    # ==================== Step 5: 确认 ====================

    async def step5_confirm(self, app: SoftCopyrightApplication,
                            auto_submit: bool = False):
        """确认信息 + 提交"""
        print("  [Step 5] 确认信息...")

        # 勾选承诺条款
        await self._click_radio_by_label(["我已阅读", "同意", "保证"])

        if auto_submit:
            for sel in ['button:has-text("提交")', 'button:has-text("确认提交")',
                        '.btn-primary']:
                try:
                    el = await self.page.wait_for_selector(sel, timeout=3000)
                    if el:
                        await el.click()
                        await self.page.wait_for_load_state("networkidle")
                        break
                except Exception:
                    continue
        else:
            print("  ⏸️ 未开启 --auto-submit，已停在确认页，请人工核对后提交")

    # ==================== 完整流程 ====================

    async def run_full(
        self,
        app: SoftCopyrightApplication,
        source_pdf: str,
        manual_pdf: str,
        auto_submit: bool = False,
        pause_at_step4: bool = True,
    ) -> dict:
        """执行完整的 R11 申请流程"""
        result = {'success': False, 'steps_completed': []}
        try:
            await self.login()
            await self.navigate_to_registration()

            await self.step1_identity(app)
            result['steps_completed'].append(1)

            await self.step2_software_info(app)
            result['steps_completed'].append(2)

            await self.step3_dev_info(app)
            result['steps_completed'].append(3)

            await self.step4_feature_info(app, source_pdf, manual_pdf)
            result['steps_completed'].append(4)

            if pause_at_step4:
                print("\n  ⏸️ Step 4 完成，请检查浏览器中的填写结果...")
                print("     重点核对：编程语言按钮是否高亮、技术特点标签是否选中、"
                      "两个 PDF 是否分别传到了程序/文档鉴别材料")
                await self.page.wait_for_timeout(5000)

            await self.step5_confirm(app, auto_submit=auto_submit)
            result['steps_completed'].append(5)
            result['success'] = True

        except Exception as e:
            result['error'] = str(e)
            import traceback
            traceback.print_exc()

        return result

    async def save_screenshot(self, path: str):
        if self.page:
            await self.page.screenshot(path=path, full_page=True)
