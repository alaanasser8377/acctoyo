# f:\0\1-5\V9\app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
import sqlite3
import hashlib
# استيراد الدوال وقاموس أنواع الحسابات من database.py
from database import get_db, hash_password, ACCOUNT_TYPES
from functools import wraps # لاستخدام المزخرف wraps
# ... (الاستيرادات الموجودة)
import io
import pandas as pd
from flask import send_file, Response # لاستخدام send_file أو Response لإرسال الملفات
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os # لاستخدام مسار الخط

import json # لقراءة ملف معلومات الشركة

from datetime import datetime
from datetime import date # <-- أضف هذا السطر
import re


import arabic_reshaper
from bidi.algorithm import get_display

# استيراد الوحدة الخاصة بتقرير قيود اليومية
from journal_voucher_report import add_journal_report_routes
# استيراد الوحدة الخاصة بتقرير كشف الحساب
from account_statement_report import account_statement_bp
# استيراد الوحدة الخاصة بتقرير الأرباح والخسائر
from profit_loss_report import profit_loss_bp
# استيراد الوحدة الخاصة بتقرير ميزان المراجعة
from trial_balance_report import trial_balance_bp
# استيراد الوحدة الخاصة بتقرير الميزانية العمومية
from balance_sheet_report import balance_sheet_bp
# استيراد الوحدة الخاصة بتقرير الأرباح والخسائر حسب مراكز التكلفة
from profit_loss_by_cost_center import profit_loss_by_cc_bp
# استيراد الوحدة الخاصة بتقرير الأداء المالي
from financial_performance_report import financial_performance_bp
# استيراد الوحدة الخاصة بتقرير دفتر الأستاذ
from ledger_report import ledger_bp

# ... (بقية الكود)



app = Flask(__name__)

# إضافة مسارات التقرير
add_journal_report_routes(app)
# تسجيل Blueprint بدلاً من استدعاء الدالة
app.register_blueprint(account_statement_bp)
# تسجيل Blueprint لتقرير الأرباح والخسائر
app.register_blueprint(profit_loss_bp)
# تسجيل Blueprint لتقرير ميزان المراجعة
app.register_blueprint(trial_balance_bp)
# تسجيل Blueprint لتقرير الميزانية العمومية
app.register_blueprint(balance_sheet_bp)
# تسجيل Blueprint لتقرير الأرباح والخسائر حسب مراكز التكلفة
app.register_blueprint(profit_loss_by_cc_bp)
# تسجيل Blueprint لتقرير الأداء المالي
app.register_blueprint(financial_performance_bp)
# تسجيل Blueprint لتقرير دفتر الأستاذ
app.register_blueprint(ledger_bp)

# إضافة تعريف بديل لجدول السنوات المالية للتوافق مع الكود القديم
@app.before_request
def handle_fiscal_years_alias():
    """
    يضيف جدول fiscal_years كبديل لجدول financial_years إذا لم يكن موجوداً
    هذا حل مؤقت للتعامل مع الكود الذي يستخدم الاسم القديم
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        # التحقق مما إذا كان الجدول موجوداً بالفعل
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fiscal_years'")
        if not cursor.fetchone():
            # إنشاء view بدلاً من جدول لضمان تحديث البيانات
            cursor.execute("CREATE VIEW IF NOT EXISTS fiscal_years AS SELECT * FROM financial_years")
            conn.commit()
    except sqlite3.Error as e:
        print(f"خطأ في إنشاء fiscal_years view: {e}")
    finally:
        if conn:
            conn.close()

# إضافة دالة جديدة لتهيئة جدول سندات الصرف
@app.before_request
def initialize_payment_vouchers_table():
    """
    يتحقق من وجود جدول سندات الصرف وينشئه إذا لم يكن موجوداً
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        # التحقق مما إذا كان الجدول موجوداً بالفعل
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payment_vouchers'")
        if not cursor.fetchone():
            # إنشاء جدول سندات الصرف
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS payment_vouchers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voucher_number INTEGER NOT NULL,
                voucher_date DATE NOT NULL,
                beneficiary TEXT NOT NULL,
                amount REAL NOT NULL,
                payment_method TEXT NOT NULL,
                check_number TEXT,
                check_date DATE,
                description TEXT,
                financial_year_id INTEGER NOT NULL,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER,
                updated_at TIMESTAMP,
                is_posted INTEGER DEFAULT 0,
                posted_by INTEGER,
                posted_at TIMESTAMP,
                FOREIGN KEY (financial_year_id) REFERENCES financial_years (id),
                FOREIGN KEY (created_by) REFERENCES users (id),
                FOREIGN KEY (updated_by) REFERENCES users (id),
                FOREIGN KEY (posted_by) REFERENCES users (id)
            )
            ''')
            conn.commit()
            print("تم إنشاء جدول سندات الصرف بنجاح")
    except sqlite3.Error as e:
        print(f"خطأ في إنشاء جدول سندات الصرف: {e}")
    finally:
        if conn:
            conn.close()

# إضافة دالة جديدة لتهيئة جدول سندات القبض
@app.before_request
def initialize_receipt_vouchers_table():
    """
    يتحقق من وجود جدول سندات القبض وينشئه إذا لم يكن موجوداً
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        # التحقق مما إذا كان الجدول موجوداً بالفعل
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='receipt_vouchers'")
        if not cursor.fetchone():
            # إنشاء جدول سندات القبض
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS receipt_vouchers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voucher_number INTEGER NOT NULL,
                voucher_date DATE NOT NULL,
                payer TEXT NOT NULL,
                amount REAL NOT NULL,
                payment_method TEXT NOT NULL,
                check_number TEXT,
                check_date DATE,
                description TEXT,
                financial_year_id INTEGER NOT NULL,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER,
                updated_at TIMESTAMP,
                is_posted INTEGER DEFAULT 0,
                posted_by INTEGER,
                posted_at TIMESTAMP,
                FOREIGN KEY (financial_year_id) REFERENCES financial_years (id),
                FOREIGN KEY (created_by) REFERENCES users (id),
                FOREIGN KEY (updated_by) REFERENCES users (id),
                FOREIGN KEY (posted_by) REFERENCES users (id)
            )
            ''')
            conn.commit()
            print("تم إنشاء جدول سندات القبض بنجاح")
    except sqlite3.Error as e:
        print(f"خطأ في إنشاء جدول سندات القبض: {e}")
    finally:
        if conn:
            conn.close()

# إضافة دالة جديدة لتهيئة جدول سندات القبض
@app.before_request
def initialize_receipt_vouchers_table():
    """
    يتحقق من وجود جدول سندات القبض وينشئه إذا لم يكن موجوداً
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        # التحقق مما إذا كان الجدول موجوداً بالفعل
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='receipt_vouchers'")
        if not cursor.fetchone():
            # إنشاء جدول سندات القبض
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS receipt_vouchers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voucher_number INTEGER NOT NULL,
                voucher_date DATE NOT NULL,
                payer TEXT NOT NULL,
                amount REAL NOT NULL,
                payment_method TEXT NOT NULL,
                check_number TEXT,
                check_date DATE,
                description TEXT,
                financial_year_id INTEGER NOT NULL,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER,
                updated_at TIMESTAMP,
                is_posted INTEGER DEFAULT 0,
                posted_by INTEGER,
                posted_at TIMESTAMP,
                FOREIGN KEY (financial_year_id) REFERENCES financial_years (id),
                FOREIGN KEY (created_by) REFERENCES users (id),
                FOREIGN KEY (updated_by) REFERENCES users (id),
                FOREIGN KEY (posted_by) REFERENCES users (id)
            )
            ''')
            conn.commit()
            print("تم إنشاء جدول سندات القبض بنجاح")
    except sqlite3.Error as e:
        print(f"خطأ في إنشاء جدول سندات القبض: {e}")
    finally:
        if conn:
            conn.close()

# ... (بعد app = Flask(__name__))

# --- تسجيل الخط العربي لـ ReportLab ---
# تأكد من وجود مجلد 'fonts' وبداخله ملف الخط
FONT_DIR = os.path.join(os.path.dirname(__file__), 'fonts')
ARABIC_FONT_PATH = os.path.join(FONT_DIR, 'Amiri-Regular.ttf') # استبدل بالاسم الصحيح لملف الخط

try:
    if os.path.exists(ARABIC_FONT_PATH):
        pdfmetrics.registerFont(TTFont('ArabicFont', ARABIC_FONT_PATH))
        print(f"Registered Arabic font: {ARABIC_FONT_PATH}")
        # إنشاء نمط فقرة يستخدم الخط العربي
        arabic_style = ParagraphStyle(
            name='ArabicStyle',
            fontName='ArabicFont',
            fontSize=10,
            alignment=2 # 2 = RIGHT alignment for Arabic
        )
        # يمكنك أيضاً تعديل الأنماط الافتراضية إذا أردت
        styles = getSampleStyleSheet()
        styles.add(arabic_style)
        # نمط للعناوين يستخدم الخط العربي
        styles.add(ParagraphStyle(name='ArabicHeading', parent=styles['Heading1'], fontName='ArabicFont', alignment=2))
        styles.add(ParagraphStyle(name='ArabicBodyText', parent=styles['BodyText'], fontName='ArabicFont', alignment=2))

    else:
        print(f"Warning: Arabic font file not found at {ARABIC_FONT_PATH}. PDF export might not display Arabic correctly.")
        # استخدام نمط افتراضي كحل بديل (قد لا يعرض العربية)
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='ArabicStyle', parent=styles['Normal'])) # Fallback
        styles.add(ParagraphStyle(name='ArabicHeading', parent=styles['Heading1']))
        styles.add(ParagraphStyle(name='ArabicBodyText', parent=styles['BodyText']))

except Exception as e:
    print(f"Error registering font or creating styles: {e}")
    styles = getSampleStyleSheet() # Fallback
    styles.add(ParagraphStyle(name='ArabicStyle', parent=styles['Normal']))
    styles.add(ParagraphStyle(name='ArabicHeading', parent=styles['Heading1']))
    styles.add(ParagraphStyle(name='ArabicBodyText', parent=styles['BodyText']))


# --- وظائف مساعدة للتصدير (يمكن وضعها في ملف منفصل لاحقاً) ---

def generate_excel(data, columns, filename="export.xlsx"):
    """
    تنشئ ملف Excel من قائمة القواميس أو صفوف قاعدة البيانات.
    :param data: قائمة من الصفوف (كل صف كـ dict أو sqlite3.Row).
    :param columns: قائمة بأسماء الأعمدة المراد تضمينها وترتيبها.
    :param filename: اسم الملف المقترح للتنزيل.
    :return: Flask Response object containing the Excel file.
    """
    # تحويل sqlite3.Row إلى dict إذا لزم الأمر
    data_list = [dict(row) for row in data]
    df = pd.DataFrame(data_list, columns=columns)

    # إنشاء ملف Excel في الذاكرة
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename # استخدام download_name بدلاً من attachment_filename
    )

# --- وظائف مساعدة للتصدير (يمكن وضعها في ملف منفصل لاحقاً) ---
# ... (دالة generate_excel تبقى كما هي)

def generate_pdf(data, headers, title, filename="export.pdf", column_widths=None):
    """
    تنشئ ملف PDF من قائمة القواميس أو صفوف قاعدة البيانات.
    تعالج النصوص العربية لضمان العرض الصحيح.
    :param data: قائمة من الصفوف (كل صف كـ dict أو sqlite3.Row).
    :param headers: قائمة بأسماء الأعمدة للعناوين في الجدول.
    :param title: عنوان التقرير.
    :param filename: اسم الملف المقترح للتنزيل.
    :param column_widths: قائمة اختيارية بعرض الأعمدة.
    :return: Flask Response object containing the PDF file.
    """
    output = io.BytesIO()
    page_size = landscape(letter) if len(headers) > 6 else letter
    doc = SimpleDocTemplate(output, pagesize=page_size, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=18)
    story = []

    # --- معالجة العنوان ---
    reshaped_title = arabic_reshaper.reshape(title)
    bidi_title = get_display(reshaped_title)
    story.append(Paragraph(bidi_title, styles['ArabicHeading']))
    story.append(Spacer(1, 12))

    # --- معالجة العناوين (Headers) ---
    processed_headers = []
    for header in headers:
        reshaped_header = arabic_reshaper.reshape(str(header))
        bidi_header = get_display(reshaped_header)
        processed_headers.append(Paragraph(bidi_header, styles['ArabicStyle'])) # استخدم النمط العربي

    # --- معالجة بيانات الجدول ---
    table_data = [processed_headers] # ابدأ بصف العناوين المعالج
    for row_data in data:
        processed_row = []
        # تأكد من أنك تمرر المفاتيح بنفس ترتيب العناوين
        # إذا كانت data قائمة قواميس، والمفاتيح تطابق العناوين الأصلية:
        keys_in_order = list(row_data.keys()) # أو استخدم ترتيبًا محددًا إذا لزم الأمر
        for key in keys_in_order:
            cell_value = str(row_data[key]) # تحويل القيمة إلى نص
            reshaped_text = arabic_reshaper.reshape(cell_value)
            bidi_text = get_display(reshaped_text)
            processed_row.append(Paragraph(bidi_text, styles['ArabicStyle'])) # استخدم النمط العربي
        table_data.append(processed_row)

    # إنشاء الجدول وتطبيق الأنماط
    table = Table(table_data, colWidths=column_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'), # المحاذاة لليمين
        # تأكد من أن الخط مسجل ويستخدم هنا
        ('FONTNAME', (0, 0), (-1, -1), 'ArabicFont'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))

    story.append(table)
    doc.build(story)
    output.seek(0)

    return send_file(
        output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )

# ... (بقية الكود في app.py)
# ... (بقية الكود مثل require_login, login, dashboard, logout)



# !!! هام جداً: قم بتغيير هذا المفتاح السري إلى قيمة قوية وعشوائية في بيئة الإنتاج !!!
app.secret_key = 'your_very_secret_key_here_please_change_me' # الرجاء تغيير هذا المفتاح

# --- وظائف مساعدة (يمكن نقلها لوحدة منفصلة لاحقاً) ---
def is_logged_in():
    """يتحقق مما إذا كان المستخدم مسجل دخوله."""
    return 'user_id' in session

def require_login(f):
    """مزخرف (Decorator) للتحقق من تسجيل الدخول قبل الوصول للمسار."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_logged_in():
            flash('الرجاء تسجيل الدخول للوصول إلى هذه الصفحة.', 'warning')
            return redirect(url_for('login', next=request.url)) # تمرير الصفحة المطلوبة بعد تسجيل الدخول
        return f(*args, **kwargs)
    return decorated_function

# --- صفحة تسجيل الدخول ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_logged_in():
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_input_password = hash_password(password)

        conn = None
        user = None # تعريف المتغير خارج try
        db_error = None # لتتبع أخطاء قاعدة البيانات
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE username = ? AND password_hash = ? AND is_active = 1",
                (username, hashed_input_password)
            )
            user = cursor.fetchone()
        except sqlite3.Error as e:
             db_error = e # تخزين الخطأ
             flash(f"خطأ في قاعدة البيانات: {e}", "danger")
             # user يبقى None
        finally:
            if conn:
                conn.close()

        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            flash('تم تسجيل الدخول بنجاح!', 'success')
            # إعادة التوجيه إلى الوجهة المطلوبة سابقاً أو لوحة التحكم
            next_url = request.args.get('next')
            return redirect(next_url or url_for('dashboard'))
        else:
            # عرض رسالة خطأ فقط إذا لم يكن هناك خطأ في قاعدة البيانات
            if not db_error:
                 flash('اسم المستخدم أو كلمة المرور غير صحيحة أو الحساب غير نشط.', 'danger')
            # إذا كان هناك خطأ في قاعدة البيانات، فقد تم عرض رسالة flash بالفعل

    return render_template('login.html')

@app.route('/journal_vouchers/print/<int:voucher_id>')
@require_login
def print_journal_voucher(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # استعلام لجلب بيانات القيد مع معلومات السنة المالية والمستخدم
        cursor.execute("""
            SELECT jv.*, fy.year_name, 
                   u_created.username as created_by,
                   u_posted.username as posted_by_name
            FROM journal_vouchers jv
            LEFT JOIN financial_years fy ON jv.financial_year_id = fy.id
            LEFT JOIN users u_created ON jv.created_by_user_id = u_created.id
            LEFT JOIN users u_posted ON jv.posted_by = u_posted.id
            WHERE jv.id = ?
        """, (voucher_id,))
        voucher = cursor.fetchone()
        
        if not voucher:
            flash('القيد المطلوب غير موجود.', 'danger')
            return redirect(url_for('list_journal_vouchers'))
        
        # استعلام لجلب تفاصيل القيد مع معلومات الحسابات ومراكز التكلفة
        cursor.execute("""
            SELECT jvd.*, a.name as account_name, a.code as account_code, cc.name as cost_center_name
            FROM journal_voucher_details jvd
            LEFT JOIN accounts a ON jvd.account_id = a.id
            LEFT JOIN cost_centers cc ON jvd.cost_center_id = cc.id
            WHERE jvd.voucher_id = ?
            ORDER BY jvd.id
        """, (voucher_id,))
        details = cursor.fetchall()
        
        # إضافة التاريخ الحالي
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # إعداد قالب الطباعة
        return render_template('print_journal_voucher.html', 
                              voucher=voucher, 
                              details=details,
                              current_date=current_date,
                              print_mode=True)
        
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء جلب بيانات القيد: {e}", 'danger')
        return redirect(url_for('list_journal_vouchers'))
    finally:
        if conn:
            conn.close()




# --- الصفحة الرئيسية ---
@app.route('/')
def index():
    # تعديل الدالة لإعادة التوجيه إلى صفحة تسجيل الدخول
    return redirect(url_for('login'))

# --- لوحة التحكم ---
@app.route('/dashboard')
@require_login
def dashboard():
    """صفحة لوحة التحكم الرئيسية"""
    return redirect(url_for('financial_performance.financial_performance_report_view'))
    
    # قراءة ملف معلومات الشركة
# قراءة ملف معلومات الشركة
def get_company_profile():
    company_profile_path = os.path.join(os.path.dirname(__file__), 'company_profile.json')
    try:
        with open(company_profile_path, 'r', encoding='utf-8') as file:
            company_profile = json.load(file)
    except Exception as e:
        # في حالة حدوث خطأ، استخدم بيانات افتراضية
        company_profile = {
            "companyName": "شركة مستويات التشغيل للمقاولات",
            "commercialRegistrationNumber": "450258658",
            "taxIdentificationNumber": "450258658300258",
            "logoPath": "assets/images/logo.png"
        }
        print(f"خطأ في قراءة ملف معلومات الشركة: {e}")
    
    # تعديل مسار اللوجو ليكون متوافقًا مع هيكل المجلدات الثابتة
    if 'logoPath' in company_profile:
        # إذا كان المسار لا يبدأ بـ 'static/'، أضفه
        if not company_profile['logoPath'].startswith('static/'):
            company_profile['logoPath'] = 'assets/images/logo.png'
    
    return company_profile

# إضافة متغير company_profile إلى جميع القوالب
@app.context_processor
def inject_company_profile():
    return {'company_profile': get_company_profile()}


# --- تسجيل الخروج ---
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('full_name', None)
    flash('تم تسجيل الخروج بنجاح.', 'info')
    return redirect(url_for('login'))

# ==================================================
# ========== إدارة المستخدمين (Users) =============
# ==================================================

# --- إدارة المستخدمين (عرض القائمة) ---
@app.route('/users')
@require_login
def manage_users():
    conn = None
    users = []
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, full_name, is_active FROM users ORDER BY username")
        users = cursor.fetchall()
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء جلب المستخدمين: {e}", "danger")
    finally:
        if conn:
            conn.close()
    return render_template('users.html', users=users)

# --- إضافة مستخدم جديد ---
@app.route('/users/add', methods=['GET', 'POST'])
@require_login
def add_user():
    if request.method == 'POST':
        username = request.form.get('username')
        full_name = request.form.get('full_name')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        is_active = 1 if request.form.get('is_active') else 0

        errors = []
        if not username: errors.append("اسم المستخدم مطلوب.")
        if not password: errors.append("كلمة المرور مطلوبة.")
        if password != confirm_password: errors.append("كلمتا المرور غير متطابقتين.")

        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            if cursor.fetchone():
                errors.append(f"اسم المستخدم '{username}' مستخدم بالفعل.")

            if errors:
                for error in errors: flash(error, 'danger')
                return render_template('add_user.html', form_data=request.form)

            hashed_pw = hash_password(password)
            cursor.execute(
                "INSERT INTO users (username, full_name, password_hash, is_active) VALUES (?, ?, ?, ?)",
                (username, full_name, hashed_pw, is_active)
            )
            conn.commit()
            flash(f"تمت إضافة المستخدم '{username}' بنجاح!", 'success')
            return redirect(url_for('manage_users'))

        except sqlite3.Error as e:
            if conn: conn.rollback()
            flash(f"حدث خطأ أثناء إضافة المستخدم: {e}", 'danger')
            return render_template('add_user.html', form_data=request.form)
        finally:
            if conn: conn.close()

    # GET request
    return render_template('add_user.html', form_data=None)


# --- تعديل مستخدم موجود ---
@app.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@require_login
def edit_user(user_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            flash('المستخدم المطلوب غير موجود.', 'danger')
            return redirect(url_for('manage_users'))

        if request.method == 'POST':
            full_name = request.form.get('full_name')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            is_active = 1 if request.form.get('is_active') else 0

            errors = []
            update_password = False
            if password:
                if password != confirm_password:
                    errors.append("كلمتا المرور الجديدتان غير متطابقتين.")
                else:
                    update_password = True
            elif confirm_password:
                 errors.append("الرجاء إدخال كلمة المرور الجديدة أيضاً.")

            if errors:
                for error in errors: flash(error, 'danger')
                return render_template('edit_user.html', user=user, form_data=request.form)

            if update_password:
                hashed_pw = hash_password(password)
                cursor.execute(
                    "UPDATE users SET full_name = ?, password_hash = ?, is_active = ? WHERE id = ?",
                    (full_name, hashed_pw, is_active, user_id)
                )
            else:
                cursor.execute(
                    "UPDATE users SET full_name = ?, is_active = ? WHERE id = ?",
                    (full_name, is_active, user_id)
                )
            conn.commit()
            flash('تم تحديث بيانات المستخدم بنجاح!', 'success')
            return redirect(url_for('manage_users'))

        # GET request
        else:
            return render_template('edit_user.html', user=user, form_data=None)

    except sqlite3.Error as e:
        if conn and request.method == 'POST': conn.rollback()
        flash(f"حدث خطأ أثناء التعامل مع المستخدم: {e}", 'danger')
        return redirect(url_for('manage_users'))
    finally:
        if conn: conn.close()


# --- حذف مستخدم ---
@app.route('/users/delete/<int:user_id>', methods=['POST'])
@require_login
def delete_user(user_id):
    if user_id == session['user_id']:
        flash('لا يمكنك حذف حسابك الخاص.', 'danger')
        return redirect(url_for('manage_users'))

    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        user_to_delete = cursor.fetchone()

        if not user_to_delete:
             flash('المستخدم المراد حذفه غير موجود.', 'warning')
             return redirect(url_for('manage_users'))

        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        flash(f"تم حذف المستخدم '{user_to_delete['username']}' بنجاح.", 'success')

    except sqlite3.Error as e:
        if conn: conn.rollback()
        flash(f"حدث خطأ أثناء حذف المستخدم: {e}", 'danger')
    finally:
        if conn: conn.close()

    return redirect(url_for('manage_users'))

# --- تصدير المستخدمين إلى Excel ---
@app.route('/users/export/excel')
@require_login
def export_users_excel():
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT username, full_name, CASE WHEN is_active = 1 THEN 'نعم' ELSE 'لا' END as active_status FROM users ORDER BY username")
        users = cursor.fetchall()
        # تحديد الأعمدة المطلوبة والترتيب
        columns = ['username', 'full_name', 'active_status']
        # إعادة تسمية الأعمدة للعرض في Excel (اختياري لكن أفضل)
        df_data = [{'اسم المستخدم': u['username'], 'الاسم الكامل': u['full_name'], 'نشط': u['active_status']} for u in users]
        df = pd.DataFrame(df_data)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='المستخدمون')
        output.seek(0)

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='users_export.xlsx'
        )
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء تصدير المستخدمين إلى Excel: {e}", "danger")
        return redirect(url_for('manage_users'))
    except Exception as e: # Catch other potential errors (like pandas issues)
        flash(f"حدث خطأ غير متوقع أثناء التصدير: {e}", "danger")
        return redirect(url_for('manage_users'))
    finally:
        if conn:
            conn.close()

# --- تصدير المستخدمين إلى PDF ---
@app.route('/users/export/pdf')
@require_login
def export_users_pdf():
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        # جلب البيانات بنفس الطريقة ولكن مع الأسماء الأصلية للأعمدة
        cursor.execute("SELECT username, full_name, CASE WHEN is_active = 1 THEN 'نعم' ELSE 'لا' END as active_status FROM users ORDER BY username")
        users = cursor.fetchall()

        # تحويل sqlite3.Row إلى dict لسهولة التعامل في دالة PDF
        data_for_pdf = [dict(row) for row in users]
        # تحديد العناوين باللغة العربية
        headers = ['اسم المستخدم', 'الاسم الكامل', 'نشط']
        # مطابقة مفاتيح القاموس مع العناوين (يجب أن يكون بنفس الترتيب)
        data_keys_ordered = ['username', 'full_name', 'active_status']
        # إعادة هيكلة البيانات لتطابق العناوين
        pdf_data_structured = [{h: d[k] for h, k in zip(headers, data_keys_ordered)} for d in data_for_pdf]


        return generate_pdf(
            pdf_data_structured,
            headers,
            "قائمة المستخدمين",
            filename="users_export.pdf",
            column_widths=[150, 200, 50] # تحديد عرض الأعمدة (اختياري)
        )
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء تصدير المستخدمين إلى PDF: {e}", "danger")
        return redirect(url_for('manage_users'))
    except Exception as e:
        flash(f"حدث خطأ غير متوقع أثناء التصدير: {e}", "danger")
        return redirect(url_for('manage_users'))
    finally:
        if conn:
            conn.close()

# ==================================================
# ========== إدارة السنوات المالية (Financial Years) =
# ==================================================

# --- إدارة السنوات المالية (عرض القائمة) ---
@app.route('/financial_years')
@require_login
def manage_financial_years():
    conn = None
    financial_years = []
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, year_name, start_date, end_date, is_active, is_closed
            FROM financial_years
            ORDER BY start_date DESC
        """)
        financial_years = cursor.fetchall()
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء جلب السنوات المالية: {e}", "danger")
        return render_template('financial_years.html', financial_years=[])
    finally:
        if conn: conn.close()

    return render_template('financial_years.html', financial_years=financial_years)

# --- إضافة سنة مالية جديدة ---
@app.route('/financial_years/add', methods=['GET', 'POST'])
@require_login
def add_financial_year():
    if request.method == 'POST':
        year_name = request.form.get('year_name')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        is_active = 1
        is_closed = 0

        errors = []
        if not year_name: errors.append("اسم السنة المالية مطلوب.")
        if not start_date: errors.append("تاريخ البدء مطلوب.")
        if not end_date: errors.append("تاريخ الانتهاء مطلوب.")

        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM financial_years WHERE year_name = ?", (year_name,))
            if cursor.fetchone():
                errors.append(f"اسم السنة المالية '{year_name}' مستخدم بالفعل.")

            if errors:
                for error in errors: flash(error, 'danger')
                return render_template('add_financial_year.html', form_data=request.form)

            cursor.execute("""
                INSERT INTO financial_years (year_name, start_date, end_date, is_active, is_closed)
                VALUES (?, ?, ?, ?, ?)
            """, (year_name, start_date, end_date, is_active, is_closed))
            conn.commit()
            flash(f"تمت إضافة السنة المالية '{year_name}' بنجاح!", 'success')
            return redirect(url_for('manage_financial_years'))
        except sqlite3.Error as e:
            if conn: conn.rollback()
            flash(f"حدث خطأ أثناء إضافة السنة المالية: {e}", 'danger')
            return render_template('add_financial_year.html', form_data=request.form)
        finally:
            if conn: conn.close()

    # GET request
    return render_template('add_financial_year.html', form_data=None)

# --- تبديل حالة النشاط للسنة المالية ---
@app.route('/financial_years/toggle_active/<int:year_id>', methods=['POST'])
@require_login
def toggle_financial_year_active(year_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM financial_years WHERE id = ?", (year_id,))
        year = cursor.fetchone()
        if not year:
            flash('السنة المالية غير موجودة.', 'danger')
            return redirect(url_for('manage_financial_years'))

        new_status = 1 - year['is_active']
        cursor.execute("UPDATE financial_years SET is_active = ? WHERE id = ?", (new_status, year_id))
        conn.commit()
        status_text = "نشطة" if new_status == 1 else "غير نشطة"
        flash(f'تم تغيير حالة السنة المالية إلى "{status_text}" بنجاح.', 'success')
    except sqlite3.Error as e:
        if conn: conn.rollback()
        flash(f"حدث خطأ أثناء تغيير حالة السنة المالية: {e}", 'danger')
    finally:
        if conn: conn.close()

    return redirect(url_for('manage_financial_years'))

# --- تبديل حالة الإغلاق للسنة المالية ---
@app.route('/financial_years/toggle_closed/<int:year_id>', methods=['POST'])
@require_login
def toggle_financial_year_closed(year_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT is_closed FROM financial_years WHERE id = ?", (year_id,))
        year = cursor.fetchone()
        if not year:
            flash('السنة المالية غير موجودة.', 'danger')
            return redirect(url_for('manage_financial_years'))

        new_status = 1 - year['is_closed']
        cursor.execute("UPDATE financial_years SET is_closed = ? WHERE id = ?", (new_status, year_id))
        conn.commit()
        status_text = "مغلقة" if new_status == 1 else "مفتوحة"
        flash(f'تم تغيير حالة السنة المالية إلى "{status_text}" بنجاح.', 'success')
    except sqlite3.Error as e:
        if conn: conn.rollback()
        flash(f"حدث خطأ أثناء تغيير حالة السنة المالية: {e}", 'danger')
    finally:
        if conn: conn.close()

    return redirect(url_for('manage_financial_years'))

# --- حذف سنة مالية ---
@app.route('/financial_years/delete/<int:year_id>', methods=['POST'])
@require_login
def delete_financial_year(year_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT year_name FROM financial_years WHERE id = ?", (year_id,))
        year_to_delete = cursor.fetchone()

        if not year_to_delete:
             flash('السنة المالية المراد حذفها غير موجودة.', 'warning')
             return redirect(url_for('manage_financial_years'))

        cursor.execute("DELETE FROM financial_years WHERE id = ?", (year_id,))
        conn.commit()
        flash(f"تم حذف السنة المالية '{year_to_delete['year_name']}' بنجاح.", 'success')

    except sqlite3.Error as e:
        if conn: conn.rollback()
        flash(f"حدث خطأ أثناء حذف السنة المالية: {e}. قد تكون هناك بيانات مرتبطة بها.", 'danger')
    finally:
        if conn: conn.close()

    return redirect(url_for('manage_financial_years'))

# --- تعديل سنة مالية موجودة ---
@app.route('/financial_years/edit/<int:year_id>', methods=['GET', 'POST'])
@require_login
def edit_financial_year(year_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM financial_years WHERE id = ?", (year_id,))
        year = cursor.fetchone()

        if not year:
            flash('السنة المالية المطلوبة غير موجودة.', 'danger')
            return redirect(url_for('manage_financial_years'))

        if request.method == 'POST':
            year_name = request.form.get('year_name')
            start_date = request.form.get('start_date')
            end_date = request.form.get('end_date')
            is_active = 1 if request.form.get('is_active') else 0
            is_closed = 1 if request.form.get('is_closed') else 0

            errors = []
            if not year_name: errors.append("اسم السنة المالية مطلوب.")
            if not start_date: errors.append("تاريخ البدء مطلوب.")
            if not end_date: errors.append("تاريخ الانتهاء مطلوب.")

            cursor.execute("SELECT id FROM financial_years WHERE year_name = ? AND id != ?", (year_name, year_id))
            if cursor.fetchone():
                errors.append(f"اسم السنة المالية '{year_name}' مستخدم بالفعل لسنة أخرى.")

            if errors:
                for error in errors: flash(error, 'danger')
                return render_template('edit_financial_year.html', year=year, form_data=request.form)

            cursor.execute("""
                UPDATE financial_years
                SET year_name = ?, start_date = ?, end_date = ?, is_active = ?, is_closed = ?
                WHERE id = ?
            """, (year_name, start_date, end_date, is_active, is_closed, year_id))
            conn.commit()
            flash(f"تم تحديث بيانات السنة المالية '{year_name}' بنجاح!", 'success')
            return redirect(url_for('manage_financial_years'))

        # GET request
        return render_template('edit_financial_year.html', year=year, form_data=None)

    except sqlite3.Error as e:
        if conn and request.method == 'POST': conn.rollback()
        flash(f"حدث خطأ أثناء التعامل مع السنة المالية: {e}", 'danger')
        return redirect(url_for('manage_financial_years'))
    finally:
        if conn: conn.close()

# --- تصدير السنوات المالية إلى Excel ---
@app.route('/financial_years/export/excel')
@require_login
def export_financial_years_excel():
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT year_name, start_date, end_date,
                   CASE WHEN is_active = 1 THEN 'نعم' ELSE 'لا' END as active_status,
                   CASE WHEN is_closed = 1 THEN 'نعم' ELSE 'لا' END as closed_status
            FROM financial_years ORDER BY start_date DESC
        """)
        years = cursor.fetchall()
        columns = ['year_name', 'start_date', 'end_date', 'active_status', 'closed_status']
        df_data = [{'اسم السنة': y['year_name'], 'تاريخ البدء': y['start_date'], 'تاريخ الانتهاء': y['end_date'], 'نشطة': y['active_status'], 'مغلقة': y['closed_status']} for y in years]
        df = pd.DataFrame(df_data)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='السنوات المالية')
        output.seek(0)

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='financial_years_export.xlsx'
        )
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء تصدير السنوات المالية إلى Excel: {e}", "danger")
        return redirect(url_for('manage_financial_years'))
    except Exception as e:
        flash(f"حدث خطأ غير متوقع أثناء التصدير: {e}", "danger")
        return redirect(url_for('manage_financial_years'))
    finally:
        if conn: conn.close()

# --- تصدير السنوات المالية إلى PDF ---
@app.route('/financial_years/export/pdf')
@require_login
def export_financial_years_pdf():
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT year_name, start_date, end_date,
                   CASE WHEN is_active = 1 THEN 'نعم' ELSE 'لا' END as active_status,
                   CASE WHEN is_closed = 1 THEN 'نعم' ELSE 'لا' END as closed_status
            FROM financial_years ORDER BY start_date DESC
        """)
        years = cursor.fetchall()

        data_for_pdf = [dict(row) for row in years]
        headers = ['اسم السنة', 'تاريخ البدء', 'تاريخ الانتهاء', 'نشطة', 'مغلقة']
        data_keys_ordered = ['year_name', 'start_date', 'end_date', 'active_status', 'closed_status']
        pdf_data_structured = [{h: d[k] for h, k in zip(headers, data_keys_ordered)} for d in data_for_pdf]

        return generate_pdf(
            pdf_data_structured,
            headers,
            "قائمة السنوات المالية",
            filename="financial_years_export.pdf",
            column_widths=[120, 80, 80, 50, 50]
        )
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء تصدير السنوات المالية إلى PDF: {e}", "danger")
        return redirect(url_for('manage_financial_years'))
    except Exception as e:
        flash(f"حدث خطأ غير متوقع أثناء التصدير: {e}", "danger")
        return redirect(url_for('manage_financial_years'))
    finally:
        if conn: conn.close()

# --- تبديل حالة الترحيل للقيد ---
@app.route('/journal_vouchers/toggle_posted/<int:voucher_id>', methods=['POST'])
@require_login
def toggle_voucher_posted(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # التحقق من وجود القيد
        cursor.execute("SELECT * FROM journal_vouchers WHERE id = ?", (voucher_id,))
        voucher = cursor.fetchone()
        
        if not voucher:
            flash('القيد المطلوب غير موجود.', 'danger')
            return redirect(url_for('list_journal_vouchers'))
        
        # تحديث حالة القيد (عكس الحالة الحالية)
        new_status = 1 if request.form.get('is_posted') else 0
        
        if new_status == 1:
            # إذا كان القيد سيتم ترحيله، نضيف معلومات المستخدم والتاريخ
            cursor.execute("""
                UPDATE journal_vouchers 
                SET is_posted = ?, 
                    posted_by = ?, 
                    posted_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (new_status, session['user_id'], voucher_id))
        else:
            # إذا كان القيد سيتم إلغاء ترحيله، نجعل معلومات المستخدم والتاريخ NULL
            cursor.execute("""
                UPDATE journal_vouchers 
                SET is_posted = ?, 
                    posted_by = NULL, 
                    posted_at = NULL
                WHERE id = ?
            """, (new_status, voucher_id))
        
        conn.commit()
        
        status_text = "مرحل" if new_status else "غير مرحل"
        flash(f'تم تحديث حالة القيد إلى {status_text} بنجاح.', 'success')
        
        return redirect(url_for('view_journal_voucher', voucher_id=voucher_id))
    
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        flash(f'حدث خطأ في قاعدة البيانات: {e}', 'danger')
        return redirect(url_for('view_journal_voucher', voucher_id=voucher_id))
    finally:
        if conn:
            conn.close()

# نقطة نهاية API للبحث عن الحسابات
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # الحصول على معيار البحث إن وجد
        search_query = request.args.get('q', '')
        
        if search_query:
            # البحث في رقم الحساب واسمه
            cursor.execute("""
                SELECT id, code, name, account_type as type
                FROM accounts
                WHERE (code LIKE ? OR name LIKE ?) AND is_active = 1
                ORDER BY code
            """, (f'%{search_query}%', f'%{search_query}%'))
        else:
            # جلب جميع الحسابات النشطة
            cursor.execute("""
                SELECT id, code, name, account_type as type
                FROM accounts
                WHERE is_active = 1
                ORDER BY code
            """)
        
        accounts = cursor.fetchall()
        
        # تحويل النتائج إلى قائمة من القواميس
        accounts_list = []
        for account in accounts:
            accounts_list.append({
                'id': account['id'],
                'code': account['code'],
                'name': account['name'],
                'type': account['type']
            })
        
        return jsonify({'accounts': accounts_list})
        
    except sqlite3.Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

# ==================================================
# ========== إدارة مراكز التكلفة (Cost Centers) ==========
# ==================================================

# --- عرض قائمة مراكز التكلفة ---
@app.route('/cost_centers')
@require_login
def list_cost_centers():
    """يعرض قائمة بجميع مراكز التكلفة."""
    conn = None
    centers = []
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, code, name FROM cost_centers ORDER BY name")
        centers = cursor.fetchall()
    except sqlite3.Error as e:
        flash(f'حدث خطأ أثناء جلب مراكز التكلفة: {e}', 'danger')
        return render_template('cost_centers.html', cost_centers=[])
    finally:
        if conn:
            conn.close()

    return render_template('cost_centers.html', cost_centers=centers)

# --- عرض نموذج إضافة مركز تكلفة جديد ---
@app.route('/cost_centers/add', methods=['GET'])
@require_login
def add_cost_center_form():
    """يعرض نموذج إضافة مركز تكلفة جديد وقائمة بالمراكز الحالية."""
    conn = None
    existing_centers = []
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, code, name FROM cost_centers ORDER BY name")
        existing_centers = cursor.fetchall()
    except sqlite3.Error as e:
        flash(f'حدث خطأ أثناء جلب مراكز التكلفة الموجودة: {e}', 'warning')
    finally:
        if conn:
            conn.close()

    return render_template('cost_center_form.html',
                           form_title="إضافة مركز تكلفة جديد",
                           form_action=url_for('add_cost_center'),
                           center=None,
                           form_data=None,
                           existing_centers=existing_centers)

# --- معالجة إضافة مركز تكلفة جديد ---
@app.route('/cost_centers/add', methods=['POST'])
@require_login
def add_cost_center():
    """يعالج بيانات نموذج إضافة مركز تكلفة جديد."""
    name = request.form.get('name')
    code = request.form.get('code')
    code = code.strip() if code else None

    errors = []
    if not name:
        errors.append('اسم مركز التكلفة مطلوب.')

    conn = None
    existing_centers = []
    try:
        conn = get_db()
        cursor = conn.cursor()

        if name:
            cursor.execute("SELECT id FROM cost_centers WHERE name = ?", (name,))
            if cursor.fetchone():
                errors.append('اسم مركز التكلفة هذا موجود بالفعل.')

        if code:
            cursor.execute("SELECT id FROM cost_centers WHERE code = ?", (code,))
            if cursor.fetchone():
                errors.append('كود مركز التكلفة هذا موجود بالفعل.')

        cursor.execute("SELECT id, code, name FROM cost_centers ORDER BY name")
        existing_centers = cursor.fetchall()

        if errors:
            for error in errors:
                flash(error, 'warning')
            return render_template('cost_center_form.html',
                                   form_title="إضافة مركز تكلفة جديد",
                                   form_action=url_for('add_cost_center'),
                                   center=None,
                                   form_data=request.form,
                                   existing_centers=existing_centers)

        cursor.execute("INSERT INTO cost_centers (name, code) VALUES (?, ?)", (name, code))
        conn.commit()
        flash(f'تمت إضافة مركز التكلفة "{name}" (الكود: {code or "لا يوجد"}) بنجاح.', 'success')
        return redirect(url_for('list_cost_centers'))

    except sqlite3.Error as e:
        if conn: conn.rollback()
        flash(f'حدث خطأ أثناء إضافة مركز التكلفة: {e}', 'danger')

        if not existing_centers and conn:
             try:
                 cursor = conn.cursor()
                 cursor.execute("SELECT id, code, name FROM cost_centers ORDER BY name")
                 existing_centers = cursor.fetchall()
             except sqlite3.Error as fetch_err:
                 print(f"Error fetching existing centers on error path: {fetch_err}")
                 existing_centers = []

        return render_template('cost_center_form.html',
                               form_title="إضافة مركز تكلفة جديد",
                               form_action=url_for('add_cost_center'),
                               center=None,
                               form_data=request.form,
                               existing_centers=existing_centers)
    finally:
        if conn: conn.close()


# --- عرض نموذج تعديل مركز تكلفة ---
@app.route('/cost_centers/edit/<int:center_id>', methods=['GET'])
@require_login
def edit_cost_center_form(center_id):
    """يعرض نموذج تعديل مركز تكلفة موجود."""
    conn = None
    center = None
    existing_centers = []
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cost_centers WHERE id = ?", (center_id,))
        center = cursor.fetchone()

        cursor.execute("SELECT id, code, name FROM cost_centers ORDER BY name")
        existing_centers = cursor.fetchall()

        if not center:
            flash('مركز التكلفة المطلوب غير موجود.', 'danger')
            return redirect(url_for('list_cost_centers'))

        return render_template('cost_center_form.html',
                               form_title=f"تعديل مركز التكلفة: {center['name']}",
                               form_action=url_for('edit_cost_center', center_id=center_id),
                               center=center,
                               form_data=None,
                               existing_centers=existing_centers)

    except sqlite3.Error as e:
        flash(f'حدث خطأ أثناء جلب بيانات مركز التكلفة: {e}', 'danger')
        return redirect(url_for('list_cost_centers'))
    finally:
        if conn:
            conn.close()

# --- معالجة تعديل مركز تكلفة ---
@app.route('/cost_centers/edit/<int:center_id>', methods=['POST'])
@require_login
def edit_cost_center(center_id):
    """يعالج بيانات نموذج تعديل مركز تكلفة موجود."""
    name = request.form.get('name')
    code = request.form.get('code')
    code = code.strip() if code else None

    errors = []
    if not name:
        errors.append('اسم مركز التكلفة مطلوب.')

    conn = None
    original_center_name = None
    existing_centers = []
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM cost_centers WHERE id = ?", (center_id,))
        result = cursor.fetchone()
        if not result:
             flash('مركز التكلفة الذي تحاول تعديله لم يعد موجوداً.', 'danger')
             return redirect(url_for('list_cost_centers'))
        original_center_name = result['name']

        if name:
            cursor.execute("SELECT id FROM cost_centers WHERE name = ? AND id != ?", (name, center_id))
            if cursor.fetchone():
                errors.append(f'اسم مركز التكلفة "{name}" مستخدم بالفعل لمركز آخر.')

        if code:
            cursor.execute("SELECT id FROM cost_centers WHERE code = ? AND id != ?", (code, center_id))
            if cursor.fetchone():
                errors.append(f'كود مركز التكلفة "{code}" مستخدم بالفعل لمركز آخر.')

        cursor.execute("SELECT id, code, name FROM cost_centers ORDER BY name")
        existing_centers = cursor.fetchall()

        if errors:
            for error in errors:
                flash(error, 'warning')
            cursor.execute("SELECT * FROM cost_centers WHERE id = ?", (center_id,))
            center_data_for_form = cursor.fetchone()
            if not center_data_for_form:
                 flash('حدث خطأ غير متوقع أثناء استرجاع بيانات النموذج.', 'danger')
                 return redirect(url_for('list_cost_centers'))

            return render_template('cost_center_form.html',
                                   form_title=f"تعديل مركز التكلفة: {original_center_name}",
                                   form_action=url_for('edit_cost_center', center_id=center_id),
                                   center=center_data_for_form,
                                   form_data=request.form,
                                   existing_centers=existing_centers)

        cursor.execute("UPDATE cost_centers SET name = ?, code = ? WHERE id = ?", (name, code, center_id))
        conn.commit()
        flash(f'تم تحديث مركز التكلفة "{name}" بنجاح.', 'success')
        return redirect(url_for('list_cost_centers'))

    except sqlite3.Error as e:
        if conn: conn.rollback()
        flash(f'حدث خطأ أثناء تحديث مركز التكلفة: {e}', 'danger')

        center_data_for_form = None
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM cost_centers WHERE id = ?", (center_id,))
                center_data_for_form = cursor.fetchone()
                cursor.execute("SELECT id, code, name FROM cost_centers ORDER BY name")
                existing_centers = cursor.fetchall()
            except sqlite3.Error as fetch_err:
                 print(f"Error fetching data on error path: {fetch_err}")
                 existing_centers = []

        if center_data_for_form:
             return render_template('cost_center_form.html',
                                   form_title=f"تعديل مركز التكلفة: {original_center_name or 'خطأ'}",
                                   form_action=url_for('edit_cost_center', center_id=center_id),
                                   center=center_data_for_form,
                                   form_data=request.form,
                                   existing_centers=existing_centers)
        else:
             flash('حدث خطأ إضافي أثناء محاولة عرض النموذج مرة أخرى.', 'danger')
             return redirect(url_for('list_cost_centers'))

    finally:
        if conn: conn.close()


# --- حذف مركز تكلفة ---
@app.route('/cost_centers/delete/<int:center_id>', methods=['POST'])
@require_login
def delete_cost_center(center_id):
    """يعالج طلب حذف مركز تكلفة."""
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM cost_centers WHERE id = ?", (center_id,))
        center_to_delete = cursor.fetchone()

        if not center_to_delete:
             flash('مركز التكلفة المراد حذفه غير موجود.', 'warning')
             return redirect(url_for('list_cost_centers'))
        
        # التحقق مما إذا كان مركز التكلفة قيد الاستخدام في قيود اليومية
        cursor.execute("""SELECT COUNT(*) as count FROM journal_voucher_details 
                       WHERE cost_center_id = ?""", (center_id,))
        jv_count = cursor.fetchone()['count']
        if jv_count > 0:
            flash(f"لا يمكن حذف مركز التكلفة '{center_to_delete['name']}' لأنه مستخدم في {jv_count} من قيود اليومية.", 'danger')
            return redirect(url_for('list_cost_centers'))
        
        # يمكن إضافة المزيد من التحققات هنا للجداول الأخرى التي قد تستخدم مركز التكلفة

        cursor.execute("DELETE FROM cost_centers WHERE id = ?", (center_id,))
        conn.commit()
        flash(f"تم حذف مركز التكلفة '{center_to_delete['name']}' بنجاح.", 'success')

    except sqlite3.Error as e:
        if conn: conn.rollback()
        flash(f"حدث خطأ أثناء حذف مركز التكلفة: {e}. قد تكون هناك بيانات مرتبطة به.", 'danger')
    finally:
        if conn: conn.close()

    return redirect(url_for('list_cost_centers'))

# --- تصدير مراكز التكلفة إلى Excel ---
@app.route('/cost_centers/export/excel')
@require_login
def export_cost_centers_excel():
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT code, name FROM cost_centers ORDER BY name")
        centers = cursor.fetchall()
        columns = ['code', 'name']
        df_data = [{'الكود': c['code'], 'الاسم': c['name']} for c in centers]
        df = pd.DataFrame(df_data)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='مراكز التكلفة')
        output.seek(0)

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='cost_centers_export.xlsx'
        )
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء تصدير مراكز التكلفة إلى Excel: {e}", "danger")
        return redirect(url_for('list_cost_centers'))
    except Exception as e:
        flash(f"حدث خطأ غير متوقع أثناء التصدير: {e}", "danger")
        return redirect(url_for('list_cost_centers'))
    finally:
        if conn: conn.close()

# --- تصدير مراكز التكلفة إلى PDF ---
@app.route('/cost_centers/export/pdf')
@require_login
def export_cost_centers_pdf():
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT code, name FROM cost_centers ORDER BY name")
        centers = cursor.fetchall()

        data_for_pdf = [dict(row) for row in centers]
        headers = ['الكود', 'الاسم']
        data_keys_ordered = ['code', 'name']
        pdf_data_structured = [{h: d[k] for h, k in zip(headers, data_keys_ordered)} for d in data_for_pdf]

        return generate_pdf(
            pdf_data_structured,
            headers,
            "قائمة مراكز التكلفة",
            filename="cost_centers_export.pdf",
            column_widths=[100, 250]
        )
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء تصدير مراكز التكلفة إلى PDF: {e}", "danger")
        return redirect(url_for('list_cost_centers'))
    except Exception as e:
        flash(f"حدث خطأ غير متوقع أثناء التصدير: {e}", "danger")
        return redirect(url_for('list_cost_centers'))
    finally:
        if conn: conn.close()

# ==================================================
# ========== نهاية إدارة مراكز التكلفة ==========
# ==================================================


# ==================================================
# ========== إدارة شجرة الحسابات (Accounts) =========
# ==================================================

# --- دالة مساعدة لجلب الحسابات بشكل هرمي مع حساب المستوى ---
def get_accounts_hierarchy_with_level(conn):
    """
    تجلب جميع الحسابات مرتبة بشكل هرمي (DFS) وتحسب مستوى كل حساب.
    """
    cursor = conn.cursor()
    # جلب جميع الحسابات اللازمة
    cursor.execute("""
        SELECT a.id, a.code, a.name, a.account_type, a.parent_id, a.is_active, a.allows_posting, p.name as parent_name
        FROM accounts a
        LEFT JOIN accounts p ON a.parent_id = p.id
        -- لا نحتاج للترتيب هنا، الترتيب سيتم أثناء بناء الشجرة
    """)
    all_accounts_list = cursor.fetchall()

    # تحويل القائمة إلى قاموس لسهولة الوصول بواسطة ID وإضافة حقل المستوى
    accounts_dict = {acc['id']: dict(acc) for acc in all_accounts_list}
    # بناء قاموس يربط ID الأب بقائمة IDs الأبناء
    children_map = {}
    root_ids = []
    for acc_id, acc_data in accounts_dict.items():
        parent_id = acc_data.get('parent_id')
        if parent_id is None:
            root_ids.append(acc_id)
        else:
            # التأكد من أن الأب موجود قبل إضافته (لتجنب الأخطاء مع البيانات غير الصحيحة)
            if parent_id in accounts_dict:
                if parent_id not in children_map:
                    children_map[parent_id] = []
                children_map[parent_id].append(acc_id)
            else:
                # إذا كان الأب غير موجود، اعتبره جذرًا مؤقتًا أو سجل تحذيرًا
                root_ids.append(acc_id)
                print(f"Warning: Account ID {acc_id} ('{acc_data['name']}') has non-existent parent ID {parent_id}.")


    # قائمة للاحتفاظ بالحسابات المرتبة النهائية مع مستوياتها
    ordered_accounts_with_level = []

    # دالة تعاودية (recursive) لتنفيذ البحث بالعمق أولاً (DFS) وتعيين المستويات
    def traverse(account_id, level):
        if account_id not in accounts_dict:
            return # الحساب غير موجود (لا يجب أن يحدث)

        account_data = accounts_dict[account_id]
        account_data['level'] = level # إضافة معلومات المستوى
        ordered_accounts_with_level.append(account_data) # إضافة الحساب الحالي للقائمة المرتبة

        # المرور على الأبناء بشكل تعاودي
        if account_id in children_map:
            # فرز الأبناء حسب الكود قبل المرور عليهم (للحفاظ على ترتيب منطقي)
            child_ids = sorted(children_map[account_id], key=lambda cid: accounts_dict[cid]['code'])
            for child_id in child_ids:
                traverse(child_id, level + 1)

    # بدء المرور من الحسابات الجذرية (التي ليس لها أب)
    # فرز الحسابات الجذرية حسب الكود
    sorted_root_ids = sorted(root_ids, key=lambda rid: accounts_dict[rid]['code'])
    for root_id in sorted_root_ids:
        traverse(root_id, 0) # الحسابات الجذرية في المستوى 0

    # التأكد من معالجة جميع الحسابات (في حال وجود حلقات أو بيانات غير متناسقة)
    processed_ids = {acc['id'] for acc in ordered_accounts_with_level}
    for acc_id, acc_data in accounts_dict.items():
        if acc_id not in processed_ids:
            print(f"Warning: Account ID {acc_id} ('{acc_data['name']}') was not included in the main traversal. Treating as root.")
            # يمكن التعامل مع الحسابات غير المعالجة كجذور إضافية
            traverse(acc_id, 0)


    return ordered_accounts_with_level # إرجاع قائمة القواميس المرتبة

# --- عرض شجرة/قائمة الحسابات ---
@app.route('/accounts')
@require_login
def list_accounts():
    """يعرض قائمة بجميع الحسابات بشكل هرمي مع إمكانية البحث."""
    # الحصول على معايير البحث من الطلب
    code = request.args.get('code', '')
    name = request.args.get('name', '')
    account_type = request.args.get('account_type', '')
    parent_name = request.args.get('parent_name', '')
    is_active = request.args.get('is_active', '')
    allows_posting = request.args.get('allows_posting', '')
    
    conn = None
    accounts = []
    try:
        conn = get_db()
        
        # إذا لم يتم تحديد أي معايير بحث، استخدم الدالة الهرمية
        if not any([code, name, account_type, parent_name, is_active, allows_posting]):
            accounts = get_accounts_hierarchy_with_level(conn)
        else:
            # بناء استعلام SQL مع معايير البحث
            query = """
            SELECT a.id, a.code, a.name, a.account_type, a.parent_id, a.is_active, a.allows_posting,
                   p.name as parent_name
            FROM accounts a
            LEFT JOIN accounts p ON a.parent_id = p.id
            WHERE 1=1
            """
            params = []
            
            # إضافة شروط البحث إذا تم تحديدها
            if code:
                query += " AND a.code LIKE ?"
                params.append(f"%{code}%")
            
            if name:
                query += " AND a.name LIKE ?"
                params.append(f"%{name}%")
            
            if account_type:
                query += " AND a.account_type = ?"
                params.append(account_type)
            
            if parent_name:
                query += " AND p.name LIKE ?"
                params.append(f"%{parent_name}%")
            
            if is_active != '':
                query += " AND a.is_active = ?"
                params.append(int(is_active))
            
            if allows_posting != '':
                query += " AND a.allows_posting = ?"
                params.append(int(allows_posting))
            
            # ترتيب النتائج حسب الرمز
            query += " ORDER BY a.code"
            
            # تنفيذ الاستعلام
            cursor = conn.cursor()
            cursor.execute(query, params)
            accounts_data = cursor.fetchall()
            
            # تحويل النتائج إلى قائمة من القواميس
            accounts = []
            for account in accounts_data:
                account_dict = dict(account)
                # إضافة حقل المستوى (level) بقيمة افتراضية 0 للعرض
                account_dict['level'] = 0
                accounts.append(account_dict)
    except sqlite3.Error as e:
        flash(f'حدث خطأ أثناء جلب الحسابات: {e}', 'danger')
        # عرض الصفحة بقائمة فارغة في حالة الخطأ
        return render_template('accounts.html', accounts=[], account_types=ACCOUNT_TYPES)
    finally:
        if conn:
            conn.close()

    return render_template('accounts.html', accounts=accounts, account_types=ACCOUNT_TYPES)







# --- عرض نموذج إضافة حساب جديد ---
@app.route('/accounts/add', methods=['GET'])
@require_login
def add_account_form():
    """يعرض نموذج إضافة حساب جديد."""
    conn = None
    parent_accounts = [] # قائمة الحسابات التي يمكن أن تكون أب
    existing_accounts_sidebar = [] # قائمة لعرضها في الشريط الجانبي
    try:
        conn = get_db()
        cursor = conn.cursor()
        # جلب الحسابات الأصل المحتملة للـ dropdown
        cursor.execute("SELECT id, code, name FROM accounts WHERE is_active = 1 ORDER BY code")
        parent_accounts = cursor.fetchall()
        # جلب كل الحسابات للشريط الجانبي باستخدام الدالة الجديدة
        existing_accounts_sidebar = get_accounts_hierarchy_with_level(conn) # <-- استخدام الدالة الجديدة
    except sqlite3.Error as e:
        flash(f'حدث خطأ أثناء جلب بيانات الحسابات: {e}', 'warning')
    finally:
        if conn:
            conn.close()

    return render_template('account_form.html',
                           form_title="إضافة حساب جديد",
                           form_action=url_for('add_account'),
                           account=None,
                           form_data=None,
                           account_types=ACCOUNT_TYPES,
                           parent_accounts=parent_accounts,
                           existing_accounts=existing_accounts_sidebar) # <-- تمرير القائمة الجديدة

# --- معالجة إضافة حساب جديد ---
@app.route('/accounts/add', methods=['POST'])
@require_login
def add_account():
    """يعالج بيانات نموذج إضافة حساب جديد."""
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    account_type_str = request.form.get('account_type')
    parent_id_str = request.form.get('parent_id')
    is_active = 1 if request.form.get('is_active') else 0
    allows_posting = 1 if request.form.get('allows_posting') else 0

    errors = []
    account_type = None
    parent_id = None

    if not code: errors.append('رمز الحساب مطلوب.')
    if not name: errors.append('اسم الحساب مطلوب.')
    if not account_type_str:
        errors.append('نوع الحساب مطلوب.')
    else:
        try:
            account_type = int(account_type_str)
            if account_type not in ACCOUNT_TYPES:
                errors.append('نوع الحساب غير صالح.')
        except ValueError:
            errors.append('نوع الحساب يجب أن يكون رقمًا.')

    if parent_id_str and parent_id_str != 'None':
        try:
            parent_id = int(parent_id_str)
        except ValueError:
            errors.append('الحساب الأصل المحدد غير صالح.')
    else:
         parent_id = None

    conn = None
    parent_accounts = []
    existing_accounts_sidebar = [] # <-- تعريف المتغير هنا
    try:
        conn = get_db()
        cursor = conn.cursor()

        if code:
            cursor.execute("SELECT id FROM accounts WHERE code = ?", (code,))
            if cursor.fetchone():
                errors.append(f'رمز الحساب "{code}" مستخدم بالفعل.')

        if parent_id is not None:
             cursor.execute("SELECT id FROM accounts WHERE id = ?", (parent_id,))
             if not cursor.fetchone():
                 errors.append('الحساب الأصل المحدد غير موجود.')

        # جلب البيانات اللازمة لإعادة العرض عند الخطأ
        cursor.execute("SELECT id, code, name FROM accounts WHERE is_active = 1 ORDER BY code")
        parent_accounts = cursor.fetchall()
        # جلب بيانات الشريط الجانبي أيضاً باستخدام الدالة الجديدة
        existing_accounts_sidebar = get_accounts_hierarchy_with_level(conn) # <-- استخدام الدالة الجديدة

        if errors:
            for error in errors:
                flash(error, 'warning')
            # لا حاجة لإعادة جلب البيانات هنا لأنها جلبت بالفعل قبل التحقق من الأخطاء
            return render_template('account_form.html',
                                   form_title="إضافة حساب جديد",
                                   form_action=url_for('add_account'),
                                   account=None,
                                   form_data=request.form,
                                   account_types=ACCOUNT_TYPES,
                                   parent_accounts=parent_accounts,
                                   existing_accounts=existing_accounts_sidebar) # <-- تمرير بيانات الشريط الجانبي

        # إضافة الحساب إلى قاعدة البيانات
        cursor.execute("""
            INSERT INTO accounts (code, name, account_type, parent_id, is_active, allows_posting)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (code, name, account_type, parent_id, is_active, allows_posting))
        conn.commit()
        flash(f'تمت إضافة الحساب "{name}" (الكود: {code}) بنجاح.', 'success')
        # إعادة التوجيه إلى نموذج الإضافة مرة أخرى للسماح بإضافة حساب آخر
        return redirect(url_for('add_account_form')) # <-- التوجيه إلى دالة عرض النموذج

    except sqlite3.Error as e:
        if conn: conn.rollback()
        flash(f'حدث خطأ أثناء إضافة الحساب: {e}', 'danger')
        # محاولة جلب البيانات اللازمة مرة أخرى لعرض النموذج بشكل صحيح
        if conn: # تأكد من أن الاتصال لا يزال مفتوحًا أو افتح واحدًا جديدًا إذا لزم الأمر
            try:
                cursor = conn.cursor() # قد تحتاج لإعادة تعريف المؤشر إذا أغلق الاتصال
                cursor.execute("SELECT id, code, name FROM accounts WHERE is_active = 1 ORDER BY code")
                parent_accounts = cursor.fetchall()
                # جلب بيانات الشريط الجانبي هنا أيضاً باستخدام الدالة الجديدة
                existing_accounts_sidebar = get_accounts_hierarchy_with_level(conn) # <-- استخدام الدالة الجديدة
            except sqlite3.Error as fetch_err:
                 print(f"Error fetching data on error path: {fetch_err}")
                 parent_accounts = [] # تعيين قيم افتراضية إذا فشل الجلب
                 existing_accounts_sidebar = []

        return render_template('account_form.html',
                               form_title="إضافة حساب جديد",
                               form_action=url_for('add_account'),
                               account=None,
                               form_data=request.form,
                               account_types=ACCOUNT_TYPES,
                               parent_accounts=parent_accounts,
                               existing_accounts=existing_accounts_sidebar) # <-- تمرير بيانات الشريط الجانبي
    finally:
        if conn: conn.close()

# --- عرض نموذج تعديل حساب ---
@app.route('/accounts/edit/<int:account_id>', methods=['GET'])
@require_login
def edit_account_form(account_id):
    """يعرض نموذج تعديل حساب موجود."""
    conn = None
    account = None
    parent_accounts = []
    existing_accounts_sidebar = [] # قائمة لعرضها في الشريط الجانبي
    try:
        conn = get_db()
        cursor = conn.cursor()

        # جلب بيانات الحساب المراد تعديله
        cursor.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        account = cursor.fetchone()

        if not account:
            flash('الحساب المطلوب غير موجود.', 'danger')
            return redirect(url_for('list_accounts'))

        # جلب قائمة الحسابات الأصل المحتملة (لاستخدامها في القائمة المنسدلة)
        cursor.execute("""
            SELECT id, code, name FROM accounts
            WHERE is_active = 1 AND id != ?
            ORDER BY code
        """, (account_id,))
        parent_accounts = cursor.fetchall()

        # جلب كل الحسابات للشريط الجانبي باستخدام الدالة الجديدة
        existing_accounts_sidebar = get_accounts_hierarchy_with_level(conn) # <-- استخدام الدالة الجديدة

        return render_template('account_form.html',
                               form_title=f"تعديل الحساب: {account['name']}",
                               form_action=url_for('edit_account', account_id=account_id),
                               account=account, # تمرير بيانات الحساب الحالي
                               form_data=None,
                               account_types=ACCOUNT_TYPES,
                               parent_accounts=parent_accounts,
                               existing_accounts=existing_accounts_sidebar) # <-- تمرير القائمة الجديدة

    except sqlite3.Error as e:
        flash(f'حدث خطأ أثناء جلب بيانات الحساب: {e}', 'danger')
        return redirect(url_for('list_accounts'))
    finally:
        if conn:
            conn.close()

# --- معالجة تعديل حساب ---
@app.route('/accounts/edit/<int:account_id>', methods=['POST'])
@require_login
def edit_account(account_id):
    """يعالج بيانات نموذج تعديل حساب موجود."""
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    account_type_str = request.form.get('account_type')
    parent_id_str = request.form.get('parent_id')
    is_active = 1 if request.form.get('is_active') else 0
    allows_posting = 1 if request.form.get('allows_posting') else 0

    errors = []
    account_type = None
    parent_id = None

    if not code: errors.append('رمز الحساب مطلوب.')
    if not name: errors.append('اسم الحساب مطلوب.')
    if not account_type_str:
        errors.append('نوع الحساب مطلوب.')
    else:
        try:
            account_type = int(account_type_str)
            if account_type not in ACCOUNT_TYPES:
                errors.append('نوع الحساب غير صالح.')
        except ValueError:
            errors.append('نوع الحساب يجب أن يكون رقمًا.')

    if parent_id_str and parent_id_str != 'None':
        try:
            parent_id = int(parent_id_str)
            # منع تعيين الحساب كأب لنفسه
            if parent_id == account_id:
                 errors.append('لا يمكن تعيين الحساب كأب لنفسه.')
            # لاحقاً: يجب إضافة تحقق أكثر تعقيدًا لمنع الحلقات (الأب يصبح ابن الابن وهكذا)
        except ValueError:
            errors.append('الحساب الأصل المحدد غير صالح.')
    else:
         parent_id = None

    conn = None
    parent_accounts = [] # لإعادة العرض عند الخطأ
    account_data_for_form = None # لتمرير بيانات الحساب الأصلية عند الخطأ
    existing_accounts_sidebar = [] # <-- إضافة هذا
    try:
        conn = get_db()
        cursor = conn.cursor()

        # جلب بيانات الحساب الأصلية للتحقق وإعادة العرض عند الخطأ
        cursor.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        account_data_for_form = cursor.fetchone()
        if not account_data_for_form:
             flash('الحساب الذي تحاول تعديله لم يعد موجوداً.', 'danger')
             return redirect(url_for('list_accounts'))

        # التحقق من تكرار رمز الحساب (باستثناء الحساب الحالي)
        if code:
            cursor.execute("SELECT id FROM accounts WHERE code = ? AND id != ?", (code, account_id))
            if cursor.fetchone():
                errors.append(f'رمز الحساب "{code}" مستخدم بالفعل لحساب آخر.')

        # التحقق من وجود الحساب الأصل إذا تم تحديده
        if parent_id is not None:
             cursor.execute("SELECT id FROM accounts WHERE id = ?", (parent_id,))
             if not cursor.fetchone():
                 errors.append('الحساب الأصل المحدد غير موجود.')

        # جلب قائمة الحسابات الأصل مرة أخرى لإعادة العرض عند الخطأ
        cursor.execute("""
            SELECT id, code, name FROM accounts
            WHERE is_active = 1 AND id != ?
            ORDER BY code
        """, (account_id,))
        parent_accounts = cursor.fetchall()
        # جلب بيانات الشريط الجانبي باستخدام الدالة الجديدة
        existing_accounts_sidebar = get_accounts_hierarchy_with_level(conn) # <-- استخدام الدالة الجديدة

        if errors:
            for error in errors:
                flash(error, 'warning')
            # تأكد من أن account_data_for_form ليس None قبل استخدامه
            if not account_data_for_form:
                 flash('خطأ: لم يتم العثور على بيانات الحساب الأصلية.', 'danger')
                 return redirect(url_for('list_accounts'))

            return render_template('account_form.html',
                                   form_title=f"تعديل الحساب: {account_data_for_form['name']}",
                                   form_action=url_for('edit_account', account_id=account_id),
                                   account=account_data_for_form, # تمرير البيانات الأصلية
                                   form_data=request.form, # إعادة تمرير البيانات المدخلة
                                   account_types=ACCOUNT_TYPES,
                                   parent_accounts=parent_accounts,
                                   existing_accounts=existing_accounts_sidebar) # <-- تمرير بيانات الشريط الجانبي

        # تحديث الحساب في قاعدة البيانات
        cursor.execute("""
            UPDATE accounts SET
            code = ?, name = ?, account_type = ?, parent_id = ?, is_active = ?, allows_posting = ?
            WHERE id = ?
        """, (code, name, account_type, parent_id, is_active, allows_posting, account_id))
        conn.commit()
        flash(f'تم تحديث الحساب "{name}" بنجاح.', 'success')
        return redirect(url_for('list_accounts'))

    except sqlite3.Error as e:
        if conn: conn.rollback()
        flash(f'حدث خطأ أثناء تحديث الحساب: {e}', 'danger')
        # محاولة جلب البيانات مرة أخرى لعرض النموذج بشكل صحيح
        if conn:
            try:
                cursor = conn.cursor()
                # جلب بيانات الحساب مرة أخرى إذا لم تكن موجودة
                if not account_data_for_form:
                    cursor.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
                    account_data_for_form = cursor.fetchone()
                # جلب قائمة الآباء مرة أخرى إذا لم تكن موجودة
                if not parent_accounts:
                    cursor.execute("""
                       SELECT id, code, name FROM accounts
                       WHERE is_active = 1 AND id != ?
                       ORDER BY code
                    """, (account_id,))
                    parent_accounts = cursor.fetchall()
                # جلب بيانات الشريط الجانبي مرة أخرى إذا لم تكن موجودة
                if not existing_accounts_sidebar:
                     existing_accounts_sidebar = get_accounts_hierarchy_with_level(conn) # <-- استخدام الدالة الجديدة
            except sqlite3.Error as fetch_err:
                 print(f"Error fetching data on error path: {fetch_err}")
                 # قد تحتاج لتعيين قيم افتراضية إذا فشل الجلب

        # إعادة العرض فقط إذا تمكنا من جلب بيانات الحساب الأصلية
        if account_data_for_form:
            return render_template('account_form.html',
                                   form_title=f"تعديل الحساب: {account_data_for_form['name']}",
                                   form_action=url_for('edit_account', account_id=account_id),
                                   account=account_data_for_form,
                                   form_data=request.form,
                                   account_types=ACCOUNT_TYPES,
                                   parent_accounts=parent_accounts,
                                   existing_accounts=existing_accounts_sidebar) # <-- تمرير بيانات الشريط الجانبي
        else:
            # إذا فشل كل شيء، أعد التوجيه للقائمة
            flash('حدث خطأ إضافي أثناء محاولة عرض النموذج مرة أخرى.', 'danger')
            return redirect(url_for('list_accounts'))

    finally:
        if conn: conn.close()


# --- حذف حساب ---
@app.route('/accounts/delete/<int:account_id>', methods=['POST'])
@require_login
def delete_account(account_id):
    """يعالج طلب حذف حساب."""
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 1. التحقق من وجود الحساب
        cursor.execute("SELECT name FROM accounts WHERE id = ?", (account_id,))
        account_to_delete = cursor.fetchone()
        if not account_to_delete:
             flash('الحساب المراد حذفه غير موجود.', 'warning')
             return redirect(url_for('list_accounts'))

        # 2. (هام) التحقق مما إذا كان الحساب أب لحسابات أخرى
        cursor.execute("SELECT COUNT(id) as child_count FROM accounts WHERE parent_id = ?", (account_id,))
        result = cursor.fetchone()
        if result and result['child_count'] > 0:
             flash(f"لا يمكن حذف الحساب '{account_to_delete['name']}' لأنه حساب أب لحسابات أخرى.", 'danger')
             return redirect(url_for('list_accounts'))

        # 3. (هام) التحقق مما إذا كانت هناك قيود محاسبية مرتبطة بهذا الحساب (مثال)
        #    cursor.execute("SELECT COUNT(*) FROM journal_entries WHERE account_id = ?", (account_id,))
        #    if cursor.fetchone()[0] > 0:
        #        flash("لا يمكن حذف الحساب لوجود قيود مرتبطة به.", 'danger')
        #        return redirect(url_for('list_accounts'))

        # 4. تنفيذ الحذف
        cursor.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        conn.commit()
        flash(f"تم حذف الحساب '{account_to_delete['name']}' بنجاح.", 'success')

    except sqlite3.Error as e:
        if conn: conn.rollback()
        # التحقق من نوع الخطأ لتحديد الرسالة المناسبة
        if "FOREIGN KEY constraint failed" in str(e):
             flash(f"لا يمكن حذف الحساب '{account_to_delete['name'] if account_to_delete else ''}' لوجود بيانات مرتبطة به (مثل قيود يومية).", 'danger')
        else:
             flash(f"حدث خطأ أثناء حذف الحساب: {e}.", 'danger')
    finally:
        if conn: conn.close()

    return redirect(url_for('list_accounts'))

# --- تصدير الحسابات إلى Excel ---
@app.route('/accounts/export/excel')
@require_login
def export_accounts_excel():
    conn = None
    try:
        conn = get_db()
        # استخدام نفس الدالة لجلب البيانات الهرمية
        accounts_hierarchy = get_accounts_hierarchy_with_level(conn)

        # تحضير البيانات لـ DataFrame مع إضافة مسافات بادئة للمستوى
        data_for_excel = []
        for acc in accounts_hierarchy:
            indent = "    " * acc.get('level', 0) # مسافة بادئة حسب المستوى
            data_for_excel.append({
                'الكود': acc['code'],
                'اسم الحساب': indent + acc['name'],
                'نوع الحساب': ACCOUNT_TYPES.get(acc['account_type'], 'غير معروف'),
                'الحساب الأب': acc.get('parent_name', '-'), # استخدام اسم الأب إذا كان متاحاً
                'نشط': 'نعم' if acc['is_active'] else 'لا',
                'يسمح بالترحيل': 'نعم' if acc['allows_posting'] else 'لا'
            })

        df = pd.DataFrame(data_for_excel)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='شجرة الحسابات')
            # (اختياري) تعديل عرض الأعمدة في Excel
            worksheet = writer.sheets['شجرة الحسابات']
            worksheet.column_dimensions['A'].width = 20 # الكود
            worksheet.column_dimensions['B'].width = 50 # اسم الحساب
            worksheet.column_dimensions['C'].width = 15 # نوع الحساب
            worksheet.column_dimensions['D'].width = 30 # الحساب الأب
            worksheet.column_dimensions['E'].width = 10 # نشط
            worksheet.column_dimensions['F'].width = 15 # يسمح بالترحيل
        output.seek(0)

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='accounts_export.xlsx'
        )
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء تصدير الحسابات إلى Excel: {e}", "danger")
        return redirect(url_for('list_accounts'))
    except Exception as e:
        flash(f"حدث خطأ غير متوقع أثناء التصدير: {e}", "danger")
        return redirect(url_for('list_accounts'))
    finally:
        if conn: conn.close()

# --- تصدير الحسابات إلى PDF ---
@app.route('/accounts/export/pdf')
@require_login
def export_accounts_pdf():
    conn = None
    try:
        conn = get_db()
        accounts_hierarchy = get_accounts_hierarchy_with_level(conn)

        headers = ['الكود', 'اسم الحساب', 'النوع', 'الأب', 'نشط', 'ترحيل']
        data_for_pdf = []
        for acc in accounts_hierarchy:
            indent = "\u00A0" * 4 * acc.get('level', 0) # استخدام مسافة غير قابلة للكسر في PDF
            data_for_pdf.append({
                'الكود': acc['code'],
                'اسم الحساب': indent + acc['name'],
                'النوع': ACCOUNT_TYPES.get(acc['account_type'], '?'),
                'الأب': acc.get('parent_name', '-'),
                'نشط': 'نعم' if acc['is_active'] else 'لا',
                'ترحيل': 'نعم' if acc['allows_posting'] else 'لا'
            })

        return generate_pdf(
            data_for_pdf,
            headers,
            "شجرة الحسابات",
            filename="accounts_export.pdf",
            column_widths=[80, 200, 60, 100, 40, 40] # تعديل العرض حسب الحاجة
        )
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء تصدير الحسابات إلى PDF: {e}", "danger")
        return redirect(url_for('list_accounts'))
    except Exception as e:
        flash(f"حدث خطأ غير متوقع أثناء التصدير: {e}", "danger")
        return redirect(url_for('list_accounts'))
    finally:
        if conn: conn.close()


# --- مسارات تبديل حالة الحساب ---
@app.route('/accounts/toggle-active/<int:account_id>', methods=['POST'])
@require_login
def toggle_account_active(account_id):
    try:
        data = request.get_json()
        is_active = data.get('is_active', 0)
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE accounts SET is_active = ? WHERE id = ?",
            (is_active, account_id)
        )
        conn.commit()
        conn.close()
        
        status_text = "نشط" if is_active else "غير نشط"
        return jsonify({
            'success': True,
            'message': f'تم تحديث حالة الحساب إلى {status_text} بنجاح'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        }), 500

@app.route('/accounts/toggle-posting/<int:account_id>', methods=['POST'])
@require_login
def toggle_account_posting(account_id):
    try:
        data = request.get_json()
        allows_posting = data.get('allows_posting', 0)
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE accounts SET allows_posting = ? WHERE id = ?",
            (allows_posting, account_id)
        )
        conn.commit()
        conn.close()
        
        status_text = "يقبل الترحيل" if allows_posting else "لا يقبل الترحيل"
        return jsonify({
            'success': True,
            'message': f'تم تحديث حالة الحساب إلى {status_text} بنجاح'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        }), 500

# ==================================================
# ========== نهاية إدارة شجرة الحسابات ==========
# ==================================================

# ==================================================
# ========== إدارة سندات الصرف (Payment Vouchers) =============
# ==================================================

# ... existing code ...

# --- وظائف سندات الصرف ---

@app.route('/receipt_vouchers/print/<int:voucher_id>')
@require_login
def print_receipt_voucher(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # استعلام لجلب بيانات سند القبض
        cursor.execute("""
            SELECT rv.*, fy.year_name, u.username as created_by_name
            FROM receipt_vouchers rv
            LEFT JOIN financial_years fy ON rv.financial_year_id = fy.id
            LEFT JOIN users u ON rv.created_by = u.id
            WHERE rv.id = ?
        """, (voucher_id,))
        voucher = cursor.fetchone()
        
        if not voucher:
            flash('سند القبض المطلوب غير موجود.', 'danger')
            return redirect(url_for('list_receipt_vouchers'))
        
        # تحويل المبلغ إلى كلمات باستخدام الدالة المعرفة
        amount_in_words = amount_to_arabic_words(voucher['amount'])
        
        # إضافة التاريخ الحالي
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # إعداد قالب الطباعة
        return render_template('print_receipt_voucher.html', 
                              voucher=voucher,
                              amount_in_words=amount_in_words,
                              current_date=current_date,
                              print_mode=True)
        
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء جلب بيانات سند القبض: {e}", 'danger')
        return redirect(url_for('list_receipt_vouchers'))
    finally:
        if conn:
            conn.close()

@app.route('/receipt_vouchers', methods=['GET'])
@require_login
def list_receipt_vouchers():
    conn = None
    vouchers = []
    pagination = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        # قراءة متغيرات البحث من الطلب
        created_by_name = request.args.get('created_by_name', '').strip()
        voucher_number = request.args.get('voucher_number', '').strip()
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()
        payer = request.args.get('payer', '').strip()
        amount_from = request.args.get('amount_from', '').strip()
        amount_to = request.args.get('amount_to', '').strip()
        payment_method = request.args.get('payment_method', '').strip()
        is_posted = request.args.get('is_posted', '').strip()
        
        # استخراج معلمات الترتيب من الطلب
        sort_by = request.args.get('sort_by', 'voucher_number')
        sort_order = request.args.get('sort_order', 'desc')
        
        # التحقق من صحة حقل الترتيب
        valid_sort_fields = ['voucher_number', 'voucher_date', 'payer', 'amount', 'payment_method', 'is_posted']
        if sort_by not in valid_sort_fields:
            sort_by = 'voucher_number'  # استخدام القيمة الافتراضية إذا كانت القيمة غير صالحة
        
        # التحقق من صحة اتجاه الترتيب
        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'  # استخدام القيمة الافتراضية إذا كانت القيمة غير صالحة
        
        query = """
            SELECT rv.*, u.full_name AS created_by_name
            FROM receipt_vouchers rv
            LEFT JOIN users u ON rv.created_by = u.id
            WHERE 1=1
        """
        params = []

        # إضافة شرط البحث على اسم المستخدم إذا تم إدخاله
        if created_by_name:
            query += " AND u.full_name LIKE ?"
            params.append(f"%{created_by_name}%")
        if voucher_number:
            query += " AND rv.voucher_number LIKE ?"
            params.append(f"%{voucher_number}%")
        if date_from:
            query += " AND rv.voucher_date >= ?"
            params.append(date_from)
        if date_to:
            query += " AND rv.voucher_date <= ?"
            params.append(date_to)
        if payer:
            query += " AND rv.payer LIKE ?"
            params.append(f"%{payer}%")
        if amount_from:
            query += " AND rv.amount >= ?"
            params.append(amount_from)
        if amount_to:
            query += " AND rv.amount <= ?"
            params.append(amount_to)
        if payment_method:
            query += " AND rv.payment_method = ?"
            params.append(payment_method)
        if is_posted != "":
            query += " AND rv.is_posted = ?"
            params.append(is_posted)

        # إضافة شرط الترتيب
        query += f" ORDER BY rv.{sort_by} {sort_order}"

        cursor.execute(query, params)
        vouchers = cursor.fetchall()
        # ... كود الترقيم (pagination) إذا كان موجود ...
    except Exception as e:
        flash(f"حدث خطأ أثناء جلب سندات القبض: {e}", "danger")
    finally:
        if conn:
            conn.close()
    
    # إضافة معلومات المستخدم الحالي
    current_user = {
        'is_admin': session.get('is_admin', False)
    }
    
    return render_template('list_receipt_vouchers.html', vouchers=vouchers, pagination=pagination, request=request, current_user=current_user)

@app.route('/receipt_vouchers/view/<int:voucher_id>')
@require_login
def view_receipt_voucher(voucher_id):
    """عرض تفاصيل سند قبض"""
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # استعلام للحصول على بيانات سند القبض
        cursor.execute("""
            SELECT rv.*, fy.year_name, 
                   u_created.username as created_by,
                   u_posted.username as posted_by_name,
                   jv.id as journal_id
            FROM receipt_vouchers rv
            LEFT JOIN financial_years fy ON rv.financial_year_id = fy.id
            LEFT JOIN users u_created ON rv.created_by = u_created.id
            LEFT JOIN users u_posted ON rv.posted_by = u_posted.id
            LEFT JOIN journal_vouchers jv ON jv.receipt_voucher_id = rv.id
            WHERE rv.id = ?
        """, (voucher_id,))
        
        voucher = cursor.fetchone()
        
        if not voucher:
            flash('سند القبض غير موجود.', 'danger')
            return redirect(url_for('list_receipt_vouchers'))
        
        # الحصول على معرف قيد اليومية المرتبط (إذا وجد)
        journal_id = voucher['journal_id'] if voucher['journal_id'] else None
        
        return render_template('view_receipt_voucher.html', 
                              voucher=voucher,
                              journal_id=journal_id)
        
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء جلب بيانات السند: {e}", 'danger')
        return redirect(url_for('list_receipt_vouchers'))
    finally:
        if conn:
            conn.close()

@app.route('/receipt_vouchers/post/<int:voucher_id>', methods=['GET'])
@require_login
def post_receipt_voucher(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # التحقق من وجود السند وأنه غير مرحل
        cursor.execute("""
            SELECT * FROM receipt_vouchers WHERE id = ? AND is_posted = 0
        """, (voucher_id,))
        voucher = cursor.fetchone()
        
        if not voucher:
            flash('سند القبض غير موجود أو تم ترحيله بالفعل.', 'warning')
            return redirect(url_for('list_receipt_vouchers'))
        
        # ترحيل السند
        cursor.execute("""
            UPDATE receipt_vouchers 
            SET is_posted = 1, posted_by = ?, posted_at = datetime('now')
            WHERE id = ?
        """, (session['user_id'], voucher_id))
        
        # ترحيل القيد المحاسبي المرتبط
        cursor.execute("""
            UPDATE journal_vouchers 
            SET is_posted = 1, posted_by = ?, posted_at = datetime('now')
            WHERE receipt_voucher_id = ?
        """, (session['user_id'], voucher_id))
        
        conn.commit()
        flash('تم ترحيل سند القبض بنجاح.', 'success')
        
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        flash(f'حدث خطأ أثناء ترحيل سند القبض: {e}', 'danger')
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for('view_receipt_voucher', voucher_id=voucher_id))

@app.route('/receipt_vouchers/unpost/<int:voucher_id>', methods=['GET'])
@require_login
def unpost_receipt_voucher(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # التحقق من وجود السند وأنه مرحل
        cursor.execute("""
            SELECT * FROM receipt_vouchers WHERE id = ? AND is_posted = 1
        """, (voucher_id,))
        voucher = cursor.fetchone()
        
        if not voucher:
            flash('سند القبض غير موجود أو غير مرحل.', 'warning')
            return redirect(url_for('list_receipt_vouchers'))
        
        # إلغاء ترحيل السند
        cursor.execute("""
            UPDATE receipt_vouchers 
            SET is_posted = 0, posted_by = NULL, posted_at = NULL
            WHERE id = ?
        """, (voucher_id,))
        
        # إلغاء ترحيل القيد المحاسبي المرتبط
        cursor.execute("""
            UPDATE journal_vouchers 
            SET is_posted = 0, posted_by = NULL, posted_at = NULL
            WHERE receipt_voucher_id = ?
        """, (voucher_id,))
        
        conn.commit()
        flash('تم إلغاء ترحيل سند القبض بنجاح.', 'success')
        
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        flash(f'حدث خطأ أثناء إلغاء ترحيل سند القبض: {e}', 'danger')
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for('view_receipt_voucher', voucher_id=voucher_id))

@app.route('/receipt_vouchers/delete/<int:voucher_id>', methods=['GET', 'POST'])
@require_login
def delete_receipt_voucher(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # التحقق من وجود السند
        cursor.execute("SELECT voucher_number FROM receipt_vouchers WHERE id = ?", (voucher_id,))
        voucher = cursor.fetchone()
        
        if not voucher:
            flash('سند القبض غير موجود.', 'danger')
            return redirect(url_for('list_receipt_vouchers'))
        
        # التحقق من حالة الترحيل
        cursor.execute("SELECT is_posted FROM receipt_vouchers WHERE id = ?", (voucher_id,))
        is_posted = cursor.fetchone()['is_posted']
        
        if is_posted:
            flash('لا يمكن حذف سند قبض مرحل.', 'danger')
            return redirect(url_for('view_receipt_voucher', voucher_id=voucher_id))
        
        # إذا كان الطلب GET، عرض صفحة تأكيد الحذف
        if request.method == 'GET':
            return render_template('confirm_delete_receipt_voucher.html', voucher_id=voucher_id, voucher_number=voucher['voucher_number'])
        
        # البحث عن القيد المرتبط بسند القبض
        cursor.execute("""
            SELECT id FROM journal_vouchers 
            WHERE receipt_voucher_id = ?
        """, (voucher_id,))
        journal_voucher = cursor.fetchone()
        
        # بدء المعاملة
        conn.execute("BEGIN TRANSACTION")
        
        # حذف القيد المرتبط إذا وجد
        if journal_voucher:
            # حذف تفاصيل القيد أولاً
            cursor.execute("DELETE FROM journal_voucher_details WHERE voucher_id = ?", (journal_voucher['id'],))
            # ثم حذف القيد نفسه
            cursor.execute("DELETE FROM journal_vouchers WHERE id = ?", (journal_voucher['id'],))
        
        # حذف سند القبض
        cursor.execute("DELETE FROM receipt_vouchers WHERE id = ?", (voucher_id,))
        
        # تأكيد المعاملة
        conn.commit()
        
        flash(f'تم حذف سند القبض رقم {voucher["voucher_number"]} والقيد المرتبط به بنجاح.', 'success')
        return redirect(url_for('list_receipt_vouchers'))
        
    except Exception as e:
        # التراجع عن المعاملة في حالة حدوث خطأ
        if conn:
            conn.rollback()
        flash(f'حدث خطأ أثناء حذف سند القبض: {e}', 'danger')
        return redirect(url_for('list_receipt_vouchers'))
    finally:
        if conn:
            conn.close()

@app.route('/receipt_vouchers/edit/<int:voucher_id>', methods=['GET', 'POST'])
@require_login
def edit_receipt_voucher(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # جلب بيانات سند القبض
        cursor.execute("SELECT * FROM receipt_vouchers WHERE id = ?", (voucher_id,))
        voucher = cursor.fetchone()
        
        if not voucher:
            flash('سند القبض المطلوب غير موجود.', 'danger')
            return redirect(url_for('list_receipt_vouchers'))
        
        # التحقق من حالة الترحيل
        if voucher['is_posted']:
            flash('لا يمكن تعديل سند قبض مرحل.', 'danger')
            return redirect(url_for('view_receipt_voucher', voucher_id=voucher_id))
        
        # جلب قائمة السنوات المالية
        cursor.execute("SELECT * FROM financial_years ORDER BY year_name")
        financial_years = cursor.fetchall()
        
        if request.method == 'POST':
            # استخراج البيانات من النموذج
            voucher_date = request.form['voucher_date']
            payer = request.form['payer']
            amount = float(request.form['amount'])
            payment_method = request.form['payment_method']
            financial_year_id = int(request.form['financial_year_id'])
            description = request.form.get('description', '')
            
            # التحقق من طريقة الدفع وجلب بيانات الشيك إذا كانت الطريقة شيك
            check_number = None
            check_date = None
            if payment_method == 'شيك':
                check_number = request.form.get('check_number', '')
                check_date = request.form.get('check_date', '')
            
            # تحديث بيانات سند القبض
            cursor.execute("""
                UPDATE receipt_vouchers SET
                    voucher_date = ?, payer = ?, amount = ?,
                    payment_method = ?, check_number = ?, check_date = ?,
                    description = ?, financial_year_id = ?,
                    updated_by = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                voucher_date, payer, amount,
                payment_method, check_number, check_date,
                description, financial_year_id,
                session['user_id'],
                voucher_id
            ))
            
            conn.commit()
            flash('تم تحديث سند القبض بنجاح!', 'success')
            return redirect(url_for('view_receipt_voucher', voucher_id=voucher_id))
        
        return render_template('edit_receipt_voucher.html', 
                              voucher=voucher,
                              financial_years=financial_years)
        
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء تعديل سند القبض: {e}", 'danger')
        return redirect(url_for('list_receipt_vouchers'))
    finally:
        if conn:
            conn.close()

@app.route('/receipt_vouchers/add', methods=['GET', 'POST'])
@require_login
def add_receipt_voucher():
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # جلب قائمة السنوات المالية
        cursor.execute("SELECT * FROM financial_years ORDER BY year_name")
        financial_years = cursor.fetchall()
        
        # جلب جميع الحسابات النشطة التي تسمح بالترحيل
        cursor.execute("SELECT id, code, name FROM accounts WHERE is_active = 1 AND allows_posting = 1 ORDER BY code")
        accounts_data = cursor.fetchall()
        
        # تحويل النتائج إلى قائمة من القواميس
        accounts = []
        for row in accounts_data:
            accounts.append({
                'id': row['id'],
                'code': row['code'],
                'name': row['name']
            })
        
        # جلب مراكز التكلفة
        cursor.execute("SELECT id, code, name FROM cost_centers ORDER BY name")
        cost_centers_data = cursor.fetchall()
        
        # تحويل النتائج إلى قائمة من القواميس
        cost_centers = []
        for row in cost_centers_data:
            cost_centers.append({
                'id': row['id'],
                'code': row['code'],
                'name': row['name']
            })
        
        if request.method == 'POST':
            # استخراج البيانات من النموذج
            voucher_number = int(request.form['voucher_number'])
            voucher_date = request.form['voucher_date']
            payer = request.form['payer']
            payment_method = request.form['payment_method']
            financial_year_id = int(request.form['financial_year_id'])
            description = request.form.get('description', '')
            
            # التحقق من طريقة الدفع وجلب بيانات الشيك إذا كانت الطريقة شيك
            check_number = None
            check_date = None
            if payment_method == 'شيك':
                check_number = request.form.get('check_number', '')
                check_date = request.form.get('check_date', '')
            
            # استلام بيانات التفاصيل
            account_ids = request.form.getlist('account_id[]')
            debits = request.form.getlist('debit[]')
            credits = request.form.getlist('credit[]')
            detail_descriptions = request.form.getlist('detail_description[]')
            cost_center_ids = request.form.getlist('cost_center_id[]')
            
            # التحقق من صحة البيانات
            errors = []
            if not account_ids or len(account_ids) == 0:
                errors.append('يجب إضافة بند واحد على الأقل')
            
            # حساب إجمالي المدين والدائن
            total_debit = 0
            total_credit = 0
            details_for_save = []
            
            for i in range(len(account_ids)):
                if not account_ids[i]:
                    continue
                
                try:
                    debit_val = float(debits[i].replace(',', '.')) if debits[i] else 0
                    credit_val = float(credits[i].replace(',', '.')) if credits[i] else 0
                    
                    if debit_val < 0 or credit_val < 0:
                        errors.append(f"البند {i+1}: المبالغ يجب أن تكون موجبة.")
                    if debit_val > 0 and credit_val > 0:
                        errors.append(f"البند {i+1}: لا يمكن إدخال مدين ودائن في نفس البند.")
                    if debit_val == 0 and credit_val == 0:
                        errors.append(f"البند {i+1}: يجب إدخال مبلغ مدين أو دائن.")
                    
                    total_debit += debit_val
                    total_credit += credit_val
                    
                    # تحويل 'None' إلى None
                    cc_id = None if cost_center_ids[i] == 'None' else cost_center_ids[i]
                    
                    details_for_save.append({
                        'account_id': int(account_ids[i]),
                        'debit': debit_val,
                        'credit': credit_val,
                        'description': detail_descriptions[i] if i < len(detail_descriptions) else '',
                        'cost_center_id': cc_id
                    })
                    
                except ValueError as ve:
                    errors.append(f"البند {i+1}: خطأ في تنسيق الأرقام ({ve}).")
            
            # التحقق من توازن القيد
            if abs(total_debit - total_credit) > 0.01:
                errors.append(f"القيد غير متوازن! إجمالي المدين: {total_debit:.2f}, إجمالي الدائن: {total_credit:.2f}")
            
            # التحقق من عدم تكرار رقم السند
            cursor.execute("SELECT id FROM receipt_vouchers WHERE voucher_number = ?", (voucher_number,))
            existing_voucher = cursor.fetchone()
            
            if existing_voucher:
                errors.append('رقم السند موجود بالفعل، الرجاء استخدام رقم آخر.')
            
            if errors:
                for error in errors:
                    flash(error, 'danger')
                return render_template('add_receipt_voucher.html', 
                                      financial_years=financial_years,
                                      accounts=accounts,
                                      cost_centers=cost_centers,
                                      next_number=voucher_number,
                                      today=voucher_date,
                                      form_data=request.form,
                                      details_data=details_for_save)
            
            # بدء المعاملة
            conn.execute("BEGIN TRANSACTION")
            
            # إدخال سند القبض الجديد
            cursor.execute("""
                INSERT INTO receipt_vouchers (
                    voucher_number, voucher_date, payer, amount, 
                    payment_method, check_number, check_date, 
                    description, financial_year_id, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                voucher_number, voucher_date, payer, total_credit,
                payment_method, check_number, check_date,
                description, financial_year_id, session['user_id']
            ))
            
            receipt_voucher_id = cursor.lastrowid
            
            # إنشاء قيد يومية مرتبط بالسند
            # الحصول على رقم القيد التلقائي التالي
            cursor.execute("SELECT MAX(CAST(voucher_number AS INTEGER)) FROM journal_vouchers WHERE financial_year_id = ?", (financial_year_id,))
            max_jv_number = cursor.fetchone()[0]
            next_jv_number = str(int(max_jv_number) + 1).zfill(5) if max_jv_number else '00001'
            
            # إدخال قيد اليومية
            cursor.execute("""
                INSERT INTO journal_vouchers (
                    voucher_number, voucher_date, description, total_debit, total_credit,
                    financial_year_id, created_by_user_id, is_posted, receipt_voucher_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """, (
                next_jv_number, voucher_date, f"سند قبض رقم {voucher_number} - {payer}",
                total_debit, total_credit, financial_year_id, session['user_id'], receipt_voucher_id
            ))
            
            journal_voucher_id = cursor.lastrowid
            
            # إدخال تفاصيل القيد
            for detail in details_for_save:
                cursor.execute("""
                    INSERT INTO journal_voucher_details (
                        voucher_id, account_id, debit, credit, description, cost_center_id, receipt_voucher_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    journal_voucher_id, detail['account_id'], detail['debit'], detail['credit'],
                    detail['description'], detail['cost_center_id'], receipt_voucher_id
                ))
            
            conn.commit()
            flash('تم إضافة سند القبض والقيد المحاسبي المرتبط به بنجاح!', 'success')
            return redirect(url_for('list_receipt_vouchers'))
        
        # الحصول على رقم السند التلقائي التالي
        cursor.execute("SELECT MAX(CAST(voucher_number AS INTEGER)) FROM receipt_vouchers")
        max_number = cursor.fetchone()[0]
        next_number = str(int(max_number) + 1).zfill(5) if max_number else '00001'
        
        return render_template('add_receipt_voucher.html', 
                              financial_years=financial_years,
                              accounts=accounts,
                              cost_centers=cost_centers,
                              next_number=next_number,
                              today=date.today().strftime('%Y-%m-%d'))
        
    except sqlite3.Error as e:
        if conn and request.method == 'POST':
            conn.rollback()
        flash(f"حدث خطأ أثناء إضافة سند القبض: {e}", 'danger')
        return redirect(url_for('list_receipt_vouchers'))
    finally:
        if conn:
            conn.close()

@app.route('/payment_vouchers', methods=['GET'])
@require_login
def list_payment_vouchers():
    conn = None
    vouchers = []
    pagination = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        # قراءة متغيرات البحث من الطلب
        created_by_name = request.args.get('created_by_name', '').strip()
        voucher_number = request.args.get('voucher_number', '').strip()
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()
        beneficiary = request.args.get('beneficiary', '').strip()
        amount_from = request.args.get('amount_from', '').strip()
        amount_to = request.args.get('amount_to', '').strip()
        payment_method = request.args.get('payment_method', '').strip()
        is_posted = request.args.get('is_posted', '').strip()
        query = """
            SELECT pv.*, u.full_name AS created_by_name
            FROM payment_vouchers pv
            LEFT JOIN users u ON pv.created_by = u.id
            WHERE 1=1
        """
        params = []

        # إضافة شرط البحث على اسم المستخدم إذا تم إدخاله
        if created_by_name:
            query += " AND u.full_name LIKE ?"
            params.append(f"%{created_by_name}%")
        if voucher_number:
            query += " AND pv.voucher_number LIKE ?"
            params.append(f"%{voucher_number}%")
        if date_from:
            query += " AND pv.voucher_date >= ?"
            params.append(date_from)
        if date_to:
            query += " AND pv.voucher_date <= ?"
            params.append(date_to)
        if beneficiary:
            query += " AND pv.beneficiary LIKE ?"
            params.append(f"%{beneficiary}%")
        if amount_from:
            query += " AND pv.amount >= ?"
            params.append(amount_from)
        if amount_to:
            query += " AND pv.amount <= ?"
            params.append(amount_to)
        if payment_method:
            query += " AND pv.payment_method = ?"
            params.append(payment_method)
        if is_posted != "":
            query += " AND pv.is_posted = ?"
            params.append(is_posted)

        query += " ORDER BY pv.voucher_date DESC, pv.id DESC"

        cursor.execute(query, params)
        vouchers = cursor.fetchall()
        # ... كود الترقيم (pagination) إذا كان موجود ...
    except Exception as e:
        flash(f"حدث خطأ أثناء جلب سندات الصرف: {e}", "danger")
    finally:
        if conn:
            conn.close()
    return render_template('list_payment_vouchers.html', vouchers=vouchers, pagination=pagination, request=request)

def get_next_payment_voucher_number(financial_year_id):
    """الحصول على رقم سند الصرف التالي للسنة المالية المحددة"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT MAX(voucher_number) as max_number FROM payment_vouchers WHERE financial_year_id = ?",
        (financial_year_id,)
    )
    result = cursor.fetchone()
    conn.close()
    
    if result['max_number'] is None:
        return 1
    else:
        return int(result['max_number']) + 1

def get_next_receipt_voucher_number(financial_year_id):
    """الحصول على رقم سند القبض التالي للسنة المالية المحددة"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT MAX(voucher_number) as max_number FROM receipt_vouchers WHERE financial_year_id = ?",
        (financial_year_id,)
    )
    result = cursor.fetchone()
    conn.close()
    
    if result['max_number'] is None:
        return 1
    else:
        return int(result['max_number']) + 1
        
def get_next_receipt_voucher_number(financial_year_id):
    """الحصول على رقم سند القبض التالي للسنة المالية المحددة"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT MAX(voucher_number) as max_number FROM receipt_vouchers WHERE financial_year_id = ?",
        (financial_year_id,)
    )
    result = cursor.fetchone()
    conn.close()
    
    if result['max_number'] is None:
        return 1
    else:
        return int(result['max_number']) + 1

@app.route('/payment_vouchers/add', methods=['GET', 'POST'])
@require_login
def add_payment_voucher():
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # جلب قائمة السنوات المالية
        cursor.execute("SELECT * FROM financial_years ORDER BY year_name")
        financial_years = cursor.fetchall()
        
        # جلب جميع الحسابات النشطة التي تسمح بالترحيل
        cursor.execute("SELECT id, code, name FROM accounts WHERE is_active = 1 AND allows_posting = 1 ORDER BY code")
        accounts = cursor.fetchall()
        
        # جلب مراكز التكلفة
        cursor.execute("SELECT id, code, name FROM cost_centers ORDER BY name")
        cost_centers = cursor.fetchall()
        
        if request.method == 'POST':
            # استخراج البيانات من النموذج
            voucher_number = int(request.form['voucher_number'])
            voucher_date = request.form['voucher_date']
            beneficiary = request.form['beneficiary']
            payment_method = request.form['payment_method']
            financial_year_id = int(request.form['financial_year_id'])
            description = request.form.get('description', '')
            
            # التحقق من طريقة الدفع وجلب بيانات الشيك إذا كانت الطريقة شيك
            check_number = None
            check_date = None
            if payment_method == 'شيك':
                check_number = request.form.get('check_number', '')
                check_date = request.form.get('check_date', '')
            
            # استلام بيانات التفاصيل
            account_ids = request.form.getlist('account_id[]')
            debits = request.form.getlist('debit[]')
            credits = request.form.getlist('credit[]')
            detail_descriptions = request.form.getlist('detail_description[]')
            cost_center_ids = request.form.getlist('cost_center_id[]')
            
            # التحقق من صحة البيانات
            errors = []
            if not account_ids or len(account_ids) == 0:
                errors.append('يجب إضافة بند واحد على الأقل')
            
            # حساب إجمالي المدين والدائن
            total_debit = 0
            total_credit = 0
            details_for_save = []
            
            for i in range(len(account_ids)):
                if not account_ids[i]:
                    continue
                
                try:
                    debit_val = float(debits[i].replace(',', '.')) if debits[i] else 0
                    credit_val = float(credits[i].replace(',', '.')) if credits[i] else 0
                    
                    if debit_val < 0 or credit_val < 0:
                        errors.append(f"البند {i+1}: المبالغ يجب أن تكون موجبة.")
                    if debit_val > 0 and credit_val > 0:
                        errors.append(f"البند {i+1}: لا يمكن إدخال مدين ودائن في نفس البند.")
                    if debit_val == 0 and credit_val == 0:
                        errors.append(f"البند {i+1}: يجب إدخال مبلغ مدين أو دائن.")
                    
                    total_debit += debit_val
                    total_credit += credit_val
                    
                    # تحويل 'None' إلى None
                    cc_id = None if cost_center_ids[i] == 'None' else cost_center_ids[i]
                    
                    details_for_save.append({
                        'account_id': int(account_ids[i]),
                        'debit': debit_val,
                        'credit': credit_val,
                        'description': detail_descriptions[i] if i < len(detail_descriptions) else '',
                        'cost_center_id': cc_id
                    })
                    
                except ValueError as ve:
                    errors.append(f"البند {i+1}: خطأ في تنسيق الأرقام ({ve}).")
            
            # التحقق من توازن القيد
            if abs(total_debit - total_credit) > 0.01:
                errors.append(f"القيد غير متوازن! إجمالي المدين: {total_debit:.2f}, إجمالي الدائن: {total_credit:.2f}")
            
            # التحقق من عدم تكرار رقم السند
            cursor.execute("SELECT id FROM payment_vouchers WHERE voucher_number = ?", (voucher_number,))
            existing_voucher = cursor.fetchone()
            
            if existing_voucher:
                errors.append('رقم السند موجود بالفعل، الرجاء استخدام رقم آخر.')
            
            if errors:
                for error in errors:
                    flash(error, 'danger')
                return render_template('add_payment_voucher.html', 
                                      financial_years=financial_years,
                                      accounts=accounts,
                                      cost_centers=cost_centers,
                                      next_number=voucher_number,
                                      today=voucher_date,
                                      form_data=request.form,
                                      details_data=details_for_save)
            
            # بدء المعاملة
            conn.execute("BEGIN TRANSACTION")
            
            # إدخال سند الصرف الجديد
            cursor.execute("""
                INSERT INTO payment_vouchers (
                    voucher_number, voucher_date, beneficiary, amount, 
                    payment_method, check_number, check_date, 
                    description, financial_year_id, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                voucher_number, voucher_date, beneficiary, total_debit,
                payment_method, check_number, check_date,
                description, financial_year_id, session['user_id']
            ))
            
            payment_voucher_id = cursor.lastrowid
            
            # إنشاء قيد يومية مرتبط بالسند
            # الحصول على رقم القيد التلقائي التالي
            cursor.execute("SELECT MAX(CAST(voucher_number AS INTEGER)) FROM journal_vouchers WHERE financial_year_id = ?", (financial_year_id,))
            max_jv_number = cursor.fetchone()[0]
            next_jv_number = str(int(max_jv_number) + 1).zfill(5) if max_jv_number else '00001'
            
            # إدخال قيد اليومية
            cursor.execute("""
                INSERT INTO journal_vouchers (
                    voucher_number, voucher_date, description, total_debit, total_credit,
                    financial_year_id, created_by_user_id, is_posted, payment_voucher_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """, (
                next_jv_number, voucher_date, f"سند صرف رقم {voucher_number} - {beneficiary}",
                total_debit, total_credit, financial_year_id, session['user_id'], payment_voucher_id
            ))
            
            journal_voucher_id = cursor.lastrowid
            
            # إدخال تفاصيل القيد
            for detail in details_for_save:
                cursor.execute("""
                    INSERT INTO journal_voucher_details (
                        voucher_id, account_id, debit, credit, description, cost_center_id, payment_voucher_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    journal_voucher_id, detail['account_id'], detail['debit'], detail['credit'],
                    detail['description'], detail['cost_center_id'], payment_voucher_id
                ))
            
            conn.commit()
            flash('تم إضافة سند الصرف والقيد المحاسبي المرتبط به بنجاح!', 'success')
            return redirect(url_for('list_payment_vouchers'))
        
        # الحصول على رقم السند التلقائي التالي
        cursor.execute("SELECT MAX(CAST(voucher_number AS INTEGER)) FROM payment_vouchers")
        max_number = cursor.fetchone()[0]
        next_number = str(int(max_number) + 1).zfill(5) if max_number else '00001'
        
        return render_template('add_payment_voucher.html', 
                              financial_years=financial_years,
                              accounts=accounts,
                              cost_centers=cost_centers,
                              next_number=next_number,
                              today=date.today().strftime('%Y-%m-%d'))
        
    except sqlite3.Error as e:
        if conn and request.method == 'POST':
            conn.rollback()
        flash(f"حدث خطأ أثناء إضافة سند الصرف: {e}", 'danger')
        return redirect(url_for('list_payment_vouchers'))
    finally:
        if conn:
            conn.close()

@app.route('/payment_vouchers/view/<int:voucher_id>')
@require_login
def view_payment_voucher(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # استعلام محسن لجلب بيانات السند مع معلومات السنة المالية والمستخدمين
        cursor.execute("""
            SELECT pv.*, fy.year_name, 
                   u_created.username as created_by,
                   u_posted.username as posted_by_name,
                   jv.id as journal_id
            FROM payment_vouchers pv
            LEFT JOIN financial_years fy ON pv.financial_year_id = fy.id
            LEFT JOIN users u_created ON pv.created_by = u_created.id
            LEFT JOIN users u_posted ON pv.posted_by = u_posted.id
            LEFT JOIN journal_vouchers jv ON jv.payment_voucher_id = pv.id
            WHERE pv.id = ?
        """, (voucher_id,))
        
        voucher = cursor.fetchone()
        
        if not voucher:
            flash('سند الصرف غير موجود.', 'danger')
            return redirect(url_for('list_payment_vouchers'))
        
        # الحصول على معرف قيد اليومية المرتبط (إذا وجد)
        journal_id = voucher['journal_id'] if voucher['journal_id'] else None
        
        return render_template('view_payment_voucher.html', 
                              voucher=voucher,
                              journal_id=journal_id)
        
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء جلب بيانات السند: {e}", 'danger')
        return redirect(url_for('list_payment_vouchers'))
    finally:
        if conn:
            conn.close()

@app.route('/payment_vouchers/edit/<int:voucher_id>', methods=['GET', 'POST'])
@require_login
def edit_payment_voucher(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # جلب قائمة السنوات المالية
        cursor.execute("SELECT * FROM financial_years ORDER BY year_name")
        financial_years = cursor.fetchall()
        
        # جلب بيانات سند الصرف
        cursor.execute("SELECT * FROM payment_vouchers WHERE id = ?", (voucher_id,))
        voucher = cursor.fetchone()
        
        if not voucher:
            flash('سند الصرف المطلوب غير موجود.', 'danger')
            return redirect(url_for('list_payment_vouchers'))
        
        # التحقق من حالة الترحيل
        if voucher['is_posted']:
            flash('لا يمكن تعديل سند صرف مرحل.', 'danger')
            return redirect(url_for('view_payment_voucher', voucher_id=voucher_id))
        
        if request.method == 'POST':
            # استخراج البيانات من النموذج
            voucher_date = request.form['voucher_date']
            beneficiary = request.form['beneficiary']
            amount = float(request.form['amount'])
            payment_method = request.form['payment_method']
            financial_year_id = int(request.form['financial_year_id'])
            description = request.form.get('description', '')
            
            # التحقق من طريقة الدفع وجلب بيانات الشيك إذا كانت الطريقة شيك
            check_number = None
            check_date = None
            if payment_method == 'شيك':
                check_number = request.form.get('check_number', '')
                check_date = request.form.get('check_date', '')
            
            # تحديث بيانات سند الصرف
            # --- التعديل هنا: تم تصحيح اسم العمود updated_by واستخدام CURRENT_TIMESTAMP ---
            cursor.execute("""
                UPDATE payment_vouchers SET
                    voucher_date = ?, beneficiary = ?, amount = ?,
                    payment_method = ?, check_number = ?, check_date = ?,
                    description = ?, financial_year_id = ?,
                    updated_by = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                voucher_date, beneficiary, amount,
                payment_method, check_number, check_date,
                description, financial_year_id,
                session['user_id'], # <-- القيمة لـ updated_by
                voucher_id
            ))
            # -----------------------------------------------------------------------
            
            conn.commit()
            flash('تم تحديث سند الصرف بنجاح!', 'success')
            return redirect(url_for('view_payment_voucher', voucher_id=voucher_id))
        
        return render_template('edit_payment_voucher.html', 
                              voucher=voucher,
                              financial_years=financial_years)
        
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء تعديل سند الصرف: {e}", 'danger')
        return redirect(url_for('list_payment_vouchers'))
    finally:
        if conn:
            conn.close()

@app.route('/payment_vouchers/delete/<int:voucher_id>', methods=['GET', 'POST'])
@require_login
def delete_payment_voucher(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # التحقق من وجود السند
        cursor.execute("SELECT voucher_number FROM payment_vouchers WHERE id = ?", (voucher_id,))
        voucher = cursor.fetchone()
        
        if not voucher:
            flash('سند الصرف غير موجود.', 'danger')
            return redirect(url_for('list_payment_vouchers'))
        
        # إذا كان الطلب GET، عرض صفحة تأكيد الحذف
        if request.method == 'GET':
            return render_template('confirm_delete_voucher.html', voucher_id=voucher_id, voucher_number=voucher['voucher_number'])
        
        # البحث عن القيد المرتبط بسند الصرف
        cursor.execute("""
            SELECT id FROM journal_vouchers 
            WHERE payment_voucher_id = ?
        """, (voucher_id,))
        journal_voucher = cursor.fetchone()
        
        # بدء المعاملة
        conn.execute("BEGIN TRANSACTION")
        
        # حذف القيد المرتبط إذا وجد
        if journal_voucher:
            # حذف تفاصيل القيد أولاً
            cursor.execute("DELETE FROM journal_voucher_details WHERE voucher_id = ?", (journal_voucher['id'],))
            # ثم حذف القيد نفسه
            cursor.execute("DELETE FROM journal_vouchers WHERE id = ?", (journal_voucher['id'],))
        
        # حذف سند الصرف
        cursor.execute("DELETE FROM payment_vouchers WHERE id = ?", (voucher_id,))
        
        # تأكيد المعاملة
        conn.commit()
        
        flash(f'تم حذف سند الصرف رقم {voucher["voucher_number"]} والقيد المرتبط به بنجاح.', 'success')
        return redirect(url_for('list_payment_vouchers'))
        
    except Exception as e:
        # التراجع عن المعاملة في حالة حدوث خطأ
        if conn:
            conn.rollback()
        flash(f'حدث خطأ أثناء حذف سند الصرف: {e}', 'danger')
        return redirect(url_for('list_payment_vouchers'))
    finally:
        if conn:
            conn.close()

@app.route('/payment_vouchers/post/<int:voucher_id>', methods=['GET'])
@require_login
def post_payment_voucher(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # التحقق من وجود السند وأنه غير مرحل
        cursor.execute("""
            SELECT * FROM payment_vouchers 
            WHERE id = ? AND is_posted = 0
        """, (voucher_id,))
        voucher = cursor.fetchone()
        
        if not voucher:
            flash('السند غير موجود أو تم ترحيله بالفعل.', 'warning')
            return redirect(url_for('list_payment_vouchers'))
        
        # تحديث حالة الترحيل
        cursor.execute("""
            UPDATE payment_vouchers 
            SET is_posted = 1, 
                posted_by = ?, 
                posted_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (session['user_id'], voucher_id))
        
        # تحديث حالة الترحيل في قيد اليومية المرتبط (إذا كان موجوداً)
        cursor.execute("""
            UPDATE journal_vouchers 
            SET is_posted = 1, 
                posted_by = ?, 
                posted_at = CURRENT_TIMESTAMP 
            WHERE payment_voucher_id = ?
        """, (session['user_id'], voucher_id))
        
        conn.commit()
        flash('تم ترحيل سند الصرف بنجاح.', 'success')
        
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        flash(f'حدث خطأ أثناء ترحيل السند: {e}', 'danger')
    finally:
        if conn:
            conn.close()
    
    # العودة إلى صفحة عرض السند
    return redirect(url_for('view_payment_voucher', voucher_id=voucher_id))

@app.route('/payment_vouchers/unpost/<int:voucher_id>', methods=['GET'])
@require_login
def unpost_payment_voucher(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # التحقق من وجود السند وأنه مرحل
        cursor.execute("""
            SELECT * FROM payment_vouchers 
            WHERE id = ? AND is_posted = 1
        """, (voucher_id,))
        voucher = cursor.fetchone()
        
        if not voucher:
            flash('السند غير موجود أو غير مرحل بالفعل.', 'warning')
            return redirect(url_for('list_payment_vouchers'))
        
        # تحديث حالة الترحيل
        cursor.execute("""
            UPDATE payment_vouchers 
            SET is_posted = 0, 
                posted_by = NULL, 
                posted_at = NULL 
            WHERE id = ?
        """, (voucher_id,))
        
        # تحديث حالة الترحيل في قيد اليومية المرتبط (إذا كان موجوداً)
        cursor.execute("""
            UPDATE journal_vouchers 
            SET is_posted = 0, 
                posted_by = NULL, 
                posted_at = NULL 
            WHERE payment_voucher_id = ?
        """, (voucher_id,))
        
        conn.commit()
        flash('تم فتح ترحيل سند الصرف بنجاح.', 'success')
        
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        flash(f'حدث خطأ أثناء فتح ترحيل السند: {e}', 'danger')
    finally:
        if conn:
            conn.close()
    
    # العودة إلى صفحة عرض السند
    return redirect(url_for('view_payment_voucher', voucher_id=voucher_id))

@app.route('/payment_vouchers/print/<int:voucher_id>')
@require_login
def print_payment_voucher(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # استعلام لجلب بيانات سند الصرف
        cursor.execute("""
            SELECT pv.*, fy.year_name, u.username as created_by_name
            FROM payment_vouchers pv
            LEFT JOIN financial_years fy ON pv.financial_year_id = fy.id
            LEFT JOIN users u ON pv.created_by = u.id
            WHERE pv.id = ?
        """, (voucher_id,))
        voucher = cursor.fetchone()
        
        if not voucher:
            flash('سند الصرف المطلوب غير موجود.', 'danger')
            return redirect(url_for('list_payment_vouchers'))
        
        # تحويل المبلغ إلى كلمات باستخدام الدالة المعرفة
        amount_in_words = amount_to_arabic_words(voucher['amount'])
        
        # إضافة التاريخ الحالي
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # إعداد قالب الطباعة
        return render_template('print_payment_voucher.html', 
                              voucher=voucher,
                              amount_in_words=amount_in_words,
                              current_date=current_date,
                              print_mode=True)
        
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء جلب بيانات سند الصرف: {e}", 'danger')
        return redirect(url_for('list_payment_vouchers'))
    finally:
        if conn:
            conn.close()

# --- دالة مساعدة لتحويل الأرقام إلى كلمات بالعربية ---
def number_to_arabic_words(number):
    # هذه دالة بسيطة لتحويل الأرقام إلى كلمات بالعربية
    # يمكن تطويرها لاحقاً لتغطية جميع الحالات
    
    # قائمة الأرقام من 0 إلى 19
    ones = [
        "صفر", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة",
        "عشرة", "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر", "خمسة عشر", "ستة عشر", "سبعة عشر", "ثمانية عشر", "تسعة عشر"
    ]
    
    # قائمة العشرات
    tens = ["", "", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون"]
    
    # قائمة المئات
    hundreds = ["", "مائة", "مائتان", "ثلاثمائة", "أربعمائة", "خمسمائة", "ستمائة", "سبعمائة", "ثمانمائة", "تسعمائة"]
    
    # قائمة الآلاف
    thousands = ["", "ألف", "ألفان", "ثلاثة آلاف", "أربعة آلاف", "خمسة آلاف", "ستة آلاف", "سبعة آلاف", "ثمانية آلاف", "تسعة آلاف"]
    
    # تحويل الرقم إلى نص
    if number < 20:
        return ones[number]
    elif number < 100:
        if number % 10 == 0:
            return tens[number // 10]
        else:
            return ones[number % 10] + " و" + tens[number // 10]
    elif number < 1000:
        if number % 100 == 0:
            return hundreds[number // 100]
        else:
            return hundreds[number // 100] + " و" + number_to_arabic_words(number % 100)
    elif number < 10000:
        if number % 1000 == 0:
            return thousands[number // 1000]
        else:
            return thousands[number // 1000] + " و" + number_to_arabic_words(number % 1000)
    else:
        return "رقم كبير"

# دالة تحويل المبالغ إلى كلمات باللغة العربية
def amount_to_arabic_words(amount):
    # تعريف الأرقام باللغة العربية
    units = ['', 'واحد', 'اثنان', 'ثلاثة', 'أربعة', 'خمسة', 'ستة', 'سبعة', 'ثمانية', 'تسعة', 'عشرة', 
             'أحد عشر', 'اثنا عشر', 'ثلاثة عشر', 'أربعة عشر', 'خمسة عشر', 'ستة عشر', 'سبعة عشر', 'ثمانية عشر', 'تسعة عشر']
    tens = ['', '', 'عشرون', 'ثلاثون', 'أربعون', 'خمسون', 'ستون', 'سبعون', 'ثمانون', 'تسعون']
    hundreds = ['', 'مائة', 'مائتان', 'ثلاثمائة', 'أربعمائة', 'خمسمائة', 'ستمائة', 'سبعمائة', 'ثمانمائة', 'تسعمائة']
    thousands = ['', 'ألف', 'ألفان', 'ثلاثة آلاف', 'أربعة آلاف', 'خمسة آلاف', 'ستة آلاف', 'سبعة آلاف', 'ثمانية آلاف', 'تسعة آلاف']
    millions = ['', 'مليون', 'مليونان', 'ثلاثة ملايين', 'أربعة ملايين', 'خمسة ملايين', 'ستة ملايين', 'سبعة ملايين', 'ثمانية ملايين', 'تسعة ملايين']
    
    # تحويل المبلغ إلى نص
    amount_str = str(amount)
    
    # فصل الجزء الصحيح عن الكسور
    if '.' in amount_str:
        integer_part, decimal_part = amount_str.split('.')
        # التأكد من أن الكسور لها رقمين فقط
        decimal_part = decimal_part[:2].ljust(2, '0')
    else:
        integer_part = amount_str
        decimal_part = '00'
    
    # تحويل الجزء الصحيح إلى كلمات
    integer_value = int(integer_part)
    if integer_value == 0:
        integer_words = 'صفر'
    else:
        integer_words = ''
        
        # الملايين
        millions_value = integer_value // 1000000
        if millions_value > 0:
            if millions_value <= 10:
                integer_words += millions[millions_value] + ' '
            else:
                integer_words += number_to_words(millions_value) + ' مليون '
            integer_value %= 1000000
        
        # الآلاف
        thousands_value = integer_value // 1000
        if thousands_value > 0:
            if thousands_value <= 10:
                integer_words += thousands[thousands_value] + ' '
            else:
                integer_words += number_to_words(thousands_value) + ' ألف '
            integer_value %= 1000
        
        # المئات
        hundreds_value = integer_value // 100
        if hundreds_value > 0:
            integer_words += hundreds[hundreds_value] + ' '
            integer_value %= 100
        
        # العشرات والآحاد
        if integer_value > 0:
            if integer_value < 20:
                integer_words += units[integer_value]
            else:
                unit = integer_value % 10
                ten = integer_value // 10
                if unit > 0:
                    integer_words += units[unit] + ' و'
                integer_words += tens[ten]
    
    # تحويل الكسور إلى كلمات
    decimal_value = int(decimal_part)
    if decimal_value == 0:
        result = integer_words + ' ' + 'ريال'
    else:
        if decimal_value < 20:
            decimal_words = units[decimal_value]
        else:
            unit = decimal_value % 10
            ten = decimal_value // 10
            if unit > 0:
                decimal_words = units[unit] + ' و' + tens[ten]
            else:
                decimal_words = tens[ten]
        
        result = integer_words + ' ريال و' + decimal_words + ' هللة'
    
    return result

# دالة مساعدة لتحويل الأرقام أقل من 1000
def number_to_words(number):
    units = ['', 'واحد', 'اثنان', 'ثلاثة', 'أربعة', 'خمسة', 'ستة', 'سبعة', 'ثمانية', 'تسعة', 'عشرة', 
             'أحد عشر', 'اثنا عشر', 'ثلاثة عشر', 'أربعة عشر', 'خمسة عشر', 'ستة عشر', 'سبعة عشر', 'ثمانية عشر', 'تسعة عشر']
    tens = ['', '', 'عشرون', 'ثلاثون', 'أربعون', 'خمسون', 'ستون', 'سبعون', 'ثمانون', 'تسعون']
    hundreds = ['', 'مائة', 'مائتان', 'ثلاثمائة', 'أربعمائة', 'خمسمائة', 'ستمائة', 'سبعمائة', 'ثمانمائة', 'تسعمائة']
    
    words = ''
    
    # المئات
    hundreds_value = number // 100
    if hundreds_value > 0:
        words += hundreds[hundreds_value] + ' '
        number %= 100
    
    # العشرات والآحاد
    if number > 0:
        if number < 20:
            words += units[number]
        else:
            unit = number % 10
            ten = number // 10
            if unit > 0:
                words += units[unit] + ' و'
            words += tens[ten]
    
    return words

# ... existing code ...

# ==================================================
# ========== قيود اليومية (Journal Vouchers) =========
# ==================================================

# --- عرض قائمة قيود اليومية ---
@app.route('/journal_vouchers', methods=['GET', 'POST'])
@require_login
def list_journal_vouchers():
    # معالجة طلبات POST (مثل حذف قيد)
    if request.method == 'POST':
        action = request.form.get('action')
        voucher_id = request.form.get('voucher_id')
        
        if action == 'delete' and voucher_id:
            conn = None
            try:
                conn = get_db()
                cursor = conn.cursor()
                
                # التحقق من أن القيد غير مرحل
                cursor.execute("SELECT is_posted FROM journal_vouchers WHERE id = ?", (voucher_id,))
                voucher = cursor.fetchone()
                
                if not voucher:
                    flash('القيد المطلوب غير موجود.', 'danger')
                elif voucher['is_posted']:
                    flash('لا يمكن حذف قيد مرحل.', 'danger')
                else:
                    # حذف تفاصيل القيد أولاً (بسبب قيود المفتاح الأجنبي)
                    cursor.execute("DELETE FROM journal_voucher_details WHERE voucher_id = ?", (voucher_id,))
                    # ثم حذف القيد نفسه
                    cursor.execute("DELETE FROM journal_vouchers WHERE id = ?", (voucher_id,))
                    conn.commit()
                    flash('تم حذف القيد بنجاح.', 'success')
            except sqlite3.Error as e:
                if conn: conn.rollback()
                flash(f"حدث خطأ أثناء حذف القيد: {e}", 'danger')
            finally:
                if conn: conn.close()
    
    # معالجة طلبات GET (عرض القائمة مع تطبيق الفلاتر)
    conn = None
    vouchers = []
    
    try:
        # استخراج معلمات البحث والترتيب
        voucher_number = request.args.get('voucher_number', '').strip()
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()
        description = request.args.get('description', '').strip()
        is_posted = request.args.get('is_posted', '').strip()
        amount_from = request.args.get('amount_from', '').strip()
        amount_to = request.args.get('amount_to', '').strip()
        created_by = request.args.get('created_by', '').strip()
        
        # معلمات الترتيب
        sort_by = request.args.get('sort_by', 'voucher_date')  # الترتيب الافتراضي حسب التاريخ
        sort_order = request.args.get('sort_order', 'desc')  # الترتيب الافتراضي تنازلي
        
        # التحقق من صحة حقل الترتيب
        valid_sort_fields = ['voucher_number', 'voucher_date', 'description', 'year_name', 
                            'total_debit', 'total_credit', 'is_posted', 'created_by_name']
        if sort_by not in valid_sort_fields:
            sort_by = 'voucher_date'  # استخدام القيمة الافتراضية إذا كانت القيمة غير صالحة
        
        # التحقق من صحة اتجاه الترتيب
        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'  # استخدام القيمة الافتراضية إذا كانت القيمة غير صالحة
        
        conn = get_db()
        cursor = conn.cursor()
        
        # بناء الاستعلام الديناميكي
        query = """
            SELECT jv.*, fy.year_name, u.full_name as created_by_name
            FROM journal_vouchers jv
            LEFT JOIN financial_years fy ON jv.financial_year_id = fy.id
            LEFT JOIN users u ON jv.created_by_user_id = u.id
            WHERE 1=1
        """
        params = []

        if voucher_number:
            query += " AND jv.voucher_number LIKE ?"
            params.append(f"%{voucher_number}%")
        if date_from:
            query += " AND jv.voucher_date >= ?"
            params.append(date_from)
        if date_to:
            query += " AND jv.voucher_date <= ?"
            params.append(date_to)
        if description:
            query += " AND jv.description LIKE ?"
            params.append(f"%{description}%")
        if is_posted != "":
            query += " AND jv.is_posted = ?"
            params.append(is_posted)
        if amount_from:
            query += " AND jv.total_debit >= ?"
            params.append(amount_from)
        if amount_to:
            query += " AND jv.total_debit <= ?"
            params.append(amount_to)
        if created_by:
            query += " AND u.full_name LIKE ?"
            params.append(f"%{created_by}%")

        # إضافة ترتيب
        query += f" ORDER BY jv.{sort_by} {sort_order}"

        cursor.execute(query, params)
        vouchers = cursor.fetchall()

    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء جلب قيود اليومية: {e}", "danger")
    finally:
        if conn:
            conn.close()

    return render_template('journal_vouchers.html', vouchers=vouchers)




# --- عرض نموذج إضافة قيد يومية جديد ---
# --- عرض نموذج إضافة قيد يومية جديد --- 
@app.route('/journal_vouchers/add', methods=['GET']) 
@require_login 
def add_journal_voucher_form(): 
    """يعرض نموذج إضافة قيد يومية جديد ويقترح رقم القيد التالي (رقمي فقط).""" 
    conn = None 
    active_financial_year = None 
    posting_accounts = [] 
    cost_centers = [] 
    today_str = date.today().strftime('%Y-%m-%d') 
    suggested_voucher_number = "Error-NoActiveYear" # قيمة افتراضية أولية 

    try: 
        conn = get_db() 
        cursor = conn.cursor() 

        # 1. جلب السنة المالية النشطة والمفتوحة 
        cursor.execute("SELECT id, year_name, start_date, end_date FROM financial_years WHERE is_active = 1 AND is_closed = 0 LIMIT 1") 
        active_financial_year = cursor.fetchone() 

        if active_financial_year: 
            fy_id = active_financial_year['id'] 

            # 2. البحث عن أكبر رقم قيد *رقمي* مسجل في هذه السنة المالية 
            cursor.execute(""" 
                SELECT voucher_number 
                FROM journal_vouchers 
                WHERE financial_year_id = ? 
            """, (fy_id,)) 
            all_vouchers_in_year = cursor.fetchall() 

            max_numeric_voucher = 0 
            for voucher in all_vouchers_in_year:
                voucher_num = voucher['voucher_number']
                # إذا كان الحقل من نوع int (INTEGER)
                if isinstance(voucher_num, int):
                    current_num = voucher_num
                    if current_num > max_numeric_voucher:
                        max_numeric_voucher = current_num
                else:
                    # إذا كان هناك بيانات قديمة كنصوص رقمية
                    try:
                        current_num = int(voucher_num)
                        if current_num > max_numeric_voucher:
                            max_numeric_voucher = current_num
                    except Exception:
                        pass

            # 3. تحديد الرقم التالي 
            next_num = max_numeric_voucher + 1 

            # 4. تنسيق الرقم الجديد (مثلاً 5 أرقام مع تبطين بالأصفار) 
            #    إذا كنت لا تريد تبطين، استخدم: suggested_voucher_number = str(next_num) 
            suggested_voucher_number = f"{next_num:05d}" # مثال: 00001, 00002 ... 

            # 5. جلب الحسابات التي تسمح بالترحيل 
            cursor.execute("SELECT id, code, name FROM accounts WHERE allows_posting = 1 AND is_active = 1 ORDER BY code") 
            posting_accounts = cursor.fetchall() 
            if not posting_accounts: 
                flash('لا توجد حسابات نشطة تسمح بالترحيل. يرجى التأكد من إعداد شجرة الحسابات.', 'warning') 

            # 6. جلب مراكز التكلفة 
            cursor.execute("SELECT id, code, name FROM cost_centers ORDER BY name") 
            cost_centers = cursor.fetchall() 

        else: # إذا لم تكن هناك سنة مالية نشطة 
            flash('لا توجد سنة مالية نشطة ومفتوحة. يرجى تفعيل أو إضافة سنة مالية أولاً.', 'warning') 
            suggested_voucher_number = "N/A" # أو أي قيمة تشير للمشكلة 

    except sqlite3.Error as e: 
        flash(f'حدث خطأ أثناء تحضير نموذج القيد: {e}', 'danger') 
        suggested_voucher_number = "Error-DB" 
    except Exception as e: # التقاط أخطاء أخرى 
        flash(f'حدث خطأ غير متوقع: {e}', 'danger') 
        suggested_voucher_number = "Error-General" 
    finally: 
        if conn: 
            conn.close() 

    return render_template('journal_voucher_form.html', 
                           form_title="إضافة قيد يومية جديد", 
                           form_action=url_for('add_journal_voucher'), 
                           voucher=None, 
                           voucher_details=[], # تمرير قائمة فارغة عند العرض الأول 
                           form_data=None, 
                           active_financial_year=active_financial_year, 
                           posting_accounts=posting_accounts, 
                           cost_centers=cost_centers, 
                           suggested_voucher_number=suggested_voucher_number, # تمرير الرقم المقترح 
                           today_date=today_str 
                           ) 



@app.route('/journal_vouchers/view/<int:voucher_id>')
@require_login
def view_journal_voucher(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # جلب بيانات القيد
        cursor.execute("""
            SELECT jv.*, fy.year_name, 
                   u_created.username as created_by,
                   u_posted.username as posted_by_name
            FROM journal_vouchers jv
            LEFT JOIN financial_years fy ON jv.financial_year_id = fy.id
            LEFT JOIN users u_created ON jv.created_by_user_id = u_created.id
            LEFT JOIN users u_posted ON jv.posted_by = u_posted.id
            WHERE jv.id = ?
        """, (voucher_id,))
        voucher = cursor.fetchone()
        
        if not voucher:
            flash('القيد المطلوب غير موجود.', 'warning')
            return redirect(url_for('list_journal_vouchers'))
        
        # جلب تفاصيل القيد
        cursor.execute("""
            SELECT jvd.*, a.name as account_name, a.code as account_code, cc.name as cost_center_name
            FROM journal_voucher_details jvd
            LEFT JOIN accounts a ON jvd.account_id = a.id
            LEFT JOIN cost_centers cc ON jvd.cost_center_id = cc.id
            WHERE jvd.voucher_id = ?
            ORDER BY jvd.id
        """, (voucher_id,))
        details = cursor.fetchall()
        
        return render_template('view_journal_voucher.html', voucher=voucher, details=details)
        
    except sqlite3.Error as e:
        flash(f"حدث خطأ أثناء عرض القيد: {e}", 'danger')
        return redirect(url_for('list_journal_vouchers'))
    finally:
        if conn: conn.close()


@app.route('/journal_vouchers/delete/<int:voucher_id>', methods=['POST'])
@require_login
def delete_journal_voucher(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # التحقق من وجود القيد وأنه غير مرحل
        cursor.execute("SELECT is_posted FROM journal_vouchers WHERE id = ?", (voucher_id,))
        voucher = cursor.fetchone()
        
        if not voucher:
            flash('القيد المراد حذفه غير موجود.', 'warning')
            return redirect(url_for('list_journal_vouchers'))
            
        if voucher['is_posted']:
            flash('لا يمكن حذف قيد مرحل.', 'danger')
            return redirect(url_for('list_journal_vouchers'))
        
        # حذف تفاصيل القيد أولاً (العلاقات الخارجية)
        cursor.execute("DELETE FROM journal_voucher_details WHERE voucher_id = ?", (voucher_id,))
        # ثم حذف القيد نفسه
        cursor.execute("DELETE FROM journal_vouchers WHERE id = ?", (voucher_id,))
        conn.commit()
        flash('تم حذف القيد بنجاح.', 'success')
        
    except sqlite3.Error as e:
        if conn: conn.rollback()
        flash(f"حدث خطأ أثناء حذف القيد: {e}", 'danger')
    finally:
        if conn: conn.close()
        
    return redirect(url_for('list_journal_vouchers'))



# --- معالجة إضافة قيد يومية جديد ---
@app.route('/journal_vouchers/add', methods=['POST'])
@require_login
def add_journal_voucher():
    """يعالج بيانات نموذج إضافة قيد يومية جديد."""
    conn = None
    # تعريف المتغير مبكراً لضمان وجوده في حالة الخطأ
    details_data_for_rerender = []
    try:
        conn = get_db()
        conn.execute("BEGIN TRANSACTION") # بدء معاملة
        cursor = conn.cursor()

        # --- 1. جلب بيانات رأس القيد ---
        voucher_number = request.form.get('voucher_number')
        voucher_date = request.form.get('voucher_date')
        financial_year_id = request.form.get('financial_year_id')
        description = request.form.get('description')
        created_by_user_id = session.get('user_id')

        # --- التحقق المبدئي من بيانات الرأس ---
        errors = []
        if not voucher_number:
            errors.append("رقم القيد مطلوب.")
        elif not voucher_number.isdigit():
            errors.append("رقم القيد يجب أن يتكون من أرقام فقط.")
        # ... (يمكن إضافة تحققات أخرى للرأس: تكرار الرقم، التاريخ ضمن السنة) ...
        if not voucher_date: errors.append("تاريخ القيد مطلوب.")
        if not financial_year_id: errors.append("السنة المالية غير محددة.")


        # --- 2. جلب ومعالجة بيانات تفاصيل القيد ---
        account_ids = request.form.getlist('account_id[]')
        debits = request.form.getlist('debit[]')
        credits = request.form.getlist('credit[]')
        detail_descriptions = request.form.getlist('detail_description[]')
        cost_center_ids = request.form.getlist('cost_center_id[]')

        total_debit = 0.0
        total_credit = 0.0
        details_for_save = [] # قائمة لتخزين البيانات بعد التحقق والتحويل للحفظ

        if not account_ids:
             errors.append("يجب إضافة بند واحد على الأقل للقيد.")

        for i in range(len(account_ids)):
            acc_id_str = account_ids[i]
            debit_str = debits[i] or '0'
            credit_str = credits[i] or '0'
            desc = detail_descriptions[i]
            cc_id_str = cost_center_ids[i] if i < len(cost_center_ids) else None

            # --- تجميع البيانات كما أدخلها المستخدم لإعادة العرض ---
            details_data_for_rerender.append({
                'account_id': acc_id_str, # الاحتفاظ بـ ID كـ string لتحديد الخيار المختار
                'debit': debit_str,
                'credit': credit_str,
                'description': desc,
                'cost_center_id': cc_id_str # الاحتفاظ بـ ID كـ string
            })

            # --- التحقق من صحة المدخلات وتحويلها للحفظ ---
            try:
                # التحقق من وجود account_id وأنه رقم
                if not acc_id_str or not acc_id_str.isdigit():
                     raise ValueError("معرف الحساب مفقود أو غير صالح.")
                acc_id_int = int(acc_id_str)

                debit_val = float(debit_str.replace(',', '.'))
                credit_val = float(credit_str.replace(',', '.'))
                cc_id = int(cc_id_str) if cc_id_str and cc_id_str != 'None' and cc_id_str.isdigit() else None

                if debit_val < 0 or credit_val < 0:
                    errors.append(f"البند {i+1}: المبالغ يجب أن تكون موجبة.")
                if debit_val > 0 and credit_val > 0:
                    errors.append(f"البند {i+1}: لا يمكن إدخال مدين ودائن في نفس البند.")
                if debit_val == 0 and credit_val == 0:
                     errors.append(f"البند {i+1}: يجب إدخال مبلغ مدين أو دائن.")
                # ... (يمكن إضافة تحققات أخرى للبند: الحساب يسمح بالترحيل، مركز التكلفة موجود) ...

                total_debit += debit_val
                total_credit += credit_val

                # إضافة البيانات المحققة لقائمة الحفظ
                details_for_save.append({
                    'account_id': acc_id_int,
                    'debit': debit_val,
                    'credit': credit_val,
                    'description': desc,
                    'cost_center_id': cc_id
                })

            except ValueError as ve:
                errors.append(f"البند {i+1}: خطأ في تنسيق الأرقام أو الحساب ({ve}).")
            except IndexError:
                 errors.append(f"البند {i+1}: بيانات غير مكتملة.")

        # التحقق من توازن القيد
        if abs(total_debit - total_credit) > 0.001:
            errors.append(f"القيد غير متوازن! إجمالي المدين: {total_debit:.2f}, إجمالي الدائن: {total_credit:.2f}")

        # --- إذا وجدت أخطاء، أعد عرض النموذج مع البيانات المدخلة ---
        if errors:
            for error in errors: flash(error, 'danger')
            conn.rollback() # التراجع عن المعاملة

            # إعادة جلب البيانات اللازمة للـ dropdowns في النموذج
            active_financial_year = None
            posting_accounts = []
            cost_centers = []
            try:
                cursor.execute("SELECT id, year_name, start_date, end_date FROM financial_years WHERE is_active = 1 AND is_closed = 0 LIMIT 1")
                active_financial_year = cursor.fetchone()
                cursor.execute("SELECT id, code, name FROM accounts WHERE allows_posting = 1 AND is_active = 1 ORDER BY code")
                posting_accounts = cursor.fetchall()
                cursor.execute("SELECT id, code, name FROM cost_centers ORDER BY name")
                cost_centers = cursor.fetchall()
            except sqlite3.Error as fetch_err:
                 flash(f"خطأ إضافي أثناء جلب بيانات النموذج: {fetch_err}", "danger")

            # --- إعادة عرض النموذج مع تمرير بيانات الرأس والتفاصيل المدخلة ---
            return render_template('journal_voucher_form.html',
                                   form_title="إضافة قيد يومية جديد (خطأ)",
                                   form_action=url_for('add_journal_voucher'),
                                   voucher=None,
                                   # تمرير بيانات البنود التي جمعناها لإعادة العرض
                                   voucher_details=details_data_for_rerender,
                                   form_data=request.form, # بيانات الرأس
                                   active_financial_year=active_financial_year,
                                   posting_accounts=posting_accounts,
                                   cost_centers=cost_centers,
                                   suggested_voucher_number=voucher_number, # الرقم الذي أدخله المستخدم
                                   today_date=date.today().strftime('%Y-%m-%d')
                                   )

        # --- 3. حفظ رأس القيد (إذا لم تكن هناك أخطاء) ---
        cursor.execute("""
            INSERT INTO journal_vouchers
            (voucher_number, voucher_date, financial_year_id, description, total_debit, total_credit, created_by_user_id, is_posted)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """, (voucher_number, voucher_date, financial_year_id, description, total_debit, total_credit, created_by_user_id))
        voucher_id = cursor.lastrowid

        # --- 4. حفظ تفاصيل القيد (باستخدام البيانات المحققة) ---
        for detail in details_for_save:
            cursor.execute("""
                INSERT INTO journal_voucher_details
                (voucher_id, account_id, debit, credit, description, cost_center_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (voucher_id, detail['account_id'], detail['debit'], detail['credit'], detail['description'], detail['cost_center_id']))

        # --- 5. إتمام المعاملة ---
        conn.commit()
        flash(f"تم حفظ قيد اليومية رقم '{voucher_number}' بنجاح!", 'success')
        return redirect(url_for('add_journal_voucher_form'))

    except sqlite3.Error as e:
        if conn: conn.rollback() # تراجع في حالة أي خطأ في قاعدة البيانات
        flash(f'حدث خطأ فادح أثناء حفظ القيد: {e}', 'danger')
        # إعادة التوجيه إلى نموذج الإضافة مرة أخرى (قد تفقد البيانات هنا)
        # من الأفضل إعادة العرض مع البيانات إذا أمكن
        # return redirect(url_for('add_journal_voucher_form'))
        # محاولة إعادة العرض مع البيانات الموجودة
        active_financial_year = None
        posting_accounts = []
        cost_centers = []
        try:
            # إعادة جلب البيانات اللازمة للنموذج
            conn_err = get_db() # فتح اتصال جديد إذا أغلق السابق
            cursor_err = conn_err.cursor()
            cursor_err.execute("SELECT id, year_name, start_date, end_date FROM financial_years WHERE is_active = 1 AND is_closed = 0 LIMIT 1")
            active_financial_year = cursor_err.fetchone()
            cursor_err.execute("SELECT id, code, name FROM accounts WHERE allows_posting = 1 AND is_active = 1 ORDER BY code")
            posting_accounts = cursor_err.fetchall()
            cursor_err.execute("SELECT id, code, name FROM cost_centers ORDER BY name")
            cost_centers = cursor_err.fetchall()
            conn_err.close()
        except sqlite3.Error as fetch_err:
            flash(f"خطأ إضافي أثناء جلب بيانات النموذج بعد خطأ الحفظ: {fetch_err}", "danger")

        return render_template('journal_voucher_form.html',
                               form_title="إضافة قيد يومية جديد (خطأ فادح)",
                               form_action=url_for('add_journal_voucher'),
                               voucher=None,
                               voucher_details=details_data_for_rerender, # استخدام البيانات المجمعة
                               form_data=request.form,
                               active_financial_year=active_financial_year,
                               posting_accounts=posting_accounts,
                               cost_centers=cost_centers,
                               suggested_voucher_number=request.form.get('voucher_number', 'خطأ'),
                               today_date=date.today().strftime('%Y-%m-%d')
                               )

    except Exception as e: # التقاط أي أخطاء أخرى غير متوقعة
        if conn: conn.rollback()
        flash(f'حدث خطأ غير متوقع: {e}', 'danger')
        # نفس منطق إعادة العرض كما في sqlite3.Error
        active_financial_year = None
        posting_accounts = []
        cost_centers = []
        try:
            conn_err = get_db()
            cursor_err = conn_err.cursor()
            cursor_err.execute("SELECT id, year_name, start_date, end_date FROM financial_years WHERE is_active = 1 AND is_closed = 0 LIMIT 1")
            active_financial_year = cursor_err.fetchone()
            cursor_err.execute("SELECT id, code, name FROM accounts WHERE allows_posting = 1 AND is_active = 1 ORDER BY code")
            posting_accounts = cursor_err.fetchall()
            cursor_err.execute("SELECT id, code, name FROM cost_centers ORDER BY name")
            cost_centers = cursor_err.fetchall()
            conn_err.close()
        except sqlite3.Error as fetch_err:
            flash(f"خطأ إضافي أثناء جلب بيانات النموذج بعد خطأ غير متوقع: {fetch_err}", "danger")

        return render_template('journal_voucher_form.html',
                               form_title="إضافة قيد يومية جديد (خطأ غير متوقع)",
                               form_action=url_for('add_journal_voucher'),
                               voucher=None,
                               voucher_details=details_data_for_rerender,
                               form_data=request.form,
                               active_financial_year=active_financial_year,
                               posting_accounts=posting_accounts,
                               cost_centers=cost_centers,
                               suggested_voucher_number=request.form.get('voucher_number', 'خطأ'),
                               today_date=date.today().strftime('%Y-%m-%d')
                               )
    finally:
        if conn:
            conn.close()



# ... (الكود المتبقي مثل if __name__ == '__main__':)

from flask import render_template, request, redirect, url_for, flash
import json
import os

@app.route('/edit_company_profile', methods=['GET', 'POST'])
def edit_company_profile():
    company_profile_path = os.path.join(os.path.dirname(__file__), 'company_profile.json')
    if request.method == 'POST':
        # استلام البيانات من النموذج وتحديث الملف
        companyName = request.form.get('companyName', '').strip()
        commercialRegistrationNumber = request.form.get('commercialRegistrationNumber', '').strip()
        taxIdentificationNumber = request.form.get('taxIdentificationNumber', '').strip()
        logoPath = request.form.get('logoPath', '').strip()
        new_data = {
            "companyName": companyName,
            "commercialRegistrationNumber": commercialRegistrationNumber,
            "taxIdentificationNumber": taxIdentificationNumber,
            "logoPath": logoPath
        }
        with open(company_profile_path, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
        flash('تم تحديث بيانات الشركة بنجاح!', 'success')
        return redirect(url_for('edit_company_profile'))
    # قراءة البيانات الحالية
    with open(company_profile_path, 'r', encoding='utf-8') as f:
        company_profile = json.load(f)
    return render_template('edit_company_profile.html', company=company_profile)

# --- تبديل حالة الترحيل لسند الصرف ---
@app.route('/payment_vouchers/toggle_posted/<int:voucher_id>', methods=['POST'])
@require_login
def toggle_payment_voucher_posted(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        # جلب السند
        cursor.execute("SELECT * FROM payment_vouchers WHERE id = ?", (voucher_id,))
        voucher = cursor.fetchone()
        if not voucher:
            flash('سند الصرف المطلوب غير موجود.', 'danger')
            return redirect(url_for('list_payment_vouchers'))

        # عكس حالة الترحيل
        new_status = 0 if voucher['is_posted'] else 1

        if new_status == 1:
            cursor.execute("""
                UPDATE payment_vouchers
                SET is_posted = 1,
                    posted_by = ?,
                    posted_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (session['user_id'], voucher_id))
            flash('تم ترحيل سند الصرف بنجاح.', 'success')
        else:
            cursor.execute("""
                UPDATE payment_vouchers
                SET is_posted = 0,
                    posted_by = NULL,
                    posted_at = NULL
                WHERE id = ?
            """, (voucher_id,))
            flash('تم إلغاء ترحيل سند الصرف بنجاح.', 'info')

        conn.commit()
        return redirect(url_for('view_payment_voucher', voucher_id=voucher_id))
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        flash(f'حدث خطأ في قاعدة البيانات: {e}', 'danger')
        return redirect(url_for('view_payment_voucher', voucher_id=voucher_id))
    finally:
        if conn:
            conn.close()

# --- تعديل قيد يومية ---
@app.route('/journal_vouchers/edit/<int:voucher_id>', methods=['GET', 'POST'])
@require_login
def edit_journal_voucher(voucher_id):
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        # --- التعامل مع طلب GET (عرض النموذج) ---
        if request.method == 'GET':
            # جلب بيانات القيد الأساسية
            cursor.execute("""
                SELECT jv.*, fy.year_name
                FROM journal_vouchers jv
                LEFT JOIN financial_years fy ON jv.financial_year_id = fy.id
                WHERE jv.id = ?
            """, (voucher_id,))
            voucher_data = cursor.fetchone()

            if not voucher_data:
                flash('القيد المطلوب غير موجود.', 'danger')
                return redirect(url_for('list_journal_vouchers'))

            # جلب تفاصيل القيد (البنود)
            cursor.execute("""
                SELECT jvd.*, a.name as account_name, a.code as account_code, cc.name as cost_center_name
                FROM journal_voucher_details jvd
                LEFT JOIN accounts a ON jvd.account_id = a.id
                LEFT JOIN cost_centers cc ON jvd.cost_center_id = cc.id
                WHERE jvd.voucher_id = ? ORDER BY jvd.id
            """, (voucher_id,))
            details_data = cursor.fetchall()

            # جلب الحسابات القابلة للنشر ومراكز التكلفة للقوائم المنسدلة
            # تم تعديل اسم العمود من is_posting إلى allows_posting بناءً على الكود الأصلي
            cursor.execute("SELECT id, code, name FROM accounts WHERE allows_posting = 1 AND is_active = 1 ORDER BY code")
            posting_accounts = cursor.fetchall()
            cursor.execute("SELECT id, name FROM cost_centers ORDER BY name")
            cost_centers = cursor.fetchall()

            # --- التعديل المطلوب هنا ---
            # تحويل بيانات القيد الأساسية إلى قاموس لإضافة التفاصيل إليه
            voucher_dict = dict(voucher_data)
            # إضافة قائمة التفاصيل إلى القاموس تحت المفتاح 'details'
            voucher_dict['details'] = [dict(row) for row in details_data] # تحويل الصفوف إلى قواميس
            # --- نهاية التعديل ---

            # تحويل التاريخ إلى كائن date إذا كان نصاً (احتياطي)
            # قد لا يكون ضرورياً إذا كان يُخزن كـ DATE في SQLite
            if isinstance(voucher_dict.get('voucher_date'), str):
                 try:
                     voucher_dict['voucher_date'] = datetime.strptime(voucher_dict['voucher_date'], '%Y-%m-%d').date()
                 except ValueError:
                     # التعامل مع حالة فشل التحويل إذا لزم الأمر
                     flash("تنسيق تاريخ القيد غير صحيح.", "warning")
                     voucher_dict['voucher_date'] = None # أو قيمة افتراضية

            return render_template(
                'edit_journal_voucher.html',
                voucher=voucher_dict, # تمرير القاموس المدمج
                posting_accounts=posting_accounts,
                cost_centers=cost_centers
            )

        # --- التعامل مع طلب POST (حفظ التعديلات) ---
        elif request.method == 'POST':
            # استخراج البيانات من النموذج
            voucher_date_str = request.form.get('voucher_date')
            description = request.form.get('description')
            account_ids = request.form.getlist('account_id[]')
            debits = request.form.getlist('debit[]')
            credits = request.form.getlist('credit[]')
            detail_descriptions = request.form.getlist('detail_description[]')
            cost_center_ids = request.form.getlist('cost_center_id[]')

            # التحقق الأساسي من البيانات
            errors = []
            if not voucher_date_str: errors.append("تاريخ القيد مطلوب.")
            if not account_ids: errors.append("يجب إضافة بند واحد على الأقل.")
            # ... (إضافة المزيد من التحققات إذا لزم الأمر) ...

            # تحويل التاريخ
            try:
                voucher_date = datetime.strptime(voucher_date_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append("تنسيق تاريخ القيد غير صحيح (يجب أن يكون YYYY-MM-DD).")
                voucher_date = None # لمنع خطأ لاحق

            # التحقق من توازن المدين والدائن
            total_debit = sum(float(d.replace(',', '.')) if d else 0 for d in debits)
            total_credit = sum(float(c.replace(',', '.')) if c else 0 for c in credits)
            if abs(total_debit - total_credit) > 0.01: # السماح بفارق بسيط
                errors.append("القيد غير متوازن (إجمالي المدين لا يساوي إجمالي الدائن).")

            if errors:
                for error in errors: flash(error, 'danger')
                # إعادة عرض النموذج مع البيانات المدخلة (تحتاج لإعادة جلب البيانات الأصلية)
                # هذا الجزء يحتاج لتحسين ليعيد عرض البيانات المدخلة بدلاً من الأصلية عند الخطأ
                # للتبسيط الآن، سنعيد التوجيه لصفحة التعديل الأصلية
                # ملاحظة: من الأفضل إعادة عرض النموذج بنفس البيانات التي أدخلها المستخدم
                # ولكن هذا يتطلب إعادة بناء كائن voucher بالبيانات الجديدة
                return redirect(url_for('edit_journal_voucher', voucher_id=voucher_id))


            try:
                # بدء معاملة (Transaction)
                conn.execute("BEGIN TRANSACTION")

                # 1. تحديث بيانات القيد الأساسية
                # --- التعديل هنا: العودة إلى updated_by_user_id ---
                cursor.execute("""
                    UPDATE journal_vouchers
                    SET voucher_date = ?, description = ?, updated_by_user_id = ?, updated_at = ?
                    WHERE id = ?
                """, (voucher_date, description, session['user_id'], datetime.now(), voucher_id))
                # --- نهاية التعديل ---

                # 2. حذف التفاصيل القديمة للقيد
                cursor.execute("DELETE FROM journal_voucher_details WHERE voucher_id = ?", (voucher_id,))

                # 3. إضافة التفاصيل الجديدة وحساب الإجماليات
                new_total_debit = 0.0
                new_total_credit = 0.0
                for i in range(len(account_ids)):
                    acc_id = account_ids[i]
                    debit_val = float(debits[i].replace(',', '.')) if debits[i] else 0
                    credit_val = float(credits[i].replace(',', '.')) if credits[i] else 0
                    desc = detail_descriptions[i]
                    cc_id_str = cost_center_ids[i]
                    cc_id = int(cc_id_str) if cc_id_str and cc_id_str.lower() != 'none' and cc_id_str.isdigit() else None

                    if debit_val > 0 or credit_val > 0:
                        cursor.execute("""
                            INSERT INTO journal_voucher_details
                            (voucher_id, account_id, debit, credit, description, cost_center_id)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (voucher_id, acc_id, debit_val, credit_val, desc, cc_id))
                        new_total_debit += debit_val
                        new_total_credit += credit_val

                # 4. تحديث الإجماليات في رأس القيد
                cursor.execute("""
                    UPDATE journal_vouchers
                    SET total_debit = ?, total_credit = ?
                    WHERE id = ?
                """, (new_total_debit, new_total_credit, voucher_id))

                # إنهاء المعاملة (Commit)
                conn.commit()
                flash('تم تحديث قيد اليومية بنجاح!', 'success')
                return redirect(url_for('list_journal_vouchers'))

            except sqlite3.Error as e:
                if conn: conn.rollback() # التراجع عن التغييرات في حالة الخطأ
                flash(f"حدث خطأ أثناء تحديث القيد: {e}", 'danger')
                # إعادة التوجيه لصفحة التعديل مرة أخرى
                return redirect(url_for('edit_journal_voucher', voucher_id=voucher_id))

    except sqlite3.Error as e:
        flash(f"حدث خطأ في قاعدة البيانات: {e}", 'danger')
        return redirect(url_for('list_journal_vouchers')) # أو صفحة خطأ مناسبة
    finally:
        if conn:
            conn.close()

# وظيفة الحصول على رقم قيد اليومية التالي
def get_next_journal_voucher_number(financial_year_id):
    """الحصول على رقم قيد اليومية التالي للسنة المالية المحددة"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT MAX(voucher_number) as max_number FROM journal_vouchers WHERE financial_year_id = ?",
        (financial_year_id,)
    )
    result = cursor.fetchone()
    conn.close()
    
    if result['max_number'] is None:
        return 1
    else:
        return int(result['max_number']) + 1

# نقطة نهاية API للبحث عن مراكز التكلفة
@app.route('/api/cost_centers', methods=['GET'])
def get_cost_centers():
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # الحصول على معيار البحث إن وجد
        search_query = request.args.get('q', '')
        
        if search_query:
            # البحث في رمز مركز التكلفة واسمه
            cursor.execute("""
                SELECT id, code, name
                FROM cost_centers
                WHERE (code LIKE ? OR name LIKE ?)
                ORDER BY name
            """, (f'%{search_query}%', f'%{search_query}%'))
        else:
            # جلب جميع مراكز التكلفة
            cursor.execute("""
                SELECT id, code, name
                FROM cost_centers
                ORDER BY name
            """)
        
        cost_centers = cursor.fetchall()
        
        # تحويل النتائج إلى قائمة من القواميس
        cost_centers_list = []
        for center in cost_centers:
            cost_centers_list.append({
                'id': center['id'],
                'code': center['code'],
                'name': center['name']
            })
        
        return jsonify({'cost_centers': cost_centers_list})
        
    except sqlite3.Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

# نقطة بداية تشغيل التطبيق
if __name__ == '__main__':
    # debug=True مفيد أثناء التطوير لعرض الأخطاء وتحديث الخادم تلقائياً
    # يجب تعطيله في بيئة الإنتاج (debug=False)
    app.run(debug=True)
