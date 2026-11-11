# 老年人预问诊与老年综合评估系统（轻量化版）

网络编程课程项目配套运行代码。以预问诊为入口，完成老年综合评估 **21 张量表** 的数字化采集，自动评分并生成**老年综合评估报告**，覆盖「评估—审核—干预—随访」闭环。

## 一、技术栈（轻量化，零外部中间件）

| 层次 | 技术 | 说明 |
|---|---|---|
| 后端 | Python + Flask | 单文件路由，无需 Tomcat/Nginx |
| 数据库 | SQLite（标准库 sqlite3） | 免安装，运行即自动生成 `cga.db` |
| 前端 | 原生 HTML + CSS + JavaScript | 无 Vue/React、无需 npm 构建 |
| 图表 | matplotlib（仅开发期出功能图用，非运行依赖） |

## 二、运行方法

```bash
# 1. 安装唯一运行依赖
pip install flask

# 2. 启动（在本目录下）
python app.py

# 3. 浏览器访问
http://127.0.0.1:5000
```

首次启动自动建库、建表并写入演示账号。

| 角色 | 账号 | 密码 |
|---|---|---|
| 医护人员 | doctor | 123456 |
| 系统管理员 | admin | 123456 |

> 患者端无需登录，首页直接「新建评估档案」即可，方便家属/护士协助老人操作。

## 三、使用流程（与业务流程一一对应）

```
① 患者端新建档案（基本信息、家属信息）
        ↓
② 预问诊病史分步采集（主诉→现病史→既往史→用药→过敏→家族史→生活习惯）
        ↓
③ 21张量表分组作答（躯体功能/认知心理/营养代谢/安全风险/社会功能 5 域）
   · 每题自动记录，提交即评分，即时反馈风险等级
   · 适老化：大字号、高对比、浏览器语音朗读题目
        ↓
④ 全部完成 → 一键生成《老年综合评估报告》
   · 各域得分汇总、异常指标提取、风险结论、健康指导建议自动匹配
        ↓
⑤ 医护端登录 → 审核/批注/退回 → 定稿
        ↓
⑥ 患者端打印 / 导出 PDF；管理端查看量表库与风险分布统计
```

## 四、21 张量表清单

系统在 `scales_data.py` 中集中配置量表题库、选项分值与风险分级规则，覆盖：

- **躯体功能**：Barthel、Lawton IADL、Tinetti 平衡步态、EAT-10 吞咽、ICIQ-SF 尿失禁
- **认知心理**：MMSE、DASC-21、CDR、GDS-15 抑郁、GAD-7 焦虑
- **营养代谢**：MNA-SF 营养、FRAIL 衰弱、SARC-F 肌少症、Beers 多重用药、Charlson 共病
- **安全风险**：Morse 跌倒、PSQI 睡眠、NRS 疼痛、Braden 压疮
- **社会功能**：LSNS-6 社会网络、EQ-5D 生活质量

> 作业演示版采用各量表的核心/筛查条目以便独立运行；临床正式版可直接在 `scales_data.py` 扩充题目，评分与报告逻辑无需改动（满足可扩展性需求）。

## 五、目录结构

```
老年预问诊系统/
├── app.py              # Flask 主程序：建库、路由、自动评分、报告生成
├── scales_data.py      # 21张量表题库 + 评分规则 + 健康指导知识库
├── requirements.txt    # 依赖（Flask）
├── cga.db              # 运行后自动生成的 SQLite 数据库
├── _e2e_test.py        # 端到端流程自测脚本（非必须）
└── templates/          # 13 个原生网页模板
    ├── base.html            # 适老化公共布局（大字/高对比/顶栏）
    ├── index.html           # 系统首页（三端入口+统计）
    ├── login.html           # 医护/管理员登录
    ├── patient_new.html     # ①新建档案
    ├── patient_previsit.html# ②预问诊
    ├── patient_scales.html  # ③量表列表（分组+进度）
    ├── patient_scale.html   # ③单量表答题（语音朗读）
    ├── report_body.html     # 报告正文片段
    ├── patient_report.html  # ④患者查看报告/生成
    ├── print.html           # 打印/导出PDF
    ├── doctor_home.html     # ⑤医护患者列表
    ├── doctor_detail.html   # ⑤医护审核
    └── admin_home.html      # ⑥管理后台
```

## 六、自测验证

```bash
python _e2e_test.py
```

脚本自动走完整条链路（建档案→预问诊→21量表→生成报告→医护审核→管理统计），
通过后输出「全部端到端流程验证通过」，可作为作业功能演示的依据。

### 健康检查接口（/healthz）

服务启动后可访问 `GET /healthz`：

```json
{"status":"ok","db":"ok","scales":21,"version":"2.0","time":"2026-10-28 15:14:53"}
```

- `200`：数据库连通且 21 张量表配置已加载；
- `503`：数据库异常或量表数为 0，此时 `status` 为 `degraded`。

## 七、与课程需求的对应关系

| 需求分析中的要求 | 实现位置 |
|---|---|
| 预问诊信息引导式采集 | `patient_previsit.html` + `patients` 表 |
| 21 张量表多模式采集 | `scales_data.py` + `patient_scale.html` |
| 量表自动评分与风险分级 | `scales_data.py` 中每条 `rule` |
| 综合报告自动生成 | `app.py` 的 `build_report()` |
| 异常指标 + 个性化健康指导 | `ADVICE_KB` 知识库匹配 |
| 医护审核与多学科协作 | `doctor_*` 页面、`reports` 表 |
| 适老化（大字/语音/高对比） | `base.html` + Web Speech API |
| 量表库可扩展 | `scales_data.py` 数据驱动，不改库表 |
| 数据安全与权限 | session 登录、角色访问控制装饰器 |
| HIS/挂号对接（预留） | 数据服务层接口，轻量化版以预留扩展点表示 |
