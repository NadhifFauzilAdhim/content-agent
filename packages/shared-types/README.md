# Shared contract types

TypeScript mirror of the FastAPI Pydantic schemas (`apps/api/app/schemas.py`). The web app imports
these from `apps/web/src/lib/types.ts`, which is a copy kept in sync by hand — a deliberate choice
while the surface is small; if it grows, generate this file from `/openapi.json`.

Rules:
- Field names match the API exactly (snake_case).
- Optional/nullable mirrors the Pydantic `| None` intent.
- No functions, no classes — plain JSON shapes only.
