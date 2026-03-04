@echo off
echo COMPLETE DATABASE FIX
echo =====================
echo.

REM Kill any Python processes (optional - be careful)
REM taskkill /F /IM python.exe 2>nul

REM Delete database
if exist db.sqlite3 (
    del /F db.sqlite3
    echo ✅ Deleted database
) else (
    echo ℹ️ No database found
)

REM Delete all migration folders
echo.
echo Deleting migration folders...

if exist apps\users\migrations (
    rmdir /s /q apps\users\migrations
    echo ✅ Deleted users migrations
) else (
    echo ℹ️ No users migrations folder
)

if exist apps\consultations\migrations (
    rmdir /s /q apps\consultations\migrations
    echo ✅ Deleted consultations migrations
) else (
    echo ℹ️ No consultations migrations folder
)

if exist apps\agents\migrations (
    rmdir /s /q apps\agents\migrations
    echo ✅ Deleted agents migrations
) else (
    echo ℹ️ No agents migrations folder
)

if exist apps\blackboard\migrations (
    rmdir /s /q apps\blackboard\migrations
    echo ✅ Deleted blackboard migrations
) else (
    echo ℹ️ No blackboard migrations folder
)

if exist apps\rag\migrations (
    rmdir /s /q apps\rag\migrations
    echo ✅ Deleted rag migrations
) else (
    echo ℹ️ No rag migrations folder
)

REM Create necessary directories
echo.
echo Creating directories...
mkdir static 2>nul
mkdir media 2>nul
mkdir media\symptoms\audio 2>nul
mkdir data 2>nul
mkdir data\medical_pdfs 2>nul
mkdir data\vector_store 2>nul
echo ✅ Directories created

REM Create fresh migrations
echo.
echo Creating fresh migrations...
python manage.py makemigrations users
python manage.py makemigrations consultations
python manage.py makemigrations agents
python manage.py makemigrations blackboard
python manage.py makemigrations rag

REM Apply migrations
echo.
echo Applying migrations...
python manage.py migrate

REM Create superuser
echo.
echo Creating superuser...
python manage.py createsuperuser

echo.
echo ========================================
echo FIX COMPLETE!
echo ========================================
echo.
echo Next steps:
echo 1. Run: python manage.py runserver
echo 2. Login at: http://127.0.0.1:8000/admin/
echo 3. Test consultation: http://127.0.0.1:8000/consultation/new/
echo.
pause