"""
نظام ERP الويب - شركة إبداع للتطوير العقاري
Ibdaa Real Estate ERP - Web Application
Flask + SQLite | Multi-user | Arabic/English | PDF Reports
"""

import hashlib, hmac, json, os, shutil, calendar, io, logging
from datetime import date, datetime
from pathlib import Path
from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, flash, send_file, make_response, abort)
import sqlite3
import bcrypt
from flask_wtf.csrf import CSRFProtect
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT

BASE_DIR   = Path(__file__).resolve().parent
DB_PATH    = BASE_DIR / "erp.db"
BACKUP_DIR = BASE_DIR / "backups"
EXPORT_DIR = BASE_DIR / "exports"

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(BASE_DIR / "logs" / "erp.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
Path(BASE_DIR / "logs").mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24).hex())
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = False  # Set True in production with HTTPS
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
csrf = CSRFProtect(app)

# ── PDF Arabic Font Setup ─────────────────────────────────────────────────────
ARABIC_FONT = None
try:
    # Try to register Arabic fonts if available
    font_paths = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            pdfmetrics.registerFont(TTFont('Arabic', fp))
            ARABIC_FONT = 'Arabic'
            break
    if not ARABIC_FONT:
        ARABIC_FONT = 'Helvetica'
except Exception:
    ARABIC_FONT = 'Helvetica'

def get_pdf_styles():
    """Get styles for PDF generation"""
    styles = getSampleStyleSheet()
    
    if ARABIC_FONT != 'Helvetica':
        styles.add(ParagraphStyle(
            name='ArabicTitle',
            parent=styles['Heading1'],
            fontName=ARABIC_FONT,
            fontSize=18,
            alignment=TA_CENTER,
            spaceAfter=20,
            textColor=colors.HexColor('#1a5276')
        ))
        styles.add(ParagraphStyle(
            name='ArabicHeading',
            parent=styles['Heading2'],
            fontName=ARABIC_FONT,
            fontSize=14,
            alignment=TA_CENTER,
            spaceAfter=10,
            textColor=colors.HexColor('#2874a6')
        ))
        styles.add(ParagraphStyle(
            name='ArabicNormal',
            parent=styles['Normal'],
            fontName=ARABIC_FONT,
            fontSize=10,
            alignment=TA_RIGHT
        ))
        styles.add(ParagraphStyle(
            name='ArabicBold',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=11,
            alignment=TA_RIGHT
        ))
        styles.add(ParagraphStyle(
            name='ArabicSmall',
            parent=styles['Normal'],
            fontName=ARABIC_FONT,
            fontSize=8,
            alignment=TA_CENTER
        ))
    else:
        # Fallback styles without Arabic
        styles.add(ParagraphStyle(
            name='ArabicTitle',
            parent=styles['Heading1'],
            fontSize=18,
            alignment=TA_CENTER,
            spaceAfter=20,
            textColor=colors.HexColor('#1a5276')
        ))
        styles.add(ParagraphStyle(
            name='ArabicHeading',
            parent=styles['Heading2'],
            fontSize=14,
            alignment=TA_CENTER,
            spaceAfter=10,
            textColor=colors.HexColor('#2874a6')
        ))
        styles.add(ParagraphStyle(
            name='ArabicNormal',
            parent=styles['Normal'],
            fontSize=10,
            alignment=TA_RIGHT
        ))
        styles.add(ParagraphStyle(
            name='ArabicBold',
            parent=styles['Normal'],
            fontSize=11,
            alignment=TA_RIGHT,
            fontName='Helvetica-Bold'
        ))
        styles.add(ParagraphStyle(
            name='ArabicSmall',
            parent=styles['Normal'],
            fontSize=8,
            alignment=TA_CENTER
        ))
    
    return styles

def rtl_text(text):
    """Prepare RTL text for PDF (adds Unicode marks for Arabic)"""
    return f'\u202B{text}\u202C' if ARABIC_FONT == 'Arabic' else text

# ── Password Hashing (bcrypt) ────────────────────────────────────────────────
def hash_password(pw: str) -> str:
    """Hash password using bcrypt (12 rounds)"""
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(12)).decode()

def verify_password(pw: str, hashed: str) -> bool:
    """Verify password against bcrypt hash"""
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False

# ── DB ────────────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_db() as c:
        c.executescript("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'Sales',
    full_name TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_DATE
);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, client TEXT NOT NULL, manager TEXT NOT NULL,
    budget REAL DEFAULT 0, status TEXT DEFAULT 'Active',
    stage TEXT DEFAULT 'Planning', location TEXT DEFAULT '',
    start_date TEXT, expected_end_date TEXT, notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
    account_type TEXT NOT NULL, parent_code TEXT,
    is_posting INTEGER DEFAULT 1, normal_balance TEXT DEFAULT 'debit'
);
CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_number TEXT UNIQUE NOT NULL,
    entry_date TEXT NOT NULL, description TEXT NOT NULL,
    reference TEXT DEFAULT '', project_id INTEGER,
    created_by TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);
CREATE TABLE IF NOT EXISTS journal_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    description TEXT DEFAULT '',
    debit REAL DEFAULT 0, credit REAL DEFAULT 0,
    FOREIGN KEY(entry_id) REFERENCES journal_entries(id) ON DELETE CASCADE,
    FOREIGN KEY(account_id) REFERENCES accounts(id)
);
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER, unit_number TEXT NOT NULL,
    unit_type TEXT NOT NULL, floor INTEGER DEFAULT 0,
    area_sqm REAL DEFAULT 0, price REAL DEFAULT 0,
    status TEXT DEFAULT 'Available', description TEXT DEFAULT '',
    FOREIGN KEY(project_id) REFERENCES projects(id)
);
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL, national_id TEXT DEFAULT '',
    phone TEXT DEFAULT '', email TEXT DEFAULT '',
    address TEXT DEFAULT '', notes TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_DATE
);
CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_number TEXT UNIQUE NOT NULL,
    client_id INTEGER NOT NULL, property_id INTEGER NOT NULL,
    contract_type TEXT DEFAULT 'Sale',
    total_price REAL NOT NULL, down_payment REAL DEFAULT 0,
    signing_date TEXT, delivery_date TEXT DEFAULT '',
    status TEXT DEFAULT 'Active', notes TEXT DEFAULT '',
    FOREIGN KEY(client_id) REFERENCES clients(id),
    FOREIGN KEY(property_id) REFERENCES properties(id)
);
CREATE TABLE IF NOT EXISTS installments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    due_date TEXT NOT NULL, amount REAL NOT NULL,
    paid_date TEXT DEFAULT '', status TEXT DEFAULT 'Pending',
    notes TEXT DEFAULT '',
    FOREIGN KEY(contract_id) REFERENCES contracts(id)
);
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, department TEXT DEFAULT '',
    job_title TEXT DEFAULT '', salary REAL DEFAULT 0,
    hire_date TEXT DEFAULT CURRENT_DATE, phone TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT, action TEXT, details TEXT,
    logged_at TEXT DEFAULT CURRENT_TIMESTAMP
);
        """)
        # Seed admin
        row = c.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        if not row:
            c.execute("INSERT INTO users (username,password_hash,role,full_name) VALUES(?,?,?,?)",
                      ("admin", hash_password("1234"), "Admin", "مدير النظام"))
        # Seed accounts
        if not c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]:
            seed_accounts(c)

DEFAULT_ACCOUNTS = [
    # ═══════════════════════════════════════════════════════════
    # 1. الأصول (Assets)
    # ═══════════════════════════════════════════════════════════
    ("1000","الأصول","Group",None,"debit"),

    # 11 - الأصول المتداولة
    ("1100","الأصول المتداولة","Header","1000","debit"),

    # 111 - النقدية وما يعادلها
    ("1110","النقدية وما يعادلها","Header","1100","debit"),
    ("1111","الصندوق الرئيسي","Posting","1110","debit"),
    ("1112","صندوق العمليات اليومية","Posting","1110","debit"),
    ("1113","الصندوق الصغير (بتي كاش)","Posting","1110","debit"),

    # 112 - البنوك
    ("1120","حسابات البنوك","Header","1100","debit"),
    ("1121","البنك الأهلي المصري - جاري","Posting","1120","debit"),
    ("1122","البنك الأهلي المصري - توفير","Posting","1120","debit"),
    ("1123","بنك القاهرة - جاري","Posting","1120","debit"),
    ("1124","بنك مصر - جاري","Posting","1120","debit"),
    ("1125","بنك الإسكندرية","Posting","1120","debit"),
    ("1126","البنك التجاري الدولي CIB","Posting","1120","debit"),
    ("1127","بنوك أخرى","Posting","1120","debit"),

    # 113 - الذمم المدينة (العملاء)
    ("1130","الذمم المدينة والعملاء","Header","1100","debit"),
    ("1131","عملاء مبيعات الوحدات السكنية","Posting","1130","debit"),
    ("1132","عملاء مبيعات الوحدات التجارية","Posting","1130","debit"),
    ("1133","عملاء مبيعات الأراضي","Posting","1130","debit"),
    ("1134","عملاء الإيجارات","Posting","1130","debit"),
    ("1135","عملاء خدمات إدارة الأملاك","Posting","1130","debit"),
    ("1136","شيكات وكمبيالات مستحقة التحصيل","Posting","1130","debit"),
    ("1137","مخصص الديون المشكوك في تحصيلها","Posting","1130","credit"),

    # 114 - المدفوعات المقدمة والمصروفات المدفوعة مسبقاً
    ("1140","المدفوعات المقدمة","Header","1100","debit"),
    ("1141","دفعات مقدمة للموردين","Posting","1140","debit"),
    ("1142","دفعات مقدمة للمقاولين","Posting","1140","debit"),
    ("1143","تأمينات مدفوعة مسبقاً","Posting","1140","debit"),
    ("1144","إيجارات مكاتب مدفوعة مسبقاً","Posting","1140","debit"),
    ("1145","اشتراكات ورسوم مدفوعة مسبقاً","Posting","1140","debit"),

    # 115 - المخزون
    ("1150","المخزون والبضاعة","Header","1100","debit"),
    ("1151","مخزون مواد البناء والإنشاء","Posting","1150","debit"),
    ("1152","مخزون أصناف التشطيب والديكور","Posting","1150","debit"),
    ("1153","مخزون قطع غيار المعدات","Posting","1150","debit"),
    ("1154","مخزون مواد الصيانة","Posting","1150","debit"),

    # 116 - الاستثمارات قصيرة الأجل
    ("1160","الاستثمارات قصيرة الأجل","Header","1100","debit"),
    ("1161","أذونات خزانة وودائع بنكية","Posting","1160","debit"),
    ("1162","أوراق مالية متداولة","Posting","1160","debit"),

    # 117 - حسابات تحت التسوية
    ("1170","حسابات تحت التسوية والمتنوعة","Header","1100","debit"),
    ("1171","ضريبة القيمة المضافة المدفوعة (مدخلات)","Posting","1170","debit"),
    ("1172","ضريبة المبيعات المحصلة مقدماً","Posting","1170","debit"),
    ("1173","أمانات وتأمينات مدفوعة","Posting","1170","debit"),
    ("1174","حسابات داخلية تحت التسوية","Posting","1170","debit"),
    ("1175","مصروفات إنشاء تحت التوزيع","Posting","1170","debit"),

    # 12 - الأصول غير المتداولة / الثابتة
    ("1200","الأصول الثابتة والطويلة الأجل","Header","1000","debit"),

    # 121 - أراضي وعقارات المشاريع
    ("1210","أراضي ومواقع المشاريع","Header","1200","debit"),
    ("1211","أراضي مشاريع قيد التطوير","Posting","1210","debit"),
    ("1212","أراضي محجوزة للتطوير المستقبلي","Posting","1210","debit"),
    ("1213","أراضي مبنية (عقارات مكتملة)","Posting","1210","debit"),
    ("1214","تكلفة إعداد وتجهيز الأراضي","Posting","1210","debit"),

    # 122 - مشاريع قيد الإنشاء
    ("1220","مشاريع قيد الإنشاء والتطوير","Header","1200","debit"),
    ("1221","تكاليف إنشاء - المشروع الأول","Posting","1220","debit"),
    ("1222","تكاليف إنشاء - المشروع الثاني","Posting","1220","debit"),
    ("1223","تكاليف إنشاء - المشروع الثالث","Posting","1220","debit"),
    ("1224","تكاليف مشاريع أخرى قيد الإنشاء","Posting","1220","debit"),
    ("1225","فوائد رأسمالية محتسبة على المشاريع","Posting","1220","debit"),

    # 123 - العقارات الاستثمارية المكتملة
    ("1230","العقارات الاستثمارية المكتملة","Header","1200","debit"),
    ("1231","وحدات سكنية استثمارية للإيجار","Posting","1230","debit"),
    ("1232","وحدات تجارية استثمارية للإيجار","Posting","1230","debit"),
    ("1233","مبانٍ إدارية للإيجار","Posting","1230","debit"),
    ("1234","مستودعات ومخازن للإيجار","Posting","1230","debit"),

    # 124 - الأصول الثابتة التشغيلية
    ("1240","الأصول الثابتة التشغيلية","Header","1200","debit"),
    ("1241","مباني ومكاتب الشركة","Posting","1240","debit"),
    ("1242","معدات الإنشاء والرفع والحفر","Posting","1240","debit"),
    ("1243","آليات ومركبات العمل","Posting","1240","debit"),
    ("1244","أثاث ومعدات مكتبية وإدارية","Posting","1240","debit"),
    ("1245","أجهزة حاسب آلي وبرمجيات","Posting","1240","debit"),
    ("1246","أجهزة ومعدات مساحة وهندسية","Posting","1240","debit"),

    # 125 - مجمع الإهلاك (بالسالب)
    ("1250","مجمع الإهلاك المتراكم","Header","1200","credit"),
    ("1251","مجمع إهلاك - المباني والعقارات","Posting","1250","credit"),
    ("1252","مجمع إهلاك - معدات الإنشاء","Posting","1250","credit"),
    ("1253","مجمع إهلاك - الآليات والمركبات","Posting","1250","credit"),
    ("1254","مجمع إهلاك - الأثاث والمعدات المكتبية","Posting","1250","credit"),
    ("1255","مجمع إهلاك - الحاسب وتكنولوجيا المعلومات","Posting","1250","credit"),

    # 126 - الأصول غير الملموسة
    ("1260","الأصول غير الملموسة","Header","1200","debit"),
    ("1261","تراخيص البناء والتشغيل","Posting","1260","debit"),
    ("1262","العلامات التجارية وحقوق الملكية الفكرية","Posting","1260","debit"),
    ("1263","برمجيات وأنظمة معلومات","Posting","1260","debit"),
    ("1264","شهرة المحل والسمعة التجارية","Posting","1260","debit"),

    # 127 - استثمارات طويلة الأجل
    ("1270","الاستثمارات طويلة الأجل","Header","1200","debit"),
    ("1271","استثمارات في شركات تابعة","Posting","1270","debit"),
    ("1272","استثمارات في شركات شقيقة","Posting","1270","debit"),
    ("1273","استثمارات عقارية طويلة الأجل","Posting","1270","debit"),

    # ═══════════════════════════════════════════════════════════
    # 2. الالتزامات (Liabilities)
    # ═══════════════════════════════════════════════════════════
    ("2000","الالتزامات","Group",None,"credit"),

    # 21 - الالتزامات المتداولة
    ("2100","الالتزامات المتداولة","Header","2000","credit"),

    # 211 - الموردون والدائنون
    ("2110","الموردون والدائنون التجاريون","Header","2100","credit"),
    ("2111","موردو مواد البناء والإنشاء","Posting","2110","credit"),
    ("2112","موردو التشطيبات والديكور","Posting","2110","credit"),
    ("2113","موردون آخرون محليون","Posting","2110","credit"),
    ("2114","موردون أجانب","Posting","2110","credit"),
    ("2115","أوراق الدفع (كمبيالات وشيكات مستحقة)","Posting","2110","credit"),

    # 212 - المقاولون الدائنون
    ("2120","المقاولون الدائنون","Header","2100","credit"),
    ("2121","مقاولو الإنشاء الرئيسيون","Posting","2120","credit"),
    ("2122","مقاولو الباطن","Posting","2120","credit"),
    ("2123","مقاولو التشطيب والتكييف","Posting","2120","credit"),
    ("2124","مقاولو الكهرباء والسباكة","Posting","2120","credit"),

    # 213 - الالتزامات الضريبية
    ("2130","الالتزامات الضريبية والحكومية","Header","2100","credit"),
    ("2131","ضريبة القيمة المضافة المحصلة (مخرجات)","Posting","2130","credit"),
    ("2132","ضريبة الأرباح التجارية والصناعية","Posting","2130","credit"),
    ("2133","ضريبة كسب العمل (الاستقطاع من الموظفين)","Posting","2130","credit"),
    ("2134","ضريبة الدمغة","Posting","2130","credit"),
    ("2135","رسوم التسجيل والتوثيق العقاري","Posting","2130","credit"),

    # 214 - الالتزامات تجاه الموظفين
    ("2140","الالتزامات تجاه الموظفين","Header","2100","credit"),
    ("2141","رواتب وأجور مستحقة الدفع","Posting","2140","credit"),
    ("2142","مكافآت وحوافز مستحقة","Posting","2140","credit"),
    ("2143","التأمينات الاجتماعية المستحقة","Posting","2140","credit"),
    ("2144","مخصص مكافآت نهاية الخدمة","Posting","2140","credit"),

    # 215 - مقدمات العملاء
    ("2150","مقدمات وعربون العملاء","Header","2100","credit"),
    ("2151","عربون حجز وحدات للبيع","Posting","2150","credit"),
    ("2152","دفعات مقدمة من المشترين","Posting","2150","credit"),
    ("2153","مقدمات عقود الإيجار","Posting","2150","credit"),
    ("2154","تأمينات مستأجرين","Posting","2150","credit"),

    # 216 - قروض وتمويلات قصيرة الأجل
    ("2160","القروض والتمويلات قصيرة الأجل","Header","2100","credit"),
    ("2161","سحب على المكشوف البنكي","Posting","2160","credit"),
    ("2162","قروض بنكية قصيرة الأجل","Posting","2160","credit"),
    ("2163","الجزء الجاري من القروض طويلة الأجل","Posting","2160","credit"),

    # 217 - مستحقات متنوعة
    ("2170","المستحقات والالتزامات المتنوعة","Header","2100","credit"),
    ("2171","مصروفات مستحقة الدفع","Posting","2170","credit"),
    ("2172","دائنون آخرون متنوعون","Posting","2170","credit"),
    ("2173","إيرادات مؤجلة (إيجارات مقبوضة مقدماً)","Posting","2170","credit"),

    # 22 - الالتزامات غير المتداولة
    ("2200","الالتزامات غير المتداولة (طويلة الأجل)","Header","2000","credit"),

    # 221 - القروض طويلة الأجل
    ("2210","القروض البنكية طويلة الأجل","Header","2200","credit"),
    ("2211","قرض البنك الأهلي - تطوير عقاري","Posting","2210","credit"),
    ("2212","قرض بنك القاهرة - إنشاء مشاريع","Posting","2210","credit"),
    ("2213","قرض بنك مصر - تمويل أراضي","Posting","2210","credit"),
    ("2214","تمويل رهن عقاري","Posting","2210","credit"),

    # 222 - سندات وأدوات دين طويلة الأجل
    ("2220","سندات الدين والأدوات المالية","Header","2200","credit"),
    ("2221","سندات قابلة للتداول","Posting","2220","credit"),
    ("2222","التزامات التأجير التمويلي (ليزينج)","Posting","2220","credit"),

    # 223 - مخصصات طويلة الأجل
    ("2230","المخصصات طويلة الأجل","Header","2200","credit"),
    ("2231","مخصص مخاطر وضمانات المشاريع","Posting","2230","credit"),
    ("2232","التزامات بيئية ومجتمعية","Posting","2230","credit"),

    # ═══════════════════════════════════════════════════════════
    # 3. حقوق الملكية (Equity)
    # ═══════════════════════════════════════════════════════════
    ("3000","حقوق الملكية","Group",None,"credit"),

    ("3100","رأس المال","Header","3000","credit"),
    ("3110","رأس المال المدفوع والمصدر","Posting","3100","credit"),
    ("3120","حساب جاري الشركاء","Header","3100","credit"),
    ("3121","حساب جاري الشريك الأول","Posting","3120","debit"),
    ("3122","حساب جاري الشريك الثاني","Posting","3120","debit"),
    ("3123","حساب جاري الشريك الثالث","Posting","3120","debit"),

    ("3200","الاحتياطيات","Header","3000","credit"),
    ("3210","الاحتياطي القانوني (5% من الأرباح الصافية)","Posting","3200","credit"),
    ("3220","الاحتياطي النظامي","Posting","3200","credit"),
    ("3230","الاحتياطي الاختياري العام","Posting","3200","credit"),
    ("3240","احتياطي إعادة تقييم الأصول","Posting","3200","credit"),

    ("3300","الأرباح والخسائر المرحلة","Header","3000","credit"),
    ("3310","أرباح السنوات السابقة المرحلة","Posting","3300","credit"),
    ("3320","توزيعات أرباح على الشركاء","Posting","3300","debit"),

    ("3400","نتائج النشاط الجاري","Header","3000","credit"),
    ("3410","صافي أرباح العام الجاري","Posting","3400","credit"),
    ("3420","سحوبات الشركاء خلال العام","Posting","3400","debit"),

    # ═══════════════════════════════════════════════════════════
    # 4. الإيرادات (Revenue)
    # ═══════════════════════════════════════════════════════════
    ("4000","الإيرادات","Group",None,"credit"),

    # 41 - إيرادات التطوير العقاري (المبيعات)
    ("4100","إيرادات التطوير العقاري والمبيعات","Header","4000","credit"),
    ("4110","مبيعات الوحدات السكنية","Header","4100","credit"),
    ("4111","مبيعات شقق سكنية","Posting","4110","credit"),
    ("4112","مبيعات فيلات ودوبليكس","Posting","4110","credit"),
    ("4113","مبيعات وحدات إدارية سكنية","Posting","4110","credit"),
    ("4120","مبيعات الوحدات التجارية","Header","4100","credit"),
    ("4121","مبيعات محلات تجارية","Posting","4120","credit"),
    ("4122","مبيعات مكاتب إدارية","Posting","4120","credit"),
    ("4123","مبيعات مستودعات ومخازن","Posting","4120","credit"),
    ("4130","مبيعات الأراضي","Header","4100","credit"),
    ("4131","مبيعات أراضي سكنية","Posting","4130","credit"),
    ("4132","مبيعات أراضي تجارية وصناعية","Posting","4130","credit"),
    ("4140","خصومات وحسومات المبيعات","Posting","4100","debit"),
    ("4150","مردودات المبيعات","Posting","4100","debit"),

    # 42 - إيرادات الإيجار وإدارة الأملاك
    ("4200","إيرادات الإيجار وإدارة الأملاك","Header","4000","credit"),
    ("4210","إيجارات الوحدات السكنية","Posting","4200","credit"),
    ("4220","إيجارات الوحدات التجارية","Posting","4200","credit"),
    ("4230","إيجارات المكاتب الإدارية","Posting","4200","credit"),
    ("4240","إيجارات المستودعات والمخازن","Posting","4200","credit"),
    ("4250","رسوم الخدمات المشتركة (صيانة ومرافق)","Posting","4200","credit"),
    ("4260","رسوم موقف السيارات","Posting","4200","credit"),
    ("4270","خصومات الإيجار","Posting","4200","debit"),

    # 43 - إيرادات خدمات إدارة الأملاك والوساطة
    ("4300","إيرادات الخدمات العقارية","Header","4000","credit"),
    ("4310","أتعاب إدارة الأملاك والعقارات","Posting","4300","credit"),
    ("4320","عمولات الوساطة العقارية","Posting","4300","credit"),
    ("4330","أتعاب الاستشارات العقارية والتقييم","Posting","4300","credit"),
    ("4340","إيرادات خدمات الصيانة والتشغيل","Posting","4300","credit"),
    ("4350","رسوم خدمات الأمن والحراسة","Posting","4300","credit"),
    ("4360","رسوم استخراج التراخيص والتوثيق","Posting","4300","credit"),

    # 44 - إيرادات مالية واستثمارية
    ("4400","الإيرادات المالية والاستثمارية","Header","4000","credit"),
    ("4410","فوائد الودائع والأذونات البنكية","Posting","4400","credit"),
    ("4420","عوائد الاستثمارات المالية","Posting","4400","credit"),
    ("4430","أرباح بيع استثمارات","Posting","4400","credit"),
    ("4440","أرباح إعادة تقييم العقارات","Posting","4400","credit"),

    # 45 - إيرادات أخرى وغير متكررة
    ("4500","إيرادات أخرى وغير متكررة","Header","4000","credit"),
    ("4510","أرباح بيع أصول ثابتة","Posting","4500","credit"),
    ("4520","تعويضات التأمين المستلمة","Posting","4500","credit"),
    ("4530","كسب صرف العملات الأجنبية","Posting","4500","credit"),
    ("4540","إيرادات متنوعة غير متكررة","Posting","4500","credit"),
    ("4550","غرامات تأخير محصلة من المتعاقدين","Posting","4500","credit"),

    # ═══════════════════════════════════════════════════════════
    # 5. المصروفات (Expenses)
    # ═══════════════════════════════════════════════════════════
    ("5000","المصروفات وتكاليف النشاط","Group",None,"debit"),

    # 51 - تكلفة المبيعات (تكلفة الإيرادات)
    ("5100","تكلفة المبيعات العقارية","Header","5000","debit"),
    ("5110","تكلفة الوحدات السكنية المباعة","Posting","5100","debit"),
    ("5120","تكلفة الوحدات التجارية المباعة","Posting","5100","debit"),
    ("5130","تكلفة الأراضي المباعة","Posting","5100","debit"),
    ("5140","تكلفة مقدمات البيع المحسوبة","Posting","5100","debit"),

    # 52 - تكاليف الإنشاء والتطوير المباشرة
    ("5200","تكاليف الإنشاء والتطوير المباشرة","Header","5000","debit"),
    ("5210","مستحقات المقاولين","Header","5200","debit"),
    ("5211","مستحقات المقاول الرئيسي للإنشاء","Posting","5210","debit"),
    ("5212","مستحقات مقاولي الباطن","Posting","5210","debit"),
    ("5213","مستحقات مقاولي التشطيب والديكور","Posting","5210","debit"),
    ("5214","مستحقات مقاولي الكهرباء والميكانيكا","Posting","5210","debit"),
    ("5215","مستحقات مقاولي السباكة والصرف","Posting","5210","debit"),
    ("5220","تكاليف مواد البناء","Header","5200","debit"),
    ("5221","الحديد والتسليح وعناصر الخرسانة","Posting","5220","debit"),
    ("5222","الخرسانة الجاهزة والبلوك والطوب","Posting","5220","debit"),
    ("5223","مواد التشطيب (سيراميك، رخام، دهانات)","Posting","5220","debit"),
    ("5224","مواد العزل والحماية","Posting","5220","debit"),
    ("5225","مستلزمات الكهرباء والميكانيكا","Posting","5220","debit"),
    ("5226","مواد السباكة وشبكات المياه","Posting","5220","debit"),
    ("5230","تكاليف هندسية مباشرة","Header","5200","debit"),
    ("5231","مكافآت مشرفي المشاريع والمهندسين","Posting","5230","debit"),
    ("5232","تكاليف الدراسات والتصاميم الهندسية","Posting","5230","debit"),
    ("5233","رسوم استشارات التصميم والمعماريين","Posting","5230","debit"),
    ("5234","تكاليف الرسم والنمذجة والماكيتات","Posting","5230","debit"),
    ("5240","رسوم حكومية وتراخيص البناء","Header","5200","debit"),
    ("5241","رسوم استخراج تراخيص البناء","Posting","5240","debit"),
    ("5242","رسوم المجاورة والتخطيط العمراني","Posting","5240","debit"),
    ("5243","رسوم التسجيل العقاري والتوثيق","Posting","5240","debit"),
    ("5244","رسوم الاتحادات المهنية والانتساب","Posting","5240","debit"),
    ("5250","تكاليف التمويل المرحلية","Header","5200","debit"),
    ("5251","فوائد قروض تمويل الإنشاء","Posting","5250","debit"),
    ("5252","عمولات وأتعاب الترتيب المالي","Posting","5250","debit"),
    ("5253","فوائد قروض شراء الأراضي","Posting","5250","debit"),

    # 53 - مصروفات تشغيلية وإدارية
    ("5300","المصروفات التشغيلية والإدارية","Header","5000","debit"),
    ("5310","الرواتب والأجور والمزايا","Header","5300","debit"),
    ("5311","رواتب الإدارة العليا والتنفيذيين","Posting","5310","debit"),
    ("5312","رواتب موظفي المبيعات والتسويق","Posting","5310","debit"),
    ("5313","رواتب موظفي المحاسبة والمالية","Posting","5310","debit"),
    ("5314","رواتب موظفي الهندسة والمشاريع","Posting","5310","debit"),
    ("5315","رواتب موظفي إدارة الأملاك والتشغيل","Posting","5310","debit"),
    ("5316","رواتب الموظفين الإداريين والدعم","Posting","5310","debit"),
    ("5317","مكافآت وبونص وحوافز الأداء","Posting","5310","debit"),
    ("5318","اشتراكات التأمينات الاجتماعية (حصة الشركة)","Posting","5310","debit"),
    ("5319","التأمين الصحي وتأمين الحياة الجماعي","Posting","5310","debit"),
    ("5320","مصروفات الإيجار والمكاتب","Header","5300","debit"),
    ("5321","إيجار المقر الرئيسي والمكاتب","Posting","5320","debit"),
    ("5322","إيجار مكاتب المبيعات ومراكز العرض","Posting","5320","debit"),
    ("5323","إيجار مواقع ومستودعات التخزين","Posting","5320","debit"),
    ("5330","مصروفات المرافق والخدمات","Header","5300","debit"),
    ("5331","فواتير الكهرباء والطاقة","Posting","5330","debit"),
    ("5332","فواتير المياه والصرف الصحي","Posting","5330","debit"),
    ("5333","مصروفات الاتصالات والإنترنت","Posting","5330","debit"),
    ("5334","الوقود والطاقة للمعدات","Posting","5330","debit"),
    ("5340","مصروفات إدارية عامة","Header","5300","debit"),
    ("5341","قرطاسية ومستلزمات مكتبية","Posting","5340","debit"),
    ("5342","طباعة وتصوير ونسخ المستندات","Posting","5340","debit"),
    ("5343","بريد وشحن وتوصيل","Posting","5340","debit"),
    ("5344","تنقلات وانتقالات الموظفين","Posting","5340","debit"),
    ("5345","سفريات واجتماعات ومؤتمرات","Posting","5340","debit"),
    ("5346","ضيافة واستقبال العملاء","Posting","5340","debit"),
    ("5350","صيانة الأصول والأجهزة","Header","5300","debit"),
    ("5351","صيانة معدات الإنشاء والرفع","Posting","5350","debit"),
    ("5352","صيانة الآليات والمركبات","Posting","5350","debit"),
    ("5353","صيانة أجهزة الحاسب والبرمجيات","Posting","5350","debit"),
    ("5354","صيانة وإصلاح المكاتب والمرافق","Posting","5350","debit"),
    ("5360","الاستشارات المهنية والأتعاب","Header","5300","debit"),
    ("5361","أتعاب المراجعة والمحاسبة القانونية","Posting","5360","debit"),
    ("5362","أتعاب الاستشارات القانونية","Posting","5360","debit"),
    ("5363","أتعاب الاستشارات الضريبية","Posting","5360","debit"),
    ("5364","أتعاب استشارات إدارية وتنظيمية","Posting","5360","debit"),

    # 54 - مصروفات التسويق والمبيعات
    ("5400","مصروفات التسويق والمبيعات","Header","5000","debit"),
    ("5410","الإعلانات والتسويق الرقمي","Header","5400","debit"),
    ("5411","إعلانات التلفزيون والراديو","Posting","5410","debit"),
    ("5412","إعلانات الصحف والمجلات","Posting","5410","debit"),
    ("5413","التسويق الرقمي ووسائل التواصل الاجتماعي","Posting","5410","debit"),
    ("5414","إعلانات الطرق والمجسمات الخارجية","Posting","5410","debit"),
    ("5415","المطبوعات والكتالوجات والبروشورات","Posting","5410","debit"),
    ("5420","عمولات الوسطاء والمسوقين","Posting","5400","debit"),
    ("5430","معارض ومؤتمرات عقارية","Posting","5400","debit"),
    ("5440","هدايا ترويجية وتذكارات للعملاء","Posting","5400","debit"),
    ("5450","تصوير وإنتاج مواد تسويقية","Posting","5400","debit"),
    ("5460","دراسات السوق وأبحاث التسويق","Posting","5400","debit"),

    # 55 - مصروفات مالية وبنكية
    ("5500","المصروفات المالية والبنكية","Header","5000","debit"),
    ("5510","فوائد القروض والتمويلات","Header","5500","debit"),
    ("5511","فوائد القروض البنكية طويلة الأجل","Posting","5510","debit"),
    ("5512","فوائد السحب على المكشوف","Posting","5510","debit"),
    ("5513","فوائد التأجير التمويلي (ليزينج)","Posting","5510","debit"),
    ("5520","عمولات وأتعاب بنكية","Posting","5500","debit"),
    ("5530","خسائر صرف العملات الأجنبية","Posting","5500","debit"),
    ("5540","مصروفات التحوط المالي والمشتقات","Posting","5500","debit"),

    # 56 - الإهلاك والاستهلاك
    ("5600","مصروفات الإهلاك والاستهلاك","Header","5000","debit"),
    ("5610","إهلاك المباني والعقارات التشغيلية","Posting","5600","debit"),
    ("5620","إهلاك معدات الإنشاء والرفع","Posting","5600","debit"),
    ("5630","إهلاك الآليات والمركبات","Posting","5600","debit"),
    ("5640","إهلاك الأثاث والمعدات المكتبية","Posting","5600","debit"),
    ("5650","إهلاك الأصول غير الملموسة والبرمجيات","Posting","5600","debit"),

    # 57 - المخصصات
    ("5700","المخصصات","Header","5000","debit"),
    ("5710","مخصص الديون المشكوك في تحصيلها","Posting","5700","debit"),
    ("5720","مخصص ضمان وصيانة ما بعد البيع","Posting","5700","debit"),
    ("5730","مخصص مخاطر المشاريع والتجاوزات","Posting","5700","debit"),
    ("5740","مخصص الطوارئ وتقلبات الأسعار","Posting","5700","debit"),

    # 58 - الضرائب والرسوم
    ("5800","الضرائب والرسوم الحكومية","Header","5000","debit"),
    ("5810","ضريبة القيمة المضافة غير القابلة للاسترداد","Posting","5800","debit"),
    ("5820","ضريبة الأرباح التجارية والصناعية","Posting","5800","debit"),
    ("5830","ضريبة الدمغة النسبية والنوعية","Posting","5800","debit"),
    ("5840","رسوم التسجيل العقاري والشهر","Posting","5800","debit"),
    ("5850","رسوم الجمارك والاستيراد","Posting","5800","debit"),

    # 59 - مصروفات أخرى وغير متكررة
    ("5900","مصروفات أخرى وغير متكررة","Header","5000","debit"),
    ("5910","خسائر بيع الأصول الثابتة","Posting","5900","debit"),
    ("5920","تبرعات ومساهمات مجتمعية","Posting","5900","debit"),
    ("5930","غرامات وجزاءات","Posting","5900","debit"),
    ("5940","مصروفات تصفية ومشاريع ملغاة","Posting","5900","debit"),
    ("5950","مصروفات متنوعة أخرى","Posting","5900","debit"),
]

def seed_accounts(c):
    for code, name, atype, parent, nb in DEFAULT_ACCOUNTS:
        c.execute("INSERT OR IGNORE INTO accounts (code,name,account_type,parent_code,is_posting,normal_balance) VALUES(?,?,?,?,?,?)",
                  (code, name, atype, parent, 1 if atype=="Posting" else 0, nb))

def log_action(username, action, details=""):
    with get_db() as c:
        c.execute("INSERT INTO activity_log (username,action,details) VALUES(?,?,?)",
                  (username, action, details))

# ── Auth decorators ───────────────────────────────────────────────────────────
ROLE_PAGES = {
    "Admin":     {"dashboard","properties","clients","contracts","installments","hr",
                  "journal","ledger","reports","coa","engineering","analytics","users","settings"},
    "Accountant":{"dashboard","clients","contracts","installments","journal","ledger","reports","coa","analytics"},
    "Engineer":  {"dashboard","properties","engineering","analytics"},
    "HR":        {"dashboard","hr"},
    "Sales":     {"dashboard","properties","clients","contracts","installments","analytics"},
}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("role") not in roles:
                flash("غير مصرح لك بالوصول لهذه الصفحة.", "error")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator

def next_entry_number():
    with get_db() as c:
        last = c.execute("SELECT entry_number FROM journal_entries ORDER BY id DESC LIMIT 1").fetchone()
    if not last:
        return "JE-0001"
    try:
        n = int(last["entry_number"].split("-")[1]) + 1
        return f"JE-{n:04d}"
    except Exception:
        return f"JE-{datetime.now().strftime('%Y%m%d%H%M%S')}"

def mark_overdue():
    today = date.today().isoformat()
    with get_db() as c:
        n = c.execute("UPDATE installments SET status='Overdue' WHERE status='Pending' AND due_date<?", (today,)).rowcount
    return n

def paginate(page=1, per_page=15):
    """Helper for pagination"""
    page = max(1, int(page) if isinstance(page, (int, str)) else 1)
    per_page = min(100, max(1, int(per_page) if isinstance(per_page, (int, str)) else 15))
    offset = (page - 1) * per_page
    return page, per_page, offset

def get_analytics():
    with get_db() as c:
        sm = c.execute("""
            SELECT
                (SELECT COUNT(*) FROM projects) projects,
                (SELECT COUNT(*) FROM projects WHERE status='Active') active_projects,
                (SELECT COUNT(*) FROM employees) employees,
                (SELECT COUNT(*) FROM properties) units,
                (SELECT COUNT(*) FROM properties WHERE status='Available') available,
                (SELECT COUNT(*) FROM properties WHERE status='Sold') sold,
                (SELECT COUNT(*) FROM clients) clients,
                (SELECT COUNT(*) FROM contracts WHERE status='Active') active_contracts,
                (SELECT COUNT(*) FROM installments WHERE status='Overdue') overdue,
                (SELECT COALESCE(SUM(amount),0) FROM installments WHERE status='Overdue') overdue_amount,
                (SELECT COALESCE(SUM(amount),0) FROM installments WHERE status='Paid') collected
        """).fetchone()
        fin = c.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN a.code LIKE '4%' THEN jl.credit-jl.debit ELSE 0 END),0) revenue,
                COALESCE(SUM(CASE WHEN a.code LIKE '5%' THEN jl.debit-jl.credit ELSE 0 END),0) expense
            FROM journal_lines jl
            JOIN journal_entries je ON je.id=jl.entry_id
            JOIN accounts a ON a.id=jl.account_id
        """).fetchone()
        recent_je = c.execute("""
            SELECT je.entry_number,je.entry_date,je.description,
                COALESCE(SUM(jl.debit),0) dr, COALESCE(SUM(jl.credit),0) cr
            FROM journal_entries je
            LEFT JOIN journal_lines jl ON jl.entry_id=je.id
            GROUP BY je.id ORDER BY je.id DESC LIMIT 8
        """).fetchall()
        recent_proj = c.execute("""
            SELECT id,name,status,stage,budget FROM projects ORDER BY id DESC LIMIT 8
        """).fetchall()
        overdue_inst = c.execute("""
            SELECT i.due_date,i.amount,cl.full_name,c.contract_number
            FROM installments i
            JOIN contracts c ON c.id=i.contract_id
            JOIN clients cl ON cl.id=c.client_id
            WHERE i.status='Overdue' ORDER BY i.due_date LIMIT 8
        """).fetchall()
    rev = float(fin["revenue"])
    exp = float(fin["expense"])
    return {
        **dict(sm), "revenue": rev, "expense": exp, "net": rev-exp,
        "recent_je": [dict(r) for r in recent_je],
        "recent_proj": [dict(r) for r in recent_proj],
        "overdue_inst": [dict(r) for r in overdue_inst],
    }

# ══════════════════════════════════════════════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        try:
            username = request.form.get("username","").strip()
            password = request.form.get("password","").strip()
            
            if not username or not password:
                flash("اسم المستخدم وكلمة المرور مطلوبان.", "error")
                return render_template("login.html")
            
            with get_db() as c:
                user = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            
            if user and verify_password(password, user["password_hash"]):
                session["user"] = username
                session["role"] = user["role"]
                session["full_name"] = user["full_name"] or username
                overdue = mark_overdue()
                log_action(username, "login", "تسجيل دخول ناجح")
                logger.info(f"User {username} logged in successfully")
                if overdue:
                    flash(f"⚠️ تنبيه: {overdue} قسط/أقساط متأخرة.", "warning")
                return redirect(url_for("dashboard"))
            
            log_action(username, "login_failed", "محاولة دخول فاشلة")
            logger.warning(f"Failed login attempt for user: {username}")
            flash("❌ اسم المستخدم أو كلمة المرور غير صحيحة.", "error")
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            flash(f"خطأ في تسجيل الدخول: {str(e)}", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    user = session.get("user","")
    log_action(user, "logout")
    session.clear()
    return redirect(url_for("login"))

# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    data = get_analytics()
    return render_template("dashboard.html", data=data)

# ── Properties ────────────────────────────────────────────────────────────────
@app.route("/properties")
@login_required
def properties():
    try:
        kw     = request.args.get("q","").strip()
        status = request.args.get("status","All")
        page = request.args.get("page", 1)
        page, per_page, offset = paginate(page, 15)
        
        with get_db() as c:
            q = f"%{kw}%"
            total = c.execute("""
                SELECT COUNT(*) as cnt FROM properties pr
                LEFT JOIN projects p ON p.id=pr.project_id
                WHERE (pr.unit_number LIKE ? OR pr.unit_type LIKE ? OR COALESCE(p.name,'') LIKE ?)
                AND (? = 'All' OR pr.status=?)
            """, (q,q,q,status,status)).fetchone()["cnt"]
            
            rows = c.execute("""
                SELECT pr.*,COALESCE(p.name,'—') project_name
                FROM properties pr LEFT JOIN projects p ON p.id=pr.project_id
                WHERE (pr.unit_number LIKE ? OR pr.unit_type LIKE ? OR COALESCE(p.name,'') LIKE ?)
                AND (? = 'All' OR pr.status=?)
                ORDER BY pr.id DESC LIMIT ? OFFSET ?
            """, (q,q,q,status,status,per_page,offset)).fetchall()
            
            projects = c.execute("SELECT id,name FROM projects ORDER BY name").fetchall()
        
        total_pages = (total + per_page - 1) // per_page
        return render_template("properties.html", rows=rows, projects=projects,
                               kw=kw, status_filter=status, page=page, total_pages=total_pages)
    except Exception as e:
        logger.error(f"Properties error: {e}")
        flash(f"❌ خطأ في تحميل الوحدات: {str(e)}", "error")
        return redirect(url_for("dashboard"))

@app.route("/properties/add", methods=["POST"])
@login_required
def add_property():
    try:
        d = request.form
        unit_number = d.get("unit_number", "").strip()
        unit_type = d.get("unit_type", "").strip()
        
        if not unit_number or not unit_type:
            flash("رقم الوحدة ونوعها مطلوبان.", "error")
            return redirect(url_for("properties"))
        
        floor = int(d.get("floor", 0))
        area_sqm = float(d.get("area_sqm", 0))
        price = float(d.get("price", 0))
        
        if area_sqm <= 0 or price < 0:
            flash("المساحة والسعر يجب أن تكون قيم صحيحة.", "error")
            return redirect(url_for("properties"))
        
        with get_db() as c:
            c.execute("""INSERT INTO properties (project_id,unit_number,unit_type,floor,area_sqm,price,status,description)
                         VALUES(?,?,?,?,?,?,?,?)""",
                      (d.get("project_id") or None, unit_number, unit_type,
                       floor, area_sqm, price,
                       d.get("status","Available"), d.get("description","")))
        
        log_action(session["user"], "add_property", f"{unit_number} - {unit_type}")
        logger.info(f"Property added: {unit_number}")
        flash("✅ تم إضافة الوحدة بنجاح.","success")
    except ValueError:
        flash("❌ بيانات رقمية غير صحيحة.", "error")
    except Exception as e:
        logger.error(f"Add property error: {e}")
        flash(f"❌ خطأ: {str(e)}", "error")
    
    return redirect(url_for("properties"))

@app.route("/properties/delete/<int:pid>", methods=["POST"])
@login_required
def delete_property(pid):
    with get_db() as c:
        linked = c.execute("SELECT COUNT(*) FROM contracts WHERE property_id=?", (pid,)).fetchone()[0]
        if linked:
            flash("لا يمكن حذف الوحدة — مرتبطة بعقد.","error")
        else:
            c.execute("DELETE FROM properties WHERE id=?", (pid,))
            flash("تم حذف الوحدة.","success")
    return redirect(url_for("properties"))

# ── Clients ───────────────────────────────────────────────────────────────────
@app.route("/clients")
@login_required
def clients():
    try:
        kw = request.args.get("q","").strip()
        page = request.args.get("page", 1)
        page, per_page, offset = paginate(page, 20)
        
        q  = f"%{kw}%"
        with get_db() as c:
            total = c.execute("""
                SELECT COUNT(*) as cnt FROM clients
                WHERE full_name LIKE ? OR national_id LIKE ? OR phone LIKE ? OR email LIKE ?
            """, (q,q,q,q)).fetchone()["cnt"]
            
            rows = c.execute("""
                SELECT * FROM clients
                WHERE full_name LIKE ? OR national_id LIKE ? OR phone LIKE ? OR email LIKE ?
                ORDER BY id DESC LIMIT ? OFFSET ?
            """, (q,q,q,q,per_page,offset)).fetchall()
        
        total_pages = (total + per_page - 1) // per_page
        return render_template("clients.html", rows=rows, kw=kw, page=page, total_pages=total_pages)
    except Exception as e:
        logger.error(f"Clients error: {e}")
        flash(f"❌ خطأ في تحميل العملاء: {str(e)}", "error")
        return redirect(url_for("dashboard"))

@app.route("/clients/add", methods=["POST"])
@login_required
def add_client():
    try:
        d = request.form
        full_name = d.get("full_name", "").strip()
        
        if not full_name:
            flash("اسم العميل مطلوب.", "error")
            return redirect(url_for("clients"))
        
        with get_db() as c:
            c.execute("INSERT INTO clients (full_name,national_id,phone,email,address,notes) VALUES(?,?,?,?,?,?)",
                      (full_name,
                       d.get("national_id","").strip(),
                       d.get("phone","").strip(),
                       d.get("email","").strip(),
                       d.get("address","").strip(),
                       d.get("notes","")))
        
        log_action(session["user"], "add_client", full_name)
        logger.info(f"Client added: {full_name}")
        flash("✅ تم إضافة العميل.","success")
    except Exception as e:
        logger.error(f"Add client error: {e}")
        flash(f"❌ خطأ: {str(e)}", "error")
    
    return redirect(url_for("clients"))

@app.route("/clients/delete/<int:cid>", methods=["POST"])
@login_required
def delete_client(cid):
    with get_db() as c:
        if c.execute("SELECT COUNT(*) FROM contracts WHERE client_id=?", (cid,)).fetchone()[0]:
            flash("لا يمكن حذف العميل — مرتبط بعقد.","error")
        else:
            c.execute("DELETE FROM clients WHERE id=?", (cid,))
            flash("تم الحذف.","success")
    return redirect(url_for("clients"))

# ── Contracts ─────────────────────────────────────────────────────────────────
@app.route("/contracts")
@login_required
def contracts():
    try:
        kw     = request.args.get("q","").strip()
        status = request.args.get("status","All")
        page = request.args.get("page", 1)
        page, per_page, offset = paginate(page, 15)
        
        q = f"%{kw}%"
        with get_db() as c:
            total = c.execute("""
                SELECT COUNT(*) as cnt FROM contracts ct
                JOIN clients cl ON cl.id=ct.client_id
                JOIN properties pr ON pr.id=ct.property_id
                LEFT JOIN projects p ON p.id=pr.project_id
                WHERE (ct.contract_number LIKE ? OR cl.full_name LIKE ? OR pr.unit_number LIKE ?)
                AND (?='All' OR ct.status=?)
            """, (q,q,q,status,status)).fetchone()["cnt"]
            
            rows = c.execute("""
                SELECT ct.*,cl.full_name client_name,pr.unit_number,COALESCE(p.name,'—') project_name
                FROM contracts ct
                JOIN clients cl ON cl.id=ct.client_id
                JOIN properties pr ON pr.id=ct.property_id
                LEFT JOIN projects p ON p.id=pr.project_id
                WHERE (ct.contract_number LIKE ? OR cl.full_name LIKE ? OR pr.unit_number LIKE ?)
                AND (?='All' OR ct.status=?)
                ORDER BY ct.id DESC LIMIT ? OFFSET ?
            """, (q,q,q,status,status,per_page,offset)).fetchall()
            
            clients_list = c.execute("SELECT id,full_name FROM clients ORDER BY full_name").fetchall()
            props_list   = c.execute("""
                SELECT pr.id, pr.unit_number || ' — ' || COALESCE(p.name,'') label
                FROM properties pr LEFT JOIN projects p ON p.id=pr.project_id
                WHERE pr.status='Available' ORDER BY pr.unit_number
            """).fetchall()
        
        total_pages = (total + per_page - 1) // per_page
        return render_template("contracts.html", rows=rows, clients_list=clients_list,
                               props_list=props_list, kw=kw, status_filter=status, page=page, total_pages=total_pages)
    except Exception as e:
        logger.error(f"Contracts error: {e}")
        flash(f"❌ خطأ في تحميل العقود: {str(e)}", "error")
        return redirect(url_for("dashboard"))

@app.route("/contracts/add", methods=["POST"])
@login_required
def add_contract():
    try:
        d = request.form
        contract_number = d.get("contract_number", "").strip()
        
        if not contract_number:
            flash("رقم العقد مطلوب.", "error")
            return redirect(url_for("contracts"))
        
        total = float(d.get("total_price", 0))
        down = float(d.get("down_payment", 0))
        prop_id = int(d.get("property_id", 0))
        client_id = int(d.get("client_id", 0))
        
        if total <= 0 or down < 0 or prop_id <= 0 or client_id <= 0:
            flash("❌ بيانات غير صحيحة.", "error")
            return redirect(url_for("contracts"))
        
        if down > total:
            flash("❌ الدفعة المقدمة لا يمكن أن تتجاوز السعر الإجمالي.", "error")
            return redirect(url_for("contracts"))
        
        with get_db() as c:
            new_st = "Sold" if d.get("contract_type","Sale")=="Sale" else "Rented"
            c.execute("UPDATE properties SET status=? WHERE id=?", (new_st, prop_id))
            c.execute("""INSERT INTO contracts (contract_number,client_id,property_id,contract_type,
                         total_price,down_payment,signing_date,delivery_date,notes)
                         VALUES(?,?,?,?,?,?,?,?,?)""",
                      (contract_number, client_id, prop_id, d.get("contract_type","Sale"),
                       total, down, d.get("signing_date",date.today().isoformat()),
                       d.get("delivery_date",""), d.get("notes","")))
        
        log_action(session["user"], "add_contract", contract_number)
        logger.info(f"Contract added: {contract_number}")
        flash("✅ تم إضافة العقد.","success")
    except (ValueError, KeyError) as e:
        logger.error(f"Add contract error: {e}")
        flash(f"❌ بيانات غير صحيحة: {str(e)}","error")
    except Exception as e:
        logger.error(f"Add contract error: {e}")
        flash(f"❌ خطأ: {str(e)}", "error")
    
    return redirect(url_for("contracts"))

@app.route("/contracts/delete/<int:cid>", methods=["POST"])
@login_required
def delete_contract(cid):
    with get_db() as c:
        if c.execute("SELECT COUNT(*) FROM installments WHERE contract_id=?", (cid,)).fetchone()[0]:
            flash("احذف الأقساط أولاً.","error")
        else:
            row = c.execute("SELECT property_id FROM contracts WHERE id=?", (cid,)).fetchone()
            if row: c.execute("UPDATE properties SET status='Available' WHERE id=?", (row["property_id"],))
            c.execute("DELETE FROM contracts WHERE id=?", (cid,))
            flash("تم الحذف.","success")
    return redirect(url_for("contracts"))

# ── Installments ──────────────────────────────────────────────────────────────
@app.route("/installments")
@login_required
def installments():
    try:
        status = request.args.get("status","All")
        kw     = request.args.get("q","").strip()
        page = request.args.get("page", 1)
        page, per_page, offset = paginate(page, 20)
        
        q = f"%{kw}%"
        with get_db() as c:
            total = c.execute("""
                SELECT COUNT(*) as cnt FROM installments i
                JOIN contracts c ON c.id=i.contract_id
                JOIN clients cl ON cl.id=c.client_id
                JOIN properties pr ON pr.id=c.property_id
                WHERE (?='All' OR i.status=?)
                AND (c.contract_number LIKE ? OR cl.full_name LIKE ? OR pr.unit_number LIKE ?)
            """, (status,status,q,q,q)).fetchone()["cnt"]
            
            rows = c.execute("""
                SELECT i.*,c.contract_number,cl.full_name client_name,pr.unit_number
                FROM installments i
                JOIN contracts c ON c.id=i.contract_id
                JOIN clients cl ON cl.id=c.client_id
                JOIN properties pr ON pr.id=c.property_id
                WHERE (?='All' OR i.status=?)
                AND (c.contract_number LIKE ? OR cl.full_name LIKE ? OR pr.unit_number LIKE ?)
                ORDER BY i.due_date ASC LIMIT ? OFFSET ?
            """, (status,status,q,q,q,per_page,offset)).fetchall()
            
            contracts_list = c.execute("""
                SELECT ct.id, ct.contract_number || ' — ' || cl.full_name label
                FROM contracts ct JOIN clients cl ON cl.id=ct.client_id ORDER BY ct.id DESC
            """).fetchall()
        
        total_pages = (total + per_page - 1) // per_page
        return render_template("installments.html", rows=rows,
                               contracts_list=contracts_list, status_filter=status, kw=kw,
                               page=page, total_pages=total_pages)
    except Exception as e:
        logger.error(f"Installments error: {e}")
        flash(f"❌ خطأ في تحميل الأقساط: {str(e)}", "error")
        return redirect(url_for("dashboard"))

@app.route("/installments/add", methods=["POST"])
@login_required
def add_installment():
    d = request.form
    with get_db() as c:
        c.execute("INSERT INTO installments (contract_id,due_date,amount,notes) VALUES(?,?,?,?)",
                  (int(d["contract_id"]), d["due_date"], float(d["amount"]), d.get("notes","")))
    flash("تم إضافة القسط.","success")
    return redirect(url_for("installments"))

@app.route("/installments/generate", methods=["POST"])
@login_required
def generate_installments():
    d = request.form
    contract_id = int(d["contract_id"])
    n = int(d["num"])
    amount_each = float(d["amount_each"])
    first_date  = d["first_date"]
    base = datetime.strptime(first_date, "%Y-%m-%d")
    with get_db() as c:
        for i in range(n):
            m = base.month - 1 + i
            y = base.year + m // 12
            m = m % 12 + 1
            day = min(base.day, calendar.monthrange(y,m)[1])
            due = datetime(y,m,day).strftime("%Y-%m-%d")
            c.execute("INSERT INTO installments (contract_id,due_date,amount) VALUES(?,?,?)",
                      (contract_id, due, amount_each))
    flash(f"تم توليد {n} قسط شهري بنجاح.","success")
    return redirect(url_for("installments"))

@app.route("/installments/pay/<int:iid>", methods=["POST"])
@login_required
def pay_installment(iid):
    paid_date = request.form.get("paid_date", date.today().isoformat())
    with get_db() as c:
        c.execute("UPDATE installments SET status='Paid',paid_date=? WHERE id=?", (paid_date, iid))
    flash("تم تسجيل السداد.","success")
    return redirect(url_for("installments"))

@app.route("/installments/delete/<int:iid>", methods=["POST"])
@login_required
def delete_installment(iid):
    with get_db() as c:
        c.execute("DELETE FROM installments WHERE id=?", (iid,))
    flash("تم الحذف.","success")
    return redirect(url_for("installments"))

# ── Journal Entries ───────────────────────────────────────────────────────────
@app.route("/journal")
@login_required
def journal():
    try:
        kw     = request.args.get("q","").strip()
        from_d = request.args.get("from","")
        to_d   = request.args.get("to","")
        page = request.args.get("page", 1)
        page, per_page, offset = paginate(page, 20)
        
        q = f"%{kw}%"
        params = [q,q]
        date_filter = ""
        if from_d: 
            date_filter += " AND je.entry_date >= ?"; params.append(from_d)
        if to_d:   
            date_filter += " AND je.entry_date <= ?"; params.append(to_d)
        
        with get_db() as c:
            total = c.execute(f"""
                SELECT COUNT(DISTINCT je.id) as cnt FROM journal_entries je
                WHERE (je.entry_number LIKE ? OR je.description LIKE ?) {date_filter}
            """, params).fetchone()["cnt"]
            
            rows = c.execute(f"""
                SELECT je.*,COALESCE(SUM(jl.debit),0) dr,COALESCE(SUM(jl.credit),0) cr
                FROM journal_entries je
                LEFT JOIN journal_lines jl ON jl.entry_id=je.id
                WHERE (je.entry_number LIKE ? OR je.description LIKE ?) {date_filter}
                GROUP BY je.id ORDER BY je.entry_date DESC, je.id DESC
                LIMIT ? OFFSET ?
            """, params + [per_page, offset]).fetchall()
            
            posting = c.execute("SELECT id,code,name FROM accounts WHERE is_posting=1 ORDER BY code").fetchall()
            projects = c.execute("SELECT id,name FROM projects ORDER BY name").fetchall()
        
        posting_list = [{"id": r["id"], "code": r["code"], "name": r["name"]} for r in posting]
        total_pages = (total + per_page - 1) // per_page
        return render_template("journal.html", rows=rows, posting=posting_list,
                               projects=projects, kw=kw, from_d=from_d, to_d=to_d,
                               page=page, total_pages=total_pages)
    except Exception as e:
        logger.error(f"Journal error: {e}")
        flash(f"❌ خطأ في تحميل القيود: {str(e)}", "error")
        return redirect(url_for("dashboard"))

@app.route("/journal/entry/<int:eid>")
@login_required
def journal_entry_detail(eid):
    with get_db() as c:
        entry = c.execute("SELECT * FROM journal_entries WHERE id=?", (eid,)).fetchone()
        lines = c.execute("""
            SELECT jl.*,a.code,a.name acc_name
            FROM journal_lines jl JOIN accounts a ON a.id=jl.account_id
            WHERE jl.entry_id=? ORDER BY jl.id
        """, (eid,)).fetchall()
    if not entry: flash("القيد غير موجود.","error"); return redirect(url_for("journal"))
    return render_template("journal_detail.html", entry=entry, lines=lines)

@app.route("/journal/add", methods=["POST"])
@login_required
def add_journal_entry():
    try:
        d = request.form
        account_ids  = request.form.getlist("account_id[]")
        line_descs   = request.form.getlist("line_desc[]")
        debits       = request.form.getlist("debit[]")
        credits      = request.form.getlist("credit[]")
        lines = []
        total_dr = total_cr = 0.0
        
        for acc_id, ld, dr, cr in zip(account_ids, line_descs, debits, credits):
            if not acc_id: continue
            try:
                dr_f = float(dr or 0)
                cr_f = float(cr or 0)
            except ValueError:
                flash("❌ قيم رقمية غير صحيحة في السطور.", "error")
                return redirect(url_for("journal"))
            
            if dr_f > 0 or cr_f > 0:
                lines.append({"account_id":int(acc_id),"description":ld,"debit":dr_f,"credit":cr_f})
                total_dr += dr_f
                total_cr += cr_f
        
        if not lines:
            flash("❌ أضف سطراً واحداً على الأقل.","error")
            return redirect(url_for("journal"))
        
        if abs(total_dr - total_cr) > 0.005:
            flash(f"❌ القيد غير متوازن — مدين: {total_dr:.2f}  دائن: {total_cr:.2f}","error")
            return redirect(url_for("journal"))
        
        entry_number = next_entry_number()
        with get_db() as c:
            cur = c.execute("""
                INSERT INTO journal_entries (entry_number,entry_date,description,reference,project_id,created_by)
                VALUES(?,?,?,?,?,?)
            """, (entry_number, d.get("entry_date",date.today().isoformat()),
                  d.get("description","").strip(), d.get("reference","").strip(),
                  d.get("project_id") or None, session.get("user","")))
            eid = cur.lastrowid
            for l in lines:
                c.execute("INSERT INTO journal_lines (entry_id,account_id,description,debit,credit) VALUES(?,?,?,?,?)",
                          (eid, l["account_id"], l["description"], l["debit"], l["credit"]))
        
        log_action(session["user"], "post_journal", entry_number)
        logger.info(f"Journal entry posted: {entry_number}")
        flash(f"✅ تم ترحيل القيد {entry_number} بنجاح.","success")
    except Exception as e:
        logger.error(f"Add journal entry error: {e}")
        flash(f"❌ خطأ: {str(e)}", "error")
    
    return redirect(url_for("journal"))

@app.route("/journal/delete/<int:eid>", methods=["POST"])
@login_required
def delete_journal_entry(eid):
    with get_db() as c:
        c.execute("DELETE FROM journal_entries WHERE id=?", (eid,))
    flash("تم حذف القيد.","success")
    return redirect(url_for("journal"))

# ── General Ledger ────────────────────────────────────────────────────────────
@app.route("/ledger")
@login_required
def ledger():
    acc_id = request.args.get("account_id","")
    from_d = request.args.get("from","")
    to_d   = request.args.get("to","")
    params = []
    filters = ""
    if acc_id: filters += " AND jl.account_id=?"; params.append(int(acc_id))
    if from_d: filters += " AND je.entry_date>=?"; params.append(from_d)
    if to_d:   filters += " AND je.entry_date<=?"; params.append(to_d)
    with get_db() as c:
        rows = c.execute(f"""
            SELECT je.entry_date,je.entry_number,je.description entry_desc,
                jl.description line_desc,a.code,a.name acc_name,
                jl.debit,jl.credit,jl.account_id
            FROM journal_lines jl
            JOIN journal_entries je ON je.id=jl.entry_id
            JOIN accounts a ON a.id=jl.account_id
            WHERE 1=1 {filters}
            ORDER BY je.entry_date,je.id
        """, params).fetchall()
        posting = c.execute("SELECT id,code,name FROM accounts WHERE is_posting=1 ORDER BY code").fetchall()
    # running balance
    running = 0.0
    enriched = []
    for r in rows:
        running += r["debit"] - r["credit"]
        enriched.append({**dict(r), "running_bal": running})
    dr_tot = sum(r["debit"]  for r in rows)
    cr_tot = sum(r["credit"] for r in rows)
    return render_template("ledger.html", rows=enriched, posting=posting,
                           sel_account=acc_id, from_d=from_d, to_d=to_d,
                           dr_tot=dr_tot, cr_tot=cr_tot, net=running)

# ══════════════════════════════════════════════════════════════════════════════
#  PDF GENERATION FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def format_currency(amount, currency="ج.م"):
    """Format currency with thousands separator"""
    return f"{currency} {amount:,.2f}"

def get_company_info():
    """Get company information from config"""
    cfg_path = BASE_DIR / "config.json"
    if cfg_path.exists():
        return json.loads(cfg_path.read_text())
    return {"company_name": "شركة إبداع للتطوير العقاري", "currency": "ج.م"}

def calculate_account_balance(conn, account_id, from_date=None, to_date=None):
    """Calculate account balance for a period"""
    params = [account_id]
    date_filter = ""
    if from_date:
        date_filter += " AND je.entry_date >= ?"
        params.append(from_date)
    if to_date:
        date_filter += " AND je.entry_date <= ?"
        params.append(to_date)
    
    result = conn.execute(f"""
        SELECT 
            COALESCE(SUM(jl.debit), 0) total_debit,
            COALESCE(SUM(jl.credit), 0) total_credit
        FROM journal_lines jl
        JOIN journal_entries je ON je.id = jl.entry_id
        WHERE jl.account_id = ? {date_filter}
    """, params).fetchone()
    
    return float(result["total_debit"]) - float(result["total_credit"])

def generate_pdf_header(story, title, report_type, from_date, to_date):
    """Generate common PDF header"""
    styles = get_pdf_styles()
    company = get_company_info()
    
    # Company name
    story.append(Paragraph(company.get("company_name", "شركة إبداع"), styles['ArabicTitle']))
    
    # Report title
    story.append(Paragraph(title, styles['ArabicHeading']))
    
    # Date range
    story.append(Paragraph(f"منذ {from_date} حتى {to_date}", styles['ArabicSmall']))
    story.append(Paragraph(f"تاريخ الطباعة: {date.today().isoformat()}", styles['ArabicSmall']))
    story.append(Spacer(1, 20))

def create_pdf_response(pdf_content, filename):
    """Create PDF response for download"""
    response = make_response(pdf_content)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response

# ── Financial Reports ─────────────────────────────────────────────────────────
@app.route("/reports")
@login_required
def reports():
    rpt    = request.args.get("type","trial_balance")
    from_d = request.args.get("from", f"{date.today().year}-01-01")
    to_d   = request.args.get("to",   date.today().isoformat())
    params = []
    date_filter = ""
    if from_d: date_filter += " AND je.entry_date>=?"; params.append(from_d)
    if to_d:   date_filter += " AND je.entry_date<=?"; params.append(to_d)
    
    with get_db() as c:
        # Get all posting accounts with balances
        balances = c.execute(f"""
            SELECT a.id,a.code,a.name,a.account_type,a.normal_balance,
                COALESCE(SUM(jl.debit),0)  total_debit,
                COALESCE(SUM(jl.credit),0) total_credit
            FROM accounts a
            LEFT JOIN journal_lines jl ON jl.account_id=a.id
            LEFT JOIN journal_entries je ON je.id=jl.entry_id
            WHERE a.is_posting=1 {date_filter}
            GROUP BY a.id ORDER BY a.code
        """, params).fetchall()
        
        # Calculate income statement items
        revenue = c.execute(f"""
            SELECT COALESCE(SUM(jl.credit - jl.debit), 0) as total
            FROM accounts a
            LEFT JOIN journal_lines jl ON jl.account_id=a.id
            LEFT JOIN journal_entries je ON je.id=jl.entry_id
            WHERE a.code LIKE '4%' {date_filter}
        """).fetchone()[0]
        
        expenses = c.execute(f"""
            SELECT COALESCE(SUM(jl.debit - jl.credit), 0) as total
            FROM accounts a
            LEFT JOIN journal_lines jl ON jl.account_id=a.id
            LEFT JOIN journal_entries je ON je.id=jl.entry_id
            WHERE a.code LIKE '5%' {date_filter}
        """).fetchone()[0]
        
        # Get detailed revenue by type
        revenue_detail = c.execute(f"""
            SELECT a.code, a.name,
                COALESCE(SUM(jl.credit - jl.debit), 0) as total
            FROM accounts a
            LEFT JOIN journal_lines jl ON jl.account_id=a.id
            LEFT JOIN journal_entries je ON je.id=jl.entry_id
            WHERE a.code LIKE '4%' AND a.account_type='Posting' {date_filter}
            GROUP BY a.id ORDER BY a.code
        """).fetchall()
        
        # Get detailed expenses by type
        expense_detail = c.execute(f"""
            SELECT a.code, a.name,
                COALESCE(SUM(jl.debit - jl.credit), 0) as total
            FROM accounts a
            LEFT JOIN journal_lines jl ON jl.account_id=a.id
            LEFT JOIN journal_entries je ON je.id=jl.entry_id
            WHERE a.code LIKE '5%' AND a.account_type='Posting' {date_filter}
            GROUP BY a.id ORDER BY a.code
        """).fetchall()
        
        # Get balance sheet items
        assets = c.execute(f"""
            SELECT a.code, a.name,
                COALESCE(SUM(jl.debit - jl.credit), 0) as balance
            FROM accounts a
            LEFT JOIN journal_lines jl ON jl.account_id=a.id
            LEFT JOIN journal_entries je ON je.id=jl.entry_id
            WHERE a.code LIKE '1%' AND a.account_type='Posting' {date_filter}
            GROUP BY a.id ORDER BY a.code
        """).fetchall()
        
        liabilities = c.execute(f"""
            SELECT a.code, a.name,
                COALESCE(SUM(jl.credit - jl.debit), 0) as balance
            FROM accounts a
            LEFT JOIN journal_lines jl ON jl.account_id=a.id
            LEFT JOIN journal_entries je ON je.id=jl.entry_id
            WHERE a.code LIKE '2%' AND a.account_type='Posting' {date_filter}
            GROUP BY a.id ORDER BY a.code
        """).fetchall()
        
        equity = c.execute(f"""
            SELECT a.code, a.name,
                COALESCE(SUM(jl.credit - jl.debit), 0) as balance
            FROM accounts a
            LEFT JOIN journal_lines jl ON jl.account_id=a.id
            LEFT JOIN journal_entries je ON je.id=jl.entry_id
            WHERE a.code LIKE '3%' AND a.account_type='Posting' {date_filter}
            GROUP BY a.id ORDER BY a.code
        """).fetchall()
    
    balances = [dict(b) for b in balances]
    for b in balances:
        b["balance"] = b["total_debit"] - b["total_credit"]
    
    net_profit = float(revenue) - float(expenses)
    
    income_data = {
        'revenue': float(revenue),
        'expenses': float(expenses),
        'net_profit': net_profit,
        'revenue_detail': [dict(r) for r in revenue_detail],
        'expense_detail': [dict(e) for e in expense_detail]
    }
    
    balance_data = {
        'assets': [dict(a) for a in assets],
        'liabilities': [dict(l) for l in liabilities],
        'equity': [dict(e) for e in equity],
        'net_profit': net_profit
    }
    
    return render_template("reports.html", rpt=rpt, balances=balances,
                           from_d=from_d, to_d=to_d,
                           income_data=income_data,
                           balance_data=balance_data)

# ── PDF Downloads ──────────────────────────────────────────────────────────────
@app.route("/reports/pdf/<report_type>")
@login_required
def download_report_pdf(report_type):
    """Generate PDF for various reports"""
    from_d = request.args.get("from", f"{date.today().year}-01-01")
    to_d   = request.args.get("to",   date.today().isoformat())
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                          rightMargin=20*mm, leftMargin=20*mm,
                          topMargin=20*mm, bottomMargin=20*mm)
    
    styles = get_pdf_styles()
    story = []
    company = get_company_info()
    
    try:
        if report_type == "trial_balance":
            title = "ميزان المراجعة"
            generate_pdf_header(story, title, report_type, from_d, to_d)
            
            with get_db() as c:
                balances = c.execute("""
                    SELECT a.code, a.name, a.account_type,
                        COALESCE(SUM(jl.debit), 0) total_debit,
                        COALESCE(SUM(jl.credit), 0) total_credit
                    FROM accounts a
                    LEFT JOIN journal_lines jl ON jl.account_id=a.id
                    LEFT JOIN journal_entries je ON je.id=jl.entry_id
                    WHERE a.is_posting=1
                    AND (je.entry_date IS NULL OR (je.entry_date >= ? AND je.entry_date <= ?))
                    GROUP BY a.id ORDER BY a.code
                """, (from_d, to_d)).fetchall()
            
            # Create table
            table_data = [["الرقم", "اسم الحساب", "مدين", "دائن"]]
            total_dr, total_cr = 0, 0
            
            for b in balances:
                bal = float(b["total_debit"]) - float(b["total_credit"])
                total_dr += float(b["total_debit"])
                total_cr += float(b["total_credit"])
                table_data.append([
                    str(b["code"]),
                    b["name"][:40] if b["name"] else "",
                    f"{float(b['total_debit']):,.2f}",
                    f"{float(b['total_credit']):,.2f}"
                ])
            
            # Totals
            table_data.append(["", "الإجمالي", f"{total_dr:,.2f}", f"{total_cr:,.2f}"])
            
            table = Table(table_data, colWidths=[50, 200, 80, 80])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2874a6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#d5dbdb')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            story.append(table)
            
        elif report_type == "income_statement":
            title = "قائمة الدخل"
            generate_pdf_header(story, title, report_type, from_d, to_d)
            
            with get_db() as c:
                # Revenue
                revenue = c.execute("""
                    SELECT a.code, a.name,
                        COALESCE(SUM(jl.credit - jl.debit), 0) as total
                    FROM accounts a
                    LEFT JOIN journal_lines jl ON jl.account_id=a.id
                    LEFT JOIN journal_entries je ON je.id=jl.entry_id
                    WHERE a.code LIKE '4%' AND a.account_type='Posting'
                    AND (je.entry_date IS NULL OR (je.entry_date >= ? AND je.entry_date <= ?))
                    GROUP BY a.id ORDER BY a.code
                """, (from_d, to_d)).fetchall()
                
                # Expenses
                expenses = c.execute("""
                    SELECT a.code, a.name,
                        COALESCE(SUM(jl.debit - jl.credit), 0) as total
                    FROM accounts a
                    LEFT JOIN journal_lines jl ON jl.account_id=a.id
                    LEFT JOIN journal_entries je ON je.id=jl.entry_id
                    WHERE a.code LIKE '5%' AND a.account_type='Posting'
                    AND (je.entry_date IS NULL OR (je.entry_date >= ? AND je.entry_date <= ?))
                    GROUP BY a.id ORDER BY a.code
                """, (from_d, to_d)).fetchall()
            
            total_revenue = 0
            total_expenses = 0
            
# Revenue section
            story.append(Paragraph("أولاً: الإيرادات", styles['ArabicBold']))
            story.append(Spacer(1, 10))
            
            table_data = [["الوصف", "المبلغ"]]
            for r in revenue:
                amt = float(r["total"])
                total_revenue += amt
                table_data.append([r["name"][:50] if r["name"] else "", f"{amt:,.2f}"])
            
            table_data.append(["إجمالي الإيرادات", f"{total_revenue:,.2f}"])
            
            table = Table(table_data, colWidths=[250, 100])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e8449')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#d5f5e3')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            story.append(table)
            story.append(Spacer(1, 20))
            
            # Expenses section
            story.append(Paragraph("ثانياً: المصروفات", styles['ArabicBold']))
            story.append(Spacer(1, 10))
            
            table_data = [["الوصف", "المبلغ"]]
            for e in expenses:
                amt = float(e["total"])
                total_expenses += amt
                table_data.append([e["name"][:50] if e["name"] else "", f"{amt:,.2f}"])
            
            table_data.append(["إجمالي المصروفات", f"{total_expenses:,.2f}"])
            
            table = Table(table_data, colWidths=[250, 100])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c0392b')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fadbd8')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            story.append(table)
            story.append(Spacer(1, 30))
            
            # Net profit/loss
            net = total_revenue - total_expenses
            net_text = "صافي الربح" if net >= 0 else "صافي الخسارة"
            story.append(Paragraph(f"{net_text}: {abs(net):,.2f} {company.get('currency', 'ج.م')}", styles['ArabicTitle']))
            
        elif report_type == "balance_sheet":
            title = "الميزانية العمومية"
            generate_pdf_header(story, title, report_type, from_d, to_d)
            
            with get_db() as c:
                # Assets
                assets = c.execute("""
                    SELECT a.code, a.name,
                        COALESCE(SUM(jl.debit - jl.credit), 0) as balance
                    FROM accounts a
                    LEFT JOIN journal_lines jl ON jl.account_id=a.id
                    LEFT JOIN journal_entries je ON je.id=jl.entry_id
                    WHERE a.code LIKE '1%' AND a.account_type='Posting'
                    AND (je.entry_date IS NULL OR (je.entry_date >= ? AND je.entry_date <= ?))
                    GROUP BY a.id ORDER BY a.code
                """, (from_d, to_d)).fetchall()
                
                # Liabilities
                liabilities = c.execute("""
                    SELECT a.code, a.name,
                        COALESCE(SUM(jl.credit - jl.debit), 0) as balance
                    FROM accounts a
                    LEFT JOIN journal_lines jl ON jl.account_id=a.id
                    LEFT JOIN journal_entries je ON je.id=jl.entry_id
                    WHERE a.code LIKE '2%' AND a.account_type='Posting'
                    AND (je.entry_date IS NULL OR (je.entry_date >= ? AND je.entry_date <= ?))
                    GROUP BY a.id ORDER BY a.code
                """, (from_d, to_d)).fetchall()
                
                # Equity
                equity = c.execute("""
                    SELECT a.code, a.name,
                        COALESCE(SUM(jl.credit - jl.debit), 0) as balance
                    FROM accounts a
                    LEFT JOIN journal_lines jl ON jl.account_id=a.id
                    LEFT JOIN journal_entries je ON je.id=jl.entry_id
                    WHERE a.code LIKE '3%' AND a.account_type='Posting'
                    AND (je.entry_date IS NULL OR (je.entry_date >= ? AND je.entry_date <= ?))
                    GROUP BY a.id ORDER BY a.code
                """, (from_d, to_d)).fetchall()
                
                # Net profit for the period
                net_profit = c.execute("""
                    SELECT (
                        COALESCE(SUM(CASE WHEN a.code LIKE '4%' THEN jl.credit - jl.debit ELSE 0 END), 0) -
                        COALESCE(SUM(CASE WHEN a.code LIKE '5%' THEN jl.debit - jl.credit ELSE 0 END), 0)
                    ) as net
                    FROM accounts a
                    LEFT JOIN journal_lines jl ON jl.account_id=a.id
                    LEFT JOIN journal_entries je ON je.id=jl.entry_id
                    WHERE je.entry_date >= ? AND je.entry_date <= ?
                """, (from_d, to_d)).fetchone()[0] or 0
            
            total_assets = 0
            total_liabilities = 0
            total_equity = 0
            
            # Assets section
            story.append(Paragraph("الأصول", styles['ArabicBold']))
            story.append(Spacer(1, 10))
            
            table_data = [["الوصف", "المبلغ"]]
            for a in assets:
                amt = float(a["balance"])
                total_assets += amt
                if abs(amt) > 0.01:
                    table_data.append([a["name"][:50] if a["name"] else "", f"{amt:,.2f}"])
            
            table_data.append(["إجمالي الأصول", f"{total_assets:,.2f}"])
            
            table = Table(table_data, colWidths=[250, 100])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2874a6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#d5dbdb')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            story.append(table)
            story.append(Spacer(1, 20))
            
            # Liabilities section
            story.append(Paragraph("الالتزامات", styles['ArabicBold']))
            story.append(Spacer(1, 10))
            
            table_data = [["الوصف", "المبلغ"]]
            for l in liabilities:
                amt = float(l["balance"])
                total_liabilities += amt
                if abs(amt) > 0.01:
                    table_data.append([l["name"][:50] if l["name"] else "", f"{amt:,.2f}"])
            
            table_data.append(["إجمالي الالتزامات", f"{total_liabilities:,.2f}"])
            
            table = Table(table_data, colWidths=[250, 100])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e74c3c')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fadbd8')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            story.append(table)
            story.append(Spacer(1, 20))
            
            # Equity section
            story.append(Paragraph("حقوق الملكية", styles['ArabicBold']))
            story.append(Spacer(1, 10))
            
            table_data = [["الوصف", "المبلغ"]]
            for e in equity:
                amt = float(e["balance"])
                total_equity += amt
                if abs(amt) > 0.01:
                    table_data.append([e["name"][:50] if e["name"] else "", f"{amt:,.2f}"])
            
            # Add net profit to equity
            total_equity += float(net_profit)
            if abs(float(net_profit)) > 0.01:
                table_data.append(["صافي ربح الفترة", f"{float(net_profit):,.2f}"])
            
            table_data.append(["إجمالي حقوق الملكية", f"{total_equity:,.2f}"])
            
            table = Table(table_data, colWidths=[250, 100])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27ae60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#d5f5e3')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            story.append(table)
            story.append(Spacer(1, 30))
            
            # Balance check
            total_liabilities_equity = total_liabilities + total_equity
            story.append(Paragraph(f"إجمالي الالتزامات وحقوق الملكية: {total_liabilities_equity:,.2f}", styles['ArabicBold']))
            if abs(total_assets - total_liabilities_equity) < 0.01:
                story.append(Paragraph("✓ الميزانية متوازنة", styles['ArabicNormal']))
            else:
                story.append(Paragraph(f"✗ الفرق: {abs(total_assets - total_liabilities_equity):,.2f}", styles['ArabicNormal']))
        
        elif report_type == "clients":
            title = "تقرير العملاء"
            generate_pdf_header(story, title, report_type, from_d, to_d)
            
            with get_db() as c:
                clients_data = c.execute("""
                    SELECT c.*, COUNT(ct.id) as contracts_count,
                        COALESCE(SUM(ct.total_price), 0) as total_sales
                    FROM clients c
                    LEFT JOIN contracts ct ON ct.client_id = c.id
                    GROUP BY c.id ORDER BY c.full_name
                """).fetchall()
            
            table_data = [["الاسم", "التليفون", "العقدات", "إجمالي المبيعات"]]
            for cl in clients_data:
                table_data.append([
                    cl["full_name"][:30] if cl["full_name"] else "",
                    cl["phone"] or "",
                    str(cl["contracts_count"]),
                    f"{float(cl['total_sales']):,.2f}"
                ])
            
            table = Table(table_data, colWidths=[100, 80, 60, 80])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8e44ad')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            story.append(table)
            
        elif report_type == "properties":
            title = "تقرير الوحدات العقارية"
            generate_pdf_header(story, title, report_type, from_d, to_d)
            
            with get_db() as c:
                props = c.execute("""
                    SELECT pr.*, p.name as project_name,
                        COALESCE(pp.name, '') as status_label
                    FROM properties pr
                    LEFT JOIN projects p ON p.id = pr.project_id
                    ORDER BY pr.status, pr.unit_number
                """).fetchall()
            
            table_data = [["الوحدة", "النوع", "المساحة", "السعر", "الحالة"]]
            for pr in props:
                table_data.append([
                    pr["unit_number"],
                    pr["unit_type"][:15] if pr["unit_type"] else "",
                    f"{float(pr['area_sqm']):,.0f}",
                    f"{float(pr['price']):,.2f}",
                    pr["status"]
                ])
            
            table = Table(table_data, colWidths=[60, 80, 60, 80, 70])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16a085')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            story.append(table)
            
        elif report_type == "installments":
            title = "تقرير الأقساط"
            generate_pdf_header(story, title, report_type, from_d, to_d)
            
            with get_db() as c:
                inst = c.execute("""
                    SELECT i.*, c.contract_number, cl.full_name client_name
                    FROM installments i
                    JOIN contracts c ON c.id = i.contract_id
                    JOIN clients cl ON cl.id = c.client_id
                    ORDER BY i.due_date
                """).fetchall()
            
            table_data = [["رقم العقد", "العميل", "تاريخ الاستحقاق", "المبلغ", "الحالة"]]
            for i in inst:
                table_data.append([
                    i["contract_number"],
                    i["client_name"][:20] if i["client_name"] else "",
                    i["due_date"],
                    f"{float(i['amount']):,.2f}",
                    i["status"]
                ])
            
            table = Table(table_data, colWidths=[70, 100, 70, 70, 60])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#d35400')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            story.append(table)
        
        elif report_type == "employees":
            title = "تقرير الموظفين"
            generate_pdf_header(story, title, report_type, from_d, to_d)
            
            with get_db() as c:
                emps = c.execute("SELECT * FROM employees ORDER BY department, name").fetchall()
            
            table_data = [["الاسم", "القسم", "المسمى الوظيفي", "الراتب", "تاريخ التعيين"]]
            for e in emps:
                table_data.append([
                    e["name"][:25] if e["name"] else "",
                    e["department"][:15] if e["department"] else "",
                    e["job_title"][:15] if e["job_title"] else "",
                    f"{float(e['salary']):,.2f}",
                    e["hire_date"]
                ])
            
            table = Table(table_data, colWidths=[90, 70, 80, 70, 70])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            story.append(table)
        
        elif report_type == "projects":
            title = "تقرير المشاريع"
            generate_pdf_header(story, title, report_type, from_d, to_d)
            
            with get_db() as c:
                projs = c.execute("""
                    SELECT p.*, COUNT(pr.id) as units_count,
                        SUM(CASE WHEN pr.status='Sold' THEN 1 ELSE 0 END) as sold_count
                    FROM projects p
                    LEFT JOIN properties pr ON pr.project_id = p.id
                    GROUP BY p.id ORDER BY p.name
                """).fetchall()
            
            table_data = [["المشروع", "العميل", "الحالة", "المرحلة", "الوحدات", "المباعة"]]
            for p in projs:
                table_data.append([
                    p["name"][:25] if p["name"] else "",
                    p["client"][:15] if p["client"] else "",
                    p["status"],
                    p["stage"][:15] if p["stage"] else "",
                    str(p["units_count"] or 0),
                    str(p["sold_count"] or 0)
                ])
            
            table = Table(table_data, colWidths=[80, 70, 50, 60, 50, 50])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            story.append(table)
        
        elif report_type == "coa":
            title = "دليل الحسابات"
            generate_pdf_header(story, title, report_type, from_d, to_d)
            
            with get_db() as c:
                accounts_data = c.execute("""
                    SELECT code, name, account_type, normal_balance
                    FROM accounts ORDER BY code
                """).fetchall()
            
            table_data = [["رقم الحساب", "اسم الحساب", "النوع", "الطبيعة"]]
            for a in accounts_data:
                type_label = {"Group": "مجموعة", "Header": "رأس", "Posting": "قيد"}.get(a["account_type"], a["account_type"])
                normal_label = {"debit": "مدين", "credit": "دائن"}.get(a["normal_balance"], a["normal_balance"])
                table_data.append([a["code"], a["name"][:40] if a["name"] else "", type_label, normal_label])
            
            table = Table(table_data, colWidths=[60, 180, 50, 50])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7f8c8d')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            story.append(table)
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        filename = f"{report_type}_{from_d}_{to_d}.pdf"
        return create_pdf_response(buffer.getvalue(), filename)
        
    except Exception as e:
        return f"خطأ في إنشاء PDF: {str(e)}", 500

# ── Chart of Accounts ─────────────────────────────────────────────────────────
@app.route("/coa")
@login_required
def coa():
    kw = request.args.get("q","")
    q  = f"%{kw}%"
    with get_db() as c:
        rows = c.execute("SELECT * FROM accounts WHERE code LIKE ? OR name LIKE ? ORDER BY code", (q,q)).fetchall()
        parents = c.execute("SELECT code,name FROM accounts WHERE account_type!='Posting' ORDER BY code").fetchall()
    return render_template("coa.html", rows=rows, parents=parents, kw=kw)

@app.route("/coa/add", methods=["POST"])
@login_required
def add_account():
    d = request.form
    nb = "credit" if d["code"][:1] in ("2","3","4") else "debit"
    with get_db() as c:
        c.execute("""INSERT INTO accounts (code,name,account_type,parent_code,is_posting,normal_balance)
                     VALUES(?,?,?,?,?,?)""",
                  (d["code"], d["name"], d["account_type"],
                   d.get("parent_code") or None,
                   1 if d["account_type"]=="Posting" else 0, d.get("normal_balance",nb)))
    flash("تم إضافة الحساب.","success")
    return redirect(url_for("coa"))

@app.route("/coa/delete/<int:aid>", methods=["POST"])
@login_required
def delete_account(aid):
    with get_db() as c:
        if c.execute("SELECT COUNT(*) FROM journal_lines WHERE account_id=?", (aid,)).fetchone()[0]:
            flash("الحساب مرتبط بقيود — لا يمكن حذفه.","error")
        else:
            c.execute("DELETE FROM accounts WHERE id=?", (aid,))
            flash("تم الحذف.","success")
    return redirect(url_for("coa"))

# ── Engineering / Projects ────────────────────────────────────────────────────
@app.route("/engineering")
@login_required
def engineering():
    kw     = request.args.get("q","")
    status = request.args.get("status","All")
    q = f"%{kw}%"
    with get_db() as c:
        rows = c.execute("""
            SELECT p.*, COUNT(pr.id) units_count,
                SUM(CASE WHEN pr.status='Sold' THEN 1 ELSE 0 END) sold_count
            FROM projects p
            LEFT JOIN properties pr ON pr.project_id=p.id
            WHERE (p.name LIKE ? OR p.client LIKE ? OR p.location LIKE ?)
            AND (?='All' OR p.status=?)
            GROUP BY p.id ORDER BY p.id DESC
        """, (q,q,q,status,status)).fetchall()
    return render_template("engineering.html", rows=rows, kw=kw, status_filter=status)

@app.route("/engineering/add", methods=["POST"])
@login_required
def add_project():
    d = request.form
    with get_db() as c:
        c.execute("""INSERT INTO projects (name,client,manager,budget,status,stage,location,start_date,expected_end_date,notes)
                     VALUES(?,?,?,?,?,?,?,?,?,?)""",
                  (d["name"],d.get("client",""),d.get("manager",""),float(d.get("budget",0)),
                   d.get("status","Active"),d.get("stage","Planning"),d.get("location",""),
                   d.get("start_date",date.today().isoformat()),d.get("expected_end_date",""),d.get("notes","")))
    flash("تم إضافة المشروع.","success")
    return redirect(url_for("engineering"))

@app.route("/engineering/delete/<int:pid>", methods=["POST"])
@login_required
def delete_project(pid):
    with get_db() as c:
        c.execute("DELETE FROM projects WHERE id=?", (pid,))
    flash("تم الحذف.","success")
    return redirect(url_for("engineering"))

# ── HR ────────────────────────────────────────────────────────────────────────
@app.route("/hr")
@login_required
def hr():
    try:
        kw = request.args.get("q","").strip()
        page = request.args.get("page", 1)
        page, per_page, offset = paginate(page, 15)
        
        q  = f"%{kw}%"
        with get_db() as c:
            total = c.execute("""
                SELECT COUNT(*) as cnt FROM employees
                WHERE name LIKE ? OR department LIKE ? OR job_title LIKE ?
            """, (q,q,q)).fetchone()["cnt"]
            
            rows = c.execute("""
                SELECT * FROM employees
                WHERE name LIKE ? OR department LIKE ? OR job_title LIKE ?
                ORDER BY id DESC LIMIT ? OFFSET ?
            """, (q,q,q,per_page,offset)).fetchall()
        
        total_pages = (total + per_page - 1) // per_page
        return render_template("hr.html", rows=rows, kw=kw, page=page, total_pages=total_pages)
    except Exception as e:
        logger.error(f"HR error: {e}")
        flash(f"❌ خطأ في تحميل بيانات الموظفين: {str(e)}", "error")
        return redirect(url_for("dashboard"))

@app.route("/hr/add", methods=["POST"])
@login_required
def add_employee():
    d = request.form
    with get_db() as c:
        c.execute("INSERT INTO employees (name,department,job_title,salary,hire_date,phone,notes) VALUES(?,?,?,?,?,?,?)",
                  (d["name"],d.get("department",""),d.get("job_title",""),float(d.get("salary",0)),
                   d.get("hire_date",date.today().isoformat()),d.get("phone",""),d.get("notes","")))
    flash("تم إضافة الموظف.","success")
    return redirect(url_for("hr"))

@app.route("/hr/delete/<int:eid>", methods=["POST"])
@login_required
def delete_employee(eid):
    with get_db() as c:
        c.execute("DELETE FROM employees WHERE id=?", (eid,))
    flash("تم الحذف.","success")
    return redirect(url_for("hr"))

# ── Analytics ─────────────────────────────────────────────────────────────────
@app.route("/analytics")
@login_required
def analytics():
    with get_db() as c:
        per_proj = c.execute("""
            SELECT p.name,p.client,p.status,p.stage,p.budget,
                COALESCE(SUM(CASE WHEN a.code LIKE '4%' THEN jl.credit-jl.debit ELSE 0 END),0) revenue,
                COALESCE(SUM(CASE WHEN a.code LIKE '5%' THEN jl.debit-jl.credit ELSE 0 END),0) expense,
                COUNT(DISTINCT pr.id) units,
                SUM(CASE WHEN pr.status='Sold' THEN 1 ELSE 0 END) sold
            FROM projects p
            LEFT JOIN journal_entries je ON je.project_id=p.id
            LEFT JOIN journal_lines jl ON jl.entry_id=je.id
            LEFT JOIN accounts a ON a.id=jl.account_id
            LEFT JOIN properties pr ON pr.project_id=p.id
            GROUP BY p.id ORDER BY p.id DESC
        """).fetchall()
        monthly = c.execute("""
            SELECT strftime('%Y-%m', je.entry_date) month,
                COALESCE(SUM(CASE WHEN a.code LIKE '4%' THEN jl.credit-jl.debit ELSE 0 END),0) revenue,
                COALESCE(SUM(CASE WHEN a.code LIKE '5%' THEN jl.debit-jl.credit ELSE 0 END),0) expense
            FROM journal_lines jl
            JOIN journal_entries je ON je.id=jl.entry_id
            JOIN accounts a ON a.id=jl.account_id
            GROUP BY month ORDER BY month DESC LIMIT 12
        """).fetchall()
    sm = get_analytics()
    return render_template("analytics.html", sm=sm, per_proj=per_proj,
                           monthly=[dict(r) for r in monthly])

# ── Users ─────────────────────────────────────────────────────────────────────
@app.route("/users")
@login_required
@role_required("Admin")
def users():
    with get_db() as c:
        rows = c.execute("SELECT id,username,role,full_name,created_at FROM users ORDER BY username").fetchall()
        logs = c.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT 30").fetchall()
    return render_template("users.html", rows=rows, logs=logs)

@app.route("/users/add", methods=["POST"])
@login_required
@role_required("Admin")
def add_user():
    d = request.form
    pw = d.get("password","").strip()
    if len(pw) < 4:
        flash("كلمة المرور يجب أن تكون 4 أحرف على الأقل.","error")
        return redirect(url_for("users"))
    with get_db() as c:
        try:
            c.execute("INSERT INTO users (username,password_hash,role,full_name) VALUES(?,?,?,?)",
                      (d["username"].strip(), _hash(pw), d.get("role","Sales"), d.get("full_name","")))
            flash(f"تم إضافة المستخدم {d['username']}.","success")
        except sqlite3.IntegrityError:
            flash("اسم المستخدم موجود مسبقاً.","error")
    return redirect(url_for("users"))

@app.route("/users/reset/<int:uid>", methods=["POST"])
@login_required
@role_required("Admin")
def reset_password(uid):
    pw = request.form.get("new_password","").strip()
    if len(pw) < 4:
        flash("كلمة المرور يجب أن تكون 4 أحرف على الأقل.","error")
    else:
        with get_db() as c:
            c.execute("UPDATE users SET password_hash=? WHERE id=?", (_hash(pw), uid))
        flash("تم تغيير كلمة المرور.","success")
    return redirect(url_for("users"))

@app.route("/users/delete/<int:uid>", methods=["POST"])
@login_required
@role_required("Admin")
def delete_user(uid):
    with get_db() as c:
        row = c.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
        if row and row["username"] == "admin":
            flash("لا يمكن حذف حساب المدير الرئيسي.","error")
        else:
            c.execute("DELETE FROM users WHERE id=?", (uid,))
            flash("تم حذف المستخدم.","success")
    return redirect(url_for("users"))

# ── Settings ──────────────────────────────────────────────────────────────────
@app.route("/settings", methods=["GET","POST"])
@login_required
@role_required("Admin")
def settings():
    cfg_path = BASE_DIR / "config.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {"company_name":"إبداع","currency":"ج.م"}
    if request.method == "POST":
        cfg["company_name"] = request.form.get("company_name","إبداع")
        cfg["currency"]     = request.form.get("currency","ج.م")
        cfg["company_phone"]= request.form.get("company_phone","")
        cfg["company_email"]= request.form.get("company_email","")
        cfg["company_address"]=request.form.get("company_address","")
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
        # change own password
        new_pw = request.form.get("new_password","").strip()
        if new_pw and len(new_pw) >= 4:
            with get_db() as c:
                c.execute("UPDATE users SET password_hash=? WHERE username=?",
                          (_hash(new_pw), session["user"]))
            flash("تم تغيير كلمة المرور.","success")
        flash("تم حفظ الإعدادات.","success")
        return redirect(url_for("settings"))
    return render_template("settings.html", cfg=cfg)


# ── PDF: Contracts ────────────────────────────────────────────────────────────
@app.route("/contracts/pdf")
@login_required
def contracts_pdf():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = get_pdf_styles()
    story = []
    company = get_company_info()
    story.append(Paragraph(company.get("company_name", "إبداع"), styles['ArabicTitle']))
    story.append(Paragraph("تقرير العقود", styles['ArabicHeading']))
    story.append(Paragraph(f"تاريخ الطباعة: {date.today().isoformat()}", styles['ArabicSmall']))
    story.append(Spacer(1, 15))
    with get_db() as c:
        rows = c.execute("""
            SELECT ct.contract_number, cl.full_name, pr.unit_number,
                   ct.contract_type, ct.total_price, ct.down_payment,
                   ct.signing_date, ct.status
            FROM contracts ct
            JOIN clients cl ON cl.id=ct.client_id
            JOIN properties pr ON pr.id=ct.property_id
            ORDER BY ct.id DESC
        """).fetchall()
    table_data = [["رقم العقد", "العميل", "الوحدة", "النوع", "الإجمالي", "المقدم", "تاريخ التوقيع", "الحالة"]]
    total_val = 0
    for r in rows:
        total_val += float(r["total_price"])
        table_data.append([
            r["contract_number"],
            (r["full_name"] or "")[:22],
            r["unit_number"],
            r["contract_type"],
            f"{float(r['total_price']):,.0f}",
            f"{float(r['down_payment']):,.0f}",
            r["signing_date"] or "",
            r["status"]
        ])
    table_data.append(["", "الإجمالي", "", "", f"{total_val:,.0f}", "", "", ""])
    col_w = [55, 70, 45, 35, 65, 55, 65, 40]
    t = Table(table_data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1a5276')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTSIZE', (0,1), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.4, colors.grey),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#d5dbdb')),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, colors.HexColor('#eaf4fb')]),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"إجمالي العقود: {len(rows)} عقد | إجمالي القيمة: {total_val:,.2f} {company.get('currency','ج.م')}", styles['ArabicBold']))
    doc.build(story)
    buffer.seek(0)
    resp = make_response(buffer.getvalue())
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=contracts_{date.today().isoformat()}.pdf'
    return resp

# ── PDF: Installments ─────────────────────────────────────────────────────────
@app.route("/installments/pdf")
@login_required
def installments_pdf():
    status_filter = request.args.get("status", "All")
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = get_pdf_styles()
    story = []
    company = get_company_info()
    title_suffix = f" - {status_filter}" if status_filter != "All" else ""
    story.append(Paragraph(company.get("company_name", "إبداع"), styles['ArabicTitle']))
    story.append(Paragraph(f"تقرير الأقساط{title_suffix}", styles['ArabicHeading']))
    story.append(Paragraph(f"تاريخ الطباعة: {date.today().isoformat()}", styles['ArabicSmall']))
    story.append(Spacer(1, 15))
    with get_db() as c:
        params = []
        where = "WHERE 1=1"
        if status_filter != "All":
            where += " AND i.status=?"
            params.append(status_filter)
        rows = c.execute(f"""
            SELECT i.due_date, i.amount, i.paid_date, i.status,
                   c.contract_number, cl.full_name, pr.unit_number
            FROM installments i
            JOIN contracts c ON c.id=i.contract_id
            JOIN clients cl ON cl.id=c.client_id
            JOIN properties pr ON pr.id=c.property_id
            {where} ORDER BY i.due_date
        """, params).fetchall()
    table_data = [["تاريخ الاستحقاق", "رقم العقد", "العميل", "الوحدة", "المبلغ", "تاريخ السداد", "الحالة"]]
    total_amt = total_paid = total_overdue = 0
    for r in rows:
        amt = float(r["amount"])
        total_amt += amt
        if r["status"] == "Paid": total_paid += amt
        if r["status"] == "Overdue": total_overdue += amt
        status_ar = {"Paid": "مسدد", "Pending": "قادم", "Overdue": "متأخر"}.get(r["status"], r["status"])
        table_data.append([
            r["due_date"], r["contract_number"],
            (r["full_name"] or "")[:22], r["unit_number"],
            f"{amt:,.2f}", r["paid_date"] or "-", status_ar
        ])
    table_data.append(["", "", "الإجمالي", "", f"{total_amt:,.2f}", "", ""])
    t = Table(table_data, colWidths=[60, 65, 80, 50, 65, 60, 50], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e8449')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTSIZE', (0,1), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.4, colors.grey),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#d5f5e3')),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, colors.HexColor('#eafaf1')]),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))
    cur = company.get('currency', 'ج.م')
    story.append(Paragraph(f"الإجمالي: {total_amt:,.2f} {cur} | محصل: {total_paid:,.2f} | متأخر: {total_overdue:,.2f}", styles['ArabicBold']))
    doc.build(story)
    buffer.seek(0)
    resp = make_response(buffer.getvalue())
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=installments_{date.today().isoformat()}.pdf'
    return resp

# ── PDF: Clients ───────────────────────────────────────────────────────────────
@app.route("/clients/pdf")
@login_required
def clients_pdf():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=20*mm, leftMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    styles = get_pdf_styles()
    story = []
    company = get_company_info()
    story.append(Paragraph(company.get("company_name", "إبداع"), styles['ArabicTitle']))
    story.append(Paragraph("تقرير بيانات العملاء", styles['ArabicHeading']))
    story.append(Paragraph(f"تاريخ الطباعة: {date.today().isoformat()}", styles['ArabicSmall']))
    story.append(Spacer(1, 15))
    with get_db() as c:
        rows = c.execute("""
            SELECT cl.*, COUNT(ct.id) contracts_count,
                   COALESCE(SUM(ct.total_price),0) total_sales
            FROM clients cl LEFT JOIN contracts ct ON ct.client_id=cl.id
            GROUP BY cl.id ORDER BY cl.full_name
        """).fetchall()
    table_data = [["الاسم", "رقم الهوية", "الهاتف", "البريد الإلكتروني", "عدد العقود", "إجمالي المبيعات"]]
    for r in rows:
        table_data.append([
            (r["full_name"] or "")[:28], r["national_id"] or "",
            r["phone"] or "", (r["email"] or "")[:22],
            str(r["contracts_count"]), f"{float(r['total_sales']):,.0f}"
        ])
    t = Table(table_data, colWidths=[90, 60, 60, 80, 45, 65], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#8e44ad')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTSIZE', (0,1), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.4, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f5eef8')]),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"إجمالي العملاء: {len(rows)} عميل", styles['ArabicBold']))
    doc.build(story)
    buffer.seek(0)
    resp = make_response(buffer.getvalue())
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=clients_{date.today().isoformat()}.pdf'
    return resp

# ── PDF: Properties ────────────────────────────────────────────────────────────
@app.route("/properties/pdf")
@login_required
def properties_pdf():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = get_pdf_styles()
    story = []
    company = get_company_info()
    story.append(Paragraph(company.get("company_name", "إبداع"), styles['ArabicTitle']))
    story.append(Paragraph("تقرير الوحدات العقارية", styles['ArabicHeading']))
    story.append(Paragraph(f"تاريخ الطباعة: {date.today().isoformat()}", styles['ArabicSmall']))
    story.append(Spacer(1, 15))
    with get_db() as c:
        rows = c.execute("""
            SELECT pr.*, COALESCE(p.name,'—') project_name
            FROM properties pr LEFT JOIN projects p ON p.id=pr.project_id
            ORDER BY pr.status, pr.unit_number
        """).fetchall()
    sold = sum(1 for r in rows if r["status"]=="Sold")
    avail = sum(1 for r in rows if r["status"]=="Available")
    total_val = sum(float(r["price"]) for r in rows)
    table_data = [["الوحدة", "المشروع", "النوع", "الدور", "المساحة م²", "السعر", "الحالة"]]
    for r in rows:
        status_ar = {"Available": "متاح", "Sold": "مباع", "Rented": "مؤجر"}.get(r["status"], r["status"])
        table_data.append([
            r["unit_number"], (r["project_name"] or "")[:20],
            (r["unit_type"] or "")[:15], str(r["floor"]),
            f"{float(r['area_sqm']):,.1f}", f"{float(r['price']):,.0f}", status_ar
        ])
    t = Table(table_data, colWidths=[55, 80, 65, 35, 55, 80, 45], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#16a085')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTSIZE', (0,1), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.4, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#e8f8f5')]),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"إجمالي: {len(rows)} وحدة | متاح: {avail} | مباع: {sold} | القيمة الإجمالية: {total_val:,.0f} {company.get('currency','ج.م')}",
        styles['ArabicBold']))
    doc.build(story)
    buffer.seek(0)
    resp = make_response(buffer.getvalue())
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=properties_{date.today().isoformat()}.pdf'
    return resp

# ── PDF: HR ────────────────────────────────────────────────────────────────────
@app.route("/hr/pdf")
@login_required
def hr_pdf():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = get_pdf_styles()
    story = []
    company = get_company_info()
    story.append(Paragraph(company.get("company_name", "إبداع"), styles['ArabicTitle']))
    story.append(Paragraph("تقرير الموارد البشرية والرواتب", styles['ArabicHeading']))
    story.append(Paragraph(f"تاريخ الطباعة: {date.today().isoformat()}", styles['ArabicSmall']))
    story.append(Spacer(1, 15))
    with get_db() as c:
        rows = c.execute("SELECT * FROM employees ORDER BY department, name").fetchall()
    total_salary = sum(float(r["salary"]) for r in rows)
    depts = {}
    for r in rows:
        d = r["department"] or "غير محدد"
        depts.setdefault(d, []).append(r)
    for dept, emps in depts.items():
        story.append(Paragraph(f"قسم: {dept}", styles['ArabicBold']))
        story.append(Spacer(1, 5))
        table_data = [["الاسم", "المسمى الوظيفي", "الراتب", "الهاتف", "تاريخ التعيين"]]
        dept_total = 0
        for e in emps:
            sal = float(e["salary"]); dept_total += sal
            table_data.append([
                (e["name"] or "")[:25], (e["job_title"] or "")[:20],
                f"{sal:,.2f}", e["phone"] or "", e["hire_date"] or ""
            ])
        table_data.append(["", "إجمالي القسم", f"{dept_total:,.2f}", "", ""])
        t = Table(table_data, colWidths=[100, 100, 75, 75, 80], repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTSIZE', (0,1), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.4, colors.grey),
            ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#d5dbdb')),
            ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, colors.HexColor('#f2f3f4')]),
        ]))
        story.append(t)
        story.append(Spacer(1, 12))
    story.append(Paragraph(
        f"إجمالي الموظفين: {len(rows)} | إجمالي الرواتب: {total_salary:,.2f} {company.get('currency','ج.م')}",
        styles['ArabicTitle']))
    doc.build(story)
    buffer.seek(0)
    resp = make_response(buffer.getvalue())
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=hr_{date.today().isoformat()}.pdf'
    return resp

# ── PDF: Engineering ───────────────────────────────────────────────────────────
@app.route("/engineering/pdf")
@login_required
def engineering_pdf():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = get_pdf_styles()
    story = []
    company = get_company_info()
    story.append(Paragraph(company.get("company_name", "إبداع"), styles['ArabicTitle']))
    story.append(Paragraph("تقرير المشاريع الهندسية", styles['ArabicHeading']))
    story.append(Paragraph(f"تاريخ الطباعة: {date.today().isoformat()}", styles['ArabicSmall']))
    story.append(Spacer(1, 15))
    with get_db() as c:
        rows = c.execute("""
            SELECT p.*, COUNT(pr.id) units_count,
                SUM(CASE WHEN pr.status='Sold' THEN 1 ELSE 0 END) sold_count,
                SUM(CASE WHEN pr.status='Available' THEN 1 ELSE 0 END) avail_count
            FROM projects p LEFT JOIN properties pr ON pr.project_id=p.id
            GROUP BY p.id ORDER BY p.status, p.name
        """).fetchall()
    total_budget = sum(float(r["budget"]) for r in rows)
    table_data = [["المشروع", "الموقع", "المدير", "الحالة", "الميزانية", "الوحدات", "مباع", "البدء", "الإنجاز"]]
    for p in rows:
        status_ar = {"Active": "نشط", "Completed": "مكتمل", "On Hold": "متوقف"}.get(p["status"], p["status"])
        table_data.append([
            (p["name"] or "")[:25], (p["location"] or "")[:15], (p["manager"] or "")[:15],
            status_ar, f"{float(p['budget']):,.0f}",
            str(p["units_count"] or 0), str(p["sold_count"] or 0),
            p["start_date"] or "", p["expected_end_date"] or ""
        ])
    t = Table(table_data, colWidths=[75, 55, 55, 40, 70, 40, 35, 60, 60], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 8),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTSIZE', (0,1), (-1,-1), 7),
        ('GRID', (0,0), (-1,-1), 0.4, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#ecf0f1')]),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"إجمالي المشاريع: {len(rows)} | إجمالي الميزانيات: {total_budget:,.0f} {company.get('currency','ج.م')}",
        styles['ArabicBold']))
    doc.build(story)
    buffer.seek(0)
    resp = make_response(buffer.getvalue())
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=projects_{date.today().isoformat()}.pdf'
    return resp

# ── PDF: Journal ───────────────────────────────────────────────────────────────
@app.route("/journal/pdf")
@login_required
def journal_pdf():
    from_d = request.args.get("from", f"{date.today().year}-01-01")
    to_d   = request.args.get("to", date.today().isoformat())
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = get_pdf_styles()
    story = []
    company = get_company_info()
    story.append(Paragraph(company.get("company_name", "إبداع"), styles['ArabicTitle']))
    story.append(Paragraph("يومية القيود المحاسبية", styles['ArabicHeading']))
    story.append(Paragraph(f"من {from_d} إلى {to_d} | تاريخ الطباعة: {date.today().isoformat()}", styles['ArabicSmall']))
    story.append(Spacer(1, 15))
    with get_db() as c:
        rows = c.execute("""
            SELECT je.entry_number, je.entry_date, je.description,
                   COALESCE(SUM(jl.debit),0) dr, COALESCE(SUM(jl.credit),0) cr
            FROM journal_entries je LEFT JOIN journal_lines jl ON jl.entry_id=je.id
            WHERE je.entry_date >= ? AND je.entry_date <= ?
            GROUP BY je.id ORDER BY je.entry_date, je.id
        """, (from_d, to_d)).fetchall()
    table_data = [["رقم القيد", "التاريخ", "البيان", "مدين", "دائن"]]
    total_dr = total_cr = 0
    for r in rows:
        dr = float(r["dr"]); cr = float(r["cr"])
        total_dr += dr; total_cr += cr
        table_data.append([r["entry_number"], r["entry_date"],
                           (r["description"] or "")[:55], f"{dr:,.2f}", f"{cr:,.2f}"])
    table_data.append(["", "", "الإجمالي", f"{total_dr:,.2f}", f"{total_cr:,.2f}"])
    t = Table(table_data, colWidths=[70, 65, 200, 80, 80], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2874a6')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTSIZE', (0,1), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.4, colors.grey),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#d5dbdb')),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, colors.HexColor('#eaf4fb')]),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"عدد القيود: {len(rows)} | إجمالي المدين: {total_dr:,.2f} | الدائن: {total_cr:,.2f}", styles['ArabicBold']))
    doc.build(story)
    buffer.seek(0)
    resp = make_response(buffer.getvalue())
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=journal_{from_d}_{to_d}.pdf'
    return resp

# ── PDF: Ledger ────────────────────────────────────────────────────────────────
@app.route("/ledger/pdf")
@login_required
def ledger_pdf():
    acc_id = request.args.get("account_id", "")
    from_d = request.args.get("from", f"{date.today().year}-01-01")
    to_d   = request.args.get("to", date.today().isoformat())
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = get_pdf_styles()
    story = []
    company = get_company_info()
    with get_db() as c:
        filters = ""; params = [from_d, to_d]
        acc_name = "جميع الحسابات"
        if acc_id:
            filters = " AND jl.account_id=?"
            params.append(int(acc_id))
            row = c.execute("SELECT name FROM accounts WHERE id=?", (int(acc_id),)).fetchone()
            if row: acc_name = row["name"]
        rows = c.execute(f"""
            SELECT je.entry_date, je.entry_number, je.description entry_desc,
                   a.code, a.name acc_name, jl.debit, jl.credit
            FROM journal_lines jl
            JOIN journal_entries je ON je.id=jl.entry_id
            JOIN accounts a ON a.id=jl.account_id
            WHERE je.entry_date >= ? AND je.entry_date <= ? {filters}
            ORDER BY je.entry_date, je.id
        """, params).fetchall()
    story.append(Paragraph(company.get("company_name", "إبداع"), styles['ArabicTitle']))
    story.append(Paragraph(f"دفتر الأستاذ — {acc_name}", styles['ArabicHeading']))
    story.append(Paragraph(f"من {from_d} إلى {to_d} | تاريخ الطباعة: {date.today().isoformat()}", styles['ArabicSmall']))
    story.append(Spacer(1, 15))
    table_data = [["التاريخ", "رقم القيد", "البيان", "الحساب", "مدين", "دائن", "الرصيد"]]
    running = 0.0
    for r in rows:
        running += float(r["debit"]) - float(r["credit"])
        table_data.append([
            r["entry_date"], r["entry_number"], (r["entry_desc"] or "")[:40],
            f"{r['code']} {(r['acc_name'] or '')[:18]}",
            f"{float(r['debit']):,.2f}" if float(r["debit"]) else "",
            f"{float(r['credit']):,.2f}" if float(r["credit"]) else "",
            f"{running:,.2f}"
        ])
    t = Table(table_data, colWidths=[55, 60, 130, 100, 60, 60, 60], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#6c3483')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTSIZE', (0,1), (-1,-1), 7),
        ('GRID', (0,0), (-1,-1), 0.4, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f4ecf7')]),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"الرصيد الختامي: {running:,.2f} {company.get('currency','ج.م')}", styles['ArabicBold']))
    doc.build(story)
    buffer.seek(0)
    resp = make_response(buffer.getvalue())
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=ledger_{from_d}_{to_d}.pdf'
    return resp

# ── PDF: COA ────────────────────────────────────────────────────────────────────
@app.route("/coa/pdf")
@login_required
def coa_pdf():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=20*mm, leftMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    styles = get_pdf_styles()
    story = []
    company = get_company_info()
    story.append(Paragraph(company.get("company_name", "إبداع"), styles['ArabicTitle']))
    story.append(Paragraph("دليل الحسابات الكامل", styles['ArabicHeading']))
    story.append(Paragraph(f"تاريخ الطباعة: {date.today().isoformat()}", styles['ArabicSmall']))
    story.append(Spacer(1, 15))
    with get_db() as c:
        rows = c.execute("SELECT code,name,account_type,normal_balance FROM accounts ORDER BY code").fetchall()
    table_data = [["رقم الحساب", "اسم الحساب", "النوع", "الطبيعة"]]
    for r in rows:
        type_ar = {"Group": "مجموعة رئيسية", "Header": "رأس (تجميعي)", "Posting": "قيد"}.get(r["account_type"], r["account_type"])
        nb_ar = {"debit": "مدين", "credit": "دائن"}.get(r["normal_balance"], r["normal_balance"])
        table_data.append([r["code"], r["name"][:55] if r["name"] else "", type_ar, nb_ar])
    t = Table(table_data, colWidths=[50, 245, 75, 45], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#7f8c8d')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTSIZE', (0,1), (-1,-1), 7),
        ('GRID', (0,0), (-1,-1), 0.3, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f2f3f4')]),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"إجمالي الحسابات: {len(rows)} حساب", styles['ArabicBold']))
    doc.build(story)
    buffer.seek(0)
    resp = make_response(buffer.getvalue())
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=coa_{date.today().isoformat()}.pdf'
    return resp

# ── API: mark overdue ─────────────────────────────────────────────────────────
@app.route("/api/mark_overdue", methods=["POST"])
@login_required
def api_mark_overdue():
    n = mark_overdue()
    return jsonify({"marked": n})

# ── Context processor ─────────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    cfg_path = BASE_DIR / "config.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {"company_name":"إبداع","currency":"ج.م"}
    allowed = ROLE_PAGES.get(session.get("role",""), set())
    return {
        "company_name": cfg.get("company_name","إبداع"),
        "currency":     cfg.get("currency","ج.م"),
        "current_user": session.get("user",""),
        "current_role": session.get("role",""),
        "full_name":    session.get("full_name",""),
        "allowed_pages": allowed,
        "today": date.today().isoformat(),
    }

# ── Error Handlers ────────────────────────────────────────────────────────────
@app.errorhandler(404)
def page_not_found(e):
    logger.warning(f"404 error: {request.path}")
    return render_template("error.html", code=404, message="الصفحة غير موجودة"), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"500 error: {str(e)}")
    return render_template("error.html", code=500, message="خطأ في الخادم"), 500

@app.errorhandler(403)
def forbidden(e):
    logger.warning(f"403 error for user: {session.get('user')}")
    flash("❌ ليس لديك صلاحيات للوصول إلى هذا المورد.", "error")
    return redirect(url_for("dashboard")), 403

# ── Before Request ────────────────────────────────────────────────────────────
@app.before_request
def before_request():
    """Check user session before each request"""
    if 'user' in session:
        session.permanent = True

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
