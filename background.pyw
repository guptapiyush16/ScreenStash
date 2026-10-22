"""
Silent Windows Background Daemon Launcher (.pyw).
Runs with pythonw.exe without opening any command prompt or console window.
"""

from background_service import BackgroundDaemon

if __name__ == "__main__":
    daemon = BackgroundDaemon()
    daemon.start()
