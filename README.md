# Agrotex — Factory Production Line (HDMI) System

A **Django-based production-line tracking system** for a factory assembly floor. It manages workstations (posts), operators and brigadiers, product variants (e.g. truck models), assembly steps per station, and live truck runs with task timing and status (on time / late / very late). The UI supports station picker, truck selection, step-by-step run view, and a production dashboard. Optional integration points for external devices (e.g. Arduino) use Redis and Django Channels.

---

## What This Project Is

- **Workstations** — Physical posts (e.g. "Post 1", "Post 2") with optional IP-based identification and a PIN for reset.
- **Workers** — Operators (`USTA`) and Brigadiers (`BRIGADIR`), identified by badge ID; can be assigned to a station.
- **Product variants** — Truck (or product) types with name, code, and optional image.
- **Assembly steps** — Ordered tasks per workstation and product (description, standard duration, tooling, torque), grouped by task categories.
- **Truck runs** — An active “run” at a station: one product + optional serial number; only one active run per station.
- **Task logs** — Each step execution: start/end time, operator, status color (GREEN / YELLOW / RED), and optional “was intervened” (brigadier takeover).

**Main flows:**

1. **Station picker** → operator chooses which station this browser is (or use IP matching).
2. **Truck selection** → choose product variant and optional truck serial number; this starts a new active run for that station.
3. **Station detail** → view current run, list of steps, progress; advance steps (e.g. via Space or API), record timing and status.
4. **Production dashboard** → overview of all stations and their current run / progress.
5. **Run page** — table view of production run data.

**APIs** (used by the UI or external clients):

- Dashboard data, station data, next task (advance step), take-over (brigadier), reset truck (with PIN), select specific task.

---

## Tech Stack

| Component        | Technology                          |
|-----------------|-------------------------------------|
| Backend         | Django 5.x                          |
| Database        | PostgreSQL 15                       |
| Cache / broker  | Redis 7                             |
| Async / channels| Django Channels, Daphne, Redis layer|
| Server          | Gunicorn (production), runserver (dev) |
| Frontend        | Django templates, HTMX, static files|
| Deployment      | Docker + Docker Compose             |

**Python deps (see `requirements.txt`):** Django, psycopg2-binary, redis, gunicorn, python-dotenv, django-htmx, channels, daphne, Pillow.

---

## Prerequisites (to run on another computer)

- **Git** — to clone the repo.
- **Docker and Docker Compose** — recommended way to run the app and its services (PostgreSQL, Redis, Django).
  - Install: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/Mac) or Docker Engine + Docker Compose (Linux).

**Optional (run without Docker):**

- **Python 3.11+**
- **PostgreSQL 15** (create DB and user matching settings or env)
- **Redis 7** (for Channels; optional if you disable Channels)

---

## How to Run (another computer) — Docker (recommended)

### 1. Clone the repository

```bash
git clone https://github.com/yujboss/agrotex.git
cd agrotex
```

### 2. Start services with Docker Compose

From the **project root** (where `docker-compose.yml` lives):

```bash
docker-compose up --build
```

This will:

- Start **PostgreSQL** on port `5432` (DB: `factory_db`, user: `factory_admin`, password: `factory_secret_password`).
- Start **Redis** on port `6379`.
- Build and start the **Django app** with code from `./backend` mounted into the container, and run `python manage.py runserver 0.0.0.0:8000`.

First run may take a few minutes while the image is built.

### 3. Import the included database backup (recommended)

The repo includes **`factory_db_backup.sql`** — a PostgreSQL dump with sample data (workstations, workers, product variants, task categories, assembly steps). There is nothing private in it; it lets the project run with something to see right away.

In **another terminal**, from the **project root** (where `factory_db_backup.sql` lives):

**Linux / macOS / Git Bash:**

```bash
docker-compose exec -T db psql -U factory_admin -d factory_db < factory_db_backup.sql
```

**Windows (PowerShell):**

```powershell
Get-Content factory_db_backup.sql -Raw | docker-compose exec -T db psql -U factory_admin -d factory_db
```

**Windows (CMD):**

```cmd
type factory_db_backup.sql | docker-compose exec -T db psql -U factory_admin -d factory_db
```

You should see SQL commands and possibly `CREATE TABLE`, `ALTER TABLE`, etc. When it finishes without errors, the database is populated. If the dump was made with a different schema version, run migrations next so the schema matches the code:

```bash
docker-compose exec web python manage.py migrate
```

**If you prefer an empty database** (no sample data), skip the backup import and run only:

```bash
docker-compose exec web python manage.py migrate
```

Then create a superuser and add workstations, workers, products, and assembly steps via Django Admin.

### 4. Create a superuser (first time only)

To access Django Admin (`/admin/`):

```bash
docker-compose exec web python manage.py createsuperuser
```

Enter username, email, and password when prompted. (The backup does not include admin users, so you must create one.)

### 5. Open the app

- **App (station picker / truck selection / station detail / dashboard):**  
  **http://localhost:8000/**
- **Django Admin:**  
  **http://localhost:8000/admin/**

Use the superuser account to log in to Admin and configure workstations, workers, products, and assembly steps.

---

## How to Run without Docker (alternative)

Use this if you prefer to run Django, PostgreSQL, and Redis directly on the host.

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/yujboss/agrotex.git
cd agrotex
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

### 2. PostgreSQL and Redis

- Install and start **PostgreSQL 15**. Create database and user, for example:

  - Database: `factory_db`
  - User: `factory_admin`
  - Password: `factory_secret_password`

- Install and start **Redis 7** (e.g. on `localhost:6379`).

### 3. Point Django to local DB and Redis

In `backend/config/settings.py`, the default config uses host `db` (Docker). For local run, either:

- **Option A:** Temporarily change `DATABASES['default']['HOST']` to `'127.0.0.1'` (and ensure `NAME` / `USER` / `PASSWORD` match your PostgreSQL setup).
- **Option B:** Use environment variables and a small change in settings to read `DATABASE_URL` or `DB_HOST` (e.g. `HOST=os.getenv('DB_HOST', 'db')`).

For Channels, `CHANNEL_LAYERS` uses `("redis", 6379)`. For local Redis, change to `("127.0.0.1", 6379)` or use an env-based config.

### 4. (Optional) Import the included backup

To use the same sample data as with Docker, restore the backup into your local `factory_db`:

**Linux / macOS:**

```bash
psql -U factory_admin -d factory_db -h 127.0.0.1 -f factory_db_backup.sql
```

**Windows (PowerShell):**

```powershell
Get-Content factory_db_backup.sql -Raw | psql -U factory_admin -d factory_db -h 127.0.0.1
```

If you skip this, start with an empty DB and run migrations only.

### 5. Migrate and run

From the **project root**:

```bash
cd backend
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

Then open **http://localhost:8000/** and **http://localhost:8000/admin/**.

---

## Environment variables (Docker)

These are set in `docker-compose.yml` for the `web` service; override or add as needed (e.g. for production):

| Variable             | Purpose                                      | Example / default                         |
|----------------------|----------------------------------------------|------------------------------------------|
| `DEBUG`              | Enable debug mode (0/1)                      | `1` (dev), `0` (prod)                    |
| `SECRET_KEY`         | Django secret key                            | Set a strong value in production         |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hosts             | `localhost,127.0.0.1,*` (dev)           |
| `DATABASE_URL`       | Not used by current settings (DB is hardcoded in `settings.py`); can be used if you switch to `dj-database-url` | `postgres://user:pass@db:5432/factory_db` |
| `REDIS_URL`          | Redis URL (optional if you use Redis only for Channels) | `redis://redis:6379/0`                |

DB connection in code uses: host `db`, port `5432`, database `factory_db`, user `factory_admin`, password `factory_secret_password` (must match `docker-compose` `db` service).

---

## Main URLs

| URL                      | Description                          |
|--------------------------|--------------------------------------|
| `/`                      | Truck selection (or redirect to station picker) |
| `/select-station/`       | Choose workstation for this client   |
| `/select-station/clear/` | Clear station and return to picker   |
| `/dashboard/`            | Production dashboard (all stations)  |
| `/run/`                  | Production run table view            |
| `/station/<slug>/`       | Station detail (current run + steps) |
| `/admin/`                | Django Admin                         |

API examples (see `backend/core/urls.py` and `api.py` for full list):

- `GET /api/dashboard/` — dashboard data for all stations
- `GET /api/station/<station_slug>/data/` — full data for one station (run, steps, logs, progress)
- `POST /api/station/<station_slug>/next-task/` — advance to next task (e.g. Space bar)
- `POST /api/station/<station_slug>/take-over/` — brigadier takeover
- `POST /api/station/<station_slug>/reset/` — reset truck (body: `{"pin": "1234"}`)
- `POST /api/station/<station_slug>/select/` — select a specific task

---

## Project layout (relevant parts)

```
agrotex/
├── docker-compose.yml      # PostgreSQL, Redis, Django web
├── Dockerfile              # Image for Django app
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── factory_db_backup.sql   # Included PostgreSQL backup (sample data; import for ready-to-use setup)
└── backend/
    ├── manage.py
    ├── config/
    │   ├── settings.py     # Django settings (DB, Redis, Channels)
    │   ├── urls.py        # Root URL config
    │   ├── asgi.py / wsgi.py
    │   └── ...
    └── core/
        ├── models.py      # WorkStation, Worker, ProductVariant, AssemblyStep, TruckRun, TaskLog
        ├── views.py       # station_picker, truck_selection, station_detail, dashboard, run_page
        ├── api.py        # REST/JSON APIs for dashboard, station data, next-task, reset, etc.
        ├── urls.py       # App URLs and API routes
        ├── admin.py      # Django Admin registration
        ├── templates/core/
        │   ├── station_picker.html
        │   ├── truck_selection.html
        │   ├── station_detail.html
        │   ├── production_dashboard.html
        │   └── run.html
        └── static/       # Static and media (e.g. truck images)
```

---

## Quick checklist (new computer, Docker)

1. Install Git and Docker (Docker Desktop or Engine + Compose).
2. `git clone https://github.com/yujboss/agrotex.git && cd agrotex`
3. `docker-compose up --build`
4. In another terminal, **import the backup** (see step 3 above — use the command for your OS).
5. Run migrations if needed: `docker-compose exec web python manage.py migrate`
6. Create admin user: `docker-compose exec web python manage.py createsuperuser`
7. Open http://localhost:8000 and http://localhost:8000/admin/

After importing the backup you’ll have sample workstations, workers, products, and assembly steps. Use the station picker and truck selection to start a run and the station detail / dashboard to use the app.



### How to Run for the First Time (Quick Setup)

Run these commands sequentially in your terminal from the project root folder:

```bash
# 1. Stop old containers and remove volumes (if any)
docker-compose down -v

# 2. Build and start containers in the background
docker-compose up -d --build

# 3. Copy the database backup file directly into the DB container
docker cp factory_db_backup.sql agrotex-db-1:/tmp/backup.sql

# 4. Restore the database from the backup
docker-compose exec db psql -U factory_admin -d factory_db -f /tmp/backup.sql

# 5. Apply Django migrations
docker-compose exec web python manage.py migrate

# 6. Collect static files (CSS, JS, images)
docker-compose exec web python manage.py collectstatic --noinput

# 7. Create a superuser (you will need to set a username and password)
docker-compose exec web python manage.py createsuperuser