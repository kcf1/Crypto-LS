# Docker Setup – Manual Summary

## Services

### PostgreSQL

- **docker-compose.yml** – Postgres 16 Alpine service:
  - **User:** `crypto`
  - **Password:** `crypto`
  - **Database:** `cryptols`
  - **Port:** `5432`
  - **Volume:** `postgres_data` for persistence
  - **Healthcheck:** `pg_isready` every 5s

### Data Updater

- **docker-compose.yml** – Data collection service:
  - **Container:** `crypto-ls-data-updater`
  - **Script:** `scripts/run_data_updater.py`
  - **Interval:** 300 seconds (5 minutes), aligned to :05, :10, :15, etc.
  - **Restart:** `unless-stopped`
  - **Depends on:** PostgreSQL (waits for healthy)
  - **Environment:** `DATABASE_URL` set automatically to connect to postgres service

## Start / Stop

- **Start:** `docker compose up -d`
- **Stop:** `docker compose down` (volume `postgres_data` is kept)

## Connection

- **Host:** `localhost` (or `host.docker.internal` from another container)
- **Port:** `5432`
- **Connection string:** `postgresql://crypto:crypto@localhost:5432/cryptols`

## pgAdmin (web GUI)

- **URL:** http://localhost:5050
- **Login:** `admin@example.com` / `admin`

**Add PostgreSQL server in pgAdmin:**

1. Right-click **Servers** → **Register** → **Server**
2. **General** tab: Name = `cryptols` (or any name)
3. **Connection** tab:
   - **Host:** `postgres` (Docker service name, not localhost)
   - **Port:** `5432`
   - **Username:** `crypto`
   - **Password:** `crypto`
   - **Save password:** optional
4. **Save**

## Migrations (Alembic)

After Postgres is up, apply schema from the repo:

```bash
# Ensure DATABASE_URL is set (e.g. in .env): postgresql://crypto:crypto@localhost:5432/cryptols
alembic upgrade head
```

- Migrations live in `alembic/versions/`.
- New schema changes: `alembic revision -m "description"`, then edit the new file and run `alembic upgrade head`.

## Container & Network

- **Containers:** `crypto-ls-postgres`, `crypto-ls-pgadmin`, `crypto-ls-data-updater`
- **Network:** `crypto-ls_default`

## Data Updater Service

The `data-updater` service runs continuously and collects OHLCV data from Binance every 5 minutes, aligned to minute marks (:05, :10, :15, etc.).

**View logs:**
```bash
docker logs -f crypto-ls-data-updater
```

**Restart the updater:**
```bash
docker compose restart data-updater
```

**Stop the updater (keep postgres running):**
```bash
docker compose stop data-updater
```

**Start only the updater:**
```bash
docker compose up -d data-updater
```
