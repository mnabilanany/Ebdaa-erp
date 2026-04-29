# 🚀 دليل الإعداد الجديد - نظام ERP المحسّن

## ✅ متطلبات النظام
- Python 3.8+
- pip / pipenv
- SQLite3

## 📦 خطوات التثبيت

### 1. تثبيت المكتبات
```bash
pip install -r requirements.txt
```

### 2. إعداد المتغيرات البيئية
```bash
# انسخ الملف النموذجي
cp .env.example .env

# عدّل .env بـ إعداداتك
# SECRET_KEY=your-secret-key
# DEBUG=False
# إلخ
```

### 3. إنشاء قاعدة البيانات
```bash
python
>>> from app import init_db
>>> init_db()
```

### 4. تشغيل التطبيق
```bash
python app.py
```

سيكون التطبيق متاح على: `http://localhost:5000`

---

## 🔐 المستخدم الافتراضي

**اسم المستخدم**: `admin`  
**كلمة المرور**: `1234`

⚠️ **تغيير كلمة المرور فوراً بعد أول دخول!**

---

## 📝 الميزات الجديدة

### 1. 🔒 الأمان المحسّن
- ✅ bcrypt للـ password hashing
- ✅ CSRF protection على جميع الـ forms
- ✅ Session security hardening
- ✅ Input validation على جميع الـ endpoints

### 2. ⚡ الأداء
- ✅ Pagination على جميع القوائم
- ✅ Search optimized
- ✅ Database query optimization

### 3. 📊 Error Handling
- ✅ Global error handlers
- ✅ Comprehensive logging
- ✅ User-friendly error messages

### 4. 📈 Monitoring
- ✅ Activity logging
- ✅ Error tracking
- ✅ Performance metrics

---

## 🔄 نسخ احتياطية

### إنشاء نسخة احتياطية يدوية
```python
from backup_manager import BackupManager

manager = BackupManager("erp.db", "backups/")
manager.create_backup()  # إنشاء نسخة احتياطية
manager.list_backups()   # قائمة النسخ
manager.cleanup_old_backups(30)  # حذف القديم
```

### استرجاع من نسخة احتياطية
```python
manager.restore_backup("erp_backup_20260101_120000.db")
```

---

## 📋 قائمة التحقق قبل الـ Production

- [ ] تغيير `SECRET_KEY` في `.env`
- [ ] تعيين `DEBUG=False` في `.env`
- [ ] تعيين `SESSION_COOKIE_SECURE=True`
- [ ] اختبار جميع الـ forms مع CSRF
- [ ] إنشاء نسخة احتياطية من قاعدة البيانات
- [ ] إعادة تعيين كلمات مرور المستخدمين
- [ ] اختبار الـ logging في `logs/erp.log`
- [ ] تفعيل HTTPS

---

## 🐛 استكشاف الأخطاء

### مشاكل الـ bcrypt
```
ImportError: No module named 'bcrypt'
الحل: pip install bcrypt
```

### خطأ في CSRF Token
```
آخر رسالة: The CSRF token is missing or invalid
الحل: أضف {{ csrf_token() }} إلى جميع الـ forms
```

### مشاكل قاعدة البيانات
```
تحقق من: logs/erp.log
للمزيد من التفاصيل حول الخطأ
```

---

## 📞 الدعم والمساعدة

### ملفات الـ Logging
- `logs/erp.log` - جميع الأخطاء والعمليات

### الملفات المرجعية
- `IMPROVEMENTS.md` - ملخص التحسينات
- `.env.example` - متغيرات البيئة المتاحة

### الاتصال
لأي استفسارات، راجع ملفات الـ logs أو توثيق الكود.

---

تم التحديث: 29 أبريل 2026
