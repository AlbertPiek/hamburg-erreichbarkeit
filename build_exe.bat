@echo off
rem Baut dist\HVV-Erreichbarkeit.exe. Voraussetzung: .venv mit requirements-desktop.txt
rem und ein aufbereiteter Cache (python -m hvv.download, python -m hvv.preprocess).
cd /d "%~dp0"
if not exist web\data\network.json (
  echo Web-Daten fehlen. Bitte zuerst: python -m hvv.download  und  python -m hvv.preprocess
  exit /b 1
)
.venv\Scripts\python -m PyInstaller --noconfirm hvv_erreichbarkeit.spec || exit /b 1
echo.
echo Fertig: dist\HVV-Erreichbarkeit.exe
