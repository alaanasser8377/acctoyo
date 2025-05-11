# e:\0\5-5\V9\account_statement_report.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from database import get_db
import pandas as pd
import io
from datetime import datetime

# إنشاء Blueprint لتقرير كشف الحساب
account_statement_bp = Blueprint('account_statement', __name__)

def get_active_financial_year_dates():
    """
    الحصول على تواريخ بداية ونهاية السنة المالية النشطة
    
    Returns:
    - tuple: (start_date, end_date) أو (None, None) إذا لم يتم العثور على سنة مالية نشطة
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT start_date, end_date 
            FROM financial_years 
            WHERE is_active = 1 
            LIMIT 1
        """)
        
        result = cursor.fetchone()
        if result:
            return result['start_date'], result['end_date']
        return None, None
    finally:
        conn.close()

@account_statement_bp.route('/reports/account_statement')
def account_statement_report_view():
    """عرض صفحة تقرير كشف الحساب مع إمكانية التصفية"""
    # التحقق من تسجيل الدخول
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # الحصول على تواريخ السنة المالية النشطة
    default_start_date, default_end_date = get_active_financial_year_dates()
    
    # استخراج معايير التصفية من الطلب
    filters = {}
    if request.args.get('account_id'):
        filters['account_id'] = request.args.get('account_id')
    
    # استخدام تاريخ بداية السنة المالية النشطة كقيمة افتراضية إذا لم يتم تحديد تاريخ البداية
    if request.args.get('start_date'):
        filters['start_date'] = request.args.get('start_date')
    elif default_start_date:
        filters['start_date'] = default_start_date
        
    # استخدام تاريخ نهاية السنة المالية النشطة كقيمة افتراضية إذا لم يتم تحديد تاريخ النهاية
    if request.args.get('end_date'):
        filters['end_date'] = request.args.get('end_date')
    elif default_end_date:
        filters['end_date'] = default_end_date
    
    # جلب قائمة الحسابات للاختيار
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, code, name FROM accounts WHERE is_active = 1 ORDER BY code")
    accounts = cursor.fetchall()
    
    # جلب بيانات التقرير إذا تم تحديد حساب
    statement_data = []
    account_info = None
    
    if filters.get('account_id'):
        # جلب معلومات الحساب
        cursor.execute("""
            SELECT id, code, name, account_type
            FROM accounts
            WHERE id = ?
        """, (filters['account_id'],))
        account_info = cursor.fetchone()
        
        if account_info:
            # جلب بيانات كشف الحساب
            statement_data = get_account_statement(conn, filters)
    
    conn.close()
    
    return render_template(
        'reports/account_statement_report.html',
        accounts=accounts,
        statement_data=statement_data,
        account_info=account_info,
        filters=filters,
        default_start_date=default_start_date,
        default_end_date=default_end_date
    )

@account_statement_bp.route('/reports/account_statement/search_accounts', methods=['POST'])
def search_accounts():
    """البحث عن الحسابات بناءً على معايير البحث"""
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح'}), 401
    
    search_term = request.form.get('search_term', '')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # البحث في الحسابات النشطة فقط
    cursor.execute("""
        SELECT id, code, name 
        FROM accounts 
        WHERE is_active = 1 
        AND (code LIKE ? OR name LIKE ?)
        ORDER BY code
    """, (f'%{search_term}%', f'%{search_term}%'))
    
    accounts = cursor.fetchall()
    conn.close()
    
    return jsonify({
        'accounts': [dict(account) for account in accounts]
    })

@account_statement_bp.route('/reports/account_statement/print')
def print_account_statement_report():
    """عرض نسخة للطباعة من تقرير كشف الحساب"""
    # التحقق من تسجيل الدخول
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # الحصول على تواريخ السنة المالية النشطة
    default_start_date, default_end_date = get_active_financial_year_dates()
    
    # استخراج معايير التصفية من الطلب
    filters = {}
    if request.args.get('account_id'):
        filters['account_id'] = request.args.get('account_id')
    
    # استخدام تاريخ بداية السنة المالية النشطة كقيمة افتراضية إذا لم يتم تحديد تاريخ البداية
    if request.args.get('start_date'):
        filters['start_date'] = request.args.get('start_date')
    elif default_start_date:
        filters['start_date'] = default_start_date
        
    # استخدام تاريخ نهاية السنة المالية النشطة كقيمة افتراضية إذا لم يتم تحديد تاريخ النهاية
    if request.args.get('end_date'):
        filters['end_date'] = request.args.get('end_date')
    elif default_end_date:
        filters['end_date'] = default_end_date
    
    # جلب بيانات التقرير إذا تم تحديد حساب
    conn = get_db()
    statement_data = []
    account_info = None
    
    if filters.get('account_id'):
        # جلب معلومات الحساب
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, code, name, account_type
            FROM accounts
            WHERE id = ?
        """, (filters['account_id'],))
        account_info = cursor.fetchone()
        
        if account_info:
            # جلب بيانات كشف الحساب
            statement_data = get_account_statement(conn, filters)
    
    conn.close()
    
    # تاريخ الطباعة
    print_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    return render_template(
        'reports/print_account_statement_report.html',
        statement_data=statement_data,
        account_info=account_info,
        filters=filters,
        print_date=print_date
    )

@account_statement_bp.route('/reports/account_statement/export')
def export_account_statement_report():
    """تصدير تقرير كشف الحساب إلى Excel"""
    # التحقق من تسجيل الدخول
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # الحصول على تواريخ السنة المالية النشطة
    default_start_date, default_end_date = get_active_financial_year_dates()
    
    # استخراج معايير التصفية من الطلب
    filters = {}
    if request.args.get('account_id'):
        filters['account_id'] = request.args.get('account_id')
    
    # استخدام تاريخ بداية السنة المالية النشطة كقيمة افتراضية إذا لم يتم تحديد تاريخ البداية
    if request.args.get('start_date'):
        filters['start_date'] = request.args.get('start_date')
    elif default_start_date:
        filters['start_date'] = default_start_date
        
    # استخدام تاريخ نهاية السنة المالية النشطة كقيمة افتراضية إذا لم يتم تحديد تاريخ النهاية
    if request.args.get('end_date'):
        filters['end_date'] = request.args.get('end_date')
    elif default_end_date:
        filters['end_date'] = default_end_date
    
    # جلب بيانات التقرير
    conn = get_db()
    statement_data = []
    account_info = None
    
    if filters.get('account_id'):
        # جلب معلومات الحساب
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, code, name, account_type
            FROM accounts
            WHERE id = ?
        """, (filters['account_id'],))
        account_info = cursor.fetchone()
        
        if account_info:
            # جلب بيانات كشف الحساب
            statement_data = get_account_statement(conn, filters)
    
    conn.close()
    
    # إذا لم يتم العثور على بيانات
    if not statement_data or not account_info:
        flash('لم يتم العثور على بيانات للتصدير', 'warning')
        return redirect(url_for('account_statement_report_view'))
    
    # تحويل البيانات إلى DataFrame
    df = pd.DataFrame(statement_data)
    
    # إعادة تسمية الأعمدة بأسماء عربية
    columns_mapping = {
        'date': 'التاريخ',
        'description': 'البيان',
        'debit': 'مدين',
        'credit': 'دائن',
        'balance': 'الرصيد',
        'voucher_number': 'رقم القيد'
    }
    
    # إعادة تسمية الأعمدة الموجودة فقط
    rename_cols = {col: columns_mapping[col] for col in df.columns if col in columns_mapping}
    df = df.rename(columns=rename_cols)
    
    # إنشاء ملف Excel في الذاكرة
    output = io.BytesIO()
    
    # استخدام openpyxl
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=f'كشف حساب {account_info["name"]}', index=False)
    
    # إعادة مؤشر الملف إلى البداية
    output.seek(0)
    
    # إنشاء اسم الملف مع التاريخ والوقت
    now = datetime.now()
    file_name = f"كشف_حساب_{account_info['code']}_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    # إرسال الملف للتنزيل
    return send_file(
        output,
        as_attachment=True,
        download_name=file_name,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

def get_account_statement(conn, filters):
    """
    استخراج بيانات كشف الحساب
    
    Parameters:
    - conn: اتصال قاعدة البيانات
    - filters: معايير التصفية (account_id مطلوب)
    
    Returns:
    - قائمة بكافة حركات الحساب مع الأرصدة المتراكمة
    """
    if not filters.get('account_id'):
        return []
    
    cursor = conn.cursor()
    
    # حساب الرصيد الافتتاحي (مجموع الحركات قبل تاريخ البداية)
    opening_balance = 0
    if filters.get('start_date'):
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN jvd.debit > 0 THEN jvd.debit ELSE 0 END) as total_debit,
                SUM(CASE WHEN jvd.credit > 0 THEN jvd.credit ELSE 0 END) as total_credit
            FROM 
                journal_voucher_details jvd
            JOIN 
                journal_vouchers jv ON jvd.voucher_id = jv.id
            WHERE 
                jvd.account_id = ? AND jv.voucher_date < ?
        """, (filters['account_id'], filters['start_date']))
        
        result = cursor.fetchone()
        if result:
            # التحقق من القيم قبل إجراء عملية الطرح
            total_debit = result['total_debit'] if result['total_debit'] is not None else 0
            total_credit = result['total_credit'] if result['total_credit'] is not None else 0
            opening_balance = total_debit - total_credit
            
    # بناء استعلام SQL الأساسي
    query = """
    SELECT 
        jv.voucher_date as date,
        jv.voucher_number,
        jv.id as voucher_id,
        CASE
            WHEN pv.id IS NOT NULL THEN 'سند صرف رقم ' || pv.voucher_number
            WHEN rv.id IS NOT NULL THEN 'سند قبض رقم ' || rv.voucher_number
            ELSE jvd.description
        END as description,
        jvd.debit,
        jvd.credit
    FROM 
        journal_voucher_details jvd
    JOIN 
        journal_vouchers jv ON jvd.voucher_id = jv.id
    LEFT JOIN 
        payment_vouchers pv ON jv.payment_voucher_id = pv.id
    LEFT JOIN 
        receipt_vouchers rv ON jv.receipt_voucher_id = rv.id
    WHERE 
        jvd.account_id = ?
    """
    
    params = [filters['account_id']]
    
    # إضافة شروط التصفية إذا وجدت
    if filters.get('start_date'):
        query += " AND jv.voucher_date >= ?"
        params.append(filters['start_date'])
    
    if filters.get('end_date'):
        query += " AND jv.voucher_date <= ?"
        params.append(filters['end_date'])
    
    # ترتيب النتائج حسب التاريخ
    query += " ORDER BY jv.voucher_date, jv.id"
    
    # تنفيذ الاستعلام
    cursor.execute(query, params)
    
    # استخراج النتائج وحساب الرصيد المتراكم
    results = []
    running_balance = opening_balance
    
    # إضافة سطر الرصيد الافتتاحي إذا كان هناك تاريخ بداية
    if filters.get('start_date'):
        results.append({
            'date': filters['start_date'],
            'voucher_number': '',
            'description': 'الرصيد اول المدة',
            'debit': opening_balance if opening_balance > 0 else 0,
            'credit': abs(opening_balance) if opening_balance < 0 else 0,
            'balance': opening_balance
        })
    
    # إضافة حركات الحساب
    for row in cursor.fetchall():
        row_dict = dict(row)
        running_balance += row_dict['debit'] - row_dict['credit']
        row_dict['balance'] = running_balance
        results.append(row_dict)
    
    # إضافة سطر الإجمالي
    total_debit = sum(row['debit'] for row in results)
    total_credit = sum(row['credit'] for row in results)
    
    results.append({
        'date': '',
        'voucher_number': '',
        'description': 'الأجمالي',
        'debit': total_debit,
        'credit': total_credit,
        'balance': running_balance
    })
    
    return results