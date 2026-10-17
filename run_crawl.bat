@echo off
cd /d E:\DM_2026.1
call C:\Users\Ruanw\anaconda3\Scripts\activate.bat wm
python src\crawl\crawl.py >> crawl.log 2>&1