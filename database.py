# F:\0\29-4\V9\database.py
import sqlite3
import hashlib
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_NAME = os.path.join(BASE_DIR, 'accounting.db')

def get_db():
    """Establish a connection to the database and set row factory."""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    # تمكين دعم المفاتيح الخارجية (مهم للعلاقات)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_password(password):
    """Hashes the given password using SHA256."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# تعريف أنواع الحسابات (كمثال، يمكنك تعديلها)
ACCOUNT_TYPES = {
    1: 'أصول',
    2: 'خصوم',
    3: 'حقوق ملكية',
    4: 'إيرادات',
    5: 'مصروفات'
}
# يمكنك إضافة قاموس معكوس إذا احتجت للبحث عن الرقم من الاسم
ACCOUNT_TYPES_REVERSE = {v: k for k, v in ACCOUNT_TYPES.items()}


def init_db():
    """Initializes the database by creating necessary tables if they don't exist."""
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        # --- إنشاء جدول المستخدمين (users) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                full_name TEXT,
                password_hash TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("Checked/Created 'users' table.")

        # --- إنشاء جدول السنوات المالية (financial_years) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS financial_years (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year_name TEXT NOT NULL UNIQUE,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                is_active INTEGER DEFAULT 1,
                is_closed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("Checked/Created 'financial_years' table.")

        # --- إنشاء جدول مراكز التكلفة (cost_centers) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cost_centers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                code TEXT UNIQUE, -- جعل الكود فريداً أيضاً
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("Checked/Created 'cost_centers' table.")

        # --- محاولة إضافة أعمدة cost_centers الناقصة وتعديل القيد UNIQUE ---
        # (هذا الكود يحاول إضافة الأعمدة إذا لم تكن موجودة)
        try:
            # محاولة إضافة القيد UNIQUE مباشرة (يعمل في SQLite 3.25+)
            cursor.execute("ALTER TABLE cost_centers ADD COLUMN code TEXT UNIQUE")
            print("Attempted to add 'code' column with UNIQUE constraint to 'cost_centers'.")
        except sqlite3.OperationalError as alter_err:
            if "duplicate column name" in str(alter_err).lower(): pass # العمود موجود بالفعل
            elif "syntax error" in str(alter_err).lower(): # SQLite < 3.25 لا يدعم ADD COLUMN UNIQUE
                try:
                    # إضافة العمود بدون UNIQUE أولاً
                    cursor.execute("ALTER TABLE cost_centers ADD COLUMN code TEXT")
                    # ثم إنشاء فهرس UNIQUE منفصل
                    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_cost_centers_code ON cost_centers(code)")
                    print("Added 'code' column and UNIQUE index separately to 'cost_centers'.")
                except sqlite3.OperationalError as index_err:
                     # قد يفشل إذا كان العمود موجودًا بالفعل أو الفهرس موجودًا
                     if "duplicate column name" not in str(index_err).lower() and "index idx_cost_centers_code already exists" not in str(index_err).lower():
                         print(f"Could not add 'code' column or index to cost_centers: {index_err}")
            else: print(f"Could not add 'code' column to cost_centers: {alter_err}")

        try:
            cursor.execute("ALTER TABLE cost_centers ADD COLUMN description TEXT")
            print("Attempted to add 'description' column to 'cost_centers'.")
        except sqlite3.OperationalError as alter_err:
            if "duplicate column name" in str(alter_err).lower(): pass # العمود موجود بالفعل
            else: print(f"Could not add 'description' column to cost_centers: {alter_err}")


        # --- إنشاء جدول الحسابات (accounts) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,       -- رمز الحساب (فريد)
                name TEXT NOT NULL,              -- اسم الحساب
                account_type INTEGER NOT NULL,   -- نوع الحساب (رقم يشير إلى النوع)
                parent_id INTEGER,               -- الحساب الأب (للهيكلية الشجرية)
                is_active INTEGER DEFAULT 1,     -- هل الحساب نشط؟ (1=نعم, 0=لا)
                allows_posting INTEGER DEFAULT 1,-- هل يسمح بالترحيل المباشر؟ (1=نعم, 0=لا)
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                -- تعريف المفتاح الخارجي للعلاقة مع النفس (الأب)
                FOREIGN KEY (parent_id) REFERENCES accounts (id) ON DELETE RESTRICT -- تغيير إلى RESTRICT لمنع حذف الأب إذا كان له أبناء
            )
        ''')
        print("Checked/Created 'accounts' table.")
        # --- إضافة فهرس على parent_id لتحسين الأداء ---
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_accounts_parent_id ON accounts(parent_id)")


        # --- إنشاء جدول قيود اليومية (الرأس) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS journal_vouchers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voucher_number INTEGER NOT NULL, -- قد نحتاج لجعله فريداً ضمن السنة المالية لاحقاً
                voucher_date DATE NOT NULL,
                financial_year_id INTEGER NOT NULL,
                description TEXT,
                total_debit REAL DEFAULT 0.0, -- استخدام REAL للأرقام العشرية
                total_credit REAL DEFAULT 0.0,
                is_posted INTEGER DEFAULT 0, -- 0 = غير مرحل, 1 = مرحل
                created_by_user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (financial_year_id) REFERENCES financial_years (id) ON DELETE RESTRICT, -- منع حذف السنة إذا بها قيود
                FOREIGN KEY (created_by_user_id) REFERENCES users (id) ON DELETE SET NULL -- إذا حذف المستخدم، يبقى القيد لكن بدون رابط للمستخدم
            )
        ''')
        print("Checked/Created 'journal_vouchers' table.")
        
        # --- محاولة إضافة أعمدة journal_vouchers الناقصة ---
        try:
            cursor.execute("ALTER TABLE journal_vouchers ADD COLUMN posted_by INTEGER REFERENCES users(id) ON DELETE SET NULL")
            print("Attempted to add 'posted_by' column to 'journal_vouchers'.")
        except sqlite3.OperationalError as alter_err:
            if "duplicate column name" in str(alter_err).lower(): pass # العمود موجود بالفعل
            else: print(f"Could not add 'posted_by' column to journal_vouchers: {alter_err}")

        try:
            cursor.execute("ALTER TABLE journal_vouchers ADD COLUMN posted_at TIMESTAMP")
            print("Attempted to add 'posted_at' column to 'journal_vouchers'.")
        except sqlite3.OperationalError as alter_err:
            if "duplicate column name" in str(alter_err).lower(): pass # العمود موجود بالفعل
            else: print(f"Could not add 'posted_at' column to journal_vouchers: {alter_err}")
            
        # إضافة عمود updated_by_user_id إلى جدول journal_vouchers
        try:
            cursor.execute("ALTER TABLE journal_vouchers ADD COLUMN updated_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
            print("Attempted to add 'updated_by_user_id' column to 'journal_vouchers'.")
        except sqlite3.OperationalError as alter_err:
            if "duplicate column name" in str(alter_err).lower(): pass # العمود موجود بالفعل
            else: print(f"Could not add 'updated_by_user_id' column to journal_vouchers: {alter_err}")
            
        # إضافة عمود updated_at إلى جدول journal_vouchers
        try:
            cursor.execute("ALTER TABLE journal_vouchers ADD COLUMN updated_at TIMESTAMP")
            print("Attempted to add 'updated_at' column to 'journal_vouchers'.")
        except sqlite3.OperationalError as alter_err:
            if "duplicate column name" in str(alter_err).lower(): pass # العمود موجود بالفعل
            else: print(f"Could not add 'updated_at' column to journal_vouchers: {alter_err}")
            
            # إضافة عمود payment_voucher_id إلى جدول journal_vouchers
            try:
                cursor.execute("ALTER TABLE journal_vouchers ADD COLUMN payment_voucher_id INTEGER REFERENCES payment_vouchers(id) ON DELETE SET NULL")
                print("Attempted to add 'payment_voucher_id' column to 'journal_vouchers'.")
            except sqlite3.OperationalError as alter_err:
                if "duplicate column name" in str(alter_err).lower(): pass # العمود موجود بالفعل
                else: print(f"Could not add 'payment_voucher_id' column to journal_vouchers: {alter_err}")
            
            # إضافة فهرس للعمود الجديد لتحسين الأداء
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_vouchers_payment_voucher_id ON journal_vouchers(payment_voucher_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_vouchers_fy_id ON journal_vouchers(financial_year_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_vouchers_date ON journal_vouchers(voucher_date)")
        # قد نحتاج لفهرس مركب على السنة والرقم إذا أردنا تفرد الرقم ضمن السنة
        # cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_journal_vouchers_fy_num ON journal_vouchers(financial_year_id, voucher_number)")


        # --- إنشاء جدول تفاصيل قيود اليومية (البنود) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS journal_voucher_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voucher_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                debit REAL DEFAULT 0.0,
                credit REAL DEFAULT 0.0,
                description TEXT,
                cost_center_id INTEGER, -- يمكن أن يكون NULL
                FOREIGN KEY (voucher_id) REFERENCES journal_vouchers (id) ON DELETE CASCADE, -- إذا حذف القيد الرئيسي، تحذف تفاصيله
                FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE RESTRICT, -- منع حذف الحساب إذا استخدم في قيد
                FOREIGN KEY (cost_center_id) REFERENCES cost_centers (id) ON DELETE SET NULL -- إذا حذف مركز التكلفة، يصبح الحقل NULL
            )
        ''')
        print("Checked/Created 'journal_voucher_details' table.")
        # --- إضافة فهارس لتحسين الأداء ---
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_details_voucher_id ON journal_voucher_details(voucher_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_details_account_id ON journal_voucher_details(account_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_details_cost_center_id ON journal_voucher_details(cost_center_id)")


        # --- إضافة عمود payment_voucher_id إلى جدول journal_voucher_details إذا لم يكن موجوداً
        try:
            cursor.execute("ALTER TABLE journal_voucher_details ADD COLUMN payment_voucher_id INTEGER REFERENCES payment_vouchers(id) ON DELETE SET NULL")
            print("Attempted to add 'payment_voucher_id' column to 'journal_voucher_details'.")
        except sqlite3.OperationalError as alter_err:
            if "duplicate column name" in str(alter_err).lower(): pass # العمود موجود بالفعل
            else: print(f"Could not add 'payment_voucher_id' column to journal_voucher_details: {alter_err}")
        
        # إضافة فهارس للعمود الجديد لتحسيم الأداء
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_details_payment_voucher_id ON journal_voucher_details(payment_voucher_id)")
        

        # --- إضافة مستخدم افتراضي (admin) ---
        # (الكود الخاص بإضافة المستخدم الافتراضي يبقى كما هو)
        try:
            default_password = "password"
            hashed_default_password = hash_password(default_password)
            cursor.execute("SELECT id FROM users WHERE username = ?", ('admin',))
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO users (username, full_name, password_hash) VALUES (?, ?, ?)",
                    ('admin', 'Admin User', hashed_default_password)
                )
                print("Default user 'admin' created with password 'password'. PLEASE CHANGE IT!")
            else:
                print("Default user 'admin' already exists.")
        except sqlite3.Error as e:
            print(f"Could not add default admin user (might already exist or other error): {e}")


        # استدعاء دالة إنشاء جدول سندات الصرف
        def create_payment_vouchers_table(conn):
            cursor = conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS payment_vouchers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voucher_number INTEGER NOT NULL,
                voucher_date TEXT NOT NULL,
                beneficiary TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT,
                payment_method TEXT NOT NULL,
                check_number TEXT,
                financial_year_id INTEGER,
                is_posted INTEGER DEFAULT 0,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                posted_by INTEGER,
                posted_at TIMESTAMP,
                FOREIGN KEY (financial_year_id) REFERENCES financial_years(id),
                FOREIGN KEY (created_by) REFERENCES users(id),
                FOREIGN KEY (posted_by) REFERENCES users(id)
            )
            ''')
            # إضافة فهارس لتحسين الأداء
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_payment_vouchers_fy_id ON payment_vouchers(financial_year_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_payment_vouchers_date ON payment_vouchers(voucher_date)")
            print("Checked/Created 'payment_vouchers' table.")
            conn.commit()
        
        # إضافة دالة إنشاء جدول سندات القبض
        def create_receipt_vouchers_table(conn):
            cursor = conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS receipt_vouchers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voucher_number INTEGER NOT NULL,
                voucher_date TEXT NOT NULL,
                payer TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT,
                payment_method TEXT NOT NULL,
                check_number TEXT,
                financial_year_id INTEGER,
                is_posted INTEGER DEFAULT 0,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                posted_by INTEGER,
                posted_at TIMESTAMP,
                FOREIGN KEY (financial_year_id) REFERENCES financial_years(id),
                FOREIGN KEY (created_by) REFERENCES users(id),
                FOREIGN KEY (posted_by) REFERENCES users(id)
            )
            ''')
            # إضافة فهارس لتحسين الأداء
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_receipt_vouchers_fy_id ON receipt_vouchers(financial_year_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_receipt_vouchers_date ON receipt_vouchers(voucher_date)")
            print("Checked/Created 'receipt_vouchers' table.")
            conn.commit()
            
        # إضافة عمود receipt_voucher_id إلى جدول journal_vouchers
        try:
            cursor.execute("ALTER TABLE journal_vouchers ADD COLUMN receipt_voucher_id INTEGER REFERENCES receipt_vouchers(id) ON DELETE SET NULL")
            print("Attempted to add 'receipt_voucher_id' column to 'journal_vouchers'.")
        except sqlite3.OperationalError as alter_err:
            if "duplicate column name" in str(alter_err).lower(): pass # العمود موجود بالفعل
            else: print(f"Could not add 'receipt_voucher_id' column to journal_vouchers: {alter_err}")
        
        # إضافة فهرس للعمود الجديد لتحسين الأداء
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_vouchers_receipt_voucher_id ON journal_vouchers(receipt_voucher_id)")
        
        # إضافة عمود receipt_voucher_id إلى جدول journal_voucher_details
        try:
            cursor.execute("ALTER TABLE journal_voucher_details ADD COLUMN receipt_voucher_id INTEGER REFERENCES receipt_vouchers(id) ON DELETE SET NULL")
            print("Attempted to add 'receipt_voucher_id' column to 'journal_voucher_details'.")
        except sqlite3.OperationalError as alter_err:
            if "duplicate column name" in str(alter_err).lower(): pass # العمود موجود بالفعل
            else: print(f"Could not add 'receipt_voucher_id' column to journal_voucher_details: {alter_err}")
        
        # إضافة فهرس للعمود الجديد لتحسين الأداء
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_details_receipt_voucher_id ON journal_voucher_details(receipt_voucher_id)")

        conn.commit() # حفظ التغييرات (بما في ذلك ALTER TABLE و CREATE TABLE)
        print("Database initialization complete.")

    except sqlite3.Error as e:
        print(f"An error occurred during database initialization: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    print("Initializing database...")
    init_db()


def create_payment_voucher_with_journal(conn, voucher_data, journal_details):
    """
    إنشاء سند صرف جديد مع قيد يومية مرتبط به
    
    Parameters:
    - conn: اتصال قاعدة البيانات
    - voucher_data: بيانات سند الصرف (dict)
    - journal_details: تفاصيل قيد اليومية (list of dicts)
    
    Returns:
    - id: معرف سند الصرف الجديد
    """
    cursor = conn.cursor()
    try:
        # بدء المعاملة
        conn.execute("BEGIN TRANSACTION")
        
        # إدراج سند الصرف
        cursor.execute('''
            INSERT INTO payment_vouchers (
                voucher_number, voucher_date, beneficiary, amount, 
                description, payment_method, check_number, 
                financial_year_id, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            voucher_data['voucher_number'], 
            voucher_data['voucher_date'], 
            voucher_data['beneficiary'], 
            voucher_data['amount'], 
            voucher_data['description'], 
            voucher_data['payment_method'], 
            voucher_data.get('check_number'), 
            voucher_data['financial_year_id'], 
            voucher_data['created_by']
        ))
        
        # الحصول على معرف سند الصرف الجديد
        payment_voucher_id = cursor.lastrowid
        
        # إنشاء قيد اليومية المرتبط
        cursor.execute('''
            INSERT INTO journal_vouchers (
                voucher_number, voucher_date, financial_year_id, 
                description, total_debit, total_credit, 
                created_by_user_id, payment_voucher_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"PV-{voucher_data['voucher_number']}", 
            voucher_data['voucher_date'], 
            voucher_data['financial_year_id'], 
            f"قيد سند الصرف رقم {voucher_data['voucher_number']} - {voucher_data['beneficiary']}", 
            voucher_data['amount'], 
            voucher_data['amount'], 
            voucher_data['created_by'],
            payment_voucher_id  # إضافة معرف سند الصرف
        ))
        
        # الحصول على معرف قيد اليومية الجديد
        journal_voucher_id = cursor.lastrowid
        
        # إدراج تفاصيل قيد اليومية مع ربطها بسند الصرف
        for detail in journal_details:
            cursor.execute('''
                INSERT INTO journal_voucher_details (
                    voucher_id, account_id, debit, credit, 
                    description, cost_center_id, payment_voucher_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                journal_voucher_id, 
                detail['account_id'], 
                detail.get('debit', 0), 
                detail.get('credit', 0), 
                detail.get('description', ''), 
                detail.get('cost_center_id'), 
                payment_voucher_id  # ربط التفاصيل بسند الصرف
            ))
        
        # تأكيد المعاملة
        conn.commit()
        return payment_voucher_id
        
    except Exception as e:
        # التراجع عن المعاملة في حالة حدوث خطأ
        conn.rollback()
        raise e


def create_receipt_voucher_with_journal(conn, voucher_data, journal_details):
    """
    إنشاء سند قبض جديد مع قيد يومية مرتبط به
    
    Parameters:
    - conn: اتصال قاعدة البيانات
    - voucher_data: بيانات سند القبض (dict)
    - journal_details: تفاصيل قيد اليومية (list of dicts)
    
    Returns:
    - id: معرف سند القبض الجديد
    """
    cursor = conn.cursor()
    try:
        # بدء المعاملة
        conn.execute("BEGIN TRANSACTION")
        
        # إدراج سند القبض
        cursor.execute('''
            INSERT INTO receipt_vouchers (
                voucher_number, voucher_date, payer, amount, 
                description, payment_method, check_number, 
                financial_year_id, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            voucher_data['voucher_number'], 
            voucher_data['voucher_date'], 
            voucher_data['payer'], 
            voucher_data['amount'], 
            voucher_data['description'], 
            voucher_data['payment_method'], 
            voucher_data.get('check_number'), 
            voucher_data['financial_year_id'], 
            voucher_data['created_by']
        ))
        
        # الحصول على معرف سند القبض الجديد
        receipt_voucher_id = cursor.lastrowid
        
        # إنشاء قيد اليومية المرتبط
        cursor.execute('''
            INSERT INTO journal_vouchers (
                voucher_number, voucher_date, financial_year_id, 
                description, total_debit, total_credit, 
                created_by_user_id, receipt_voucher_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"RV-{voucher_data['voucher_number']}", 
            voucher_data['voucher_date'], 
            voucher_data['financial_year_id'], 
            f"قيد سند القبض رقم {voucher_data['voucher_number']} - {voucher_data['payer']}", 
            voucher_data['amount'], 
            voucher_data['amount'], 
            voucher_data['created_by'],
            receipt_voucher_id  # إضافة معرف سند القبض
        ))
        
        # الحصول على معرف قيد اليومية الجديد
        journal_voucher_id = cursor.lastrowid
        
        # إدراج تفاصيل قيد اليومية مع ربطها بسند القبض
        for detail in journal_details:
            cursor.execute('''
                INSERT INTO journal_voucher_details (
                    voucher_id, account_id, debit, credit, 
                    description, cost_center_id, receipt_voucher_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                journal_voucher_id, 
                detail['account_id'], 
                detail.get('debit', 0), 
                detail.get('credit', 0), 
                detail.get('description', ''), 
                detail.get('cost_center_id'), 
                receipt_voucher_id  # ربط التفاصيل بسند القبض
            ))
        
        # تأكيد المعاملة
        conn.commit()
        return receipt_voucher_id
        
    except Exception as e:
        # التراجع عن المعاملة في حالة حدوث خطأ
        conn.rollback()
        raise e
