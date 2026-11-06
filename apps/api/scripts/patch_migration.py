from __future__ import annotations

import pathlib
import re

p = pathlib.Path("alembic/versions/33855a02808b_initial_schema.py")
src = p.read_text(encoding="utf-8")

# JSONB type is rendered as app.db.base.JSONB(); the migration must be self-contained.
src = src.replace("app.db.base.JSONB()", "sa.JSON()")
if "from app.db.base import" not in src:
    src = src.replace(
        "from alembic import op\n",
        "from alembic import op\n\n# JSONB is JSON on SQLite and JSONB on PostgreSQL (see app.db.base)\n",
    )
p.write_text(src, encoding="utf-8")
print("patched", p)
print("json columns:", src.count("sa.JSON()"))
