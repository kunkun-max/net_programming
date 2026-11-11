# AGENTS.md

本文件为 AI 编码助手（CodeBuddy / Claude Code / Codex 等）在本仓库工作时的指引，是仓库协作规范的**唯一事实来源**。
仓库为单模块轻量项目，不设分层子指南；本文档覆盖全部开发约定。

参考模板：`medical-evaluate-main/AGENTS.md`（本文件按其结构裁剪，适配轻量技术栈）。

---

## 项目背景

本项目为**老年人预问诊与老年综合评估系统（轻量化二期 demo）**，面向社区与病区老年人群。以预问诊为入口，完成**老年综合评估（CGA）21 张量表**的数字化采集、自动评分、风险分级、综合报告生成、医护审核与健康指导，覆盖「评估—审核—干预—随访」闭环。

系统分为三端：

- **患者端**：免登录，新建档案、预问诊、量表作答、查看/打印报告。
- **医护端**：登录后查看患者、审核/批注报告。
- **管理端**：量表库使用统计、风险分布、业务概览。

> 参考项目 `medical-evaluate` 的业务思想（CICARE、分级宣教、Teach-back、知情同意、人机对比）纳入后续期次；**本项目保留轻量技术栈，不引入重型框架**。

---

## 约定

1. **命令环境**：Windows 11，必须使用 **Windows PowerShell** 指令执行命令。
2. **编码**：所有文件统一 **UTF-8**，文档使用**简体中文**。
3. **任务前回复**：每次执行任务前先回复 `bro.`。
4. **禁止直接开发**：收到新需求时，先阅读相关代码、评估可行性、给出公正意见（可以反驳），与用户充分讨论并确认方案后，**先写计划文档再动手**。
5. **保留技术栈**：不得擅自替换 Flask / SQLite / 原生 HTML/CSS/JS，不得引入 FastAPI、PostgreSQL、React/Vue、npm 构建等。
6. **任务结束**：检查并停止前后端进程，避免后台残留占用端口、影响 IDE 调试。
7. **数据库谨慎**：`cga.db` 为演示数据库，禁止在未确认时删除或覆盖；改表结构须同步更新 `项目构想总需求.md` 第 8 步。
8. **文档同步**：代码或架构变更时，同步更新 `AGENTS.md` 与 `项目构想总需求.md`。

---

## 技术栈

| 层次 | 选型 | 说明 |
|---|---|---|
| 后端 | Python + Flask（≥2.3） | 单文件路由，无 Tomcat/Nginx |
| 数据库 | SQLite（标准库 `sqlite3`） | 免安装，运行自动生成 `cga.db` |
| 前端 | 原生 HTML + CSS + JavaScript（Jinja2 模板） | 无框架、无 npm 构建 |
| 语音朗读 | 浏览器 Web Speech API | 适老化题目朗读 |
| 图表 | matplotlib | 仅开发期出图，非运行依赖 |

依赖清单见 `requirements.txt`（仅 `Flask`）。

---

## 项目目录结构

```text
老年预问诊系统/
├── app.py                  # Flask 主程序：建库、路由、自动评分、报告生成、审计
├── scales_data.py          # 21 张量表题库 + 评分规则（RULES）+ 健康指导知识库（ADVICE_KB）
├── requirements.txt        # 运行依赖（Flask）
├── cga.db                  # 运行后自动生成的 SQLite 数据库（勿随意删除）
├── 项目构想总需求.md          # 需求文档：技术栈、三类数据表设计、字段归类
├── 二期数据库设计说明书.md     # 数据库设计详稿
├── AGENTS.md               # 本文件：协作规范
├── AGENT.md                # 指向本文件的简写入口
├── README.md               # 项目运行手册
├── _e2e_test.py            # 端到端流程自测脚本
└── templates/              # 13 个原生网页模板
    ├── base.html           # 适老化公共布局（大字/高对比/顶栏）
    ├── index.html          # 首页（三端入口 + 统计）
    ├── login.html          # 医护/管理员登录
    ├── patient_new.html    # 新建档案
    ├── patient_previsit.html # 预问诊病史采集
    ├── patient_scales.html # 量表列表（分组 + 进度）
    ├── patient_scale.html  # 单量表答题（语音朗读）
    ├── report_body.html    # 报告正文片段
    ├── patient_report.html # 患者查看/生成报告
    ├── print.html          # 打印/导出 PDF
    ├── doctor_home.html    # 医护患者列表
    ├── doctor_detail.html  # 医护审核
    └── admin_home.html     # 管理后台
```

---

## 运行与验证

```powershell
# 安装依赖
pip install -r requirements.txt

# 启动（本目录下）
python app.py
# 访问 http://127.0.0.1:5000

# 端到端自测
python _e2e_test.py

# 健康检查（服务启动后另开终端）
Invoke-RestMethod http://127.0.0.1:5000/healthz
```

> `_e2e_test.py` 会重建 `cga.db`，运行前先备份、验证后恢复，避免演示数据丢失。

演示账号：

| 角色 | 账号 | 密码 |
|---|---|---|
| 医护人员 | doctor | 123456 |
| 系统管理员 | admin | 123456 |

患者端免登录，首页直接「新建评估档案」。

---

## 开发规范

1. **任务顺序**：分析需求 → 需求确认 → Git 新建分支 → 开发 → 测试 → review → 修复 → 测试通过 → 合并分支。
2. **计划文档**：在动手前于仓库根或 `docs/plan/` 创建计划文档，先列大步骤（1、2、…），再列子步骤（1.1、1.2、…），使用 `- [ ]` 标记，完成后改为 `- [X]`。
3. **文档位置**：开发文档写 `docs/`（`docs/plan`、`docs/review`、`docs/bug`、`docs/sql`）；需求与数据库设计写仓库根。
4. **测试**：功能改动需通过 `python _e2e_test.py`；新增路由/表结构需补充自测覆盖。
5. **适老化**：新增页面须保持大字号、高对比、可键盘操作，题目支持语音朗读。
6. **避免硬编码膨胀**：量表结构优先走数据库配置；确需临时硬编码时，须在计划文档注明后续迁移点。
7. **新增功能完成定义（DoD）**：新增路由/接口必须同时完成 ① 路由实现；② `_e2e_test.py` 增加断言并通过；③ README 同步接口说明；④ 涉及表结构时同步 `项目构想总需求.md` 第 8 步。缺任一项视为未完成，不得提交。
8. **验证前备份**：运行 `_e2e_test.py` 前备份 `cga.db`，验证后恢复；脚本会重建数据库。

---

## 数据库规范（重点）

### 表分类

数据表按需求文档第 8 步分为三类，共 28 张：

- **配置类（10 张）**：`form_templates`、`form_versions`、`form_sections`、`form_questions`、`form_options`、`scoring_rules`、`education_materials`、`consent_templates`、`dialogue_scripts`、`trigger_rules`
- **业务类（13 张）**：`patients`、`encounters`、`assessment_sessions`、`assessment_answers`、`assessment_scores`、`dialogue_turns`、`education_sessions`、`teachback_results`、`consent_sessions`、`patient_profiles`、`nursing_plans`、`nurse_reviews`、`ai_nurse_comparisons`
- **审计与科研类（5 张）**：`template_approvals`、`clinical_audit_logs`、`data_exports`、`deidentified_records`、`model_quality_metrics`

### 字段归类

每张表字段归为 5 类，新增表必须遵循：

| 类别 | 用途 | 示例 |
|---|---|---|
| 标识字段 | 唯一定位 | `id`、`session_no`、`code` |
| 归属/关联字段 | 外键关系 | `patient_id`、`template_id`、`question_id` |
| 内容/业务字段 | 承载业务结果 | `score`、`answers`、`risk_level`、`content` |
| 状态/生命周期字段 | 阶段与版本 | `status`、`published_status`、`created_at` |
| 审计/溯源字段 | 追责与版本回放 | `created_by`、`form_version_id`、`generated_by` |

归类判据：**「这个字段变了，要不要影响历史记录？」** 要 → 配置类并加版本；不要但属于过程 → 业务类；用于追责/统计 → 审计科研类。

### 建表与迁移

- 统一在 `app.py` 的 `init_db()` 中用 `CREATE TABLE IF NOT EXISTS` 建表，配合 `PRAGMA foreign_keys=ON`。
- SQLite 类型映射：自增主键用 `INTEGER PRIMARY KEY AUTOINCREMENT`，时间用 `TEXT`，JSON 用 `TEXT`，布尔用 `INTEGER(0/1)`。
- 量表配置通过 `seed_scale_config()` 幂等导入，禁止在业务代码中重复硬编码题库。
- 业务表只存 `form_version_id`，不得直接复制量表题目文本作为历史依据。

---

## Git 规范

- **提交前缀**：`feat|fix|docs|refactor|test|chore|build|ci`，并用括号写明修改位置，位置分三类：`backend-xxx`、`frontend-xxx`、`db-xxx`，例如 `feat(db-config): 量表配置落库`。
- **提交备注**：使用中文，包含开发摘要（修复了什么问题 + 修改位置），便于查阅。
- **分支模型**：`dev` 为开发分支；新功能/修 BUG 必须从 `dev` 新建 `feat/...` 或 `fix/...` 分支。
- **稳定分支**：`main` 为稳定主分支，仅在人工确认版本稳定后由 `dev` 合并。
- **分支命名**：禁止使用 `codex/xx`、`claude/xx` 前缀。
- **合并清理**：功能分支测试通过后及时合并回本地 `dev` 并删除，避免分支堆积。
- **远程推送**：仅当功能分支完整合并、测试通过、工作区干净时才可推送远程 `dev`；否则只能推送当前功能分支。
- **禁止提交**：`cga.db`、真实患者隐私数据、含身份证/手机号的导出文件不得提交 Git。

---

## 文档规范

- 全部使用**简体中文**、UTF-8。
- `项目构想总需求.md`：项目定位、技术栈、核心模块、第 8 步三类数据表与字段归类。
- `二期数据库设计说明书.md`：表结构详稿（字段、类型、归类、设计思路）。
- 需求或架构变更时同步更新上述文档，禁止文档与代码脱节。

---

## 禁止事项

| 禁止 | 原因 |
|---|---|
| 替换技术栈（Flask→FastAPI、SQLite→PostgreSQL） | 作业要求保留原技术栈 |
| 未讨论直接开发 | 违反协作约定 |
| 删除/覆盖 `cga.db` | 演示数据丢失 |
| 把真实患者隐私数据提交 Git | 合规风险 |
| 在 `scales_data.py` 之外重复硬编码量表题库 | 配置漂移 |
| 让 AI 结果直接作为临床最终记录 | 责任边界，须护士确认 |
| 擅自停止/占用端口后不清理进程 | 影响 IDE 调试 |

---

## Where to Go Next

- **需求与数据模型** → [`项目构想总需求.md`](项目构想总需求.md)
- **数据库设计详稿** → [`二期数据库设计说明书.md`](二期数据库设计说明书.md)
- **运行手册** → [`README.md`](README.md)
- **端到端自测** → [`_e2e_test.py`](_e2e_test.py)
