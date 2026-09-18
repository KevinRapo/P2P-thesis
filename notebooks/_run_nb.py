"""Execute a notebook in-process via nbclient, bypassing any PATH-resolved
jupyter-nbconvert console script (which resolves to a broken .venv on this
machine and silently reports success even when it crashes at import).
Usage: python _run_nb.py <notebook.ipynb> [timeout_seconds]
"""
import sys
import traceback
import nbformat

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

path = sys.argv[1]
timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 600
nb = nbformat.read(path, as_version=4)
client = NotebookClient(nb, timeout=timeout, kernel_name="python3", resources={"metadata": {"path": "."}})
try:
    client.execute()
    print(f"PASS: {path}")
except CellExecutionError as e:
    print(f"FAIL: {path}")
    print(str(e)[:4000])
    sys.exit(1)
except Exception:
    print(f"FAIL: {path} (harness error)")
    traceback.print_exc()
    sys.exit(1)
