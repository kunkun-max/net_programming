# -*- coding: utf-8 -*-
"""
老年人预问诊与老年综合评估系统（轻量化版）
技术栈：Flask + SQLite + 原生HTML/CSS/JS（无前端构建、无外部框架）
运行：pip install flask  →  python app.py  → 浏览器访问 http://127.0.0.1:5000
账号：
  患者端演示入口：首页"新建评估档案"即可，无需登录
  医护端：doctor / 123456
  管理端：admin / 123456
"""
import os
import json
import sqlite3
from datetime import datetime
from functools import wraps
from flask import (Flask, g, render_template, request, redirect,
                   url_for, session, flash, jsonify)

from scales_data import SCALES, SCALE_MAP, ADVICE_KB, RULES

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'cga.db')

app = Flask(__name__)
app.secret_key = 'cga-lightweight-demo-key'


# ---------------- 数据库 ----------------
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db is not None:
        db.close()


# 风险等级中用于判定“正常/低风险”的关键词（二期患者画像与护理计划共用）
NORMAL_WORDS = ('正常', '自理', '良好', '阴性', '低风险', '无焦虑', '无抑郁',
                '无明显疼痛', '无尿失禁', '健壮', '低跌倒', '低度', '低共病',
                '支持良好')


def load_scales_from_db(db):
    """从数据库配置表读取量表结构（二期：量表配置已落库）。

    返回结构与 scales_data.SCALES 兼容的列表，每条含 id/name/abbr/domain/
    mode/items/rule，供原评分与报告逻辑无缝使用。
    """
    rows = db.execute(
        'SELECT id,code,name,abbr,domain,mode FROM form_templates ORDER BY id'
    ).fetchall()
    if not rows:
        return None
    out = []
    for t in rows:
        qs = db.execute(
            'SELECT id,seq,stem FROM form_questions WHERE template_id=? ORDER BY seq',
            (t['id'],)).fetchall()
        items = []
        for q in qs:
            opts = db.execute(
                'SELECT label,value FROM form_options WHERE question_id=? ORDER BY sort_order',
                (q['id'],)).fetchall()
            items.append({'q': q['stem'],
                         'opts': [(o['label'], o['value']) for o in opts]})
        out.append({
            'id': t['code'], 'name': t['name'], 'abbr': t['abbr'],
            'domain': t['domain'], 'mode': t['mode'], 'items': items,
            'rule': RULES.get(t['code'], lambda s: '未分级'),
        })
    return out


def _scales():
    """当前生效量表列表：优先读数据库，空库时回退硬编码源。"""
    db = get_db()
    lst = load_scales_from_db(db)
    return lst if lst else SCALES


def _scale_map():
    """量表 code → 量表定义 字典。"""
    return {s['id']: s for s in _scales()}


def seed_scale_config(db):
    """幂等导入 21 张量表到配置表（二期：量表配置落库）。

    把 scales_data.SCALES 的题库/选项分值写入 form_templates/form_versions/
    form_sections/form_questions/form_options/scoring_rules，并发布为“已发布”版本。
    """
    if db.execute('SELECT COUNT(*) c FROM form_templates').fetchone()['c'] > 0:
        return
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    for s in SCALES:
        cur = db.execute(
            'INSERT INTO form_templates(code,name,abbr,domain,mode,current_version,created_at) '
            'VALUES(?,?,?,?,?,?,?)',
            (s['id'], s['name'], s['abbr'], s['domain'], s['mode'], 1, ts))
        tid = cur.lastrowid
        vid = db.execute(
            'INSERT INTO form_versions(template_id,version,published_status,effective_from) '
            'VALUES(?,?,?,?)', (tid, 1, '已发布', ts)).lastrowid
        sec = db.execute(
            'INSERT INTO form_sections(template_id,version_id,title,sort_order) '
            'VALUES(?,?,?,?)', (tid, vid, s['name'], 1)).lastrowid
        for i, item in enumerate(s['items'], start=1):
            maxv = max(o[1] for o in item['opts'])
            qid = db.execute(
                'INSERT INTO form_questions(template_id,version_id,section_id,seq,stem,q_type,max_score) '
                'VALUES(?,?,?,?,?,?,?)',
                (tid, vid, sec, i, item['q'], 'single', maxv)).lastrowid
            for j, (label, val) in enumerate(item['opts'], start=1):
                db.execute(
                    'INSERT INTO form_options(question_id,label,value,sort_order) '
                    'VALUES(?,?,?,?)', (qid, label, val, j))
        db.execute(
            'INSERT INTO scoring_rules(template_id,version_id,rule_key,total_formula,grade_bands) '
            'VALUES(?,?,?,?,?)', (tid, vid, s['id'], 'SUM(option_value)', '[]'))
    db.commit()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL,           -- doctor / admin
        name TEXT
    );
    CREATE TABLE IF NOT EXISTS patients(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        gender TEXT,
        age INTEGER,
        phone TEXT,
        id_card TEXT,
        contact_name TEXT,            -- 家属/照护者
        contact_phone TEXT,
        chief_complaint TEXT,         -- 主诉
        present_illness TEXT,         -- 现病史
        past_history TEXT,            -- 既往史
        medication TEXT,              -- 用药情况
        allergy TEXT,                 -- 过敏史
        family_history TEXT,          -- 家族史
        lifestyle TEXT,               -- 生活习惯
        previsit_status TEXT DEFAULT '未完成',  -- 预问诊状态
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS scale_results(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        scale_id TEXT NOT NULL,
        scale_name TEXT,
        score INTEGER DEFAULT 0,
        risk_level TEXT,
        mode TEXT,                    -- 自评/他评/护士施测
        answers TEXT,                 -- JSON字符串
        created_at TEXT,
        UNIQUE(patient_id, scale_id),
        FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS reports(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL UNIQUE,
        content TEXT,
        risk_count INTEGER DEFAULT 0,
        status TEXT DEFAULT '待审核',
        doctor_comment TEXT,
        created_at TEXT,
        FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
    );

    -- ===== 二期扩展：配置类数据表（10）=====
    CREATE TABLE IF NOT EXISTS form_templates(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL, abbr TEXT, domain TEXT, mode TEXT,
        description TEXT, current_version INTEGER DEFAULT 1, created_at TEXT);
    CREATE TABLE IF NOT EXISTS form_versions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id INTEGER NOT NULL REFERENCES form_templates(id) ON DELETE CASCADE,
        version INTEGER NOT NULL, published_status TEXT DEFAULT '草稿',
        effective_from TEXT, approved_by TEXT);
    CREATE TABLE IF NOT EXISTS form_sections(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id INTEGER NOT NULL, version_id INTEGER NOT NULL,
        title TEXT, sort_order INTEGER);
    CREATE TABLE IF NOT EXISTS form_questions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id INTEGER NOT NULL REFERENCES form_templates(id) ON DELETE CASCADE,
        version_id INTEGER NOT NULL, section_id INTEGER,
        seq INTEGER, stem TEXT NOT NULL, q_type TEXT DEFAULT 'single', max_score INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS form_options(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL REFERENCES form_questions(id) ON DELETE CASCADE,
        label TEXT NOT NULL, value INTEGER DEFAULT 0, sort_order INTEGER);
    CREATE TABLE IF NOT EXISTS scoring_rules(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id INTEGER NOT NULL REFERENCES form_templates(id) ON DELETE CASCADE,
        version_id INTEGER NOT NULL, rule_key TEXT, total_formula TEXT, grade_bands TEXT);
    CREATE TABLE IF NOT EXISTS education_materials(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT, category TEXT, content_raw TEXT, content_simple TEXT,
        content_audio TEXT, risk_tags TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS consent_templates(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT, type TEXT, clauses TEXT, key_points TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS dialogue_scripts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stage TEXT, scene TEXT, script_text TEXT, is_ai_generated INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS trigger_rules(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        condition_expr TEXT, action_type TEXT, target_material_id INTEGER, risk_level TEXT);

    -- ===== 二期扩展：业务类数据表（12 新增）=====
    CREATE TABLE IF NOT EXISTS encounters(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        encounter_no TEXT UNIQUE, admission_date TEXT, department TEXT,
        diagnosis_snapshot TEXT, discharge_date TEXT, status TEXT DEFAULT '在院', created_at TEXT);
    CREATE TABLE IF NOT EXISTS assessment_sessions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_no TEXT UNIQUE, patient_id INTEGER NOT NULL, encounter_id INTEGER,
        collection_mode TEXT DEFAULT 'traditional_form', template_ids TEXT,
        form_version_ids TEXT, status TEXT DEFAULT 'pending', created_at TEXT);
    CREATE TABLE IF NOT EXISTS assessment_answers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER, patient_id INTEGER, scale_code TEXT,
        question_id INTEGER, question_seq INTEGER, option_id INTEGER,
        option_value INTEGER, answer_text TEXT, answered_at TEXT);
    CREATE TABLE IF NOT EXISTS assessment_scores(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER, patient_id INTEGER, scale_code TEXT,
        form_version_id INTEGER, section_scores TEXT, total_score INTEGER,
        risk_level TEXT, mode TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS dialogue_turns(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER, role TEXT, content TEXT, transcript TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS education_sessions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER, material_id INTEGER, status TEXT, confirmed_at TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS teachback_results(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER, question TEXT, answer TEXT, understood INTEGER, created_at TEXT);
    CREATE TABLE IF NOT EXISTS consent_sessions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER, template_id INTEGER, status TEXT, signature_path TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS patient_profiles(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL, encounter_id INTEGER, snapshot_at TEXT,
        dimension_scores TEXT, risk_tags TEXT, evidence_source TEXT, generated_by TEXT);
    CREATE TABLE IF NOT EXISTS nursing_plans(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL, encounter_id INTEGER, profile_id INTEGER,
        risk_summary TEXT, plan_items TEXT, education_focus TEXT,
        status TEXT DEFAULT 'draft', confirmed_by TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS nurse_reviews(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER, session_id INTEGER, review_type TEXT,
        content TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS ai_nurse_comparisons(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER, scale_code TEXT, ai_result TEXT, nurse_result TEXT,
        diff_fields TEXT, diff_reason TEXT, created_at TEXT);

    -- ===== 二期扩展：审计与科研类数据表（5）=====
    CREATE TABLE IF NOT EXISTS template_approvals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_type TEXT, template_id INTEGER, status TEXT, approved_by TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS clinical_audit_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor TEXT, actor_role TEXT, action TEXT, target_type TEXT,
        target_id INTEGER, detail TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS data_exports(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        export_name TEXT, scope TEXT, deidentify_params TEXT, created_by TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS deidentified_records(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        export_id INTEGER, payload TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS model_quality_metrics(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_name TEXT, metric_value REAL, sample_n INTEGER, created_at TEXT);
    ''')
    # 内置账号
    cur = db.execute('SELECT COUNT(*) FROM users')
    if cur.fetchone()[0] == 0:
        db.executemany(
            'INSERT INTO users(username,password,role,name) VALUES(?,?,?,?)',
            [('doctor', '123456', 'doctor', '王医生'),
             ('admin', '123456', 'admin', '系统管理员')])
    seed_scale_config(db)
    db.commit()
    db.close()


# ---------------- 登录 ----------------
def login_required(role=None):
    def deco(f):
        @wraps(f)
        def wrap(*a, **kw):
            if 'uid' not in session:
                return redirect(url_for('login', next=request.path))
            if role and session.get('role') != role:
                flash('无权访问该页面')
                return redirect(url_for('index'))
            return f(*a, **kw)
        return wrap
    return deco


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username', '').strip()
        p = request.form.get('password', '')
        row = get_db().execute(
            'SELECT * FROM users WHERE username=? AND password=?', (u, p)).fetchone()
        if row:
            session['uid'] = row['id']
            session['role'] = row['role']
            session['name'] = row['name']
            return redirect(request.args.get('next') or url_for('index'))
        flash('用户名或密码错误')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


# ---------------- 首页 ----------------
@app.route('/')
def index():
    db = get_db()
    stats = {
        'patient_n': db.execute('SELECT COUNT(*) c FROM patients').fetchone()['c'],
        'finished_n': db.execute(
            "SELECT COUNT(*) c FROM patients WHERE previsit_status='已完成'").fetchone()['c'],
        'report_n': db.execute('SELECT COUNT(*) c FROM reports').fetchone()['c'],
        'scale_n': len(_scales()),
    }
    return render_template('index.html', stats=stats)


# ---------------- 患者端：预问诊 ----------------
@app.route('/patient/new', methods=['GET', 'POST'])
def patient_new():
    """新建评估档案（含基本信息）"""
    if request.method == 'POST':
        f = request.form
        db = get_db()
        cur = db.execute('''INSERT INTO patients
            (name,gender,age,phone,id_card,contact_name,contact_phone,created_at)
            VALUES(?,?,?,?,?,?,?,?)''',
            (f.get('name'), f.get('gender'), f.get('age') or 0,
             f.get('phone'), f.get('id_card'), f.get('contact_name'),
             f.get('contact_phone'), datetime.now().strftime('%Y-%m-%d %H:%M')))
        ts = datetime.now().strftime('%Y-%m-%d %H:%M')
        stamp = int(datetime.now().timestamp())
        db.execute('INSERT INTO encounters(patient_id,encounter_no,admission_date,status,created_at) '
                   'VALUES(?,?,?,?,?)', (cur.lastrowid, f"E{cur.lastrowid}{stamp}", ts, '在院', ts))
        db.execute('INSERT INTO assessment_sessions(patient_id,session_no,collection_mode,status,created_at) '
                   'VALUES(?,?,?,?,?)', (cur.lastrowid, f"S{cur.lastrowid}{stamp}", 'traditional_form', 'active', ts))
        db.execute('INSERT INTO clinical_audit_logs(actor,actor_role,action,target_type,target_id,created_at) '
                   'VALUES(?,?,?,?,?,?)', ('anonymous', 'patient', 'create_patient', 'patient', cur.lastrowid, ts))
        db.commit()
        return redirect(url_for('patient_previsit', pid=cur.lastrowid))
    return render_template('patient_new.html')


@app.route('/patient/<int:pid>/previsit', methods=['GET', 'POST'])
def patient_previsit(pid):
    """预问诊病史采集：主诉-现病史-既往史-用药-过敏-家族史-生活习惯"""
    db = get_db()
    p = db.execute('SELECT * FROM patients WHERE id=?', (pid,)).fetchone()
    if request.method == 'POST':
        f = request.form
        db.execute('''UPDATE patients SET
            chief_complaint=?,present_illness=?,past_history=?,medication=?,
            allergy=?,family_history=?,lifestyle=?,previsit_status='已完成'
            WHERE id=?''',
            (f.get('chief_complaint'), f.get('present_illness'),
             f.get('past_history'), f.get('medication'), f.get('allergy'),
             f.get('family_history'), f.get('lifestyle'), pid))
        db.commit()
        flash('预问诊信息已保存')
        return redirect(url_for('patient_scale_list', pid=pid))
    return render_template('patient_previsit.html', p=p)


@app.route('/patient/<int:pid>/scales')
def patient_scale_list(pid):
    """21张量表分组列表 + 完成进度"""
    db = get_db()
    p = db.execute('SELECT * FROM patients WHERE id=?', (pid,)).fetchone()
    done_rows = db.execute(
        'SELECT scale_id,score,risk_level FROM scale_results WHERE patient_id=?',
        (pid,)).fetchall()
    done = {r['scale_id']: r for r in done_rows}
    # 按评估域分组
    domains = {}
    for s in _scales():
        domains.setdefault(s['domain'], []).append(s)
    progress = round(len(done) / len(_scales()) * 100)
    return render_template('patient_scales.html', p=p, domains=domains,
                           done=done, progress=progress, total=len(_scales()))


@app.route('/patient/<int:pid>/scale/<sid>', methods=['GET', 'POST'])
def patient_scale(pid, sid):
    """单张量表答题，提交即自动评分"""
    scale = _scale_map()[sid]
    db = get_db()
    if request.method == 'POST':
        score = 0
        answers = []
        for i, item in enumerate(scale['items']):
            v = request.form.get(f'q{i}')
            if v is None:
                flash('还有题目未作答，请完成全部题目')
                return redirect(url_for('patient_scale', pid=pid, sid=sid))
            vi = int(v)
            score += vi
            answers.append(vi)
        risk = scale['rule'](score)
        ts = datetime.now().strftime('%Y-%m-%d %H:%M')
        db.execute('''INSERT INTO scale_results
            (patient_id,scale_id,scale_name,score,risk_level,mode,answers,created_at)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(patient_id,scale_id) DO UPDATE SET
              score=excluded.score, risk_level=excluded.risk_level,
              answers=excluded.answers, created_at=excluded.created_at''',
            (pid, sid, scale['name'], score, risk, scale['mode'],
             json.dumps(answers, ensure_ascii=False), ts))
        sess = db.execute('SELECT id FROM assessment_sessions WHERE patient_id=? ORDER BY id DESC LIMIT 1', (pid,)).fetchone()
        session_id = sess['id'] if sess else None
        for i, item in enumerate(scale['items']):
            vi = int(request.form.get(f'q{i}'))
            db.execute('INSERT INTO assessment_answers(session_id,patient_id,scale_code,question_seq,option_value,answer_text,answered_at) '
                       'VALUES(?,?,?,?,?,?,?)', (session_id, pid, sid, i + 1, vi, str(vi), ts))
        db.execute('INSERT INTO assessment_scores(session_id,patient_id,scale_code,total_score,risk_level,mode,created_at) '
                   'VALUES(?,?,?,?,?,?,?)', (session_id, pid, sid, score, risk, scale['mode'], ts))
        db.execute('INSERT INTO clinical_audit_logs(actor,actor_role,action,target_type,target_id,created_at) '
                   'VALUES(?,?,?,?,?,?)', ('anonymous', 'patient', 'submit_scale', 'scale_result', pid, ts))
        db.commit()
        flash(f'《{scale["name"]}》已完成：{score}分，判定：{risk}')
        return redirect(url_for('patient_scale_list', pid=pid))
    return render_template('patient_scale.html', p_id=pid, scale=scale,
                           enumerate=enumerate)


@app.route('/patient/<int:pid>/report')
def patient_report(pid):
    """患者端查看综合报告"""
    db = get_db()
    p = db.execute('SELECT * FROM patients WHERE id=?', (pid,)).fetchone()
    rep = db.execute('SELECT * FROM reports WHERE patient_id=?', (pid,)).fetchone()
    results = db.execute(
        'SELECT * FROM scale_results WHERE patient_id=? ORDER BY id', (pid,)
    ).fetchall()
    return render_template('patient_report.html', p=p, rep=rep, results=results,
                           total_scale=len(_scales()))


# ---------------- 报告生成（核心算法） ----------------
def build_report(db, pid):
    """汇总21张量表得分 → 分域统计 → 异常项提取 → 匹配健康建议 → 渲染报告"""
    p = db.execute('SELECT * FROM patients WHERE id=?', (pid,)).fetchone()
    results = db.execute(
        'SELECT * FROM scale_results WHERE patient_id=? ORDER BY id', (pid,)
    ).fetchall()
    if not results:
        return None

    # 正常/低风险关键词，用于判定是否为异常项（复用模块级常量）
    normal_words = NORMAL_WORDS
    domain_stat = {}
    abnormal = []
    for r in results:
        sc = _scale_map().get(r['scale_id'])
        domain = sc['domain'] if sc else '其他'
        domain_stat.setdefault(domain, []).append(r)
        lvl = r['risk_level'] or ''
        if not any(w in lvl for w in normal_words):
            abnormal.append({'sid': r['scale_id'], 'name': r['scale_name'],
                             'score': r['score'], 'level': lvl,
                             'advice': ADVICE_KB.get(r['scale_id'], '建议结合临床进一步评估。')})

    # 综合结论
    n = len(results)
    ab_n = len(abnormal)
    if not abnormal:
        conclusion = f'本次已完成{n}张量表评估，各维度总体情况良好，建议保持健康生活方式，定期（6-12个月）复评。'
    elif ab_n <= 4:
        conclusion = f'本次已完成{n}张量表评估，发现{ab_n}项异常指标，属于轻度风险人群，建议按下方指导干预，3个月后复评。'
    elif ab_n <= 9:
        conclusion = f'本次已完成{n}张量表评估，发现{ab_n}项异常指标，属于中度风险人群，建议由老年医学科多学科团队制定综合干预方案，1-3个月复评。'
    else:
        conclusion = f'本次已完成{n}张量表评估，发现{ab_n}项异常指标，属于高度风险/衰弱老年人群，建议尽快启动多学科综合管理，48小时内启动干预并加密随访。'

    html = render_template('report_body.html', p=p, results=results,
                           domain_stat=domain_stat, abnormal=abnormal,
                           conclusion=conclusion,
                           gen_time=datetime.now().strftime('%Y-%m-%d %H:%M'))
    return {'html': html, 'risk_count': ab_n}


@app.route('/patient/<int:pid>/report/generate', methods=['POST'])
def generate_report(pid):
    db = get_db()
    done_n = db.execute(
        'SELECT COUNT(*) c FROM scale_results WHERE patient_id=?', (pid,)
    ).fetchone()['c']
    if done_n < len(_scales()):
        flash(f'请先完成全部{len(_scales())}张量表（当前{done_n}张），再生成报告')
        return redirect(url_for('patient_scale_list', pid=pid))
    rep = build_report(db, pid)
    results = db.execute(
        'SELECT * FROM scale_results WHERE patient_id=? ORDER BY scale_id', (pid,)
    ).fetchall()
    old = db.execute('SELECT id FROM reports WHERE patient_id=?', (pid,)).fetchone()
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    if old:
        db.execute('UPDATE reports SET content=?,risk_count=?,status="待审核",created_at=? WHERE id=?',
                   (rep['html'], rep['risk_count'], ts, old['id']))
    else:
        db.execute('''INSERT INTO reports(patient_id,content,risk_count,status,created_at)
                      VALUES(?,?,?,'待审核',?)''',
                   (pid, rep['html'], rep['risk_count'], ts))
    # 二期：生成患者画像快照与护理计划草稿
    dims = {}
    tags = []
    plan_items = []
    for r in results:
        sc = _scale_map().get(r['scale_id'])
        dom = sc['domain'] if sc else '其他'
        dims[dom] = dims.get(dom, 0) + 1
        lvl = r['risk_level'] or ''
        if not any(w in lvl for w in NORMAL_WORDS):
            tags.append(r['scale_name'])
            plan_items.append({'focus': r['scale_name'],
                              'advice': ADVICE_KB.get(r['scale_id'], '建议结合临床进一步评估。')})
    enc = db.execute('SELECT id FROM encounters WHERE patient_id=? ORDER BY id DESC LIMIT 1', (pid,)).fetchone()
    enc_id = enc['id'] if enc else None
    prof = db.execute('SELECT id FROM patient_profiles WHERE patient_id=? ORDER BY id DESC LIMIT 1', (pid,)).fetchone()
    if prof:
        db.execute('UPDATE patient_profiles SET encounter_id=?,snapshot_at=?,dimension_scores=?,risk_tags=?,evidence_source=?,generated_by=? WHERE id=?',
                   (enc_id, ts, json.dumps(dims, ensure_ascii=False), json.dumps(tags, ensure_ascii=False), 'ai_extracted', 'system', prof['id']))
    else:
        db.execute('INSERT INTO patient_profiles(patient_id,encounter_id,snapshot_at,dimension_scores,risk_tags,evidence_source,generated_by) '
                   'VALUES(?,?,?,?,?,?,?)', (pid, enc_id, ts, json.dumps(dims, ensure_ascii=False), json.dumps(tags, ensure_ascii=False), 'ai_extracted', 'system'))
    plan = db.execute('SELECT id FROM nursing_plans WHERE patient_id=? ORDER BY id DESC LIMIT 1', (pid,)).fetchone()
    if plan:
        db.execute('UPDATE nursing_plans SET encounter_id=?,risk_summary=?,plan_items=?,education_focus=?,status=?,created_at=? WHERE id=?',
                   (enc_id, f'发现{len(tags)}项异常指标', json.dumps(plan_items, ensure_ascii=False), json.dumps(tags, ensure_ascii=False), 'draft', ts, plan['id']))
    else:
        db.execute('INSERT INTO nursing_plans(patient_id,encounter_id,risk_summary,plan_items,education_focus,status,created_at) '
                   'VALUES(?,?,?,?,?,?,?)', (pid, enc_id, f'发现{len(tags)}项异常指标', json.dumps(plan_items, ensure_ascii=False), json.dumps(tags, ensure_ascii=False), 'draft', ts))
    db.commit()
    flash('老年综合评估报告已自动生成，等待医护审核')
    return redirect(url_for('patient_report', pid=pid))


# ---------------- 医护端 ----------------
@app.route('/doctor')
@login_required(role='doctor')
def doctor_home():
    db = get_db()
    patients = db.execute('''SELECT p.*,
        (SELECT COUNT(*) FROM scale_results s WHERE s.patient_id=p.id) scale_n,
        (SELECT status FROM reports r WHERE r.patient_id=p.id) report_status
        FROM patients p ORDER BY p.id DESC''').fetchall()
    return render_template('doctor_home.html', patients=patients,
                           total_scale=len(_scales()))


@app.route('/doctor/patient/<int:pid>')
@login_required(role='doctor')
def doctor_detail(pid):
    db = get_db()
    p = db.execute('SELECT * FROM patients WHERE id=?', (pid,)).fetchone()
    results = db.execute(
        'SELECT * FROM scale_results WHERE patient_id=? ORDER BY id', (pid,)
    ).fetchall()
    rep = db.execute('SELECT * FROM reports WHERE patient_id=?', (pid,)).fetchone()
    return render_template('doctor_detail.html', p=p, results=results, rep=rep)


@app.route('/doctor/report/<int:pid>/audit', methods=['POST'])
@login_required(role='doctor')
def audit_report(pid):
    status = request.form.get('status', '已通过')
    comment = request.form.get('doctor_comment', '')
    db = get_db()
    db.execute('UPDATE reports SET status=?, doctor_comment=? WHERE patient_id=?',
               (status, comment, pid))
    db.execute('INSERT INTO clinical_audit_logs(actor,actor_role,action,target_type,target_id,created_at) '
               'VALUES(?,?,?,?,?,?)', (session.get('name', '医护'), session.get('role', 'staff'),
                'audit_report', 'report', pid, datetime.now().strftime('%Y-%m-%d %H:%M')))
    db.commit()
    flash(f'报告已{status}')
    return redirect(url_for('doctor_detail', pid=pid))


# ---------------- 管理端 ----------------
@app.route('/admin')
@login_required(role='admin')
def admin_home():
    db = get_db()
    rows = db.execute('''SELECT scale_id, scale_name, COUNT(*) n
        FROM scale_results GROUP BY scale_id ORDER BY scale_id''').fetchall()
    used = {r['scale_id']: r['n'] for r in rows}
    risk_rows = db.execute('''SELECT risk_level, COUNT(*) n
        FROM scale_results GROUP BY risk_level ORDER BY n DESC''').fetchall()
    svc = {
        '患者总数': db.execute('SELECT COUNT(*) c FROM patients').fetchone()['c'],
        '预问诊完成': db.execute(
            "SELECT COUNT(*) c FROM patients WHERE previsit_status='已完成'").fetchone()['c'],
        '报告总数': db.execute('SELECT COUNT(*) c FROM reports').fetchone()['c'],
        '已审核报告': db.execute(
            "SELECT COUNT(*) c FROM reports WHERE status='已通过'").fetchone()['c'],
    }
    return render_template('admin_home.html', scales=_scales(), used=used,
                           risk_rows=risk_rows, svc=svc)


# ---------------- 打印报告（独立页） ----------------
@app.route('/patient/<int:pid>/report/print')
def print_report(pid):
    db = get_db()
    rep = db.execute('SELECT * FROM reports WHERE patient_id=?', (pid,)).fetchone()
    if not rep:
        flash('报告尚未生成')
        return redirect(url_for('patient_report', pid=pid))
    return render_template('print.html', rep=rep)


# ---------------- 量表目录（只读元数据接口） ----------------
@app.route('/api/scales')
def api_scales():
    rows = [{
        'id': s['id'],
        'name': s['name'],
        'abbr': s.get('abbr', ''),
        'domain': s.get('domain', ''),
        'mode': s.get('mode', ''),
        'items': len(s.get('items', [])),
    } for s in _scales()]
    return jsonify({'count': len(rows), 'scales': rows})


# ---------------- 健康检查（最小可验证功能） ----------------
@app.route('/healthz')
def healthz():
    db_ok = True
    err = None
    try:
        get_db().execute('SELECT 1').fetchone()
    except sqlite3.Error as e:
        db_ok = False
        err = str(e)
    scale_n = len(_scales()) if db_ok else 0
    payload = {
        'status': 'ok' if db_ok and scale_n > 0 else 'degraded',
        'db': 'ok' if db_ok else 'error',
        'scales': scale_n,
        'version': '2.0',
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    if err:
        payload['error'] = err
    return jsonify(payload), (200 if payload['status'] == 'ok' else 503)


if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=5000, debug=True)
