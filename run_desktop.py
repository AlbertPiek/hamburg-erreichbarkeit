"""Einstiegspunkt für PyInstaller (absolute Imports, kein -m nötig)."""
import sys

from hvv.desktop import main, show_error

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        show_error("Unerwarteter Fehler:\n\n" + traceback.format_exc())
        sys.exit(1)
