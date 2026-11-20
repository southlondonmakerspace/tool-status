# Woodshop tool status

A small Django app that shows which workshop tools are working, which need
maintenance, and lets members report problems or log maintenance.

## Running in production (Docker)

The stack is two containers:

- **web**: the Django app served by gunicorn, with static files served by WhiteNoise.
  Migrations run automatically on start. The SQLite database lives in the
  `woodcode-data` volume.
- **caddy**: [caddy-docker-proxy](https://github.com/lucaslorentz/caddy-docker-proxy),
  which reads the `caddy` labels on `web` through the Docker socket and serves it
  over HTTPS with an automatic Let's Encrypt certificate.

1. Point the domain's DNS at the server and open ports 80 and 443.
2. Create `.env` from the example and fill it in, including a fresh secret key:

   ```bash
   cp .env.example .env
   python3 -c "import secrets; print(secrets.token_urlsafe(50))"
   ```

3. Start it:

   ```bash
   docker compose up -d --build
   ```

4. Create an admin user and add tools at `/admin/`:

   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

### Moving an existing database across

```bash
docker compose cp ./db.sqlite3 web:/app/data/db.sqlite3
docker compose restart web
```

### Already running caddy-docker-proxy on the host?

Remove the `caddy` service from `compose.yaml` and make the `caddy` network
`external: true` so `web` joins the existing proxy's network.

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
DEBUG=1 .venv/bin/python manage.py migrate
DEBUG=1 .venv/bin/python manage.py runserver
```

Run the tests with:

```bash
DEBUG=1 .venv/bin/python manage.py test
```
