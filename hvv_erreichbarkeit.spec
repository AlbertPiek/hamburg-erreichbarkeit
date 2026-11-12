# PyInstaller-Spezifikation:  pyinstaller --noconfirm hvv_erreichbarkeit.spec
# Ergebnis: dist/HVV-Erreichbarkeit.exe (eine Datei, ohne Konsolenfenster)
# Die Oberfläche ist die Web-App aus web/ (inkl. web/data/); gerechnet wird im Fenster per JavaScript.

datas = [("web", "web")]

a = Analysis(
    ["run_desktop.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=[],
    excludes=["pandas", "numpy", "pytest", "tkinter", "matplotlib", "IPython", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="HVV-Erreichbarkeit",
    console=False,
    upx=False,
    icon=None,
)
