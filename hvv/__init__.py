import sys

# Windows-Konsolen nutzen oft cp1252 – Umlaute/Pfeile in Ausgaben sollen nicht abstürzen.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
