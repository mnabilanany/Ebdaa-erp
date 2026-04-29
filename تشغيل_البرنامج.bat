@echo off
chcp 65001 > nul
title نظام إبداع ERP
color 0A

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║       نظام إبداع للتطوير العقاري - ERP          ║
echo  ╚══════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

python --version > nul 2>&1
if errorlevel 1 (
    echo [خطأ] Python غير مثبت. نزّله من: https://python.org/downloads
    pause
    exit /b 1
)

echo [1/3] تثبيت المكتبات...
pip install flask openpyxl reportlab --quiet --no-warn-script-location

echo [2/3] تجهيز قاعدة البيانات...

echo [3/3] فتح المتصفح...
start "" /b cmd /c "timeout /t 3 > nul && start http://localhost:5000"

echo.
echo  ✓ البرنامج يعمل على: http://localhost:5000
echo  ✓ المستخدم: admin  |  كلمة المرور: 1234
echo  للإيقاف: أغلق هذه النافذة
echo.

python app.py

pause
