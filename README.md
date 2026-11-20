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
- **Areas**, such as Woodshop or Metal shop, group the tools on the home page
- **Admin** at `/admin/` for adding tools, descriptions and maintenance intervals,
  with editing limited to each person's areas
- Light and dark mode, and works on phones, so it's handy from a QR code on the tool

## Areas and who can edit them

Every tool belongs to an **area**. The home page shows one section per area,
and tools with no area are listed last under "Other tools".

Each tool's page is at `/<area>/<tool>`, such as `/woodshop/band-saw`. Both
parts are made from the names automatically, and change if an area or tool is
renamed. Tools with no area are at `/other/<tool>`. Old links that used the
tool's name, such as `/Band%20saw`, redirect to the new address.

Anyone can report a problem, mark a tool as working or log maintenance without
logging in. Editing tools in the admin (adding, renaming, changing intervals,
deleting) is limited by area:

- **Superusers** can edit every tool and are the only ones who manage areas.
- **Area editors** can see, add, edit and delete tools in their own areas only.
- **Groups with permissions**: give a group Tool or Area permissions in the
  admin and its members can do that across every area.

To make someone an editor of an area:

1. In the admin, create or open their user and tick **Staff status** so they
   can log in. They don't need any other permissions.
2. Open the area under **Areas** and add them to **Editors**, or add a group
   they're in to **Editor groups**. Groups are handy for a team, such as
   "Woodshop maintainers".

When upgrading an existing database, any tools already there are put into a
new **Woodshop** area.

## Single sign-on (OpenID Connect)

People can sign in with an OpenID Connect provider such as Authentik. It's
off until `OIDC_CLIENT_ID` is set. When it's on, there's a **Sign in with …**
button on the admin login page. The
admin's password login still works, so a local superuser can always get in.

Each time someone signs in with SSO:

- Their Django groups are set to exactly the groups in the token's groups
  claim. Groups are created as needed, so a group called "Woodshop team" in
  the provider can be added to an area's **Editor groups**.
- They're a **superuser** while they're in `OIDC_SUPERUSER_GROUP` (for
  example `Systems`), and stop being one when they leave it.
- They get **staff status** (admin access) while they're a superuser, an
  editor of at least one area, or in a group that has permissions in the admin.

Their email and username come from the provider, with no sign-up form. If
an account here already has the same email, such as one made with
`createsuperuser`, they're signed in to that account and it's linked to SSO
from then on. Linking removes that account's password, so keep any
break-glass admin account on an email address nobody uses in the provider.
If the username is taken by another account, a number is added to it.

Changes in the provider take effect the next time the person signs in.
Users who sign in with a password are never changed.

### Setting it up in Authentik

1. Create an **OAuth2/OpenID Provider** with a confidential client, and set
   its redirect URI to `https://<your domain>/accounts/oidc/sso/login/callback/`.
   Keep the default `openid`, `email` and `profile` scopes; Authentik's
   profile scope includes a `groups` claim.
2. Create an **Application** that uses the provider, and bind the groups or
   users who should be able to sign in.
   Because sign-in trusts the provider's email address, don't let users
   change their own email in Authentik's user settings flow.
3. Add the client ID, client secret and the provider's **OpenID Configuration
   Issuer** URL to `.env` as `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` and
   `OIDC_SERVER_URL`, then restart the app.

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
| `CSRF_TRUSTED_ORIGINS` | Yes | Comma-separated origins, including the scheme, e.g. `https://toolstatus.southlondonmakerspace.org`. |
| `DEBUG` | No | `true` to turn on debug pages. Never use it in production. Defaults to `false`. |
| `SECURE_COOKIES` | No | Defaults to `true`. Set to `false` only if the site is served over plain HTTP. |
| `TIME_ZONE` | No | The space's time zone, used for the date when maintenance is logged. Defaults to `Europe/London`. |
| `DJANGO_DB_PATH` | No | Path to the SQLite file. The Docker image sets it to `/app/data/db.sqlite3`. |
| `OIDC_CLIENT_ID` | No | Turns on single sign-on. See [Single sign-on](#single-sign-on-openid-connect). |
| `OIDC_CLIENT_SECRET` | With SSO | The client secret from the provider. |
| `OIDC_SERVER_URL` | With SSO | The provider's issuer URL, such as `https://auth.example.org/application/o/tool-status/`. |
| `OIDC_PROVIDER_NAME` | No | Label on the sign-in button. Defaults to `SSO`. |
| `OIDC_GROUPS_CLAIM` | No | Token claim that lists the user's groups. Defaults to `groups`. |
| `OIDC_SUPERUSER_GROUP` | No | Members of this group become superusers, such as `Systems`. Empty means none. |

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

You need Python 3.12 or newer, and Node.js to build the CSS (see below).

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

### The CSS

The pages use Bootstrap classes only, with no custom CSS and no JavaScript.
Bootstrap is compiled from [`static/scss/bootstrap.scss`](static/scss/bootstrap.scss)
with `$color-mode-type: media-query`, so dark mode follows the device through
`@media (prefers-color-scheme: dark)`. The compiled CSS isn't committed:

- **Docker** builds it: the image's first stage compiles it with Node, and
  only the CSS is copied into the final image.
- **The dev stack** runs a `css` service that rebuilds it whenever the Sass
  changes.
- **Without Docker**, build it once with Node.js before running the app:

  ```bash
  npm install
  ```

  ```bash
  npm run build:css
  ```

## Project layout

```
core/              Django project settings and URL config
tools/             The tools app: model, views, URLs, templates and tests
templates/         Shared base layout, header, status badge and 404 page
static/            Bootstrap Sass entry point and the compiled CSS
package.json       Pins Bootstrap and Sass for building the CSS
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
