from flask import Blueprint, render_template, request, redirect, url_for, session, send_file
from database import get_db, ACCOUNT_TYPES, ACCOUNT_TYPES_REVERSE
import pandas as pd
import io
from datetime import datetime
from profit_loss_report import get_profit_loss_data, get_active_financial_year_dates

# إنشاء Blueprint لتقرير الميزانية العمومية
balance_sheet_bp = Blueprint('balance_sheet', __name__)

def get_balance_sheet_data(conn, filters):
    """
    استخراج بيانات تقرير الميزانية العمومية
    
    Parameters:
    - conn: اتصال قاعدة البيانات
    - filters: معايير التصفية (start_date, end_date)
    
    Returns:
    - قاموس يحتوي على بيانات الأصول والخصوم وحقوق الملكية والأرباح/الخسائر
    """
    cursor = conn.cursor()
    
    # استخراج الأصول (نوع الحساب = 1)
    assets_type = ACCOUNT_TYPES_REVERSE['أصول']
    
    # استعلام الأصول
    assets_query = """
    SELECT 
        a.id, a.code, a.name,
        SUM(CASE WHEN jvd.debit > 0 THEN jvd.debit ELSE 0 END) as total_debit,
        SUM(CASE WHEN jvd.credit > 0 THEN jvd.credit ELSE 0 END) as total_credit
    FROM 
        accounts a
    LEFT JOIN 
        journal_voucher_details jvd ON a.id = jvd.account_id
    LEFT JOIN 
        journal_vouchers jv ON jvd.voucher_id = jv.id
    WHERE 
        a.account_type = ? AND a.is_active = 1
    """
    
    params = [assets_type]
    
    # إضافة شروط التصفية إذا وجدت
    if filters.get('end_date'):
        assets_query += " AND jv.voucher_date <= ?"
        params.append(filters['end_date'])
    
    assets_query += " GROUP BY a.id, a.code, a.name ORDER BY a.code"
    
    cursor.execute(assets_query, params)
    assets_rows = cursor.fetchall()
    
    # تحويل البيانات إلى قائمة من القواميس مع حساب الرصيد
    assets = []
    total_assets_debit = 0
    total_assets_credit = 0
    
    for row in assets_rows:
        debit = row['total_debit'] if row['total_debit'] is not None else 0
        credit = row['total_credit'] if row['total_credit'] is not None else 0
        balance = debit - credit
        
        # الأصول عادة تكون مدينة، لذا نضع القيمة الموجبة في عمود المدين والسالبة في عمود الدائن
        debit_balance = balance if balance > 0 else 0
        credit_balance = abs(balance) if balance < 0 else 0
        
        assets.append({
            'id': row['id'],
            'code': row['code'],
            'name': row['name'],
            'debit': debit_balance,
            'credit': credit_balance
        })
        
        total_assets_debit += debit_balance
        total_assets_credit += credit_balance
    
    # استخراج الخصوم (نوع الحساب = 2)
    liabilities_type = ACCOUNT_TYPES_REVERSE['خصوم']
    
    # استعلام الخصوم
    liabilities_query = """
    SELECT 
        a.id, a.code, a.name,
        SUM(CASE WHEN jvd.debit > 0 THEN jvd.debit ELSE 0 END) as total_debit,
        SUM(CASE WHEN jvd.credit > 0 THEN jvd.credit ELSE 0 END) as total_credit
    FROM 
        accounts a
    LEFT JOIN 
        journal_voucher_details jvd ON a.id = jvd.account_id
    LEFT JOIN 
        journal_vouchers jv ON jvd.voucher_id = jv.id
    WHERE 
        a.account_type = ? AND a.is_active = 1
    """
    
    params = [liabilities_type]
    
    # إضافة شروط التصفية إذا وجدت
    if filters.get('end_date'):
        liabilities_query += " AND jv.voucher_date <= ?"
        params.append(filters['end_date'])
    
    liabilities_query += " GROUP BY a.id, a.code, a.name ORDER BY a.code"
    
    cursor.execute(liabilities_query, params)
    liabilities_rows = cursor.fetchall()
    
    # تحويل البيانات إلى قائمة من القواميس مع حساب الرصيد
    liabilities = []
    total_liabilities_debit = 0
    total_liabilities_credit = 0
    
    for row in liabilities_rows:
        debit = row['total_debit'] if row['total_debit'] is not None else 0
        credit = row['total_credit'] if row['total_credit'] is not None else 0
        balance = credit - debit  # الخصوم عادة دائنة، لذا نعكس الحساب
        
        # الخصوم عادة تكون دائنة، لذا نضع القيمة الموجبة في عمود الدائن والسالبة في عمود المدين
        debit_balance = abs(balance) if balance < 0 else 0
        credit_balance = balance if balance > 0 else 0
        
        liabilities.append({
            'id': row['id'],
            'code': row['code'],
            'name': row['name'],
            'debit': debit_balance,
            'credit': credit_balance
        })
        
        total_liabilities_debit += debit_balance
        total_liabilities_credit += credit_balance
    
    # استخراج حقوق الملكية (نوع الحساب = 3)
    equity_type = ACCOUNT_TYPES_REVERSE['حقوق ملكية']
    
    # استعلام حقوق الملكية
    equity_query = """
    SELECT 
        a.id, a.code, a.name,
        SUM(CASE WHEN jvd.debit > 0 THEN jvd.debit ELSE 0 END) as total_debit,
        SUM(CASE WHEN jvd.credit > 0 THEN jvd.credit ELSE 0 END) as total_credit
    FROM 
        accounts a
    LEFT JOIN 
        journal_voucher_details jvd ON a.id = jvd.account_id
    LEFT JOIN 
        journal_vouchers jv ON jvd.voucher_id = jv.id
    WHERE 
        a.account_type = ? AND a.is_active = 1
    """
    
    params = [equity_type]
    
    # إضافة شروط التصفية إذا وجدت
    if filters.get('end_date'):
        equity_query += " AND jv.voucher_date <= ?"
        params.append(filters['end_date'])
    
    equity_query += " GROUP BY a.id, a.code, a.name ORDER BY a.code"
    
    cursor.execute(equity_query, params)
    equity_rows = cursor.fetchall()
    
    # تحويل البيانات إلى قائمة من القواميس مع حساب الرصيد
    equity = []
    total_equity_debit = 0
    total_equity_credit = 0
    
    for row in equity_rows:
        debit = row['total_debit'] if row['total_debit'] is not None else 0
        credit = row['total_credit'] if row['total_credit'] is not None else 0
        balance = credit - debit  # حقوق الملكية عادة دائنة، لذا نعكس الحساب
        
        # حقوق الملكية عادة تكون دائنة، لذا نضع القيمة الموجبة في عمود الدائن والسالبة في عمود المدين
        debit_balance = abs(balance) if balance < 0 else 0
        credit_balance = balance if balance > 0 else 0
        
        equity.append({
            'id': row['id'],
            'code': row['code'],
            'name': row['name'],
            'debit': debit_balance,
            'credit': credit_balance
        })
        
        total_equity_debit += debit_balance
        total_equity_credit += credit_balance
    
    # الحصول على صافي الربح أو الخسارة من تقرير الأرباح والخسائر
    profit_loss_data = get_profit_loss_data(conn, filters)
    net_profit = profit_loss_data['net_profit']
    is_profit = profit_loss_data['is_profit']
    
    # إضافة صافي الربح أو الخسارة إلى حقوق الملكية
    if is_profit:
        # الربح يزيد حقوق الملكية (دائن)
        profit_loss_item = {
            'id': None,
            'code': '',
            'name': 'صافي الربح للفترة',
            'debit': 0,
            'credit': net_profit
        }
        total_equity_credit += net_profit
    else:
        # الخسارة تنقص حقوق الملكية (مدين)
        profit_loss_item = {
            'id': None,
            'code': '',
            'name': 'صافي الخسارة للفترة',
            'debit': abs(net_profit),
            'credit': 0
        }
        total_equity_debit += abs(net_profit)
    
    equity.append(profit_loss_item)
    
    # حساب إجمالي الأصول والخصوم وحقوق الملكية
    total_assets = total_assets_debit - total_assets_credit
    total_liabilities = total_liabilities_credit - total_liabilities_debit
    total_equity = total_equity_credit - total_equity_debit
    total_liabilities_equity = total_liabilities + total_equity
    
    return {
        'assets': assets,
        'liabilities': liabilities,
        'equity': equity,
        'profit_loss_item': profit_loss_item,
        'total_assets_debit': total_assets_debit,
        'total_assets_credit': total_assets_credit,
        'total_liabilities_debit': total_liabilities_debit,
        'total_liabilities_credit': total_liabilities_credit,
        'total_equity_debit': total_equity_debit,
        'total_equity_credit': total_equity_credit,
        'total_assets': total_assets,
        'total_liabilities': total_liabilities,
        'total_equity': total_equity,
        'total_liabilities_equity': total_liabilities_equity,
        'is_balanced': abs(total_assets - total_liabilities_equity) < 0.01  # التحقق من توازن الميزانية مع هامش خطأ صغير
    }

@balance_sheet_bp.route('/reports/balance_sheet')
def balance_sheet_report_view():
    """عرض صفحة تقرير الميزانية العمومية مع إمكانية التصفية"""
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
    
    # جلب بيانات التقرير
    conn = get_db()
    report_data = get_balance_sheet_data(conn, filters)
    conn.close()
    
    return render_template(
        'reports/balance_sheet_report.html',
        report_data=report_data,
        filters=filters,
        default_start_date=default_start_date,
        default_end_date=default_end_date
    )

@balance_sheet_bp.route('/reports/balance_sheet/print')
def print_balance_sheet_report():
    """عرض نسخة للطباعة من تقرير الميزانية العمومية"""
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
    
    # جلب بيانات التقرير
    conn = get_db()
    report_data = get_balance_sheet_data(conn, filters)
    conn.close()
    
    # تاريخ الطباعة
    print_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    return render_template(
        'reports/print_balance_sheet_report.html',
        report_data=report_data,
        filters=filters,
        print_date=print_date
    )

@balance_sheet_bp.route('/reports/balance_sheet/export')
def export_balance_sheet_report():
    """تصدير تقرير الميزانية العمومية إلى Excel"""
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
    
    # جلب بيانات التقرير
    conn = get_db()
    report_data = get_balance_sheet_data(conn, filters)
    conn.close()
    
    # إنشاء DataFrame للأصول
    assets_data = []
    for asset in report_data['assets']:
        assets_data.append({
            'كود الحساب': asset['code'],
            'اسم الحساب': asset['name'],
            'مدين': asset['debit'],
            'دائن': asset['credit']
        })
    
    # إضافة إجمالي الأصول
    assets_data.append({
        'كود الحساب': '',
        'اسم الحساب': 'إجمالي الأصول',
        'مدين': report_data['total_assets_debit'],
        'دائن': report_data['total_assets_credit']
    })
    
    # إضافة صافي الأصول
    assets_data.append({
        'كود الحساب': '',
        'اسم الحساب': 'صافي الأصول',
        'مدين': report_data['total_assets'],
        'دائن': 0
    })
    
    # إنشاء DataFrame للخصوم
    liabilities_data = []
    for liability in report_data['liabilities']:
        liabilities_data.append({
            'كود الحساب': liability['code'],
            'اسم الحساب': liability['name'],
            'مدين': liability['debit'],
            'دائن': liability['credit']
        })
    
    # إضافة إجمالي الخصوم
    liabilities_data.append({
        'كود الحساب': '',
        'اسم الحساب': 'إجمالي الخصوم',
        'مدين': report_data['total_liabilities_debit'],
        'دائن': report_data['total_liabilities_credit']
    })
    
    # إضافة صافي الخصوم
    liabilities_data.append({
        'كود الحساب': '',
        'اسم الحساب': 'صافي الخصوم',
        'مدين': 0,
        'دائن': report_data['total_liabilities']
    })
    
    # إنشاء DataFrame لحقوق الملكية
    equity_data = []
    for equity in report_data['equity']:
        equity_data.append({
            'كود الحساب': equity['code'],
            'اسم الحساب': equity['name'],
            'مدين': equity['debit'],
            'دائن': equity['credit']
        })
    
    # إضافة إجمالي حقوق الملكية
    equity_data.append({
        'كود الحساب': '',
        'اسم الحساب': 'إجمالي حقوق الملكية',
        'مدين': report_data['total_equity_debit'],
        'دائن': report_data['total_equity_credit']
    })
    
    # إضافة صافي حقوق الملكية
    equity_data.append({
        'كود الحساب': '',
        'اسم الحساب': 'صافي حقوق الملكية',
        'مدين': 0,
        'دائن': report_data['total_equity']
    })
    
    # إنشاء ملف Excel في الذاكرة
    output = io.BytesIO()
    
    # استخدام openpyxl مع تنسيق الخلايا
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # إنشاء DataFrame للأصول وتصديرها
        df_assets = pd.DataFrame(assets_data)
        df_assets.to_excel(writer, sheet_name='الميزانية العمومية', startrow=1, index=False)
        
        # إنشاء DataFrame للخصوم وتصديرها
        df_liabilities = pd.DataFrame(liabilities_data)
        df_liabilities.to_excel(writer, sheet_name='الميزانية العمومية', startrow=len(assets_data) + 4, index=False)
        
        # إنشاء DataFrame لحقوق الملكية وتصديرها
        df_equity = pd.DataFrame(equity_data)
        df_equity.to_excel(writer, sheet_name='الميزانية العمومية', startrow=len(assets_data) + len(liabilities_data) + 7, index=False)
        
        # الحصول على ورقة العمل لتطبيق التنسيق
        workbook = writer.book
        worksheet = writer.sheets['الميزانية العمومية']
        
        # إضافة عناوين الأقسام
        worksheet.cell(row=1, column=1, value='الأصول')
        worksheet.cell(row=len(assets_data) + 4, column=1, value='الخصوم')
        worksheet.cell(row=len(assets_data) + len(liabilities_data) + 7, column=1, value='حقوق الملكية')
        
        # إضافة معلومات التقرير
        worksheet.cell(row=len(assets_data) + len(liabilities_data) + len(equity_data) + 10, column=1, value='إجمالي الخصوم وحقوق الملكية')
        worksheet.cell(row=len(assets_data) + len(liabilities_data) + len(equity_data) + 10, column=4, value=report_data['total_liabilities_equity'])
        
        # تعيين عرض الأعمدة
        worksheet.column_dimensions['A'].width = 15
        worksheet.column_dimensions['B'].width = 40
        worksheet.column_dimensions['C'].width = 15
        worksheet.column_dimensions['D'].width = 15
    
    # إعادة مؤشر الملف إلى البداية
    output.seek(0)
    
    # إنشاء اسم الملف مع التاريخ والوقت
    now = datetime.now()
    file_name = f"تقرير_الميزانية_العمومية_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    # إرسال الملف للتنزيل
    return send_file(
        output,
        as_attachment=True,
        download_name=file_name,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# إضافة فلتر format_currency
@balance_sheet_bp.app_template_filter('format_currency')
def format_currency_filter(value):
    if value is None:
        return "0.00"
    return "{:,.2f}".format(float(value))
