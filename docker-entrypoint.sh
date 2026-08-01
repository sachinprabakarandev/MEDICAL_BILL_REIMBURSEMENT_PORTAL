#!/bin/sh
set -e

# seed.py calls Base.metadata.drop_all() — it is destructive. Run it only when
# the database genuinely does not exist yet (first boot on a fresh volume),
# never on an ordinary restart or redeploy.
DB_PATH="/app/backend/app/data/medical_verification.db"

if [ ! -f "$DB_PATH" ]; then
    echo "No database found at $DB_PATH — seeding for first boot."
    python app/seed.py
else
    echo "Existing database found — skipping seed."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
