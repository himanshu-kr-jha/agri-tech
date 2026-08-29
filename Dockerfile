# The FastAPI tier, for Render.
#
# The build context is the REPOSITORY ROOT, not apps/api, and that is not a convenience.
# ingestion/weather.py and ingestion/agmarknet.py resolve their fixtures as
# ``parents[4] / "seed" / "generated"`` — the repo root — at *runtime*. An image built from
# apps/api alone compiles, starts, passes a health check, and then fails on the first
# weather or market question. See .dockerignore: seed/generated must ship.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# The full copy precedes the install deliberately. Hatchling resolves
# ``packages = ["agrivardhak"]`` at install time, so the usual trick of copying pyproject.toml
# alone to win a cached dependency layer makes the build fail outright. If build minutes
# become a problem, split it with a --no-install-project dependency pass rather than by
# reordering these two lines.
COPY . .

RUN pip install uv && uv pip install --system -e apps/api

# psycopg[binary] ships wheels and GeoAlchemy2 is pure Python, so slim needs no toolchain.

# Render supplies $PORT and expects the process to bind 0.0.0.0. The editable install puts
# ``agrivardhak`` on sys.path while leaving __file__ under /app/apps/api, which is what keeps
# the parents[4] fixture lookup resolving to /app/seed/generated.
CMD ["sh", "-c", "uvicorn agrivardhak.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
