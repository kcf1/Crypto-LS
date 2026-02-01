# Docker PostgreSQL – Manual Summary

## Created

- **docker-compose.yml** – Postgres 16 Alpine service:
  - **User:** `crypto`
  - **Password:** `crypto`
  - **Database:** `cryptols`
  - **Port:** `5432`
  - **Volume:** `postgres_data` for persistence
  - **Healthcheck:** `pg_isready` every 5s

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

## Container & Network

- **Containers:** `crypto-ls-postgres`, `crypto-ls-pgadmin`
- **Network:** `crypto-ls_default`
