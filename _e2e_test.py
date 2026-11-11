# -*- coding: utf-8 -*-
"""端到端流程验证脚本：通过Flask测试客户端走完整条业务链路"""
import sys, re, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\网络编程\5\老年预问诊系统')
import app as A

# 每次验证使用全新数据库
import os
if os.path.exists(A.DB_PATH):
    os.remove(A.DB_PATH)
A.init_db()
c = A.app.test_client()

# 0 健康检查接口（/healthz）
r = c.get('/healthz')
assert r.status_code == 200, r.status_code
h = r.get_json()
assert h['status'] == 'ok' and h['db'] == 'ok' and h['scales'] == 21, h
print('0. 健康检查通过：', h)

# 1 新建档案
r = c.post('/patient/new', data={'name':'张桂芳','gender':'女','age':78,
    'phone':'13800000000','contact_name':'张先生','contact_phone':'13900000000'})
assert r.status_code in (302,), r.status_code
loc = r.headers['Location']
pid = int(re.search(r'/patient/(\d+)/previsit', loc).group(1))
print('1. 档案建立成功 pid =', pid)

# 2 预问诊
r = c.post(f'/patient/{pid}/previsit', data={
    'chief_complaint':'头晕乏力2周，走路不稳',
    'present_illness':'晨起明显，伴记忆力下降',
    'past_history':'高血压15年，糖尿病8年，2年前脑梗',
    'medication':'氨氯地平、二甲双胍、阿司匹林',
    'allergy':'无','family_history':'无','lifestyle':'不吸烟，偶饮酒，运动少'})
assert r.status_code == 302
print('2. 预问诊提交成功')

# 3 21张量表全部按最高分（异常）选项作答
from scales_data import SCALES
for s in SCALES:
    data = {f'q{i}': str(item['opts'][-1][1])  # 每题选最后一个选项
            for i, item in enumerate(s['items'])}
    r = c.post(f"/patient/{pid}/scale/{s['id']}", data=data)
    assert r.status_code == 302, (s['id'], r.status_code)
print(f'3. 全部 {len(SCALES)} 张量表提交成功')

# 列表页进度
r = c.get(f'/patient/{pid}/scales')
assert '100%' in r.get_data(as_text=True)
print('   进度=100% 校验通过')

# 4 生成报告
r = c.post(f'/patient/{pid}/report/generate')
assert r.status_code == 302
r = c.get(f'/patient/{pid}/report')
txt = r.get_data(as_text=True)
assert '老年综合评估报告' in txt and '异常指标汇总' in txt
print('4. 综合评估报告自动生成成功')

# 5 打印页
r = c.get(f'/patient/{pid}/report/print')
assert '老年综合评估报告' in r.get_data(as_text=True)
print('5. 打印/导出页正常')

# 6 医护登录+审核
r = c.post('/login', data={'username':'doctor','password':'123456'})
assert r.status_code == 302
r = c.get('/doctor')
if r.status_code != 200 or '张桂芳' not in r.get_data(as_text=True):
    open(r'C:\网络编程\5\老年预问诊系统\_dbg2.txt','w',encoding='utf-8').write(
        f'status={r.status_code}\n'+r.get_data(as_text=True)[:800])
    raise SystemExit('doctor home 校验失败，见 _dbg2.txt')
r = c.post(f'/doctor/report/{pid}/audit',
           data={'status':'已通过','doctor_comment':'报告属实，建议转介营养科与康复科，1月后复评。'})
if r.status_code != 302:
    open(r'C:\网络编程\5\老年预问诊系统\_dbg4.txt','w',encoding='utf-8').write(
        f'audit={r.status_code}\n'+r.get_data(as_text=True)[:1200])
    raise SystemExit('audit失败，见_dbg4.txt')
r = c.get(f'/doctor/patient/{pid}')
assert '已通过' in r.get_data(as_text=True)
print('6. 医护端审核通过')

# 7 管理端
r = c.get('/logout'); r = c.post('/login', data={'username':'admin','password':'123456'})
r = c.get('/admin')
t = r.get_data(as_text=True)
assert '量表库管理' in t and 'Barthel指数' in t and '风险分布统计' in t
print('7. 管理后台（量表库+统计）正常')

# 8 校验数据库落库
import sqlite3
db = sqlite3.connect(A.DB_PATH); db.row_factory = sqlite3.Row
n = db.execute('SELECT COUNT(*) c FROM scale_results WHERE patient_id=?',(pid,)).fetchone()['c']
rep = db.execute('SELECT risk_count,status FROM reports WHERE patient_id=?',(pid,)).fetchone()
print(f'8. 落库校验：量表结果 {n} 条；异常指标 {rep["risk_count"]} 项；报告状态={rep["status"]}')
assert n == 21
print('\n===== 全部端到端流程验证通过 =====')
