# 🔐 تطبيق CSRF Tokens في الـ Forms

## ما هو CSRF؟
Cross-Site Request Forgery - هجوم يقوم بتنفيذ عمليات غير مصرح بها نيابة عن المستخدم.

## الحل في app.py
تم إضافة `CSRFProtect` من `flask_wtf`:
```python
from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect(app)
```

## التطبيق في الـ Templates

### إضافة CSRF Token إلى جميع الـ Forms

#### مثال 1: Form عادي
```html
<form method="POST" action="{{ url_for('add_client') }}">
    {{ csrf_token() }}
    
    <input type="text" name="full_name" required>
    <input type="text" name="phone">
    <button type="submit">إضافة</button>
</form>
```

#### مثال 2: Form مع Hidden Input
```html
<form method="POST">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    
    <input type="text" name="full_name">
    <button>حفظ</button>
</form>
```

#### مثال 3: AJAX Request
```javascript
// الحصول على CSRF token من meta tag
const csrf_token = document.querySelector('meta[name="csrf-token"]').content;

// في form الـ HTML
<meta name="csrf-token" content="{{ csrf_token() }}">

// في JavaScript
fetch('/api/endpoint', {
    method: 'POST',
    headers: {
        'X-CSRFToken': csrf_token,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({...})
});
```

---

## الـ Forms التي تحتاج تحديث

### في properties.html
```html
<!-- إضافة عند بداية كل form -->
{{ csrf_token() }}
```

تطبق في:
- ✅ add property form
- ✅ filter/search form

### في clients.html
- ✅ add client form
- ✅ search form

### في contracts.html
- ✅ add contract form
- ✅ search form

### في installments.html
- ✅ add installment form
- ✅ generate installments form
- ✅ payment form

### في journal.html
- ✅ add journal entry form

### في users.html
- ✅ add/edit user form

### في settings.html
- ✅ جميع forms

---

## اختبار CSRF

### كود الاختبار
```python
# في app.py أو test file
@app.route('/test', methods=['POST'])
def test_csrf():
    # إذا وصلت لهنا، فـ CSRF محمي
    return "CSRF Protection Working!"
```

### اختبار في المتصفح
1. فتح صفحة containing form
2. Inspect Element وابحث عن `<input name="csrf_token">`
3. تأكد من وجود token

### اختبار الـ Errors
- إذا نسيت CSRF token → الخطأ: "CSRF token missing"
- إذا كان token خاطئ → الخطأ: "CSRF token invalid"

---

## رسالة خطأ CSRF

عند نسيان CSRF token، ستظهر رسالة:
```
400: The CSRF token is missing or invalid.
```

**الحل**: أضف `{{ csrf_token() }}` إلى الـ form

---

## مثال عملي - إضافة عميل

### الكود الحالي (بدون CSRF):
```html
<form method="POST" action="{{ url_for('add_client') }}">
    <input type="text" name="full_name" required>
    <input type="text" name="phone">
    <button>حفظ</button>
</form>
```

### الكود المحدث (مع CSRF):
```html
<form method="POST" action="{{ url_for('add_client') }}">
    {{ csrf_token() }}  {# ← أضف هذا السطر #}
    
    <input type="text" name="full_name" required>
    <input type="text" name="phone">
    <button>حفظ</button>
</form>
```

---

## طريقة بديلة: Meta Tag

### في base.html:
```html
<head>
    ...
    <meta name="csrf-token" content="{{ csrf_token() }}">
</head>
```

### في JavaScript:
```javascript
document.querySelectorAll('form').forEach(form => {
    // يمكن الوصول للـ token من meta tag
    const token = document.querySelector('meta[name="csrf-token"]').content;
});
```

---

## الخلاصة

| الخطوة | الوصف |
|-------|-------|
| 1 | استيراد CSRFProtect في app.py ✅ (تم) |
| 2 | تفعيل CSRF في app ✅ (تم) |
| 3 | إضافة `{{ csrf_token() }}` لكل form | ← **تحتاج التطبيق** |
| 4 | اختبار جميع forms | ← **تحتاج التطبيق** |

---

## الأسئلة الشائعة

**Q: هل يؤثر CSRF على Performance؟**
A: لا، الـ overhead ضئيل جداً

**Q: هل أحتاج تغيير الـ JavaScript؟**
A: فقط إذا كنت تستخدم AJAX

**Q: ماذا لو نسيت CSRF token؟**
A: الـ request سيفشل مع رسالة خطأ واضحة

---

**آخر تحديث**: 29 أبريل 2026
