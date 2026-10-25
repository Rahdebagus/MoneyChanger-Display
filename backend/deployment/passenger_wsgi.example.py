"""Reference only. Do not copy over a working passenger_wsgi.py.

Keep the host's interpreter/path setup. Merge only the application wrapping
if needed. Configure REALTIME_ENABLED=false in the application's environment.
"""
import os

os.environ.setdefault("REALTIME_ENABLED", "false")
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(variable, "1")

from a2wsgi import ASGIMiddleware
from app.main import app

# wait_time bounds post-response background-task waiting, NOT PNG execution.
application = ASGIMiddleware(app, wait_time=1.0)
