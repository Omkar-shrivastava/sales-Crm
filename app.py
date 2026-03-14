"""
CRM Dashboard — Multi-File Version with PostgreSQL + Login/Logout + Form Builder
✅ Multiple Files/Projects — har file ka alag data, alag columns
✅ Unnamed columns Excel import mein skip
✅ Add Record: Full Row + Single Column tabs
✅ 📎 Attachment button in each row
✅ Excel import/export per file
✅ Full CRUD + Search
✅ LOGIN / LOGOUT — Session-based Auth
✅ Admin User Management — create/delete users
✅ PostgreSQL Backend
✅ 🆕 Form Builder — Admin custom form banaye, logo + org name, public link generate kare
✅ 🆕 Public Form — permanent link, unlimited submissions
✅ 🆕 Form submissions CRM dashboard mein auto file mein aate hain
✅ 🆕 Dropdown fields mein options ek-ek add karne ka UI
✅ 🆕 Image upload field with preview info panel

pip install flask psycopg2-binary openpyxl pandas werkzeug

PostgreSQL setup:
  createdb crmdb
  export DATABASE_URL="postgresql://username:password@localhost/crmdb"

python app.py → http://127.0.0.1:5000
Default admin: username=admin  password=admin123
"""

import os, json, uuid, functools
from datetime import datetime, date
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from flask import (Flask, render_template_string, request, jsonify,
                   send_from_directory, url_for, send_file,
                   session, redirect, flash)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import io

app = Flask(__name__)
app.config['SECRET_KEY']         = 'crm-2025-secret-change-in-prod'
app.config['UPLOAD_FOLDER']      = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:omkar123@localhost/crmdb')

ALLOWED = {'png','jpg','jpeg','gif','webp','pdf','mp4','mov','avi','mkv','xlsx','xls','docx','txt','csv'}
COLORS  = ['#00c8ff','#00e07a','#ff9500','#ff3d5a','#a855f7','#f59e0b','#06b6d4','#84cc16']
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# ─────────────── DB ───────────────
@contextmanager
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def qone(conn, sql, params=()):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchone()

def qall(conn, sql, params=()):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchall()

def qexec(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)

def qinsert(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id         SERIAL PRIMARY KEY,
                    username   TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    is_admin   BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id         SERIAL PRIMARY KEY,
                    name       TEXT NOT NULL,
                    color      TEXT DEFAULT '#00c8ff',
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS crm_columns (
                    id         SERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    name       TEXT NOT NULL,
                    col_type   TEXT DEFAULT 'text',
                    col_order  INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS crm_records (
                    id         SERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    data       TEXT DEFAULT '{}',
                    tags       TEXT DEFAULT '',
                    notes      TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS attachments (
                    id            SERIAL PRIMARY KEY,
                    record_id     INTEGER NOT NULL REFERENCES crm_records(id) ON DELETE CASCADE,
                    filename      TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    file_type     TEXT DEFAULT 'file',
                    file_size     INTEGER DEFAULT 0,
                    created_at    TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS custom_forms (
                    id            SERIAL PRIMARY KEY,
                    token         TEXT NOT NULL UNIQUE,
                    project_id    INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                    title         TEXT NOT NULL,
                    org_name      TEXT DEFAULT '',
                    description   TEXT DEFAULT '',
                    logo_filename TEXT DEFAULT '',
                    accent_color  TEXT DEFAULT '#00c8ff',
                    fields        TEXT DEFAULT '[]',
                    is_active     BOOLEAN DEFAULT TRUE,
                    created_by    INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    created_at    TIMESTAMP DEFAULT NOW()
                );
            """)

        cnt = qone(conn, "SELECT COUNT(*) as c FROM users")['c']
        if cnt == 0:
            pw = generate_password_hash('admin123')
            qexec(conn, "INSERT INTO users(username, password_hash, is_admin) VALUES(%s,%s,%s)",
                  ('admin', pw, True))
            print("✅ Default admin created: admin / admin123")

        cnt2 = qone(conn, "SELECT COUNT(*) as c FROM projects")['c']
        if cnt2 == 0:
            pid = qinsert(conn,
                "INSERT INTO projects(name,color) VALUES(%s,%s) RETURNING id",
                ('Filter Bag Tracker', '#00c8ff'))
            defaults = [
                ('Client Name','text'),('Location','text'),('PO Number','text'),
                ('Item Code','text'),  ('Size','text'),    ('Type','text'),
                ('Material','text'),   ('Diameter','text'),('Quantity','number'),
                ('Date','text'),       ('Remarks','text')
            ]
            with conn.cursor() as cur:
                for i, (n, t) in enumerate(defaults):
                    cur.execute(
                        "INSERT INTO crm_columns(project_id,name,col_type,col_order) VALUES(%s,%s,%s,%s)",
                        (pid, n, t, i))

init_db()


# ─────────────── AUTH ───────────────
def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': 'Login required'}), 401
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Login required'}), 401
        if not session.get('is_admin'):
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        with get_db() as conn:
            user = qone(conn, "SELECT * FROM users WHERE username=%s", (username,))
        if user and check_password_hash(user['password_hash'], password):
            session['user_id']  = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            return redirect('/')
        return render_template_string(LOGIN_HTML, error='Invalid username or password')
    return render_template_string(LOGIN_HTML, error=None)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ─────────────── UTILS ───────────────
def _human_size(n):
    n = n or 0
    for u in ['B','KB','MB','GB']:
        if n < 1024: return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"

def _file_type(fn):
    e = fn.rsplit('.',1)[-1].lower() if '.' in fn else ''
    if e in {'png','jpg','jpeg','gif','webp'}: return 'image'
    if e == 'pdf':  return 'pdf'
    if e in {'mp4','mov','avi','mkv','webm'}: return 'video'
    return 'file'

def allowed(fn):
    return '.' in fn and fn.rsplit('.',1)[1].lower() in ALLOWED

def fmt_date(s):
    if not s: return ''
    try:
        if isinstance(s, datetime): return s.strftime('%d %b %Y')
        return datetime.fromisoformat(str(s).split('.')[0]).strftime('%d %b %Y')
    except: return str(s)

def att_to_dict(a):
    return {
        'id': a['id'], 'filename': a['filename'],
        'original_name': a['original_name'], 'file_type': a['file_type'],
        'file_size_str': _human_size(a['file_size']),
        'url': url_for('serve_upload', filename=a['filename'])
    }

def record_to_dict(row, atts):
    try:    data = json.loads(row['data'])
    except: data = {}
    return {
        'id': row['id'], 'data': data,
        'tags': row['tags'] or '', 'notes': row['notes'] or '',
        'created_at': fmt_date(row['created_at']),
        'attachments': atts
    }

def get_record_with_atts(conn, rid):
    row = qone(conn, "SELECT * FROM crm_records WHERE id=%s", (rid,))
    if not row: return None
    atts = [att_to_dict(a) for a in
            qall(conn, "SELECT * FROM attachments WHERE record_id=%s ORDER BY id", (rid,))]
    return record_to_dict(row, atts)


# ─────────────── MAIN ROUTES ───────────────
@app.route('/')
@login_required
def index():
    return render_template_string(HTML)

@app.route('/uploads/<filename>')
def serve_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ─────────────── API — USERS (Admin) ───────────────
@app.route('/api/admin/users')
@admin_required
def get_users():
    with get_db() as conn:
        rows = qall(conn, "SELECT id,username,is_admin,created_at FROM users ORDER BY id")
        result = [{'id': r['id'], 'username': r['username'],
                   'is_admin': r['is_admin'],
                   'created_at': fmt_date(r['created_at'])} for r in rows]
    return jsonify({'success': True, 'users': result})

@app.route('/api/admin/users', methods=['POST'])
@admin_required
def add_user():
    d = request.get_json() or {}
    username = d.get('username','').strip()
    password = d.get('password','').strip()
    is_admin = d.get('is_admin', False)
    if not username: return jsonify({'success': False, 'message': 'Username required'}), 400
    if len(password) < 4: return jsonify({'success': False, 'message': 'Password min 4 chars'}), 400
    pw_hash = generate_password_hash(password)
    try:
        with get_db() as conn:
            uid = qinsert(conn,
                "INSERT INTO users(username,password_hash,is_admin) VALUES(%s,%s,%s) RETURNING id",
                (username, pw_hash, is_admin))
            user = qone(conn, "SELECT id,username,is_admin,created_at FROM users WHERE id=%s", (uid,))
        return jsonify({'success': True, 'user': {
            'id': user['id'], 'username': user['username'],
            'is_admin': user['is_admin'], 'created_at': fmt_date(user['created_at'])
        }})
    except psycopg2.errors.UniqueViolation:
        return jsonify({'success': False, 'message': 'Username already exists'}), 400

@app.route('/api/admin/users/<int:uid>', methods=['DELETE'])
@admin_required
def del_user(uid):
    if uid == session.get('user_id'):
        return jsonify({'success': False, 'message': 'Aap apna account delete nahi kar sakte'}), 400
    with get_db() as conn:
        qexec(conn, "DELETE FROM users WHERE id=%s", (uid,))
    return jsonify({'success': True})

@app.route('/api/admin/users/<int:uid>/password', methods=['PUT'])
@admin_required
def change_password(uid):
    d = request.get_json() or {}
    new_pw = d.get('password','').strip()
    if len(new_pw) < 4:
        return jsonify({'success': False, 'message': 'Password min 4 chars'}), 400
    with get_db() as conn:
        qexec(conn, "UPDATE users SET password_hash=%s WHERE id=%s",
              (generate_password_hash(new_pw), uid))
    return jsonify({'success': True})

@app.route('/api/me')
@login_required
def me():
    return jsonify({'success': True, 'username': session.get('username'),
                    'is_admin': session.get('is_admin', False),
                    'user_id': session.get('user_id')})


# ─────────────── API — PROJECTS ───────────────
@app.route('/api/projects')
@login_required
def get_projects():
    with get_db() as conn:
        rows = qall(conn, "SELECT * FROM projects ORDER BY created_at")
        result = []
        for r in rows:
            rc = qone(conn, "SELECT COUNT(*) as c FROM crm_records WHERE project_id=%s", (r['id'],))['c']
            result.append({'id': r['id'], 'name': r['name'], 'color': r['color'],
                           'created_at': fmt_date(r['created_at']), 'record_count': rc})
    return jsonify({'success': True, 'projects': result})

@app.route('/api/projects', methods=['POST'])
@login_required
def add_project():
    d = request.get_json() or {}
    name = d.get('name','').strip()
    if not name: return jsonify({'success': False, 'message': 'Name required'}), 400
    with get_db() as conn:
        pid = qinsert(conn,
            "INSERT INTO projects(name,color) VALUES(%s,%s) RETURNING id",
            (name, d.get('color','#00c8ff')))
        proj = dict(qone(conn, "SELECT * FROM projects WHERE id=%s", (pid,)))
    proj['record_count'] = 0
    proj['created_at'] = fmt_date(proj['created_at'])
    return jsonify({'success': True, 'project': proj})

@app.route('/api/projects/<int:pid>', methods=['DELETE'])
@login_required
def del_project(pid):
    with get_db() as conn:
        recs = qall(conn, "SELECT id FROM crm_records WHERE project_id=%s", (pid,))
        for rec in recs:
            for a in qall(conn, "SELECT filename FROM attachments WHERE record_id=%s", (rec['id'],)):
                try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], a['filename']))
                except: pass
        qexec(conn, "DELETE FROM projects WHERE id=%s", (pid,))
    return jsonify({'success': True})


# ─────────────── API — COLUMNS ───────────────
@app.route('/api/projects/<int:pid>/columns')
@login_required
def get_columns(pid):
    with get_db() as conn:
        cols = [dict(r) for r in qall(conn,
            "SELECT * FROM crm_columns WHERE project_id=%s ORDER BY col_order", (pid,))]
    return jsonify({'success': True, 'columns': cols})

@app.route('/api/projects/<int:pid>/columns', methods=['POST'])
@login_required
def add_column(pid):
    d = request.get_json() or {}
    name = d.get('name','').strip()
    if not name: return jsonify({'success': False, 'message': 'Name required'}), 400
    insert_after = d.get('insert_after', None)
    with get_db() as conn:
        if insert_after is None:
            mo = qone(conn, "SELECT MAX(col_order) as m FROM crm_columns WHERE project_id=%s", (pid,))['m'] or 0
            new_order = mo + 1
        else:
            ref = qone(conn, "SELECT col_order FROM crm_columns WHERE id=%s AND project_id=%s",
                       (insert_after, pid))
            if ref:
                pos = ref['col_order']
                new_order = pos + 1
                qexec(conn,
                    "UPDATE crm_columns SET col_order = col_order + 1 "
                    "WHERE project_id=%s AND col_order >= %s", (pid, new_order))
            else:
                mo = qone(conn, "SELECT MAX(col_order) as m FROM crm_columns WHERE project_id=%s", (pid,))['m'] or 0
                new_order = mo + 1
        cid = qinsert(conn,
            "INSERT INTO crm_columns(project_id,name,col_type,col_order) VALUES(%s,%s,%s,%s) RETURNING id",
            (pid, name, d.get('col_type','text'), new_order))
        col = dict(qone(conn, "SELECT * FROM crm_columns WHERE id=%s", (cid,)))
    return jsonify({'success': True, 'column': col})

@app.route('/api/projects/<int:pid>/columns/<int:cid>', methods=['DELETE'])
@login_required
def del_column(pid, cid):
    with get_db() as conn:
        for rec in qall(conn, "SELECT id, data FROM crm_records WHERE project_id=%s", (pid,)):
            try:
                d = json.loads(rec['data']); d.pop(str(cid), None)
                qexec(conn, "UPDATE crm_records SET data=%s WHERE id=%s", (json.dumps(d), rec['id']))
            except: pass
        qexec(conn, "DELETE FROM crm_columns WHERE id=%s AND project_id=%s", (cid, pid))
    return jsonify({'success': True})


# ─────────────── API — RECORDS ───────────────
@app.route('/api/projects/<int:pid>/records')
@login_required
def get_records(pid):
    q = request.args.get('q','').strip().lower()
    with get_db() as conn:
        rows = qall(conn,
            "SELECT * FROM crm_records WHERE project_id=%s ORDER BY created_at DESC", (pid,))
        result = []
        for row in rows:
            atts = [att_to_dict(a) for a in
                    qall(conn, "SELECT * FROM attachments WHERE record_id=%s", (row['id'],))]
            rec = record_to_dict(row, atts)
            if q:
                txt = ' '.join(str(v) for v in rec['data'].values()).lower()
                txt += ' ' + (rec['notes'] or '').lower() + ' ' + (rec['tags'] or '').lower()
                if q not in txt: continue
            result.append(rec)
    return jsonify({'success': True, 'records': result, 'total': len(result)})

@app.route('/api/projects/<int:pid>/records', methods=['POST'])
@login_required
def add_record(pid):
    d = request.get_json() or {}
    with get_db() as conn:
        rid = qinsert(conn,
            "INSERT INTO crm_records(project_id,data,tags,notes) VALUES(%s,%s,%s,%s) RETURNING id",
            (pid, json.dumps(d.get('data',{})), d.get('tags',''), d.get('notes','')))
        rec = get_record_with_atts(conn, rid)
    return jsonify({'success': True, 'record': rec})

@app.route('/api/records/<int:rid>')
@login_required
def get_record(rid):
    with get_db() as conn:
        rec = get_record_with_atts(conn, rid)
    if not rec: return jsonify({'success': False}), 404
    return jsonify({'success': True, 'record': rec})

@app.route('/api/records/<int:rid>', methods=['PUT'])
@login_required
def upd_record(rid):
    d = request.get_json() or {}
    with get_db() as conn:
        row = qone(conn, "SELECT * FROM crm_records WHERE id=%s", (rid,))
        if not row: return jsonify({'success': False}), 404
        try:    old = json.loads(row['data'])
        except: old = {}
        qexec(conn,
            "UPDATE crm_records SET data=%s,tags=%s,notes=%s,updated_at=NOW() WHERE id=%s",
            (json.dumps(d.get('data', old)),
             d.get('tags', row['tags']),
             d.get('notes', row['notes']), rid))
        rec = get_record_with_atts(conn, rid)
    return jsonify({'success': True, 'record': rec})

@app.route('/api/records/<int:rid>', methods=['DELETE'])
@login_required
def del_record(rid):
    with get_db() as conn:
        for a in qall(conn, "SELECT filename FROM attachments WHERE record_id=%s", (rid,)):
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], a['filename']))
            except: pass
        qexec(conn, "DELETE FROM crm_records WHERE id=%s", (rid,))
    return jsonify({'success': True})


# ─────────────── API — ATTACHMENTS ───────────────
@app.route('/api/records/<int:rid>/attachments', methods=['POST'])
@login_required
def upload_att(rid):
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file'}), 400
    file = request.files['file']
    if not file.filename or not allowed(file.filename):
        return jsonify({'success': False, 'message': 'File type not allowed'}), 400
    orig   = secure_filename(file.filename)
    ext    = orig.rsplit('.',1)[-1] if '.' in orig else 'bin'
    stored = f"{uuid.uuid4().hex}.{ext}"
    fp     = os.path.join(app.config['UPLOAD_FOLDER'], stored)
    file.save(fp)
    with get_db() as conn:
        aid = qinsert(conn,
            "INSERT INTO attachments(record_id,filename,original_name,file_type,file_size) VALUES(%s,%s,%s,%s,%s) RETURNING id",
            (rid, stored, orig, _file_type(orig), os.path.getsize(fp)))
        a = dict(qone(conn, "SELECT * FROM attachments WHERE id=%s", (aid,)))
    return jsonify({'success': True, 'attachment': att_to_dict(a)})

@app.route('/api/attachments/<int:aid>', methods=['DELETE'])
@login_required
def del_att(aid):
    with get_db() as conn:
        a = qone(conn, "SELECT * FROM attachments WHERE id=%s", (aid,))
        if not a: return jsonify({'success': False}), 404
        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], a['filename']))
        except: pass
        qexec(conn, "DELETE FROM attachments WHERE id=%s", (aid,))
    return jsonify({'success': True})


# ─────────────── API — IMPORT / EXPORT / STATS ───────────────
@app.route('/api/projects/<int:pid>/import', methods=['POST'])
@login_required
def import_excel(pid):
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file'}), 400
    f = request.files['file']
    if not f.filename.endswith(('.xlsx','.xls')):
        return jsonify({'success': False, 'message': 'Only .xlsx / .xls'}), 400
    try:
        import re as _re
        file_bytes = f.read()

        def _clean_hdrs(df):
            return [h for h in df.columns
                    if str(h).strip()
                    and not _re.match(r'^Unnamed:\s*\d+', str(h))
                    and str(h).strip().lower() not in ('nan','none','')]

        df = pd.read_excel(io.BytesIO(file_bytes), dtype=str).fillna('')
        headers = _clean_hdrs(df)

        if not headers:
            df = pd.read_excel(io.BytesIO(file_bytes), dtype=str, header=1).fillna('')
            headers = _clean_hdrs(df)

        if not headers:
            df = pd.read_excel(io.BytesIO(file_bytes), dtype=str, header=2).fillna('')
            headers = _clean_hdrs(df)

        if not headers:
            df = pd.read_excel(io.BytesIO(file_bytes), dtype=str).fillna('')
            headers = [str(h).strip() for h in df.columns if str(h).strip()]
            df.columns = [str(c).strip() for c in df.columns]

        if not headers:
            return jsonify({'success': False,
                            'message': 'Excel mein koi valid column header nahi mila.'}), 400

        df = df[headers]

        with get_db() as conn:
            existing = {r['name'].strip().lower(): r['id'] for r in
                        qall(conn, "SELECT id,name FROM crm_columns WHERE project_id=%s", (pid,))}
            col_map = {}
            mo = qone(conn, "SELECT MAX(col_order) as m FROM crm_columns WHERE project_id=%s", (pid,))['m'] or 0

            for i, h in enumerate(headers):
                k = h.strip().lower()
                if k in existing:
                    col_map[h] = existing[k]
                else:
                    cid = qinsert(conn,
                        "INSERT INTO crm_columns(project_id,name,col_type,col_order) VALUES(%s,%s,%s,%s) RETURNING id",
                        (pid, h.strip(), 'text', mo+i+1))
                    col_map[h] = cid

            inserted = 0
            for _, row in df.iterrows():
                rd = {str(col_map[h]): str(row[h]).strip()
                      for h in headers
                      if str(row[h]).strip() and str(row[h]).strip() != 'nan'}
                if any(rd.values()):
                    qexec(conn, "INSERT INTO crm_records(project_id,data) VALUES(%s,%s)",
                          (pid, json.dumps(rd)))
                    inserted += 1

        return jsonify({'success': True, 'message': f'{inserted} rows imported',
                        'rows': inserted, 'cols': len(headers)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/projects/<int:pid>/export')
@login_required
def export_excel(pid):
    with get_db() as conn:
        proj = qone(conn, "SELECT name FROM projects WHERE id=%s", (pid,))
        cols = qall(conn, "SELECT * FROM crm_columns WHERE project_id=%s ORDER BY col_order", (pid,))
        recs = qall(conn, "SELECT * FROM crm_records WHERE project_id=%s ORDER BY created_at DESC", (pid,))
    rows = []
    for r in recs:
        try:    d = json.loads(r['data'])
        except: d = {}
        row = {c['name']: d.get(str(c['id']),'') for c in cols}
        row['Notes']   = r['notes']
        row['Tags']    = r['tags']
        row['Created'] = fmt_date(r['created_at'])
        rows.append(row)
    out = io.BytesIO()
    pd.DataFrame(rows).to_excel(out, index=False, engine='openpyxl')
    out.seek(0)
    fname = f"{proj['name'] if proj else 'export'}.xlsx"
    return send_file(out,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True, download_name=fname)

@app.route('/api/stats/<int:pid>')
@login_required
def stats(pid):
    today = date.today().isoformat()
    with get_db() as conn:
        records     = qone(conn, "SELECT COUNT(*) as c FROM crm_records WHERE project_id=%s", (pid,))['c']
        columns     = qone(conn, "SELECT COUNT(*) as c FROM crm_columns WHERE project_id=%s", (pid,))['c']
        today_c     = qone(conn,
            "SELECT COUNT(*) as c FROM crm_records WHERE project_id=%s AND created_at::date=%s",
            (pid, today))['c']
        attachments = qone(conn,
            "SELECT COUNT(*) as c FROM attachments a "
            "JOIN crm_records r ON a.record_id=r.id WHERE r.project_id=%s", (pid,))['c']
    return jsonify({'records': records, 'columns': columns,
                    'attachments': attachments, 'today': today_c})


# ─────────────── API — CUSTOM FORMS ───────────────
@app.route('/api/forms')
@admin_required
def get_forms():
    with get_db() as conn:
        forms = qall(conn, "SELECT * FROM custom_forms ORDER BY created_at DESC")
        result = []
        for f in forms:
            fc = qone(conn, "SELECT COUNT(*) as c FROM crm_records WHERE project_id=%s",
                      (f['project_id'],))['c'] if f['project_id'] else 0
            logo_url = url_for('serve_upload', filename=f['logo_filename']) if f['logo_filename'] else ''
            result.append({
                'id': f['id'], 'token': f['token'], 'title': f['title'],
                'org_name': f['org_name'], 'description': f['description'],
                'logo_url': logo_url, 'logo_filename': f['logo_filename'],
                'accent_color': f['accent_color'],
                'fields': json.loads(f['fields'] or '[]'),
                'is_active': f['is_active'], 'project_id': f['project_id'],
                'submission_count': fc,
                'created_at': fmt_date(f['created_at']),
                'public_url': url_for('public_form', token=f['token'], _external=True)
            })
    return jsonify({'success': True, 'forms': result})

@app.route('/api/forms', methods=['POST'])
@admin_required
def create_form():
    is_multipart = request.content_type and 'multipart' in request.content_type
    if is_multipart:
        title      = request.form.get('title','').strip()
        org_name   = request.form.get('org_name','').strip()
        desc       = request.form.get('description','').strip()
        accent     = request.form.get('accent_color','#00c8ff').strip()
        fields_raw = request.form.get('fields','[]')
        color      = request.form.get('color','#00c8ff').strip()
    else:
        d = request.get_json() or {}
        title      = d.get('title','').strip()
        org_name   = d.get('org_name','').strip()
        desc       = d.get('description','').strip()
        accent     = d.get('accent_color','#00c8ff')
        fields_raw = json.dumps(d.get('fields',[]))
        color      = d.get('color','#00c8ff')

    if not title:
        return jsonify({'success': False, 'message': 'Form title required'}), 400

    logo_filename = ''
    if is_multipart and 'logo' in request.files:
        logo = request.files['logo']
        if logo.filename and allowed(logo.filename):
            orig = secure_filename(logo.filename)
            ext  = orig.rsplit('.',1)[-1] if '.' in orig else 'png'
            stored = f"logo_{uuid.uuid4().hex}.{ext}"
            logo.save(os.path.join(app.config['UPLOAD_FOLDER'], stored))
            logo_filename = stored

    token = uuid.uuid4().hex

    with get_db() as conn:
        proj_name = f"📋 {title}" + (f" ({org_name})" if org_name else "")
        pid = qinsert(conn,
            "INSERT INTO projects(name,color) VALUES(%s,%s) RETURNING id",
            (proj_name, color))

        try:    fields = json.loads(fields_raw)
        except: fields = []

        for i, fld in enumerate(fields):
            fname = fld.get('label','').strip()
            ftype = fld.get('type','text')
            db_type = 'number' if ftype=='number' else 'text'
            if fname:
                qinsert(conn,
                    "INSERT INTO crm_columns(project_id,name,col_type,col_order) VALUES(%s,%s,%s,%s) RETURNING id",
                    (pid, fname, db_type, i))

        fid = qinsert(conn,
            """INSERT INTO custom_forms(token,project_id,title,org_name,description,
               logo_filename,accent_color,fields,created_by)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (token, pid, title, org_name, desc, logo_filename, accent,
             fields_raw, session.get('user_id')))

        form = qone(conn, "SELECT * FROM custom_forms WHERE id=%s", (fid,))
        logo_url = url_for('serve_upload', filename=form['logo_filename']) if form['logo_filename'] else ''

    return jsonify({
        'success': True,
        'form': {
            'id': form['id'], 'token': form['token'], 'title': form['title'],
            'org_name': form['org_name'], 'logo_url': logo_url,
            'accent_color': form['accent_color'], 'project_id': pid,
            'submission_count': 0,
            'public_url': url_for('public_form', token=token, _external=True)
        }
    })

@app.route('/api/forms/<int:fid>', methods=['PUT'])
@admin_required
def update_form(fid):
    is_multipart = request.content_type and 'multipart' in request.content_type
    if is_multipart:
        title      = request.form.get('title','').strip()
        org_name   = request.form.get('org_name','').strip()
        desc       = request.form.get('description','').strip()
        accent     = request.form.get('accent_color','#00c8ff').strip()
        fields_raw = request.form.get('fields','[]')
        is_active  = request.form.get('is_active','true') == 'true'
    else:
        d = request.get_json() or {}
        title      = d.get('title','').strip()
        org_name   = d.get('org_name','').strip()
        desc       = d.get('description','').strip()
        accent     = d.get('accent_color','#00c8ff')
        fields_raw = json.dumps(d.get('fields',[]))
        is_active  = d.get('is_active', True)

    with get_db() as conn:
        form = qone(conn, "SELECT * FROM custom_forms WHERE id=%s", (fid,))
        if not form: return jsonify({'success': False}), 404

        logo_filename = form['logo_filename']
        if is_multipart and 'logo' in request.files:
            logo = request.files['logo']
            if logo.filename and allowed(logo.filename):
                if logo_filename:
                    try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], logo_filename))
                    except: pass
                orig = secure_filename(logo.filename)
                ext  = orig.rsplit('.',1)[-1] if '.' in orig else 'png'
                stored = f"logo_{uuid.uuid4().hex}.{ext}"
                logo.save(os.path.join(app.config['UPLOAD_FOLDER'], stored))
                logo_filename = stored

        qexec(conn,
            "UPDATE custom_forms SET title=%s,org_name=%s,description=%s,"
            "accent_color=%s,fields=%s,logo_filename=%s,is_active=%s WHERE id=%s",
            (title, org_name, desc, accent, fields_raw, logo_filename, is_active, fid))

        pid = form['project_id']
        if pid:
            try:    fields = json.loads(fields_raw)
            except: fields = []
            qexec(conn, "DELETE FROM crm_columns WHERE project_id=%s", (pid,))
            for i, fld in enumerate(fields):
                fname = fld.get('label','').strip()
                ftype = fld.get('type','text')
                db_type = 'number' if ftype=='number' else 'text'
                if fname:
                    qinsert(conn,
                        "INSERT INTO crm_columns(project_id,name,col_type,col_order) VALUES(%s,%s,%s,%s) RETURNING id",
                        (pid, fname, db_type, i))

    return jsonify({'success': True})

@app.route('/api/forms/<int:fid>', methods=['DELETE'])
@admin_required
def delete_form(fid):
    with get_db() as conn:
        form = qone(conn, "SELECT * FROM custom_forms WHERE id=%s", (fid,))
        if not form: return jsonify({'success': False}), 404
        if form['logo_filename']:
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], form['logo_filename']))
            except: pass
        if form['project_id']:
            recs = qall(conn, "SELECT id FROM crm_records WHERE project_id=%s", (form['project_id'],))
            for rec in recs:
                for a in qall(conn, "SELECT filename FROM attachments WHERE record_id=%s", (rec['id'],)):
                    try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], a['filename']))
                    except: pass
            qexec(conn, "DELETE FROM projects WHERE id=%s", (form['project_id'],))
        qexec(conn, "DELETE FROM custom_forms WHERE id=%s", (fid,))
    return jsonify({'success': True})

@app.route('/api/forms/<int:fid>/toggle', methods=['POST'])
@admin_required
def toggle_form(fid):
    with get_db() as conn:
        form = qone(conn, "SELECT is_active FROM custom_forms WHERE id=%s", (fid,))
        if not form: return jsonify({'success': False}), 404
        new_state = not form['is_active']
        qexec(conn, "UPDATE custom_forms SET is_active=%s WHERE id=%s", (new_state, fid))
    return jsonify({'success': True, 'is_active': new_state})


# ─────────────── PUBLIC FORM ───────────────
@app.route('/form/<token>')
def public_form(token):
    with get_db() as conn:
        form = qone(conn, "SELECT * FROM custom_forms WHERE token=%s", (token,))
    if not form:
        return "<h2>Form not found</h2>", 404
    if not form['is_active']:
        return render_template_string(FORM_INACTIVE_HTML, form=form)

    try:    fields = json.loads(form['fields'] or '[]')
    except: fields = []
    logo_url = url_for('serve_upload', filename=form['logo_filename']) if form['logo_filename'] else ''

    return render_template_string(PUBLIC_FORM_HTML,
        form=form, fields=fields, logo_url=logo_url, token=token)

@app.route('/form/<token>/submit', methods=['POST'])
def submit_form(token):
    with get_db() as conn:
        form = qone(conn, "SELECT * FROM custom_forms WHERE token=%s AND is_active=TRUE", (token,))
        if not form:
            return jsonify({'success': False, 'message': 'Form not found or inactive'}), 404

        try:    fields = json.loads(form['fields'] or '[]')
        except: fields = []

        pid = form['project_id']
        if not pid:
            return jsonify({'success': False, 'message': 'Form has no linked project'}), 500

        col_map = {c['name']: c['id'] for c in
                   qall(conn, "SELECT id,name FROM crm_columns WHERE project_id=%s", (pid,))}

        is_multipart = request.content_type and 'multipart' in request.content_type

        if is_multipart:
            form_data = request.form
        else:
            form_data = request.get_json() or {}

        data = {}
        for fld in fields:
            label = fld.get('label','').strip()
            ftype = fld.get('type','text')
            if label in col_map:
                val = form_data.get(label,'') or form_data.get(str(col_map[label]),'')
                if isinstance(val, str): val = val.strip()
                if val:
                    data[str(col_map[label])] = str(val)

        rid = qinsert(conn,
            "INSERT INTO crm_records(project_id,data,tags,notes) VALUES(%s,%s,%s,%s) RETURNING id",
            (pid, json.dumps(data), 'form-submission', f'Submitted via form: {form["title"]}'))

        if is_multipart:
            for fld in fields:
                label = fld.get('label','').strip()
                ftype = fld.get('type','')
                if ftype == 'image' and label in request.files:
                    img_file = request.files[label]
                    if img_file and img_file.filename and allowed(img_file.filename):
                        orig   = secure_filename(img_file.filename)
                        ext    = orig.rsplit('.',1)[-1] if '.' in orig else 'bin'
                        stored = f"{uuid.uuid4().hex}.{ext}"
                        fp     = os.path.join(app.config['UPLOAD_FOLDER'], stored)
                        img_file.save(fp)
                        qinsert(conn,
                            "INSERT INTO attachments(record_id,filename,original_name,file_type,file_size) VALUES(%s,%s,%s,%s,%s) RETURNING id",
                            (rid, stored, orig, _file_type(orig), os.path.getsize(fp)))

    return jsonify({'success': True, 'message': 'Form submitted successfully!'})


# ─────────────── FORM UPLOAD LOGO (admin) ───────────────
@app.route('/api/forms/upload-logo', methods=['POST'])
@admin_required
def upload_form_logo():
    if 'logo' not in request.files:
        return jsonify({'success': False, 'message': 'No file'}), 400
    logo = request.files['logo']
    if not logo.filename or not allowed(logo.filename):
        return jsonify({'success': False, 'message': 'Invalid file'}), 400
    orig = secure_filename(logo.filename)
    ext  = orig.rsplit('.',1)[-1] if '.' in orig else 'png'
    stored = f"logo_{uuid.uuid4().hex}.{ext}"
    logo.save(os.path.join(app.config['UPLOAD_FOLDER'], stored))
    return jsonify({'success': True, 'filename': stored,
                    'url': url_for('serve_upload', filename=stored)})


# ─────────────── INACTIVE FORM HTML ───────────────
FORM_INACTIVE_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"/><title>Form Inactive</title>
<style>body{font-family:sans-serif;background:#080c14;color:#ddeeff;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.box{text-align:center;padding:40px;border:1px solid #1a3050;border-radius:14px;
background:#0f1620}h2{color:#ff9500;margin-bottom:8px}p{color:#7aaed0}</style>
</head><body><div class="box">
<h2>⏸ Form Inactive</h2>
<p>Yeh form abhi available nahi hai.</p>
</div></body></html>"""


# ─────────────── LOGIN HTML ───────────────
LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>CRM — Login</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=IBM+Plex+Mono:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;font-family:'IBM Plex Mono',monospace;
  background:#080c14;color:#ddeeff;font-size:13px;
  display:flex;align-items:center;justify-content:center}
.card{background:#0f1620;border:1px solid #1a3050;border-radius:14px;
  width:100%;max-width:370px;padding:32px;box-shadow:0 20px 60px rgba(0,0,0,.7)}
.logo{text-align:center;margin-bottom:24px}
.logo h1{font-family:'Syne',sans-serif;font-size:22px;font-weight:800;
  color:#00c8ff;letter-spacing:3px}
.logo p{font-size:9px;color:#3a6080;letter-spacing:1px;margin-top:4px;text-transform:uppercase}
.fg{display:flex;flex-direction:column;gap:5px;margin-bottom:14px}
.fg label{font-size:10px;color:#3a6080;letter-spacing:.4px;text-transform:uppercase}
.fg input{background:#141e2e;border:1px solid #1a3050;border-radius:8px;
  color:#ddeeff;font-family:inherit;font-size:13px;padding:9px 12px;
  outline:none;transition:.15s;width:100%}
.fg input:focus{border-color:#00c8ff;box-shadow:0 0 0 2px rgba(0,200,255,.1)}
.btn{width:100%;padding:10px;border-radius:8px;border:none;cursor:pointer;
  font-family:inherit;font-size:13px;font-weight:700;background:#00c8ff;
  color:#000;transition:.15s;margin-top:4px}
.btn:hover{background:#0090bb}
.err{background:#200a10;border:1px solid #ff3d5a;color:#ff3d5a;
  border-radius:8px;padding:9px 12px;font-size:11px;margin-bottom:12px;
  display:flex;align-items:center;gap:6px}
.foot{text-align:center;margin-top:16px;font-size:10px;color:#3a6080}
</style>
</head>
<body>
<div class="card">
  <div class="logo">
    <h1>◈ CRM</h1>
    <p>MULTI-FILE TRACKER — Login</p>
  </div>
  {% if error %}
  <div class="err">⚠ {{ error }}</div>
  {% endif %}
  <form method="POST" action="/login">
    <div class="fg">
      <label>Username</label>
      <input type="text" name="username" placeholder="Enter username" required autofocus/>
    </div>
    <div class="fg">
      <label>Password</label>
      <input type="password" name="password" placeholder="Enter password" required/>
    </div>
    <button type="submit" class="btn">🔐 Login</button>
  </form>
  <div class="foot">Default: admin / admin123</div>
</div>
</body>
</html>"""


# ─────────────── PUBLIC FORM HTML ───────────────
PUBLIC_FORM_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{{ form.title }}{% if form.org_name %} — {{ form.org_name }}{% endif %}</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=IBM+Plex+Mono:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
:root{--acc:{{ form.accent_color }};--acc2:color-mix(in srgb,{{ form.accent_color }} 70%,black)}
*{margin:0;padding:0;box-sizing:border-box}
html,body{min-height:100%;font-family:'IBM Plex Mono',monospace;background:#080c14;color:#ddeeff;font-size:14px}
.page{max-width:640px;margin:0 auto;padding:24px 16px 60px}
.card{background:#0f1620;border:1px solid #1a3050;border-radius:16px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.7)}
.card-head{padding:28px 28px 22px;border-bottom:1px solid #1a3050;position:relative}
.card-head::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--acc)}
.logo-row{display:flex;align-items:center;gap:14px;margin-bottom:14px}
.logo-img{width:56px;height:56px;border-radius:10px;object-fit:contain;background:#141e2e;border:1px solid #1a3050;padding:4px}
.org-nm{font-family:'Syne',sans-serif;font-size:13px;font-weight:700;color:var(--acc);letter-spacing:2px;text-transform:uppercase}
.form-title{font-family:'Syne',sans-serif;font-size:22px;font-weight:800;color:#ddeeff;margin-top:4px}
.form-desc{font-size:12px;color:#7aaed0;margin-top:6px;line-height:1.6}
.card-body{padding:24px 28px}
.fg{display:flex;flex-direction:column;gap:5px;margin-bottom:16px}
.fg label{font-size:10px;color:#7aaed0;letter-spacing:.6px;text-transform:uppercase;font-weight:600}
.req{color:var(--acc)}
input[type=text],input[type=number],input[type=email],input[type=date],
input[type=url],input[type=tel],select,textarea{
  background:#141e2e;border:1px solid #1a3050;border-radius:9px;color:#ddeeff;
  font-family:inherit;font-size:13px;padding:10px 13px;outline:none;
  transition:.15s;width:100%}
input:focus,select:focus,textarea:focus{
  border-color:var(--acc);box-shadow:0 0 0 3px color-mix(in srgb,var(--acc) 15%,transparent)}
textarea{resize:vertical;min-height:72px}
select option{background:#141e2e}
.img-upload{border:2px dashed #1a3050;border-radius:9px;padding:18px;text-align:center;
  cursor:pointer;transition:.2s;position:relative}
.img-upload:hover{border-color:var(--acc);background:color-mix(in srgb,var(--acc) 5%,transparent)}
.img-upload input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
.img-prev{max-width:100%;max-height:140px;border-radius:7px;margin-top:8px;display:none}
.submit-btn{width:100%;padding:13px;border-radius:10px;border:none;cursor:pointer;
  font-family:inherit;font-size:14px;font-weight:700;background:var(--acc);
  color:#000;transition:.2s;margin-top:6px;letter-spacing:.5px}
.submit-btn:hover{background:var(--acc2);transform:translateY(-1px)}
.submit-btn:active{transform:translateY(0)}
.submit-btn:disabled{opacity:.5;cursor:not-allowed;transform:none}
.success-box{display:none;text-align:center;padding:36px 20px}
.success-box h2{font-family:'Syne',sans-serif;font-size:24px;color:var(--acc);margin-bottom:8px}
.success-box p{color:#7aaed0;font-size:13px;margin-bottom:20px}
.more-btn{padding:10px 22px;border-radius:9px;border:1px solid var(--acc);color:var(--acc);
  background:none;cursor:pointer;font-family:inherit;font-size:13px;font-weight:600;transition:.15s}
.more-btn:hover{background:color-mix(in srgb,var(--acc) 10%,transparent)}
.err-box{background:#200a10;border:1px solid #ff3d5a;color:#ff3d5a;border-radius:9px;
  padding:10px 14px;font-size:12px;margin-bottom:14px;display:none}
.foot{text-align:center;margin-top:18px;font-size:10px;color:#3a6080}
.spin{display:inline-block;width:12px;height:12px;border:2px solid rgba(0,0,0,.3);
      border-top-color:#000;border-radius:50%;animation:rot .5s linear infinite;vertical-align:middle}
@keyframes rot{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<div class="page">
  <div class="card">
    <div class="card-head">
      <div class="logo-row">
        {% if logo_url %}
        <img class="logo-img" src="{{ logo_url }}" alt="Logo"/>
        {% endif %}
        <div>
          {% if form.org_name %}<div class="org-nm">{{ form.org_name }}</div>{% endif %}
          <div class="form-title">{{ form.title }}</div>
        </div>
      </div>
      {% if form.description %}
      <div class="form-desc">{{ form.description }}</div>
      {% endif %}
    </div>
    <div class="card-body">
      <div class="err-box" id="errBox"></div>
      <div id="formContent">
        {% for fld in fields %}
        <div class="fg">
          <label>{{ fld.label }}{% if fld.required %} <span class="req">*</span>{% endif %}</label>
          {% if fld.type == 'textarea' %}
            <textarea name="{{ fld.label }}" id="fld_{{ loop.index }}"
              placeholder="{{ fld.placeholder or fld.label + ' daalo…' }}"
              {% if fld.required %}required{% endif %} rows="3"></textarea>
          {% elif fld.type == 'select' %}
            <select name="{{ fld.label }}" id="fld_{{ loop.index }}" {% if fld.required %}required{% endif %}>
              <option value="">— Choose —</option>
              {% for opt in (fld.options or '').split(',') %}
              {% if opt.strip() %}<option value="{{ opt.strip() }}">{{ opt.strip() }}</option>{% endif %}
              {% endfor %}
            </select>
          {% elif fld.type == 'image' %}
            <div class="img-upload" onclick="document.getElementById('fld_{{ loop.index }}').click()">
              <input type="file" accept="image/*" name="{{ fld.label }}" id="fld_{{ loop.index }}"
                onchange="previewImg(this,'prev_{{ loop.index }}')"
                {% if fld.required %}required{% endif %}/>
              <div>📷 <strong style="color:var(--acc)">Click to upload image</strong></div>
              <div style="font-size:10px;color:#3a6080;margin-top:3px">JPG · PNG · WEBP</div>
              <img class="img-prev" id="prev_{{ loop.index }}"/>
            </div>
          {% else %}
            <input type="{{ fld.type }}" name="{{ fld.label }}" id="fld_{{ loop.index }}"
              placeholder="{{ fld.placeholder or fld.label + ' daalo…' }}"
              {% if fld.required %}required{% endif %}/>
          {% endif %}
        </div>
        {% endfor %}
        {% if not fields %}
        <p style="color:#3a6080;text-align:center;padding:20px">Koi field nahi.</p>
        {% endif %}
        <button class="submit-btn" id="submitBtn" onclick="submitForm()">
          ✅ Submit Form
        </button>
      </div>
      <div class="success-box" id="successBox">
        <div style="font-size:56px;margin-bottom:12px">✅</div>
        <h2>Submitted!</h2>
        <p>You have successfully submitted your form .<br/>Thank you !</p>
        <button class="more-btn" onclick="resetForm()">➕ submit again </button>
      </div>
    </div>
  </div>
  <div class="foot">Powered by CRM Dashboard</div>
</div>
<script>
const TOKEN = '{{ token }}';
const FIELDS = {{ fields|tojson }};

function previewImg(inp, prevId) {
  const prev = document.getElementById(prevId);
  if(inp.files && inp.files[0]) {
    const reader = new FileReader();
    reader.onload = e => { prev.src = e.target.result; prev.style.display='block'; };
    reader.readAsDataURL(inp.files[0]);
  }
}

async function submitForm() {
  const btn = document.getElementById('submitBtn');
  const errBox = document.getElementById('errBox');
  errBox.style.display = 'none';

  let valid = true;
  for(const fld of FIELDS) {
    if(!fld.required) continue;
    const el = document.querySelector(`[name="${fld.label}"]`);
    if(!el) continue;
    if(fld.type === 'image') {
      if(!el.files || !el.files.length) { valid=false; errBox.textContent=`"${fld.label}" required hai`; errBox.style.display='block'; break; }
    } else {
      if(!el.value.trim()) { valid=false; errBox.textContent=`"${fld.label}" required hai`; errBox.style.display='block'; break; }
    }
  }
  if(!valid) return;

  btn.disabled = true;
  btn.innerHTML = '<span class="spin"></span> Submitting…';

  const hasImage = FIELDS.some(f => f.type === 'image');
  let body, headers = {};

  if(hasImage) {
    const fd = new FormData();
    for(const fld of FIELDS) {
      const el = document.querySelector(`[name="${fld.label}"]`);
      if(!el) continue;
      if(fld.type === 'image') {
        if(el.files && el.files[0]) fd.append(fld.label, el.files[0]);
      } else {
        fd.append(fld.label, el.value || '');
      }
    }
    body = fd;
  } else {
    const data = {};
    for(const fld of FIELDS) {
      const el = document.querySelector(`[name="${fld.label}"]`);
      if(el) data[fld.label] = el.value || '';
    }
    body = JSON.stringify(data);
    headers['Content-Type'] = 'application/json';
  }

  try {
    const r = await fetch(`/form/${TOKEN}/submit`, {method:'POST', headers, body}).then(r=>r.json());
    if(r.success) {
      document.getElementById('formContent').style.display = 'none';
      document.getElementById('successBox').style.display  = 'block';
    } else {
      errBox.textContent = r.message || 'Error occur. Try again.';
      errBox.style.display = 'block';
      btn.disabled = false;
      btn.innerHTML = '✅ Submit Form';
    }
  } catch(e) {
    errBox.textContent = 'Network error. Try again.';
    errBox.style.display = 'block';
    btn.disabled = false;
    btn.innerHTML = '✅ Submit Form';
  }
}

function resetForm() {
  document.getElementById('formContent').style.display = '';
  document.getElementById('successBox').style.display  = 'none';
  document.getElementById('submitBtn').disabled = false;
  document.getElementById('submitBtn').innerHTML = '✅ Submit Form';
  document.querySelectorAll('input:not([type=file]),textarea,select').forEach(e=>e.value='');
  document.querySelectorAll('input[type=file]').forEach(e=>e.value='');
  document.querySelectorAll('.img-prev').forEach(e=>{e.src='';e.style.display='none';});
}
</script>
</body>
</html>"""


# ─────────────── MAIN HTML ───────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>CRM Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=IBM+Plex+Mono:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
:root{
  --bg:#080c14;--s1:#0f1620;--s2:#141e2e;--s3:#192438;
  --b1:#1a3050;--b2:#1e3d66;
  --acc:#00c8ff;--acc2:#0090bb;--acc3:rgba(0,200,255,.1);
  --ok:#00e07a;--err:#ff3d5a;
  --t1:#ddeeff;--t2:#7aaed0;--t3:#3a6080;
  --fc:#00c8ff;
  --r:10px;--sh:0 12px 40px rgba(0,0,0,.6);
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;font-family:'IBM Plex Mono',monospace;background:var(--bg);color:var(--t1);font-size:13px}
.app{display:flex;height:100vh;overflow:hidden}

/* ── SIDEBAR ── */
.side{width:248px;min-width:248px;background:var(--s1);border-right:1px solid var(--b1);
      display:flex;flex-direction:column;overflow:hidden}
.logo{padding:15px 17px;border-bottom:1px solid var(--b1);flex-shrink:0}
.logo h1{font-family:'Syne',sans-serif;font-size:17px;font-weight:800;color:var(--acc);letter-spacing:2px}
.logo p{font-size:9px;color:var(--t3);letter-spacing:1px;margin-top:2px}

.files-hd{padding:10px 14px 6px;display:flex;align-items:center;
          justify-content:space-between;flex-shrink:0}
.files-hd span{font-size:9px;letter-spacing:1px;text-transform:uppercase;color:var(--t3)}
.new-file-btn{display:inline-flex;align-items:center;gap:3px;padding:4px 9px;
  border-radius:6px;background:var(--acc);color:#000;border:none;cursor:pointer;
  font-size:10px;font-weight:700;font-family:inherit;transition:.15s}
.new-file-btn:hover{background:var(--acc2)}

.file-list{flex:1;overflow-y:auto;padding:3px 7px}
.fi{display:flex;align-items:center;gap:7px;padding:8px 9px;border-radius:8px;
    cursor:pointer;transition:.15s;border:1px solid transparent;margin-bottom:2px;position:relative}
.fi:hover{background:var(--s2);border-color:var(--b1)}
.fi.on{background:rgba(0,200,255,.06);border-color:var(--fc)}
.fi-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.fi-name{flex:1;font-size:11px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fi.on .fi-name{color:var(--fc)}
.fi-cnt{font-size:9px;color:var(--t3);flex-shrink:0;background:var(--s2);
        padding:1px 5px;border-radius:4px}
.fi-del{opacity:0;background:none;border:none;color:var(--err);cursor:pointer;
        font-size:12px;padding:0 2px;transition:.15s;flex-shrink:0}
.fi:hover .fi-del{opacity:1}

.nav-btns{padding:8px 7px;border-top:1px solid var(--b1);display:flex;flex-direction:column;
          gap:2px;flex-shrink:0}
.ni{display:flex;align-items:center;gap:8px;padding:8px 9px;color:var(--t2);cursor:pointer;
    border-radius:8px;font-size:11px;transition:.15s;user-select:none;border:1px solid transparent}
.ni:hover,.ni.on{color:var(--fc);background:rgba(0,200,255,.06);border-color:rgba(0,200,255,.15)}
.ni svg{width:13px;height:13px;flex-shrink:0}

.user-bar{padding:8px 10px;border-top:1px solid var(--b1);display:flex;
          align-items:center;gap:7px;flex-shrink:0;background:var(--s2)}
.user-av{width:26px;height:26px;border-radius:50%;background:var(--acc);color:#000;
         font-size:10px;font-weight:800;display:flex;align-items:center;justify-content:center;
         flex-shrink:0;text-transform:uppercase}
.user-inf{flex:1;min-width:0}
.user-nm{font-size:11px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.user-role{font-size:9px;color:var(--t3)}
.user-acts{display:flex;gap:4px;flex-shrink:0}
.icon-btn{background:none;border:1px solid var(--b1);border-radius:6px;color:var(--t3);
          cursor:pointer;font-size:12px;padding:3px 6px;transition:.15s}
.icon-btn:hover{border-color:var(--acc);color:var(--acc)}
.side-foot{padding:6px 16px;font-size:9px;color:var(--t3)}

/* ── MAIN ── */
.content{flex:1;display:flex;flex-direction:column;min-width:0;overflow:hidden}
.view{display:none;flex:1;flex-direction:column;overflow:hidden;min-height:0}
.view.on{display:flex}
.no-file{flex:1;display:flex;flex-direction:column;align-items:center;
         justify-content:center;gap:14px;color:var(--t3)}
.no-file h2{font-family:'Syne',sans-serif;font-size:17px;color:var(--t2)}
.no-file p{font-size:12px}

.topbar{padding:11px 18px;border-bottom:1px solid var(--b1);display:flex;align-items:center;
        justify-content:space-between;flex-wrap:wrap;gap:8px;background:var(--s1);flex-shrink:0}
.topbar h2{font-family:'Syne',sans-serif;font-size:17px;font-weight:800}
.topbar h2 span{color:var(--fc)}
.topbar-r{display:flex;gap:6px;flex-wrap:wrap;align-items:center}

.stats{display:flex;gap:8px;padding:9px 18px;border-bottom:1px solid var(--b1);
       flex-wrap:wrap;background:var(--s2);flex-shrink:0}
.sc{background:var(--s1);border:1px solid var(--b1);border-radius:var(--r);
    padding:8px 13px;flex:1;min-width:100px;position:relative;overflow:hidden}
.sc::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;
           background:linear-gradient(90deg,var(--fc),transparent)}
.sc-l{font-size:9px;color:var(--t3);letter-spacing:1px;text-transform:uppercase;margin-bottom:2px}
.sc-v{font-family:'Syne',sans-serif;font-size:21px;font-weight:800;color:var(--fc)}

.toolbar{padding:7px 18px;display:flex;align-items:center;gap:7px;flex-wrap:wrap;
         border-bottom:1px solid var(--b1);background:var(--s2);flex-shrink:0}
.srch{display:flex;align-items:center;gap:5px;background:var(--s1);border:1px solid var(--b1);
      border-radius:8px;padding:6px 10px;flex:1;max-width:300px}
.srch input{background:none;border:none;color:var(--t1);font-family:inherit;
            font-size:12px;outline:none;width:100%}
.srch input::placeholder{color:var(--t3)}
.rec-info{font-size:11px;color:var(--t3)}

.table-area{flex:1;overflow:auto;min-height:0}
table{width:100%;border-collapse:collapse;min-width:900px}
thead{position:sticky;top:0;z-index:20}
th{background:var(--s2);padding:8px 10px;text-align:left;font-size:9px;letter-spacing:1px;
   text-transform:uppercase;color:var(--t3);font-weight:500;border-bottom:2px solid var(--b1);
   white-space:nowrap}
.th-w{display:flex;align-items:center;gap:4px}
.dc{opacity:0;cursor:pointer;color:var(--err);font-size:12px;transition:.15s}
th:hover .dc{opacity:1}
td{padding:7px 10px;border-bottom:1px solid rgba(26,48,80,.4);color:var(--t1);
   vertical-align:middle;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
tr:hover td{background:rgba(0,200,255,.025)}
.td-n{color:var(--t3);font-size:10px;width:30px;text-align:right}
.td-act{white-space:nowrap;width:1%}

.att-btn{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:5px;
         font-size:10px;font-weight:600;cursor:pointer;border:1px solid var(--b2);
         background:var(--s3);color:var(--t2);transition:.15s;user-select:none}
.att-btn:hover{border-color:var(--acc);color:var(--acc);background:var(--acc3)}
.att-btn.has{background:rgba(0,224,122,.08);border-color:rgba(0,224,122,.4);color:var(--ok)}

.btn{display:inline-flex;align-items:center;gap:4px;padding:6px 11px;border-radius:8px;
     border:none;cursor:pointer;font-family:inherit;font-size:11px;font-weight:600;
     transition:.15s;white-space:nowrap}
.btn-acc{background:var(--acc);color:#000}.btn-acc:hover{background:var(--acc2)}
.btn-g{background:var(--s2);color:var(--t1);border:1px solid var(--b1)}
.btn-g:hover{border-color:var(--acc);color:var(--acc)}
.btn-err{background:rgba(255,61,90,.1);color:var(--err);border:1px solid rgba(255,61,90,.25)}
.btn-ok{background:rgba(0,224,122,.1);color:var(--ok);border:1px solid rgba(0,224,122,.25)}
.btn-warn{background:rgba(255,149,0,.1);color:#ff9500;border:1px solid rgba(255,149,0,.25)}
.btn-sm{padding:4px 8px;font-size:10px}
.btn-ico{padding:4px 6px}

.ovl{position:fixed;inset:0;background:rgba(0,0,0,.78);z-index:500;display:none;
     align-items:center;justify-content:center;padding:12px;backdrop-filter:blur(3px)}
.ovl.on{display:flex}
.modal{background:var(--s1);border:1px solid var(--b2);border-radius:14px;width:100%;
       max-width:620px;max-height:92vh;overflow-y:auto;box-shadow:var(--sh)}
.modal-w{max-width:860px}
.modal-xl{max-width:700px}
.mh{padding:13px 17px;border-bottom:1px solid var(--b1);display:flex;
    align-items:center;justify-content:space-between}
.mh h3{font-family:'Syne',sans-serif;font-size:15px;font-weight:700}
.mb{padding:17px}
.mf{padding:10px 17px;border-top:1px solid var(--b1);display:flex;
    justify-content:flex-end;gap:7px}
.xb{background:none;border:none;color:var(--t3);cursor:pointer;font-size:16px;padding:2px 5px}
.xb:hover{color:var(--t1)}

.fg{display:flex;flex-direction:column;gap:4px;margin-bottom:10px}
.fg label{font-size:10px;color:var(--t3);letter-spacing:.4px;text-transform:uppercase}
input[type=text],input[type=number],input[type=email],input[type=date],
input[type=url],input[type=password],select,textarea{
  background:var(--s2);border:1px solid var(--b1);border-radius:8px;color:var(--t1);
  font-family:inherit;font-size:12px;padding:7px 10px;outline:none;transition:.15s;width:100%}
input:focus,select:focus,textarea:focus{
  border-color:var(--acc);box-shadow:0 0 0 2px rgba(0,200,255,.1)}
textarea{resize:vertical;min-height:58px}
select option{background:var(--s2)}
.fgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.full{grid-column:1/-1}

.color-opts{display:flex;gap:7px;flex-wrap:wrap;margin-top:5px}
.co{width:22px;height:22px;border-radius:50%;cursor:pointer;
    border:2px solid transparent;transition:.15s}
.co.on{border-color:#fff;transform:scale(1.2)}
.co:hover{transform:scale(1.1)}

.rtab-bar{display:flex;border-bottom:1px solid var(--b1);background:var(--s2);padding:0 17px}
.rtab{padding:9px 15px;font-size:11px;font-weight:600;cursor:pointer;color:var(--t3);
      border-bottom:2px solid transparent;transition:.15s;user-select:none}
.rtab:hover{color:var(--t2)}
.rtab.on{color:var(--acc);border-bottom-color:var(--acc)}

.att-dz{border:2px dashed var(--b2);border-radius:var(--r);padding:20px;text-align:center;
        cursor:pointer;transition:.2s;position:relative;margin-bottom:11px}
.att-dz:hover{border-color:var(--acc);background:var(--acc3)}
.att-dz input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
.att-list{display:flex;flex-direction:column;gap:6px;max-height:290px;overflow-y:auto}
.att-item{display:flex;align-items:center;gap:8px;background:var(--s2);
          border:1px solid var(--b1);border-radius:8px;padding:8px 10px}
.att-thumb{width:34px;height:34px;border-radius:5px;object-fit:cover;flex-shrink:0}
.att-ico{font-size:20px;width:34px;text-align:center;flex-shrink:0}
.att-inf{flex:1;min-width:0}
.att-nm{font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.att-mt{font-size:9px;color:var(--t3);margin-top:2px}
.att-ac{display:flex;gap:4px;flex-shrink:0}
.upl-ov{position:absolute;inset:0;background:rgba(8,12,20,.88);display:flex;
        align-items:center;justify-content:center;border-radius:inherit;
        z-index:20;gap:7px;font-size:12px;color:var(--acc)}

.utbl{width:100%;border-collapse:collapse}
.utbl th{background:var(--s3);padding:8px 11px;text-align:left;font-size:9px;
         letter-spacing:1px;text-transform:uppercase;color:var(--t3)}
.utbl td{padding:8px 11px;border-bottom:1px solid var(--b1);font-size:11px}
.badge{display:inline-block;padding:2px 7px;border-radius:4px;font-size:9px;font-weight:700}
.badge-admin{background:rgba(0,200,255,.15);color:var(--acc)}
.badge-user{background:rgba(122,174,208,.1);color:var(--t2)}
.badge-active{background:rgba(0,224,122,.12);color:var(--ok)}
.badge-off{background:rgba(255,61,90,.1);color:var(--err)}

.imp-box{background:var(--s2);border:1px solid var(--b1);border-radius:var(--r);
         padding:18px;max-width:500px}
.step{display:flex;gap:9px;margin-bottom:11px}
.sn{width:20px;height:20px;border-radius:50%;background:var(--acc);color:#000;
    font-size:9px;font-weight:800;display:flex;align-items:center;justify-content:center;
    flex-shrink:0;margin-top:2px}
.st h4{font-size:12px;font-weight:600;margin-bottom:1px}
.st p{font-size:11px;color:var(--t3)}
.dz{border:2px dashed var(--b2);border-radius:var(--r);padding:26px;text-align:center;
    cursor:pointer;transition:.2s;position:relative;margin-top:12px}
.dz:hover,.dz.drag{border-color:var(--acc);background:var(--acc3)}
.dz input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}

.col-list{display:flex;flex-direction:column;gap:6px}
.col-row{display:flex;align-items:center;justify-content:space-between;
         background:var(--s2);border:1px solid var(--b1);border-radius:8px;padding:8px 11px}
.ct-badge{font-size:9px;padding:2px 6px;border-radius:4px;
          background:rgba(0,200,255,.1);color:var(--acc)}

/* Form Builder Specific */
.fb-fields{display:flex;flex-direction:column;gap:6px;min-height:40px}
.fb-field{display:flex;align-items:center;gap:7px;background:var(--s2);
          border:1px solid var(--b1);border-radius:8px;padding:9px 11px;
          cursor:grab;transition:.15s}
.fb-field:hover{border-color:var(--b2)}
.fb-drag{color:var(--t3);font-size:14px;cursor:grab;flex-shrink:0;user-select:none}
.fb-label{flex:1;font-size:12px;font-weight:600}
.fb-type{font-size:9px;padding:2px 6px;border-radius:4px;background:rgba(0,200,255,.1);color:var(--acc);flex-shrink:0}
.fb-req{font-size:9px;padding:2px 5px;border-radius:4px;background:rgba(255,149,0,.1);color:#ff9500;flex-shrink:0}
.fb-acts{display:flex;gap:4px;flex-shrink:0}
.form-card{background:var(--s2);border:1px solid var(--b1);border-radius:var(--r);
           padding:14px;margin-bottom:10px;position:relative;overflow:hidden}
.form-card::before{content:'';position:absolute;top:0;left:0;bottom:0;width:3px;
                   background:var(--form-color,var(--acc))}
.form-card-head{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.form-logo{width:32px;height:32px;border-radius:6px;object-fit:contain;
           background:var(--s1);border:1px solid var(--b1);flex-shrink:0}
.form-logo-ph{width:32px;height:32px;border-radius:6px;background:var(--s1);
              border:1px solid var(--b1);display:flex;align-items:center;
              justify-content:center;font-size:16px;flex-shrink:0}
.form-info{flex:1;min-width:0}
.form-title{font-weight:700;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.form-org{font-size:10px;color:var(--t3);margin-top:1px}
.form-meta{font-size:10px;color:var(--t3);display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.form-actions{display:flex;gap:5px;flex-wrap:wrap}
.link-box{background:var(--s1);border:1px solid var(--b2);border-radius:7px;
          padding:7px 10px;font-size:10px;color:var(--acc);font-family:monospace;
          display:flex;align-items:center;gap:7px;margin-top:6px;overflow:hidden}
.link-txt{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.logo-upload-area{border:2px dashed var(--b2);border-radius:9px;padding:16px;
  text-align:center;cursor:pointer;transition:.2s;position:relative}
.logo-upload-area:hover{border-color:var(--acc);background:var(--acc3)}
.logo-upload-area input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
.logo-preview{max-height:70px;max-width:200px;border-radius:7px;margin-top:8px}

/* Dropdown options builder */
.opt-item{display:flex;align-items:center;gap:6px;background:var(--s1);
          border:1px solid var(--b1);border-radius:6px;padding:6px 9px}
.opt-num{font-size:10px;color:var(--t3);min-width:16px}
.opt-txt{flex:1;font-size:12px}

.tc{position:fixed;bottom:15px;right:15px;z-index:999;display:flex;
    flex-direction:column;gap:4px;pointer-events:none}
.toast{padding:8px 13px;border-radius:8px;font-size:11px;min-width:185px;box-shadow:var(--sh);
       display:flex;align-items:center;gap:5px;animation:tin .2s ease;pointer-events:all}
.t-ok{background:#0a2018;border:1px solid var(--ok);color:var(--ok)}
.t-err{background:#200a10;border:1px solid var(--err);color:var(--err)}
.t-info{background:#0a1828;border:1px solid var(--acc);color:var(--acc)}
@keyframes tin{from{transform:translateX(110%);opacity:0}to{transform:translateX(0);opacity:1}}
.empty{text-align:center;padding:42px 20px;color:var(--t3)}
.empty h3{font-family:'Syne',sans-serif;font-size:14px;color:var(--t2);margin-bottom:4px}
.spin{display:inline-block;width:11px;height:11px;border:2px solid var(--b2);
      border-top-color:var(--acc);border-radius:50%;animation:rot .5s linear infinite}
@keyframes rot{to{transform:rotate(360deg)}}
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:var(--s1)}
::-webkit-scrollbar-thumb{background:var(--b2);border-radius:2px}
@media(max-width:680px){.side{display:none}.fgrid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="app">

<!-- ══════ SIDEBAR ══════ -->
<aside class="side">
  <div class="logo">
    <h1>◈ CRM</h1>
    <p>MULTI-FILE TRACKER</p>
  </div>
  <div class="files-hd">
    <span>📁 Files</span>
    <button class="new-file-btn" onclick="openCreateFile()">＋ New File</button>
  </div>
  <div class="file-list" id="fileList"></div>
  <div class="nav-btns">
    <div class="ni" id="nav-columns" onclick="gotoSection('columns')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
      </svg>Manage Columns
    </div>
    <div class="ni" id="nav-import" onclick="gotoSection('import')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
        <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
      </svg>Import Excel
    </div>
    <div class="ni" onclick="doExport()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
        <polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
      </svg>Export Excel
    </div>
    <div class="ni" id="nav-forms" onclick="gotoSection('forms')" style="display:none">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="3" width="18" height="18" rx="2"/>
        <line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/>
      </svg>Form Builder
    </div>
    <div class="ni" id="nav-users" onclick="gotoSection('users')" style="display:none">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/>
        <circle cx="9" cy="7" r="4"/>
        <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/>
      </svg>Manage Users
    </div>
  </div>
  <div class="user-bar">
    <div class="user-av" id="userAv">?</div>
    <div class="user-inf">
      <div class="user-nm" id="userNm">…</div>
      <div class="user-role" id="userRole">…</div>
    </div>
    <div class="user-acts">
      <button class="icon-btn" onclick="openChangePw()" title="Change Password">🔑</button>
      <button class="icon-btn" onclick="doLogout()" title="Logout">⏻</button>
    </div>
  </div>
  <div class="side-foot">PostgreSQL · Flask · Python</div>
</aside>

<!-- ══════ MAIN ══════ -->
<div class="content">

  <!-- No file -->
  <div class="view on" id="view-nofile">
    <div class="no-file">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="1.2" style="color:var(--t3)">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
      </svg>
      <h2>Koi file select nahi</h2>
      <p>Sidebar se file choose karo ya naya file banao</p>
      <button class="btn btn-acc" onclick="openCreateFile()">＋ New File Banao</button>
    </div>
  </div>

  <!-- Records -->
  <div class="view" id="view-records">
    <div class="topbar">
      <h2>📄 <span id="fileTitleSpan">—</span></h2>
      <div class="topbar-r">
        <button class="btn btn-g btn-sm" onclick="gotoSection('import')">📥 Import</button>
        <button class="btn btn-acc" onclick="openAddRec()">＋ Add Record</button>
      </div>
    </div>
    <div class="stats">
      <div class="sc"><div class="sc-l">Records</div><div class="sc-v" id="sRec">—</div></div>
      <div class="sc"><div class="sc-l">Columns</div><div class="sc-v" id="sCols">—</div></div>
      <div class="sc"><div class="sc-l">Attachments</div><div class="sc-v" id="sAtts">—</div></div>
      <div class="sc"><div class="sc-l">Today</div><div class="sc-v" id="sToday">—</div></div>
    </div>
    <div class="toolbar">
      <div class="srch">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input type="text" id="srchInput" placeholder="Search all fields…" oninput="onSearch()"/>
      </div>
      <button class="btn btn-g btn-sm" onclick="loadRecs()">↺</button>
      <span class="rec-info" id="recInfo"></span>
    </div>
    <div class="table-area">
      <table><thead id="tHead"></thead><tbody id="tBody"></tbody></table>
    </div>
  </div>

  <!-- Columns -->
  <div class="view" id="view-columns">
    <div class="topbar">
      <h2>Manage <span>Columns</span></h2>
      <button class="btn btn-acc" onclick="openAddCol()">＋ Add Column</button>
    </div>
    <div style="padding:15px;overflow-y:auto;flex:1">
      <div class="col-list" id="colList"></div>
    </div>
  </div>

  <!-- Import -->
  <div class="view" id="view-import">
    <div class="topbar"><h2>Import <span>Excel</span></h2></div>
    <div style="padding:16px;overflow-y:auto;flex:1">
      <div class="imp-box">
        <div class="step"><div class="sn">1</div>
          <div class="st"><h4>Active File</h4>
            <p id="impFileLbl" style="color:var(--acc);font-weight:600">—</p></div></div>
        <div class="step"><div class="sn">2</div>
          <div class="st"><h4>Excel upload karo</h4>
            <p>Row 1 = Column headings · Unnamed columns skip</p></div></div>
        <div class="step"><div class="sn">3</div>
          <div class="st"><h4>Done!</h4><p>Sirf is file ke records mein import hoga.</p></div></div>
        <div class="dz" id="dz">
          <input type="file" accept=".xlsx,.xls" id="xlsInp" onchange="doImport(this)"/>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="1.5" style="color:var(--acc)">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          <p style="margin-top:7px;font-size:12px"><strong style="color:var(--acc)">Click or drag</strong></p>
          <p style="font-size:10px;color:var(--t3);margin-top:3px">.xlsx / .xls · max 100 MB</p>
        </div>
        <div id="impRes" style="margin-top:10px"></div>
      </div>
    </div>
  </div>

  <!-- Form Builder (admin only) -->
  <div class="view" id="view-forms">
    <div class="topbar">
      <h2>🧩 Form <span>Builder</span></h2>
      <button class="btn btn-acc" onclick="openCreateForm()">＋ New Form</button>
    </div>
    <div style="padding:16px;overflow-y:auto;flex:1" id="formsContainer">
      <div class="empty"><h3>Loading…</h3></div>
    </div>
  </div>

  <!-- Users (admin only) -->
  <div class="view" id="view-users">
    <div class="topbar">
      <h2>👥 Manage <span>Users</span></h2>
      <button class="btn btn-acc" onclick="openAddUser()">＋ Add User</button>
    </div>
    <div style="padding:16px;overflow-y:auto;flex:1">
      <table class="utbl" id="usersTable">
        <thead><tr>
          <th>#</th><th>Username</th><th>Role</th><th>Created</th>
          <th style="text-align:right">Actions</th>
        </tr></thead>
        <tbody id="usersTbody"></tbody>
      </table>
    </div>
  </div>

</div><!-- /content -->
</div><!-- /app -->

<!-- ════════ MODALS ════════ -->

<!-- Create File -->
<div class="ovl" id="mFile">
  <div class="modal" style="max-width:370px">
    <div class="mh"><h3>📁 New File Banao</h3><button class="xb" onclick="closeM('mFile')">✕</button></div>
    <div class="mb">
      <div class="fg"><label>File Name *</label>
        <input type="text" id="fileNm" placeholder="e.g. Sales Orders…"/></div>
      <div class="fg"><label>Color</label>
        <div class="color-opts" id="colorOpts"></div></div>
    </div>
    <div class="mf">
      <button class="btn btn-g" onclick="closeM('mFile')">Cancel</button>
      <button class="btn btn-acc" onclick="saveFile()">✅ Create File</button>
    </div>
  </div>
</div>

<!-- Add/Edit Record -->
<div class="ovl" id="mRec">
  <div class="modal modal-w">
    <div class="mh"><h3 id="mRecT">Add Record</h3><button class="xb" onclick="closeM('mRec')">✕</button></div>
    <div class="rtab-bar" id="recTabs">
      <div class="rtab on" id="tab-full" onclick="switchTab('full')">📋 Full Row</div>
      <div class="rtab" id="tab-single" onclick="switchTab('single')">⚡ Single Column</div>
    </div>
    <div id="panelFull" class="mb">
      <div class="fgrid" id="recFlds"></div>
      <div class="full" style="margin-top:4px">
        <div class="fg"><label>Tags</label>
          <input type="text" id="recTags" placeholder="vip, follow-up"/></div>
        <div class="fg"><label>Notes</label>
          <textarea id="recNotes" rows="2" placeholder="Notes…"></textarea></div>
      </div>
    </div>
    <div id="panelSingle" class="mb" style="display:none">
      <div class="fg"><label>Column *</label>
        <select id="singleColSel" onchange="onSingleColChange()">
          <option value="">— Column choose karo —</option>
        </select></div>
      <div class="fg" id="singleValFg" style="display:none">
        <label id="singleValLbl">Value</label>
        <input type="text" id="singleVal" placeholder="Value daalo…"/></div>
    </div>
    <div class="mf">
      <button class="btn btn-g" onclick="closeM('mRec')">Cancel</button>
      <button class="btn btn-acc" onclick="saveRec()">💾 Save</button>
    </div>
  </div>
</div>

<!-- Attachment Modal -->
<div class="ovl" id="mAtt">
  <div class="modal">
    <div class="mh">
      <h3>📎 Attachments <span style="color:var(--acc);font-size:12px" id="mAttLbl"></span></h3>
      <button class="xb" onclick="closeM('mAtt')">✕</button>
    </div>
    <div class="mb" style="position:relative" id="mAttBody">
      <div class="att-dz">
        <input type="file" multiple id="attInp" onchange="doUpload()"/>
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="1.5" style="color:var(--acc)">
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>
        </svg>
        <p style="font-size:12px;margin-top:6px"><strong style="color:var(--acc)">Click or drop files</strong></p>
      </div>
      <div class="att-list" id="attList"></div>
    </div>
    <div class="mf"><button class="btn btn-g" onclick="closeM('mAtt')">Close</button></div>
  </div>
</div>

<!-- Add Column -->
<div class="ovl" id="mCol">
  <div class="modal" style="max-width:380px">
    <div class="mh"><h3 id="mColTitle">Add Column</h3><button class="xb" onclick="closeM('mCol')">✕</button></div>
    <div class="mb">
      <div class="fg"><label>Column Name *</label>
        <input type="text" id="colNm" placeholder="e.g. Company, Status"/></div>
      <div class="fg"><label>Type</label>
        <select id="colTp">
          <option value="text">Text</option><option value="number">Number</option>
          <option value="email">Email</option><option value="phone">Phone</option>
          <option value="date">Date</option><option value="url">URL</option>
        </select></div>
      <div class="fg"><label>Position — Kahan Add Karo</label>
        <select id="colPos"><option value="">⬇ Sabse Last (End mein)</option></select></div>
      <div id="colPosHint" style="font-size:10px;color:var(--t3);margin-top:-6px;margin-bottom:8px">
        Naya column selected column ke BAAD insert hoga</div>
    </div>
    <div class="mf">
      <button class="btn btn-g" onclick="closeM('mCol')">Cancel</button>
      <button class="btn btn-acc" onclick="saveCol()">＋ Add Column</button>
    </div>
  </div>
</div>

<!-- ════ FORM BUILDER MODAL ════ -->
<div class="ovl" id="mForm">
  <div class="modal modal-xl">
    <div class="mh">
      <h3 id="mFormTitle">🧩 New Form Banao</h3>
      <button class="xb" onclick="closeM('mForm')">✕</button>
    </div>
    <div class="mb" style="max-height:75vh;overflow-y:auto">

      <!-- Basic Info -->
      <div style="background:var(--s2);border:1px solid var(--b1);border-radius:var(--r);
                  padding:14px;margin-bottom:14px">
        <div style="font-size:10px;color:var(--t3);letter-spacing:1px;text-transform:uppercase;
                    margin-bottom:10px">📋 Basic Info</div>
        <div class="fgrid">
          <div class="fg full"><label>Form Title *</label>
            <input type="text" id="fmTitle" placeholder="e.g. Customer Enquiry Form"/></div>
          <div class="fg"><label>Organization Name</label>
            <input type="text" id="fmOrg" placeholder="e.g. ABC Industries"/></div>
          <div class="fg"><label>Accent Color</label>
            <input type="color" id="fmColor" value="#00c8ff"
              style="height:36px;padding:3px;cursor:pointer"/></div>
          <div class="fg full"><label>Description (optional)</label>
            <textarea id="fmDesc" rows="2" placeholder="Form ki short description…"></textarea></div>
        </div>
      </div>

      <!-- Logo Upload -->
      <div style="background:var(--s2);border:1px solid var(--b1);border-radius:var(--r);
                  padding:14px;margin-bottom:14px">
        <div style="font-size:10px;color:var(--t3);letter-spacing:1px;text-transform:uppercase;
                    margin-bottom:10px">🖼 Logo / Brand Image</div>
        <div class="logo-upload-area" id="logoArea">
          <input type="file" accept="image/*" id="fmLogoInp" onchange="previewLogo(this)"/>
          <div id="logoPlaceholder">
            <div style="font-size:24px">🏢</div>
            <div style="font-size:12px;margin-top:4px"><strong style="color:var(--acc)">Click to upload logo</strong></div>
            <div style="font-size:10px;color:var(--t3);margin-top:2px">PNG · JPG · WEBP (recommended: square)</div>
          </div>
          <img id="logoPreviewImg" class="logo-preview" style="display:none"/>
        </div>
        <div style="font-size:10px;color:var(--t3);margin-top:6px" id="logoFilename"></div>
      </div>

      <!-- Fields Builder -->
      <div style="background:var(--s2);border:1px solid var(--b1);border-radius:var(--r);padding:14px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
          <div style="font-size:10px;color:var(--t3);letter-spacing:1px;text-transform:uppercase">
            📝 Form Fields</div>
          <button class="btn btn-acc btn-sm" onclick="addFormField()">＋ Add Field</button>
        </div>
        <div class="fb-fields" id="fbFields">
          <div style="text-align:center;padding:18px;color:var(--t3);font-size:11px;
                      border:2px dashed var(--b1);border-radius:8px" id="fbEmpty">
            Koi field nahi. "Add Field" se fields add karo.
          </div>
        </div>
      </div>

    </div>
    <div class="mf">
      <button class="btn btn-g" onclick="closeM('mForm')">Cancel</button>
      <button class="btn btn-acc" id="mFormSaveBtn" onclick="saveForm()">✅ Create Form & Generate Link</button>
    </div>
  </div>
</div>

<!-- ════ ADD FORM FIELD MODAL (UPDATED) ════ -->
<div class="ovl" id="mFField" style="z-index:600">
  <div class="modal" style="max-width:460px">
    <div class="mh">
      <h3 id="mFFieldTitle">Add Field</h3>
      <button class="xb" onclick="closeM('mFField')">✕</button>
    </div>
    <div class="mb" style="max-height:70vh;overflow-y:auto">

      <div class="fg"><label>Field Label *</label>
        <input type="text" id="ffLabel" placeholder="e.g. Customer Name, City, Status…"/></div>

      <div class="fg"><label>Field Type</label>
        <select id="ffType" onchange="onFfTypeChange()">
          <option value="text">📝 Text</option>
          <option value="number">🔢 Number</option>
          <option value="email">📧 Email</option>
          <option value="tel">📞 Phone</option>
          <option value="date">📅 Date</option>
          <option value="url">🔗 URL</option>
          <option value="textarea">📄 Textarea (Long Text)</option>
          <option value="select">🔽 Dropdown (Select Options)</option>
          <option value="image">🖼️ Image Upload</option>
        </select>
      </div>

      <!-- ── Dropdown Options Builder ── -->
      <div id="ffOptsFg" style="display:none;background:var(--s2);border:1px solid var(--b1);
           border-radius:var(--r);padding:12px;margin-bottom:10px">
        <div style="font-size:10px;color:var(--t3);letter-spacing:1px;text-transform:uppercase;
                    margin-bottom:8px">🔽 Dropdown Options</div>
        <div class="fg">
          <label>Option text daalo</label>
          <div style="display:flex;gap:6px">
            <input type="text" id="ffOptInput" placeholder="e.g. Mumbai, Delhi, Pune…"
              onkeydown="if(event.key==='Enter'){event.preventDefault();addDropdownOption()}"
              style="flex:1"/>
            <button class="btn btn-acc btn-sm" onclick="addDropdownOption()" type="button"
                    style="flex-shrink:0;white-space:nowrap">＋ Add</button>
          </div>
        </div>
        <div id="ffOptsList" style="display:flex;flex-direction:column;gap:4px;
             margin-top:4px;max-height:160px;overflow-y:auto">
          <div style="font-size:10px;color:var(--t3);padding:4px 0">
            Abhi koi option nahi — upar se add karo
          </div>
        </div>
        <input type="hidden" id="ffOpts"/>
        <div style="font-size:10px;color:var(--t3);margin-top:6px">
          💡 Enter key dabao ya ＋ Add button click karo
        </div>
      </div>

      <!-- ── Image Field Info Panel ── -->
      <div id="ffImageFg" style="display:none;background:rgba(0,200,255,.04);
           border:1px solid rgba(0,200,255,.2);border-radius:var(--r);
           padding:12px;margin-bottom:10px">
        <div style="font-size:10px;color:var(--acc);letter-spacing:1px;
                    text-transform:uppercase;margin-bottom:8px">🖼️ Image Upload Field</div>
        <div style="font-size:11px;color:var(--t2);line-height:1.8">
          ✅ User form mein image upload kar sakta hai<br/>
          ✅ JPG · PNG · WEBP · GIF supported<br/>
          ✅ Image CRM ke attachments mein save hogi<br/>
          ✅ Dashboard mein thumbnail dikhega
        </div>
        <div style="margin-top:12px">
          <div style="font-size:10px;color:var(--t3);letter-spacing:.4px;
                      text-transform:uppercase;margin-bottom:6px">Form mein kaisa dikhega:</div>
          <div style="border:2px dashed rgba(0,200,255,.25);border-radius:9px;
               padding:14px;text-align:center;background:var(--s2)">
            <div style="font-size:22px">📷</div>
            <div style="font-size:11px;color:var(--acc);margin-top:4px;font-weight:600">
              Click to upload image</div>
            <div style="font-size:10px;color:var(--t3);margin-top:2px">JPG · PNG · WEBP</div>
          </div>
        </div>
      </div>

      <div class="fg"><label>Placeholder Text</label>
        <input type="text" id="ffPlaceholder" placeholder="Field ka hint text…"/></div>

      <div class="fg">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;
                      font-size:11px;text-transform:none;letter-spacing:0">
          <input type="checkbox" id="ffRequired" style="width:auto;cursor:pointer"/>
          <span>Required field — user ko fill karna hoga</span>
        </label>
      </div>

    </div>
    <div class="mf">
      <button class="btn btn-g" onclick="closeM('mFField')">Cancel</button>
      <button class="btn btn-acc" onclick="confirmAddField()">＋ Add Field</button>
    </div>
  </div>
</div>

<!-- Form Link Modal -->
<div class="ovl" id="mFormLink">
  <div class="modal" style="max-width:480px">
    <div class="mh"><h3>🔗 Form Link Ready!</h3><button class="xb" onclick="closeM('mFormLink')">✕</button></div>
    <div class="mb">
      <div style="text-align:center;padding:12px 0 18px">
        <div style="font-size:48px">🎉</div>
        <div style="font-family:'Syne',sans-serif;font-size:17px;font-weight:800;
                    color:var(--acc);margin-top:8px" id="linkFormTitle">Form Created!</div>
        <div style="font-size:11px;color:var(--t3);margin-top:4px">
          Yeh link share karo — unlimited users form fill kar sakte hain
        </div>
      </div>
      <div class="link-box" id="linkBox">
        <span class="link-txt" id="linkTxt">—</span>
        <button class="btn btn-acc btn-sm" onclick="copyLink()">📋 Copy</button>
      </div>
      <div style="margin-top:10px;font-size:11px;color:var(--t3)">
        ✅ Form submissions directly CRM mein aayenge<br/>
        ✅ Ek dedicated file automatic ban gayi hai<br/>
        ✅ Link permanent hai, koi expiry nahi
      </div>
    </div>
    <div class="mf">
      <button class="btn btn-g btn-sm" onclick="window.open(document.getElementById('linkTxt').textContent,'_blank')">
        👁 Preview Form
      </button>
      <button class="btn btn-acc" onclick="closeM('mFormLink');loadProjects()">
        ✅ Done, Go to Dashboard
      </button>
    </div>
  </div>
</div>

<!-- Add User -->
<div class="ovl" id="mUser">
  <div class="modal" style="max-width:370px">
    <div class="mh"><h3 id="mUserTitle">👤 Add User</h3><button class="xb" onclick="closeM('mUser')">✕</button></div>
    <div class="mb">
      <div class="fg"><label>Username *</label>
        <input type="text" id="uNm" placeholder="e.g. john, sales_team"/></div>
      <div class="fg"><label>Password * (min 4 chars)</label>
        <input type="password" id="uPw" placeholder="Password daalo"/></div>
      <div class="fg"><label>Role</label>
        <select id="uRole">
          <option value="false">User (Normal)</option>
          <option value="true">Admin</option>
        </select></div>
    </div>
    <div class="mf">
      <button class="btn btn-g" onclick="closeM('mUser')">Cancel</button>
      <button class="btn btn-acc" onclick="saveUser()">✅ Create User</button>
    </div>
  </div>
</div>

<!-- Change Password -->
<div class="ovl" id="mPw">
  <div class="modal" style="max-width:370px">
    <div class="mh"><h3>🔑 Change Password</h3><button class="xb" onclick="closeM('mPw')">✕</button></div>
    <div class="mb">
      <p style="font-size:11px;color:var(--t3);margin-bottom:12px" id="mPwLbl">Apna password change karo</p>
      <div class="fg"><label>New Password * (min 4 chars)</label>
        <input type="password" id="newPw" placeholder="New password"/></div>
      <div class="fg"><label>Confirm Password</label>
        <input type="password" id="confPw" placeholder="Dobara daalo"/></div>
    </div>
    <div class="mf">
      <button class="btn btn-g" onclick="closeM('mPw')">Cancel</button>
      <button class="btn btn-acc" onclick="doChangePw()">💾 Save Password</button>
    </div>
  </div>
</div>

<div class="tc" id="tc"></div>

<script>
const COLORS=['#00c8ff','#00e07a','#ff9500','#ff3d5a','#a855f7','#f59e0b','#06b6d4','#84cc16'];
let projects=[],curPid=null,cols=[],curRecId=null,curAttId=null,stimer=null;
let activeTab='full',selColor=COLORS[0];
let currentUser={username:'',is_admin:false,user_id:null};
let pwTargetUid=null;
// Form builder state
let fbFields=[];
let editFormId=null;
let uploadedLogoFilename='';
// Dropdown options state
let dropdownOptions=[];

// ════ BOOT ════
(async()=>{
  buildColorOpts();
  await loadMe();
  await loadProjects();
  if(projects.length) selectProject(projects[0].id);
})();

// ════ ME ════
async function loadMe(){
  const r=await fetch('/api/me').then(r=>r.json()).catch(()=>null);
  if(!r||!r.success){window.location='/login';return;}
  currentUser=r;
  document.getElementById('userNm').textContent=r.username;
  document.getElementById('userRole').textContent=r.is_admin?'★ Admin':'User';
  document.getElementById('userAv').textContent=r.username[0].toUpperCase();
  if(r.is_admin){
    document.getElementById('nav-users').style.display='flex';
    document.getElementById('nav-forms').style.display='flex';
  }
}

function doLogout(){window.location='/logout';}

// ════ COLORS ════
function buildColorOpts(){
  document.getElementById('colorOpts').innerHTML=
    COLORS.map((c,i)=>`<div class="co${i===0?' on':''}" style="background:${c}"
      onclick="pickColor('${c}',this)"></div>`).join('');
}
function pickColor(clr,el){
  selColor=clr;
  document.querySelectorAll('.co').forEach(e=>e.classList.remove('on'));
  el.classList.add('on');
}

// ════ PROJECTS ════
async function loadProjects(){
  const r=await fetch('/api/projects').then(r=>r.json());
  projects=r.projects;
  renderFileList();
}
function renderFileList(){
  const el=document.getElementById('fileList');
  if(!projects.length){
    el.innerHTML='<div style="padding:10px;font-size:11px;color:var(--t3)">Koi file nahi</div>';return;
  }
  el.innerHTML=projects.map(p=>`
    <div class="fi${p.id===curPid?' on':''}" onclick="selectProject(${p.id})" id="fi-${p.id}"
         style="${p.id===curPid?'--fc:'+p.color:''}">
      <div class="fi-dot" style="background:${p.color}"></div>
      <span class="fi-name">${p.name}</span>
      <span class="fi-cnt">${p.record_count}</span>
      <button class="fi-del" onclick="delProject(event,${p.id})">🗑</button>
    </div>`).join('');
}
async function selectProject(pid){
  curPid=pid;
  const p=projects.find(x=>x.id===pid);
  document.documentElement.style.setProperty('--fc',p?p.color:'#00c8ff');
  document.querySelectorAll('.fi').forEach(e=>e.classList.remove('on'));
  const fi=document.getElementById('fi-'+pid);if(fi)fi.classList.add('on');
  document.getElementById('fileTitleSpan').textContent=p?p.name:'';
  document.getElementById('impFileLbl').textContent=p?'→ '+p.name:'—';
  await loadCols();
  gotoSection('records');
  loadRecs();
  loadStats();
}
function openCreateFile(){
  document.getElementById('fileNm').value='';
  selColor=COLORS[0];
  document.querySelectorAll('.co').forEach((e,i)=>e.classList.toggle('on',i===0));
  openM('mFile');
}
async function saveFile(){
  const nm=document.getElementById('fileNm').value.trim();
  if(!nm){toast('File ka naam daalo','err');return;}
  const r=await fetch('/api/projects',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:nm,color:selColor})
  }).then(r=>r.json());
  if(r.success){
    toast('"'+nm+'" file ban gayi!','ok');
    closeM('mFile');projects.push(r.project);
    renderFileList();selectProject(r.project.id);
  } else toast(r.message,'err');
}
async function delProject(e,pid){
  e.stopPropagation();
  const p=projects.find(x=>x.id===pid);
  if(!confirm(`"${p?.name}" file delete karna chahte ho?\nSaare records bhi delete ho jaayenge!`)) return;
  await fetch('/api/projects/'+pid,{method:'DELETE'});
  toast('File deleted','ok');
  projects=projects.filter(x=>x.id!==pid);
  if(curPid===pid){curPid=null;showView('nofile');}
  renderFileList();
}

// ════ VIEWS ════
function showView(name){
  document.querySelectorAll('.view').forEach(e=>e.classList.remove('on'));
  document.getElementById('view-'+name).classList.add('on');
}
function gotoSection(sec){
  if(sec==='records'&&!curPid&&sec!=='forms'&&sec!=='users'){
    toast('Pehle ek file choose karo','err');return;
  }
  const vmap={records:'records',columns:'columns',import:'import',forms:'forms',users:'users'};
  showView(vmap[sec]||'nofile');
  document.querySelectorAll('.ni').forEach(e=>e.classList.remove('on'));
  const ni=document.getElementById('nav-'+sec);if(ni)ni.classList.add('on');
  if(sec==='columns') renderColList();
  if(sec==='users')   loadUsers();
  if(sec==='forms')   loadForms();
}

// ════ STATS ════
async function loadStats(){
  if(!curPid) return;
  const r=await fetch('/api/stats/'+curPid).then(r=>r.json());
  document.getElementById('sRec').textContent=r.records;
  document.getElementById('sCols').textContent=r.columns;
  document.getElementById('sAtts').textContent=r.attachments;
  document.getElementById('sToday').textContent=r.today;
  const p=projects.find(x=>x.id===curPid);
  if(p){p.record_count=r.records;renderFileList();}
}

// ════ COLUMNS ════
async function loadCols(){
  if(!curPid) return;
  const r=await fetch('/api/projects/'+curPid+'/columns').then(r=>r.json());
  cols=r.columns;
}
function renderColList(){
  const el=document.getElementById('colList');
  if(!cols.length){el.innerHTML='<div class="empty"><p>Koi column nahi.</p></div>';return;}
  el.innerHTML=`<div style="font-size:10px;color:var(--t3);margin-bottom:8px">
    💡 Insert ↓ se kisi ke baad column add karo</div>`+
  cols.map((c,i)=>`
    <div class="col-row">
      <div style="display:flex;align-items:center;gap:8px;flex:1">
        <span style="color:var(--t3);font-size:10px;min-width:18px">${i+1}.</span>
        <span style="font-weight:600">${c.name}</span>
        <span class="ct-badge">${c.col_type}</span>
      </div>
      <div style="display:flex;gap:5px">
        <button class="btn btn-g btn-sm" onclick="openInsertAfter(${c.id},'${c.name.replace(/'/g,"\\'")}')">Insert ↓</button>
        <button class="btn btn-err btn-sm" onclick="delCol(${c.id},'${c.name}')">Delete</button>
      </div>
    </div>`).join('')+
  `<div style="margin-top:8px;padding:8px;border:1px dashed var(--b2);border-radius:8px;
               text-align:center;font-size:11px;color:var(--t3);cursor:pointer"
        onclick="openAddCol()">＋ Sabse end mein add karo</div>`;
}
function openAddCol(){
  document.getElementById('mColTitle').textContent='Add Column';
  document.getElementById('colNm').value='';
  document.getElementById('colTp').value='text';
  populateColPosSel(null);openM('mCol');
}
function openInsertAfter(afterId,afterName){
  document.getElementById('mColTitle').textContent='Insert Column After "'+afterName+'"';
  document.getElementById('colNm').value='';
  document.getElementById('colTp').value='text';
  populateColPosSel(afterId);openM('mCol');
}
function populateColPosSel(selectedId){
  const sel=document.getElementById('colPos');
  sel.innerHTML='<option value="">⬇ Sabse Last</option>'+
    cols.map(c=>`<option value="${c.id}"${c.id==selectedId?' selected':''}> After: ${c.name}</option>`).join('');
  document.getElementById('colPosHint').style.display=selectedId?'':'none';
}
async function saveCol(){
  if(!curPid) return;
  const nm=document.getElementById('colNm').value.trim();
  if(!nm){toast('Name daalo','err');return;}
  const posVal=document.getElementById('colPos').value;
  const r=await fetch('/api/projects/'+curPid+'/columns',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:nm,col_type:document.getElementById('colTp').value,
      insert_after:posVal?parseInt(posVal):null})
  }).then(r=>r.json());
  if(r.success){
    toast('Column "'+nm+'" added!','ok');
    closeM('mCol');await loadCols();loadRecs();loadStats();
    if(document.getElementById('view-columns').classList.contains('on')) renderColList();
  } else toast(r.message,'err');
}
async function delCol(id,name){
  if(!confirm(`Column "${name}" delete karna chahte ho?`)) return;
  await fetch('/api/projects/'+curPid+'/columns/'+id,{method:'DELETE'});
  toast('Column deleted','ok');await loadCols();loadRecs();loadStats();
}

// ════ RECORDS ════
function onSearch(){clearTimeout(stimer);stimer=setTimeout(loadRecs,280);}
async function loadRecs(){
  if(!curPid) return;
  const q=document.getElementById('srchInput').value;
  const r=await fetch('/api/projects/'+curPid+'/records?q='+encodeURIComponent(q)).then(r=>r.json());
  renderTable(r.records);
  document.getElementById('recInfo').textContent=r.total+' records';
}
function renderTable(recs){
  const head=document.getElementById('tHead');
  const body=document.getElementById('tBody');
  head.innerHTML=`<tr><th style="color:var(--t3);width:30px">#</th>`+
    cols.map(c=>`<th><div class="th-w">${c.name}
      <span class="dc" onclick="delCol(${c.id},'${c.name}')">✕</span></div></th>`).join('')+
    `<th>📎 Files</th><th>Added</th><th style="text-align:right">Actions</th></tr>`;
  if(!recs.length){
    body.innerHTML=`<tr><td colspan="${cols.length+4}">
      <div class="empty"><h3>Koi record nahi</h3>
      <p>Add Record ya Import Excel se data daalo</p></div></td></tr>`;
    return;
  }
  body.innerHTML=recs.map((rec,i)=>{
    const cells=cols.map(c=>{
      const v=rec.data[c.id]||'';
      return `<td title="${v.replace(/"/g,'&quot;')}">${v||'<span style="color:var(--t3)">—</span>'}</td>`;
    }).join('');
    const ac=rec.attachments.length;
    const abtn=ac
      ?`<span class="att-btn has" onclick="openAtt(${rec.id})">📎 ${ac} file${ac>1?'s':''}</span>`
      :`<span class="att-btn" onclick="openAtt(${rec.id})">📎 Add</span>`;
    return `<tr><td class="td-n">${i+1}</td>${cells}<td>${abtn}</td>
      <td style="color:var(--t3);font-size:10px;white-space:nowrap">${rec.created_at}</td>
      <td class="td-act" style="text-align:right">
        <button class="btn btn-g btn-ico btn-sm" onclick="openEditRec(${rec.id})">✏️</button>
        <button class="btn btn-err btn-ico btn-sm" onclick="delRec(${rec.id})">🗑</button>
      </td></tr>`;
  }).join('');
}

function switchTab(tab){
  activeTab=tab;
  document.getElementById('tab-full').classList.toggle('on',tab==='full');
  document.getElementById('tab-single').classList.toggle('on',tab==='single');
  document.getElementById('panelFull').style.display=tab==='full'?'':'none';
  document.getElementById('panelSingle').style.display=tab==='single'?'':'none';
}
function populateSingleColSel(){
  document.getElementById('singleColSel').innerHTML=
    '<option value="">— Column choose karo —</option>'+
    cols.map(c=>`<option value="${c.id}" data-type="${c.col_type}">${c.name}</option>`).join('');
  document.getElementById('singleValFg').style.display='none';
}
function onSingleColChange(){
  const sel=document.getElementById('singleColSel');
  const opt=sel.options[sel.selectedIndex];
  const fg=document.getElementById('singleValFg');
  if(!sel.value){fg.style.display='none';return;}
  document.getElementById('singleValLbl').textContent=opt.text;
  const inp=document.getElementById('singleVal');
  const ct=opt.dataset.type||'text';
  inp.type=ct==='number'?'number':ct==='date'?'date':ct==='email'?'email':ct==='url'?'url':'text';
  inp.placeholder=opt.text+' daalo…';inp.value='';
  fg.style.display='';
}
function openAddRec(){
  curRecId=null;
  document.getElementById('mRecT').textContent='Add Record';
  document.getElementById('recTabs').style.display='flex';
  switchTab('full');
  document.getElementById('recTags').value='';
  document.getElementById('recNotes').value='';
  buildFlds({});populateSingleColSel();openM('mRec');
}
async function openEditRec(id){
  const r=await fetch('/api/records/'+id).then(r=>r.json());
  curRecId=id;
  document.getElementById('mRecT').textContent='Edit Record #'+id;
  document.getElementById('recTabs').style.display='none';
  switchTab('full');
  document.getElementById('recTags').value=r.record.tags||'';
  document.getElementById('recNotes').value=r.record.notes||'';
  buildFlds(r.record.data);openM('mRec');
}
function buildFlds(data){
  const c=document.getElementById('recFlds');
  c.className='fgrid';
  c.innerHTML=cols.map(col=>`
    <div class="fg"><label>${col.name}</label>
      <input type="${col.col_type==='email'?'email':col.col_type==='date'?'date':
                    col.col_type==='number'?'number':col.col_type==='url'?'url':'text'}"
        id="f_${col.id}" value="${(data[col.id]||'').replace(/"/g,'&quot;')}"
        placeholder="${col.name}"/>
    </div>`).join('')||'<p style="color:var(--t3)">Pehle columns banao.</p>';
}
async function saveRec(){
  if(!curPid) return;
  if(!curRecId&&activeTab==='single'){
    const colId=document.getElementById('singleColSel').value;
    const val=document.getElementById('singleVal').value.trim();
    if(!colId){toast('Column choose karo','err');return;}
    if(!val){toast('Value daalo','err');return;}
    const r=await fetch('/api/projects/'+curPid+'/records',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({data:{[colId]:val},tags:'',notes:''})
    }).then(r=>r.json());
    if(r.success){toast('Record added!','ok');closeM('mRec');loadRecs();loadStats();}
    else toast(r.message||'Error','err');
    return;
  }
  const fd={};
  cols.forEach(c=>{const e=document.getElementById('f_'+c.id);if(e&&e.value.trim())fd[c.id]=e.value.trim();});
  const payload={data:fd,tags:document.getElementById('recTags').value,
                 notes:document.getElementById('recNotes').value};
  const m=curRecId?'PUT':'POST';
  const u=curRecId?'/api/records/'+curRecId:'/api/projects/'+curPid+'/records';
  const r=await fetch(u,{method:m,headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload)}).then(r=>r.json());
  if(r.success){toast(curRecId?'Updated!':'Record added!','ok');closeM('mRec');loadRecs();loadStats();}
  else toast(r.message||'Error','err');
}
async function delRec(id){
  if(!confirm('Record aur uski files delete karna chahte ho?')) return;
  await fetch('/api/records/'+id,{method:'DELETE'});
  toast('Deleted','ok');loadRecs();loadStats();
}

// ════ ATTACHMENTS ════
async function openAtt(recId){
  curAttId=recId;
  document.getElementById('mAttLbl').textContent='— Record #'+recId;
  await refreshAtts();openM('mAtt');
}
async function refreshAtts(){
  const r=await fetch('/api/records/'+curAttId).then(r=>r.json());
  const atts=r.record.attachments;
  const el=document.getElementById('attList');
  if(!atts.length){
    el.innerHTML='<p style="color:var(--t3);font-size:11px;text-align:center;padding:8px">Koi file nahi.</p>';
  } else {
    el.innerHTML=atts.map(a=>{
      const icon=a.file_type==='image'?'🖼️':a.file_type==='video'?'🎬':a.file_type==='pdf'?'📄':'📁';
      const prev=a.file_type==='image'
        ?`<img class="att-thumb" src="${a.url}" onerror="this.outerHTML='<div class=att-ico>🖼️</div>'">`
        :`<div class="att-ico">${icon}</div>`;
      return `<div class="att-item">${prev}
        <div class="att-inf">
          <div class="att-nm" title="${a.original_name}">${a.original_name}</div>
          <div class="att-mt">${a.file_size_str} · ${a.file_type}</div>
        </div>
        <div class="att-ac">
          <a href="${a.url}" download="${a.original_name}" class="btn btn-g btn-sm">⬇</a>
          ${a.file_type==='image'||a.file_type==='pdf'||a.file_type==='video'
            ?`<a href="${a.url}" target="_blank" class="btn btn-g btn-sm">👁</a>`:''}
          <button class="btn btn-err btn-sm" onclick="delAtt(${a.id})">✕</button>
        </div></div>`;
    }).join('');
  }
  const oldBtn=document.querySelector(`[onclick="openAtt(${curAttId})"]`);
  if(oldBtn){
    oldBtn.className=atts.length?'att-btn has':'att-btn';
    oldBtn.innerHTML=atts.length?`📎 ${atts.length} file${atts.length>1?'s':''}`:'📎 Add';
  }
  loadStats();
}
async function doUpload(){
  const files=document.getElementById('attInp').files;
  if(!files.length) return;
  const body=document.getElementById('mAttBody');
  const ov=document.createElement('div');ov.className='upl-ov';
  ov.innerHTML=`<span class="spin"></span>&nbsp;Uploading…`;body.appendChild(ov);
  for(const f of files){
    const fd=new FormData();fd.append('file',f);
    const r=await fetch('/api/records/'+curAttId+'/attachments',{method:'POST',body:fd}).then(r=>r.json());
    if(!r.success) toast('Error: '+r.message,'err');
  }
  ov.remove();document.getElementById('attInp').value='';
  toast(files.length+' file(s) uploaded!','ok');await refreshAtts();
}
async function delAtt(id){
  if(!confirm('Attachment delete karna chahte ho?')) return;
  await fetch('/api/attachments/'+id,{method:'DELETE'});
  toast('Deleted','ok');await refreshAtts();
}

// ════ EXCEL ════
async function doImport(inp){
  if(!curPid){toast('Pehle file choose karo','err');return;}
  const f=inp.files[0];if(!f) return;
  const rd=document.getElementById('impRes');
  rd.innerHTML='<div class="toast t-info"><span class="spin"></span> Importing…</div>';
  const fd=new FormData();fd.append('file',f);
  const r=await fetch('/api/projects/'+curPid+'/import',{method:'POST',body:fd}).then(r=>r.json());
  rd.innerHTML=r.success
    ?`<div class="toast t-ok">✅ ${r.message} (${r.cols} columns)</div>`
    :`<div class="toast t-err">❌ ${r.message}</div>`;
  inp.value='';
  if(r.success){await loadCols();loadRecs();loadStats();}
}
function doExport(){
  if(!curPid){toast('Pehle file choose karo','err');return;}
  window.open('/api/projects/'+curPid+'/export','_blank');
  toast('Downloading…','info');
}

// ════════════════════════════════════
// ════ FORM BUILDER ════
// ════════════════════════════════════

async function loadForms(){
  const r=await fetch('/api/forms').then(r=>r.json());
  if(!r.success){document.getElementById('formsContainer').innerHTML='<div class="empty"><h3>Admin access required</h3></div>';return;}
  renderForms(r.forms);
}

function renderForms(forms){
  const el=document.getElementById('formsContainer');
  if(!forms.length){
    el.innerHTML=`<div class="empty">
      <h3>Koi form nahi</h3>
      <p>Naya form banao — users se data collect karo</p>
      <button class="btn btn-acc" style="margin-top:12px" onclick="openCreateForm()">＋ New Form Banao</button>
    </div>`;
    return;
  }
  el.innerHTML=forms.map(f=>`
    <div class="form-card" style="--form-color:${f.accent_color}">
      <div class="form-card-head">
        ${f.logo_url
          ?`<img class="form-logo" src="${f.logo_url}" alt="Logo"/>`
          :`<div class="form-logo-ph">🏢</div>`}
        <div class="form-info">
          <div class="form-title">${f.title}</div>
          ${f.org_name?`<div class="form-org">${f.org_name}</div>`:''}
        </div>
        <span class="badge ${f.is_active?'badge-active':'badge-off'}">${f.is_active?'Active':'Inactive'}</span>
      </div>
      <div class="form-meta">
        <span>📝 ${f.fields.length} fields</span>
        <span>📊 ${f.submission_count} submissions</span>
        <span>📅 ${f.created_at}</span>
      </div>
      <div class="link-box">
        <span class="link-txt" id="link-${f.id}">${f.public_url}</span>
        <button class="btn btn-acc btn-sm" onclick="copyFormLink('${f.id}')">📋 Copy</button>
        <a href="${f.public_url}" target="_blank" class="btn btn-g btn-sm">👁 View</a>
      </div>
      <div class="form-actions" style="margin-top:8px">
        <button class="btn btn-g btn-sm" onclick="openEditForm(${f.id})">✏️ Edit</button>
        <button class="btn ${f.is_active?'btn-warn':'btn-ok'} btn-sm" onclick="toggleForm(${f.id})">
          ${f.is_active?'⏸ Deactivate':'▶ Activate'}
        </button>
        <button class="btn btn-g btn-sm" onclick="goToFormData(${f.project_id})">
          📊 View Data (${f.submission_count})
        </button>
        <button class="btn btn-err btn-sm" onclick="deleteForm(${f.id},'${f.title.replace(/'/g,"\\'")}')">🗑 Delete</button>
      </div>
    </div>`).join('');
}

function copyFormLink(fid){
  const txt=document.getElementById('link-'+fid).textContent;
  navigator.clipboard.writeText(txt).then(()=>toast('Link copied!','ok'))
    .catch(()=>{toast('Copy failed — manually copy karo','err');});
}

function goToFormData(pid){
  if(!pid) return;
  selectProject(pid);
}

async function toggleForm(fid){
  const r=await fetch('/api/forms/'+fid+'/toggle',{method:'POST'}).then(r=>r.json());
  if(r.success){toast(r.is_active?'Form activated!':'Form deactivated','ok');loadForms();}
  else toast('Error','err');
}

async function deleteForm(fid,title){
  if(!confirm(`"${title}" form aur uska saara data delete karna chahte ho?`)) return;
  const r=await fetch('/api/forms/'+fid,{method:'DELETE'}).then(r=>r.json());
  if(r.success){toast('Form deleted','ok');loadForms();await loadProjects();}
  else toast('Error','err');
}

// ── Form Builder Modal ──
function openCreateForm(){
  editFormId=null;
  fbFields=[];
  uploadedLogoFilename='';
  document.getElementById('mFormTitle').textContent='🧩 New Form Banao';
  document.getElementById('mFormSaveBtn').textContent='✅ Create Form & Generate Link';
  document.getElementById('fmTitle').value='';
  document.getElementById('fmOrg').value='';
  document.getElementById('fmColor').value='#00c8ff';
  document.getElementById('fmDesc').value='';
  document.getElementById('fmLogoInp').value='';
  document.getElementById('logoPreviewImg').style.display='none';
  document.getElementById('logoPlaceholder').style.display='';
  document.getElementById('logoFilename').textContent='';
  renderFbFields();
  openM('mForm');
}

async function openEditForm(fid){
  const r=await fetch('/api/forms').then(r=>r.json());
  const form=r.forms.find(f=>f.id===fid);
  if(!form) return;
  editFormId=fid;
  fbFields=form.fields.map(f=>({...f}));
  uploadedLogoFilename=form.logo_filename||'';
  document.getElementById('mFormTitle').textContent='✏️ Edit Form';
  document.getElementById('mFormSaveBtn').textContent='💾 Save Changes';
  document.getElementById('fmTitle').value=form.title;
  document.getElementById('fmOrg').value=form.org_name||'';
  document.getElementById('fmColor').value=form.accent_color||'#00c8ff';
  document.getElementById('fmDesc').value=form.description||'';
  document.getElementById('fmLogoInp').value='';
  if(form.logo_url){
    document.getElementById('logoPreviewImg').src=form.logo_url;
    document.getElementById('logoPreviewImg').style.display='block';
    document.getElementById('logoPlaceholder').style.display='none';
    document.getElementById('logoFilename').textContent='Current logo: '+form.logo_url.split('/').pop();
  } else {
    document.getElementById('logoPreviewImg').style.display='none';
    document.getElementById('logoPlaceholder').style.display='';
    document.getElementById('logoFilename').textContent='';
  }
  renderFbFields();
  openM('mForm');
}

// ── Dropdown Options Management ──
function addDropdownOption(){
  const inp=document.getElementById('ffOptInput');
  const val=inp.value.trim();
  if(!val){toast('Option text daalo','err');return;}
  if(dropdownOptions.includes(val)){toast('Yeh option pehle se hai','err');return;}
  dropdownOptions.push(val);
  inp.value='';
  inp.focus();
  renderDropdownOptions();
  syncHiddenOpts();
}

function removeDropdownOption(i){
  dropdownOptions.splice(i,1);
  renderDropdownOptions();
  syncHiddenOpts();
}

function renderDropdownOptions(){
  const el=document.getElementById('ffOptsList');
  if(!dropdownOptions.length){
    el.innerHTML='<div style="font-size:10px;color:var(--t3);padding:4px 0">Abhi koi option nahi — upar se add karo</div>';
    return;
  }
  el.innerHTML=dropdownOptions.map((opt,i)=>`
    <div class="opt-item">
      <span class="opt-num">${i+1}.</span>
      <span class="opt-txt">${opt}</span>
      <button class="btn btn-err btn-sm" onclick="removeDropdownOption(${i})" type="button">✕</button>
    </div>`).join('');
}

function syncHiddenOpts(){
  document.getElementById('ffOpts').value=dropdownOptions.join(',');
}

// ── Field type change ──
function onFfTypeChange(){
  const t=document.getElementById('ffType').value;
  document.getElementById('ffOptsFg').style.display  = t==='select' ? '' : 'none';
  document.getElementById('ffImageFg').style.display  = t==='image'  ? '' : 'none';
}

// ── Add / Edit Field Modal ──
let editingFieldIdx=null;

function addFormField(){
  editingFieldIdx=null;
  dropdownOptions=[];
  document.getElementById('mFFieldTitle').textContent='Add Field';
  document.getElementById('ffLabel').value='';
  document.getElementById('ffType').value='text';
  document.getElementById('ffPlaceholder').value='';
  document.getElementById('ffRequired').checked=false;
  document.getElementById('ffOpts').value='';
  document.getElementById('ffOptInput').value='';
  renderDropdownOptions();
  onFfTypeChange();
  openM('mFField');
}

function editField(i){
  editingFieldIdx=i;
  const f=fbFields[i];
  document.getElementById('mFFieldTitle').textContent='Edit Field: '+f.label;
  document.getElementById('ffLabel').value=f.label;
  document.getElementById('ffType').value=f.type;
  document.getElementById('ffPlaceholder').value=f.placeholder||'';
  document.getElementById('ffRequired').checked=!!f.required;
  // Restore dropdown options
  dropdownOptions=f.options ? f.options.split(',').map(o=>o.trim()).filter(Boolean) : [];
  document.getElementById('ffOpts').value=f.options||'';
  document.getElementById('ffOptInput').value='';
  renderDropdownOptions();
  onFfTypeChange();
  openM('mFField');
}

function confirmAddField(){
  const label=document.getElementById('ffLabel').value.trim();
  if(!label){toast('Field label daalo','err');return;}
  const type=document.getElementById('ffType').value;
  if(type==='select'&&!dropdownOptions.length){
    toast('Dropdown ke liye kam se kam ek option add karo','err');return;
  }
  syncHiddenOpts();
  const fld={
    label,
    type,
    placeholder:document.getElementById('ffPlaceholder').value.trim(),
    required:   document.getElementById('ffRequired').checked,
    options:    document.getElementById('ffOpts').value.trim()
  };
  if(editingFieldIdx!==null){
    fbFields[editingFieldIdx]=fld;
  } else {
    fbFields.push(fld);
  }
  closeM('mFField');
  renderFbFields();
  toast('Field '+(editingFieldIdx!==null?'updated':'added')+'!','ok');
  editingFieldIdx=null;
}

function renderFbFields(){
  const el=document.getElementById('fbFields');
  if(!fbFields.length){
    el.innerHTML=`<div style="text-align:center;padding:18px;color:var(--t3);font-size:11px;
      border:2px dashed var(--b1);border-radius:8px">
      Koi field nahi. "Add Field" se fields add karo.</div>`;
    return;
  }
  const typeIcon={
    text:'📝',number:'🔢',email:'📧',tel:'📞',date:'📅',
    url:'🔗',textarea:'📄',select:'🔽',image:'🖼️'
  };
  el.innerHTML=fbFields.map((f,i)=>{
    const optCount=f.type==='select'&&f.options
      ? f.options.split(',').filter(Boolean).length : 0;
    const optPreview=optCount
      ? `<div style="font-size:9px;color:var(--t3);margin-top:2px">${optCount} options: ${
          f.options.split(',').slice(0,3).map(o=>o.trim()).join(', ')}${optCount>3?'…':''}</div>`
      : '';
    const imgInfo=f.type==='image'
      ? `<div style="font-size:9px;color:var(--acc);margin-top:2px">🖼️ Image upload</div>`
      : '';
    return `
    <div class="fb-field" draggable="true" data-idx="${i}"
         ondragstart="fbDragStart(event,${i})" ondragover="fbDragOver(event)"
         ondrop="fbDrop(event,${i})">
      <span class="fb-drag">⠿</span>
      <span style="font-size:16px;flex-shrink:0">${typeIcon[f.type]||'📝'}</span>
      <div style="flex:1;min-width:0">
        <div class="fb-label">${f.label}</div>
        ${optPreview}${imgInfo}
      </div>
      <span class="fb-type">${f.type}</span>
      ${f.required?'<span class="fb-req">required</span>':''}
      <div class="fb-acts">
        <button class="btn btn-g btn-sm" onclick="editField(${i})">✏️</button>
        <button class="btn btn-err btn-sm" onclick="removeField(${i})">✕</button>
        ${i>0?`<button class="btn btn-g btn-sm btn-ico" onclick="moveField(${i},-1)">↑</button>`:''}
        ${i<fbFields.length-1?`<button class="btn btn-g btn-sm btn-ico" onclick="moveField(${i},1)">↓</button>`:''}
      </div>
    </div>`;
  }).join('');
}

let fbDragIdx=null;
function fbDragStart(e,i){fbDragIdx=i;}
function fbDragOver(e){e.preventDefault();}
function fbDrop(e,i){
  e.preventDefault();
  if(fbDragIdx===null||fbDragIdx===i) return;
  const moved=fbFields.splice(fbDragIdx,1)[0];
  fbFields.splice(i,0,moved);
  fbDragIdx=null;renderFbFields();
}
function moveField(i,dir){
  const j=i+dir;if(j<0||j>=fbFields.length) return;
  [fbFields[i],fbFields[j]]=[fbFields[j],fbFields[i]];
  renderFbFields();
}
function removeField(i){fbFields.splice(i,1);renderFbFields();}

function previewLogo(inp){
  if(inp.files&&inp.files[0]){
    const reader=new FileReader();
    reader.onload=e=>{
      document.getElementById('logoPreviewImg').src=e.target.result;
      document.getElementById('logoPreviewImg').style.display='block';
      document.getElementById('logoPlaceholder').style.display='none';
      document.getElementById('logoFilename').textContent=inp.files[0].name;
    };
    reader.readAsDataURL(inp.files[0]);
  }
}

async function saveForm(){
  const title=document.getElementById('fmTitle').value.trim();
  if(!title){toast('Form title daalo','err');return;}
  if(!fbFields.length){toast('Kam se kam ek field add karo','err');return;}

  const btn=document.getElementById('mFormSaveBtn');
  btn.disabled=true;btn.innerHTML='<span class="spin"></span> Saving…';

  const fd=new FormData();
  fd.append('title',title);
  fd.append('org_name',document.getElementById('fmOrg').value.trim());
  fd.append('description',document.getElementById('fmDesc').value.trim());
  fd.append('accent_color',document.getElementById('fmColor').value);
  fd.append('color',document.getElementById('fmColor').value);
  fd.append('fields',JSON.stringify(fbFields));

  const logoInp=document.getElementById('fmLogoInp');
  if(logoInp.files&&logoInp.files[0]){
    fd.append('logo',logoInp.files[0]);
  }

  let r;
  if(editFormId){
    r=await fetch('/api/forms/'+editFormId,{method:'PUT',body:fd}).then(r=>r.json());
  } else {
    r=await fetch('/api/forms',{method:'POST',body:fd}).then(r=>r.json());
  }

  btn.disabled=false;
  btn.innerHTML=editFormId?'💾 Save Changes':'✅ Create Form & Generate Link';

  if(r.success){
    closeM('mForm');
    if(!editFormId){
      document.getElementById('linkFormTitle').textContent=title;
      document.getElementById('linkTxt').textContent=r.form.public_url;
      openM('mFormLink');
    } else {
      toast('Form updated!','ok');
    }
    loadForms();
    await loadProjects();
  } else {
    toast(r.message||'Error','err');
  }
}

function copyLink(){
  const txt=document.getElementById('linkTxt').textContent;
  navigator.clipboard.writeText(txt).then(()=>toast('Link copied!','ok'))
    .catch(()=>toast('Copy failed','err'));
}

// ════ USERS ════
async function loadUsers(){
  const r=await fetch('/api/admin/users').then(r=>r.json());
  if(!r.success){toast('Admin access required','err');return;}
  const tb=document.getElementById('usersTbody');
  tb.innerHTML=r.users.map((u,i)=>`
    <tr>
      <td style="color:var(--t3)">${i+1}</td>
      <td style="font-weight:600">${u.username}</td>
      <td><span class="badge ${u.is_admin?'badge-admin':'badge-user'}">${u.is_admin?'Admin':'User'}</span></td>
      <td style="color:var(--t3);font-size:10px">${u.created_at}</td>
      <td style="text-align:right">
        <button class="btn btn-g btn-sm" onclick="openResetPw(${u.id},'${u.username}')">🔑 Reset PW</button>
        <button class="btn btn-err btn-sm" onclick="delUser(${u.id},'${u.username}')">🗑 Delete</button>
      </td>
    </tr>`).join('');
}
function openAddUser(){
  document.getElementById('uNm').value='';document.getElementById('uPw').value='';
  document.getElementById('uRole').value='false';openM('mUser');
}
async function saveUser(){
  const nm=document.getElementById('uNm').value.trim();
  const pw=document.getElementById('uPw').value.trim();
  if(!nm){toast('Username daalo','err');return;}
  if(pw.length<4){toast('Password min 4 chars','err');return;}
  const r=await fetch('/api/admin/users',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({username:nm,password:pw,is_admin:document.getElementById('uRole').value==='true'})
  }).then(r=>r.json());
  if(r.success){toast('"'+nm+'" user ban gaya!','ok');closeM('mUser');loadUsers();}
  else toast(r.message,'err');
}
async function delUser(id,name){
  if(!confirm(`"${name}" ko delete karna chahte ho?`)) return;
  const r=await fetch('/api/admin/users/'+id,{method:'DELETE'}).then(r=>r.json());
  if(r.success){toast('"'+name+'" deleted','ok');loadUsers();}
  else toast(r.message,'err');
}

// ════ PASSWORD ════
function openChangePw(){
  pwTargetUid=null;
  document.getElementById('mPwLbl').textContent='Apna password change karo';
  document.getElementById('newPw').value='';document.getElementById('confPw').value='';
  openM('mPw');
}
function openResetPw(uid,uname){
  pwTargetUid=uid;
  document.getElementById('mPwLbl').textContent='Reset password for: '+uname;
  document.getElementById('newPw').value='';document.getElementById('confPw').value='';
  openM('mPw');
}
async function doChangePw(){
  const np=document.getElementById('newPw').value.trim();
  const cp=document.getElementById('confPw').value.trim();
  if(np.length<4){toast('Password min 4 chars','err');return;}
  if(np!==cp){toast('Passwords match nahi karte','err');return;}
  const uid=pwTargetUid||currentUser.user_id;
  const r=await fetch('/api/admin/users/'+uid+'/password',{
    method:'PUT',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({password:np})
  }).then(r=>r.json());
  if(r.success){toast('Password badal gaya!','ok');closeM('mPw');}
  else toast(r.message||'Error','err');
}

// ════ HELPERS ════
function openM(id){document.getElementById(id).classList.add('on');}
function closeM(id){document.getElementById(id).classList.remove('on');}
document.querySelectorAll('.ovl').forEach(el=>
  el.addEventListener('click',e=>{if(e.target===el)el.classList.remove('on');}));

const dz=document.getElementById('dz');
dz.addEventListener('dragover',e=>{e.preventDefault();dz.classList.add('drag');});
dz.addEventListener('dragleave',()=>dz.classList.remove('drag'));
dz.addEventListener('drop',e=>{
  e.preventDefault();dz.classList.remove('drag');
  const f=e.dataTransfer.files[0];
  if(f){const dt=new DataTransfer();dt.items.add(f);
    document.getElementById('xlsInp').files=dt.files;
    doImport(document.getElementById('xlsInp'));}
});

function toast(msg,type='info'){
  const tc=document.getElementById('tc');
  const t=document.createElement('div');
  t.className='toast t-'+type;t.textContent=msg;
  tc.appendChild(t);setTimeout(()=>t.remove(),3200);
}
</script>
</body>
</html>"""


if __name__ == '__main__':
    print("="*60)
    print("🚀 CRM Dashboard — PostgreSQL + Login + Form Builder")
    print("📍 http://127.0.0.1:5000")
    print("─"*60)
    print("🐘 DB: PostgreSQL")
    print("   Set env: DATABASE_URL=postgresql://user:pass@host/db")
    print("─"*60)
    print("🔐 Default admin: admin / admin123")
    print("─"*60)
    print("✅ Login / Logout — Session-based Auth")
    print("✅ Admin User Management")
    print("✅ Multiple Files/Projects")
    print("✅ Excel Import/Export")
    print("✅ Full CRUD + Attachments")
    print("🆕 Form Builder — Custom forms with logo & branding")
    print("🆕 Dropdown fields — ek ek option add karo with + button")
    print("🆕 Image field — dedicated info panel with preview")
    print("🆕 Public Form Links — Permanent, unlimited submissions")
    print("🆕 Auto CRM File — Form data directly dashboard mein")
    print("="*60)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)