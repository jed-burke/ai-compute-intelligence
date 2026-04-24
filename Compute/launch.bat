@echo off
cd /d "%~dp0"
py -3.14 -m streamlit run src/app.py
