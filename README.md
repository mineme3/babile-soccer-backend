# Babile Sport Server

Football live-score & news platform. **There is no external data API**: admin and
staff insert every piece of data from the admin website, and the server broadcasts
each change to mobile app users in real time over Server-Sent Events. Watching
matches works without an account — registration is optional (e.g. for favorites
sync), exactly like BeSoccer.

## Roles

| Role | What they can do |
|------|------------------|
| `admin` | Everything — manages users/staff, plus all data entry. |
| `staff` | Works under the admin: inserts clubs, players, competitions, matches, and runs matches live (events, lineups, results). |
| `user` | Consumer (mobile app). Registration is optional; can read everything without an account. |

## Architecture

Layered: `routers/` → `services/` → `repositories/` → `models/` + `schemas/`.

```
app/
├── routers/        # Thin HTTP layer (public reads + admin/staff writes)
├── services/       # Business logic (matches, standings, auth, SSE, search)
├── repositories/   # DB access
├── models/         # SQLAlchemy ORM models
└── schemas/        # Pydantic request/response schemas
```

- **Data entry** — admin/staff create and update teams, players, competitions,
  seasons, stages, groups, matches, news via the REST API. All public read
  endpoints require no auth.
- **Real-time** — every create/update publishes to Redis pub/sub; SSE streams fan
  it out to the app instantly. Broadcast failures never block data entry, so the
  system keeps working on poor network connections.
- **Offline-friendly** — staff can queue match events and replay them later via
  `POST /matches/{id}/events/batch`.

## Tech Stack

| Concern | Choice |
|---------|--------|
| Language | Python 3.12+ |
| API Framework | FastAPI + Uvicorn |
| Database | Postgres (asyncpg) |
| ORM | SQLAlchemy 2.0 (async) |
| Validation | Pydantic v2 |
| Real-time | Server-Sent Events via Redis pub/sub |
| Auth | OAuth2 + JWT (access + refresh), bcrypt |

Tables are created automatically on startup (`Base.metadata.create_all`) — no
migration tooling in the MVP. **Consequence:** schema changes (new models/columns)
do not alter an existing database; to pick them up, drop and recreate the dev DB
(`dropdb babile_sport && createdb ...` then restart). Before any production data
exists we will adopt Alembic; until then `create_all` keeps the MVP deployable
with zero extra tooling.

## Quick Start (Local Dev)

```bash
# Start Postgres + Redis
docker compose up -d postgres redis

# Install dependencies
pip install .

# Start API
uvicorn app.main:app --reload
```

## Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

**Never commit real credentials.**

## API Docs

When running with `DEBUG=true`, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/health

## Real-Time Events (SSE)

The mobile app subscribes to these streams to update in real time:

```bash
curl -N http://localhost:8000/api/v1/events/matches      # match status, score, events, lineups
curl -N http://localhost:8000/api/v1/events/standings    # standings recomputed at full time
curl -N http://localhost:8000/api/v1/events/data         # any catalog change (team/player/competition/news)
curl -N http://localhost:8000/api/v1/events/news         # published news
```

## Tests

Requires a Postgres database named `babile_sport_test` (Redis optional).

```bash
docker compose up -d postgres
createdb -U postgres babile_sport_test
pytest
```
