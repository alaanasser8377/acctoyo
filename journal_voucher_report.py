import sqlite3
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, send_file
from database import get_db, init_db

def get_journal_vouchers_report(conn=None, filters=None):
    """
    استخراج بيانات تقرير قيود اليومية مع كافة التفاصيل المطلوبة
    
    Parameters:
    - conn: اتصال قاعدة البيانات (اختياري)
    - filters: معايير التصفية (اختياري)
     
    Returns:
    - قائمة بكافة بنود قيود اليومية مع التفاصيل المطلوبة
    """
    close_conn = False
    if conn is None:
        conn = get_db()
        close_conn = True
    
    try:
        cursor = conn.cursor()
        
        # بناء استعلام SQL الأساسي
        query = """
        SELECT 
            jv.id AS voucher_id,
            jv.voucher_number AS voucher_number,
            pv.voucher_number AS payment_voucher_number,
            pv.id AS payment_voucher_id,
            rv.voucher_number AS receipt_voucher_number,
            rv.id AS receipt_voucher_id,
            jv.voucher_date AS voucher_date,
            a.code AS account_code,
            a.name AS account_name,
            jvd.description AS description,
            jvd.debit AS debit,
            jvd.credit AS credit,
            cc.id AS cost_center_id,
            cc.name AS cost_center_name,
            u.username AS created_by,
            CASE
                WHEN pv.id IS NOT NULL THEN 'سند صرف'
                WHEN rv.id IS NOT NULL THEN 'سند قبض'
                ELSE 'قيد يومية'
            END AS voucher_type
        FROM 
            journal_voucher_details jvd
        JOIN 
            journal_vouchers jv ON jvd.voucher_id = jv.id
        JOIN 
            accounts a ON jvd.account_id = a.id
        LEFT JOIN 
            cost_centers cc ON jvd.cost_center_id = cc.id
        LEFT JOIN 
            users u ON jv.created_by_user_id = u.id
        LEFT JOIN 
            payment_vouchers pv ON jv.payment_voucher_id = pv.id
        LEFT JOIN 
            receipt_vouchers rv ON jv.receipt_voucher_id = rv.id
        """
        
        # إضافة شروط التصفية إذا وجدت
        where_clauses = []
        params = []
        
        if filters:
            if filters.get('start_date'):
                where_clauses.append("jv.voucher_date >= ?")
                params.append(filters['start_date'])
            
            if filters.get('end_date'):
                where_clauses.append("jv.voucher_date <= ?")
                params.append(filters['end_date'])
            
            if filters.get('voucher_number'):
                # تعديل البحث برقم القيد ليكون مطابقاً تماماً
                where_clauses.append("jv.voucher_number = ?")
                params.append(filters['voucher_number'])
            
            if filters.get('description'):
                where_clauses.append("jvd.description LIKE ?")
                params.append(f"%{filters['description']}%")
            
            if filters.get('account_id'):
                where_clauses.append("jvd.account_id = ?")
                params.append(filters['account_id'])
            
            if filters.get('cost_center_id'):
                where_clauses.append("jvd.cost_center_id = ?")
                params.append(filters['cost_center_id'])
            
            if filters.get('debit_from') and filters.get('debit_from').strip():
                where_clauses.append("jvd.debit >= ?")
                params.append(float(filters['debit_from']))
            
            if filters.get('debit_to') and filters.get('debit_to').strip():
                where_clauses.append("jvd.debit <= ?")
                params.append(float(filters['debit_to']))
            
            if filters.get('credit_from') and filters.get('credit_from').strip():
                where_clauses.append("jvd.credit >= ?")
                params.append(float(filters['credit_from']))
            
            if filters.get('credit_to') and filters.get('credit_to').strip():
                where_clauses.append("jvd.credit <= ?")
                params.append(float(filters['credit_to']))
            
            if filters.get('voucher_type'):
                if filters['voucher_type'] == 'payment':
                    where_clauses.append("pv.id IS NOT NULL")
                elif filters['voucher_type'] == 'receipt':
                    where_clauses.append("rv.id IS NOT NULL")
                elif filters['voucher_type'] == 'journal':
                    where_clauses.append("pv.id IS NULL AND rv.id IS NULL")
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        # إضافة الترتيب
        query += " ORDER BY jv.voucher_date DESC, jv.id DESC"
        
        # تنفيذ الاستعلام
        cursor.execute(query, params)
        
        # استخراج النتائج
        results = []
        for row in cursor.fetchall():
            results.append(dict(row))
        
        return results
    
    finally:
        if close_conn:
            conn.close()

def get_journal_vouchers_summary(conn=None, filters=None):
    """
    استخراج ملخص لقيود اليومية (بدون تفاصيل البنود)
    
    Parameters:
    - conn: اتصال قاعدة البيانات (اختياري)
    - filters: معايير التصفية (اختياري)
    
    Returns:
    - قائمة بملخص قيود اليومية
    """
    close_conn = False
    if conn is None:
        conn = get_db()
        close_conn = True
    
    try:
        cursor = conn.cursor()
        
        # بناء استعلام SQL الأساسي
        query = """
        SELECT 
            jv.id AS voucher_id,
            jv.voucher_number AS voucher_number,
            pv.voucher_number AS payment_voucher_number,
            rv.voucher_number AS receipt_voucher_number,
            jv.voucher_date AS voucher_date,
            jv.description AS description,
            jv.total_debit AS total_debit,
            jv.total_credit AS total_credit,
            u.username AS created_by,
            CASE
                WHEN pv.id IS NOT NULL THEN 'سند صرف'
                WHEN rv.id IS NOT NULL THEN 'سند قبض'
                ELSE 'قيد يومية'
            END AS voucher_type
        FROM 
            journal_vouchers jv
        LEFT JOIN 
            users u ON jv.created_by_user_id = u.id
        LEFT JOIN 
            payment_vouchers pv ON jv.payment_voucher_id = pv.id
        LEFT JOIN 
            receipt_vouchers rv ON jv.receipt_voucher_id = rv.id
        """
        
        # إضافة شروط التصفية إذا وجدت
        where_clauses = []
        params = []
        
        if filters:
            if filters.get('start_date'):
                where_clauses.append("jv.voucher_date >= ?")
                params.append(filters['start_date'])
            
            if filters.get('end_date'):
                where_clauses.append("jv.voucher_date <= ?")
                params.append(filters['end_date'])
            
            if filters.get('voucher_number'):
                where_clauses.append("jv.voucher_number LIKE ?")
                params.append(f"%{filters['voucher_number']}%")
            
            if filters.get('voucher_type'):
                if filters['voucher_type'] == 'payment':
                    where_clauses.append("pv.id IS NOT NULL")
                elif filters['voucher_type'] == 'receipt':
                    where_clauses.append("rv.id IS NOT NULL")
                elif filters['voucher_type'] == 'journal':
                    where_clauses.append("pv.id IS NULL AND rv.id IS NULL")
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        # إضافة الترتيب
        query += " ORDER BY jv.voucher_date DESC, jv.id DESC"
        
        # تنفيذ الاستعلام
        cursor.execute(query, params)
        
        # استخراج النتائج
        results = []
        for row in cursor.fetchall():
            results.append(dict(row))
        
        return results
    
    finally:
        if close_conn:
            conn.close()

# دالة للحصول على تواريخ السنة المالية النشطة
def get_active_financial_year_dates():
    """
    الحصول على تواريخ بداية ونهاية السنة المالية النشطة
    
    Returns:
    - tuple: (start_date, end_date) أو (None, None) إذا لم تكن هناك سنة نشطة
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT start_date, end_date 
            FROM financial_years 
            WHERE is_active = 1 
            LIMIT 1
        """)
        result = cursor.fetchone()
        if result:
            return (result['start_date'], result['end_date'])
        return (None, None)
    finally:
        conn.close()

# إضافة الطرق إلى تطبيق Flask
def add_journal_report_routes(app):
    # التحقق مما إذا كان المسار موجودًا بالفعل
    if '/reports/journal_vouchers' not in [rule.rule for rule in app.url_map.iter_rules()]:
        @app.route('/reports/journal_vouchers')
        def journal_vouchers_report_view():
            # التحقق من تسجيل الدخول
            if 'user_id' not in session:
                return redirect(url_for('login'))
            
            # الحصول على تواريخ السنة المالية النشطة
            default_start_date, default_end_date = get_active_financial_year_dates()
            
            # استخراج معايير التصفية من الطلب
            filters = {}
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
                
            if request.args.get('voucher_number'):
                filters['voucher_number'] = request.args.get('voucher_number')
            if request.args.get('description'):
                filters['description'] = request.args.get('description')
            if request.args.get('account_id'):
                filters['account_id'] = request.args.get('account_id')
            if request.args.get('cost_center_id'):
                filters['cost_center_id'] = request.args.get('cost_center_id')
            if request.args.get('debit_from'):
                filters['debit_from'] = request.args.get('debit_from')
            if request.args.get('debit_to'):
                filters['debit_to'] = request.args.get('debit_to')
            if request.args.get('credit_from'):
                filters['credit_from'] = request.args.get('credit_from')
            if request.args.get('credit_to'):
                filters['credit_to'] = request.args.get('credit_to')
            if request.args.get('voucher_type'):
                filters['voucher_type'] = request.args.get('voucher_type')
            
            # استخراج البيانات
            conn = get_db()
            vouchers_data = get_journal_vouchers_report(conn, filters)
            
            # استخراج قائمة الحسابات ومراكز التكلفة للفلترة
            cursor = conn.cursor()
            cursor.execute("SELECT id, code, name FROM accounts WHERE is_active = 1 ORDER BY code")
            accounts = cursor.fetchall()
            
            cursor.execute("SELECT id, name FROM cost_centers ORDER BY name")
            cost_centers = cursor.fetchall()
            
            conn.close()
            
            # عرض القالب مع البيانات
            return render_template(
                'reports/journal_vouchers_report.html',
                vouchers_data=vouchers_data,
                accounts=accounts,
                cost_centers=cost_centers,
                filters=filters,
                default_start_date=default_start_date,
                default_end_date=default_end_date
            )

        @app.route('/reports/journal_vouchers/print')
        def print_journal_vouchers_report():
            # التحقق من تسجيل الدخول
            if 'user_id' not in session:
                return redirect(url_for('login'))
            
            # الحصول على تواريخ السنة المالية النشطة
            default_start_date, default_end_date = get_active_financial_year_dates()
            
            # استخراج معايير التصفية من الطلب
            filters = {}
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
                
            if request.args.get('voucher_number'):
                filters['voucher_number'] = request.args.get('voucher_number')
            if request.args.get('description'):
                filters['description'] = request.args.get('description')
            if request.args.get('account_id'):
                filters['account_id'] = request.args.get('account_id')
            if request.args.get('cost_center_id'):
                filters['cost_center_id'] = request.args.get('cost_center_id')
            if request.args.get('debit_from'):
                filters['debit_from'] = request.args.get('debit_from')
            if request.args.get('debit_to'):
                filters['debit_to'] = request.args.get('debit_to')
            if request.args.get('credit_from'):
                filters['credit_from'] = request.args.get('credit_from')
            if request.args.get('credit_to'):
                filters['credit_to'] = request.args.get('credit_to')
            if request.args.get('voucher_type'):
                filters['voucher_type'] = request.args.get('voucher_type')
            
            # استخراج البيانات
            conn = get_db()
            vouchers_data = get_journal_vouchers_report(conn, filters)
            conn.close()
            
            # عرض قالب الطباعة مع البيانات
            return render_template(
                'reports/print_journal_vouchers_report.html',
                vouchers_data=vouchers_data,
                filters=filters,
                print_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )

        @app.route('/reports/journal_vouchers/export')
        def export_journal_vouchers_report():
            # التحقق من تسجيل الدخول
            if 'user_id' not in session:
                return redirect(url_for('login'))
            
            # الحصول على تواريخ السنة المالية النشطة
            default_start_date, default_end_date = get_active_financial_year_dates()
            
            # استخراج معايير التصفية من الطلب
            filters = {}
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
                
            if request.args.get('voucher_number'):
                filters['voucher_number'] = request.args.get('voucher_number')
            if request.args.get('description'):
                filters['description'] = request.args.get('description')
            if request.args.get('account_id'):
                filters['account_id'] = request.args.get('account_id')
            if request.args.get('cost_center_id'):
                filters['cost_center_id'] = request.args.get('cost_center_id')
            if request.args.get('debit_from'):
                filters['debit_from'] = request.args.get('debit_from')
            if request.args.get('debit_to'):
                filters['debit_to'] = request.args.get('debit_to')
            if request.args.get('credit_from'):
                filters['credit_from'] = request.args.get('credit_from')
            if request.args.get('credit_to'):
                filters['credit_to'] = request.args.get('credit_to')
            if request.args.get('voucher_type'):
                filters['voucher_type'] = request.args.get('voucher_type')
            
            # استخراج البيانات
            conn = get_db()
            vouchers_data = get_journal_vouchers_report(conn, filters)
            conn.close()
            
            # ... باقي الكود كما هو