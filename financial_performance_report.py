from flask import Blueprint, render_template, session, redirect, url_for
from database import get_db
from datetime import datetime

financial_performance_bp = Blueprint('financial_performance', __name__)

@financial_performance_bp.route('/reports/financial_performance')
def financial_performance_report_view():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()
    
    # جلب معلومات المستخدم
    cursor.execute("""
        SELECT id, username, full_name 
        FROM users 
        WHERE id = ?
    """, (session['user_id'],))
    user = cursor.fetchone()
    
    # مثال: استخراج الإيرادات والمصروفات شهريًا للسنة الحالية
    cursor.execute("""
        SELECT 
            strftime('%Y-%m', jv.voucher_date) as month,
            SUM(CASE WHEN a.account_type=4 THEN jvd.credit-jvd.debit ELSE 0 END) as revenues,
            SUM(CASE WHEN a.account_type=5 THEN jvd.debit-jvd.credit ELSE 0 END) as expenses
        FROM journal_voucher_details jvd
        JOIN journal_vouchers jv ON jvd.voucher_id = jv.id
        JOIN accounts a ON jvd.account_id = a.id
        WHERE jv.voucher_date >= date('now','start of year')
        GROUP BY month
        ORDER BY month
    """)
    data = cursor.fetchall()
    
    # استعلام لجلب أعلى 5 حسابات مصروفات
    cursor.execute("""
        SELECT 
            a.name as account_name,
            SUM(jvd.debit-jvd.credit) as amount
        FROM journal_voucher_details jvd
        JOIN journal_vouchers jv ON jvd.voucher_id = jv.id
        JOIN accounts a ON jvd.account_id = a.id
        WHERE jv.voucher_date >= date('now','start of year')
        AND a.account_type = 5  -- نوع الحساب مصروفات
        GROUP BY a.id, a.name
        ORDER BY amount DESC
        LIMIT 5
    """)
    top_expenses = cursor.fetchall()
    
    # استعلام لجلب أعلى 5 حسابات عملاء
    cursor.execute("""
        SELECT 
            a.name as account_name,
            SUM(jvd.debit-jvd.credit) as amount
        FROM journal_voucher_details jvd
        JOIN journal_vouchers jv ON jvd.voucher_id = jv.id
        JOIN accounts a ON jvd.account_id = a.id
        WHERE jv.voucher_date <= date('now')
        AND a.code LIKE '1203%'  -- حسابات العملاء تبدأ بـ 1203 (تم تعديل a.id إلى a.code)
        GROUP BY a.id, a.name
        HAVING SUM(jvd.debit-jvd.credit) <> 0
        ORDER BY amount DESC
        LIMIT 5
    """)
    top_customers = cursor.fetchall()
    
    # استعلام لجلب أعلى 5 حسابات موردين
    cursor.execute("""
        SELECT 
            a.name as account_name,
            SUM(jvd.credit-jvd.debit) as amount
        FROM journal_voucher_details jvd
        JOIN journal_vouchers jv ON jvd.voucher_id = jv.id
        JOIN accounts a ON jvd.account_id = a.id
        WHERE jv.voucher_date <= date('now')
        AND a.code LIKE '2101%'  -- حسابات الموردين تبدأ بـ 2101
        GROUP BY a.id, a.name
        HAVING SUM(jvd.credit-jvd.debit) <> 0
        ORDER BY amount DESC
        LIMIT 5
    """)
    top_suppliers = cursor.fetchall()
    
    # استعلام لجلب بيانات الميزانية (الأصول، الخصوم، حقوق الملكية)
    cursor.execute("""
        SELECT 
            CASE 
                WHEN a.account_type = 1 THEN 'الأصول'
                WHEN a.account_type = 2 THEN 'الخصوم'
                WHEN a.account_type = 3 THEN 'حقوق الملكية'
                ELSE 'أخرى'
            END as account_category,
            SUM(CASE 
                WHEN a.account_type = 1 THEN jvd.debit - jvd.credit
                WHEN a.account_type IN (2, 3) THEN jvd.credit - jvd.debit
                ELSE 0
            END) as amount
        FROM journal_voucher_details jvd
        JOIN journal_vouchers jv ON jvd.voucher_id = jv.id
        JOIN accounts a ON jvd.account_id = a.id
        WHERE jv.voucher_date <= date('now')
        AND a.account_type IN (1, 2, 3)
        GROUP BY account_category
        ORDER BY a.account_type
    """)
    balance_sheet_data = cursor.fetchall()
    
    # استعلام لجلب حسابات البنوك والصندوق
    cursor.execute("""
        SELECT 
            a.code as account_code,
            a.name as account_name,
            SUM(jvd.debit - jvd.credit) as balance
        FROM journal_voucher_details jvd
        JOIN journal_vouchers jv ON jvd.voucher_id = jv.id
        JOIN accounts a ON jvd.account_id = a.id
        WHERE jv.voucher_date <= date('now')
        AND (a.code LIKE '1201%' OR a.code LIKE '1202%')
        GROUP BY a.id, a.code, a.name
        HAVING balance <> 0
        ORDER BY a.code
    """)
    cash_bank_accounts = cursor.fetchall()
    # حساب الإجمالي
    total_cash_bank_balance = sum(acc['balance'] or 0 for acc in cash_bank_accounts)
    
    conn.close()
    # تجهيز البيانات للواجهة
    months = [row['month'] for row in data]
    revenues = [row['revenues'] for row in data]
    expenses = [row['expenses'] for row in data]
    net_profit = [rev - exp for rev, exp in zip(revenues, expenses)]
    
    # تجهيز بيانات الميزانية
    balance_categories = [row['account_category'] for row in balance_sheet_data]
    balance_amounts = [row['amount'] for row in balance_sheet_data]
    
    return render_template('reports/financial_performance_report.html',
                           months=months, revenues=revenues, expenses=expenses, 
                           net_profit=net_profit, top_expenses=top_expenses,
                           balance_categories=balance_categories, 
                           balance_amounts=balance_amounts,
                           top_customers=top_customers,
                           top_suppliers=top_suppliers,
                           cash_bank_accounts=cash_bank_accounts,
                           total_cash_bank_balance=total_cash_bank_balance,
                           user=user)  # إضافة معلومات المستخدم إلى القالب