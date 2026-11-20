# Tool Status

A small web app for the South London Makerspace woodshop that shows, at a
glance, which tools are safe to use, which are due for maintenance and which
are out of action.

Members check a tool before using it, report problems when something breaks,
and log maintenance when they've done it. Everything happens from the tool's
page, with no account needed.

## Features

- **Dashboard of every tool**, each with a status badge:
  - 🟢 **Working**
  - 🟠 **Maintenance due**: the maintenance interval has passed since it was last maintained
  - 🔴 **Not working**: someone has reported a problem
- **Report a problem**: describe what's wrong and the tool is marked as not working
  until someone marks it as fixed
- **Log maintenance**: one click records today as the last maintenance date
  and resets the countdown
- **Admin** at `/admin/` for adding tools, descriptions and maintenance intervals
- Light and dark mode, and works on phones, so it's handy from a QR code on the tool

## How maintenance is worked out

Each tool has a **last maintained** date and a **maintenance interval** in
months. A month counts as 30 days, so the next due date is

```
last maintained + interval × 30 days
```

If either value is missing, the tool shows "No maintenance schedule" and is
never flagged as due.

## Running it in production (Docker)

The production stack is two containers, defined in [`compose.prod.yaml`](compose.prod.yaml):

| Service | What it does |
| --- | --- |
| `web` | Runs the Django app under gunicorn, with static files served by WhiteNoise. Migrations run on start, and the SQLite database lives in the `woodcode-data` volume. |
| `caddy` | Runs [caddy-docker-proxy](https://github.com/lucaslorentz/caddy-docker-proxy), which reads the `caddy` labels on `web` through the Docker socket (read-only) and serves the site over HTTPS with an automatic Let's Encrypt certificate. |

1. Point the domain's DNS at the server and open ports 80 and 443.
2. Create `.env` from the example and fill it in:

   ```bash
   cp .env.example .env
   ```

   Generate a secret key with:

   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(50))"
   ```

3. Start it:

   ```bash
   docker compose -f compose.prod.yaml up -d --build
   ```

4. Create an admin user, then add tools at `https://<your domain>/admin/`:

   ```bash
   docker compose -f compose.prod.yaml exec web python manage.py createsuperuser
   ```

### Configuration

All settings come from `.env`:

| Variable | Required | Description |
| --- | --- | --- |
| `SITE_DOMAIN` | Yes | Public hostname that Caddy gets a certificate for. |
| `SITE_NAME` | No | Name shown in the header and page titles. Defaults to `Tool Status`. |
| `DJANGO_SECRET_KEY` | Yes | Long random string. The app won't start without one unless `DEBUG` is on. |
| `DJANGO_ALLOWED_HOSTS` | Yes | Comma-separated hostnames the app answers to. |
| `CSRF_TRUSTED_ORIGINS` | Yes | Comma-separated origins, including the scheme, e.g. `https://woodshop.example.org`. |
| `DEBUG` | No | `true` to turn on debug pages. Never use it in production. Defaults to `false`. |
| `SECURE_COOKIES` | No | Defaults to `true`. Set to `false` only if the site is served over plain HTTP. |
| `DJANGO_DB_PATH` | No | Path to the SQLite file. The Docker image sets it to `/app/data/db.sqlite3`. |

### Backups and moving a database

The database is a single SQLite file in the `woodcode-data` volume.

Copy it out:

```bash
docker compose -f compose.prod.yaml cp web:/app/data/db.sqlite3 ./backup.sqlite3
```

Copy an existing database in:

```bash
docker compose -f compose.prod.yaml cp ./db.sqlite3 web:/app/data/db.sqlite3
```

```bash
docker compose -f compose.prod.yaml restart web
```

### Already running caddy-docker-proxy on the host?

Remove the `caddy` service from `compose.prod.yaml` and mark the `caddy`
network as `external: true`, so `web` joins the existing proxy's network.

## Local development

### With Docker

The default [`compose.yaml`](compose.yaml) is a development stack with no
Caddy and no HTTPS. It runs Django's dev server with debug on and your working
copy mounted, so changes reload without a rebuild. It needs no `.env`.

```bash
docker compose up --build
```

Then open http://localhost:8000. To create an admin user:

```bash
docker compose exec web python manage.py createsuperuser
```

### Without Docker

You need Python 3.12 or newer.

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

```bash
DEBUG=1 .venv/bin/python manage.py migrate
```

```bash
DEBUG=1 .venv/bin/python manage.py createsuperuser
```

```bash
DEBUG=1 .venv/bin/python manage.py runserver
```

Then open http://127.0.0.1:8000.

Run the tests with:

```bash
DEBUG=1 .venv/bin/python manage.py test
```

## Project layout

```
core/              Django project settings and URL config
tools/             The tools app: model, views, URLs, templates and tests
templates/         Shared base layout, header, status badge and 404 page
static/            Stylesheet
Dockerfile         Image (gunicorn, non-root)
compose.yaml       Development stack (dev server on :8000, no Caddy)
compose.prod.yaml  Production stack (gunicorn + Caddy HTTPS)
```

## Known limitations

- Anyone who can reach the site can report problems, mark tools as working
  and log maintenance. This is deliberate, so it's quick to use in the
  workshop; only the admin needs a login.
- A tool's name is its database key, so renaming a tool in the admin creates
  a new tool rather than renaming the old one.

## Credits

Originally built by [d3stom](https://github.com/d3stom/woodcode), and
maintained here by South London Makerspace.
