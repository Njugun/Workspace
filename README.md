# Workspace
# Workspace

A Notion-style collaborative workspace: teams write and organise pages made of blocks, and everyone looking at a page sees changes as they happen.

**Live demo:** https://workspace-hxwp.onrender.com
(It runs on a free plan that sleeps when idle, so the first load can take up to a minute.)

![Two people editing the same page](docs/live-editing.png)

## What it does

- **Workspaces, pages and blocks.** Paragraphs, headings and to-dos that you can add, edit in place, tick, delete and reorder with buttons or by dragging.
- **Live collaboration.** A change in one browser appears in everyone else's without a refresh, and a "Here now" strip shows who has the page open.
- **Roles.** Owners, editors and viewers. Viewers see live updates but get no editing controls.
- **Members page.** Owners add people by username, change roles and remove members, and anyone can leave. A workspace always keeps at least one owner. Removed people are cut off at once, and role changes reload their open pages.
- **Safe simultaneous editing.** If two people edit the same block, the second save is refused and shows both versions, so nobody's work is silently overwritten.

## How it works

- **Writes use ordinary Django views** (HTMX swaps in the changed block). Every action is permission-checked there and covered by tests.
- **WebSockets only carry announcements.** After a change, the server sends a small message such as "block 7 changed". Each browser then fetches its own copy through a permission-checked request, so viewers never receive editing controls.
- **Conflicts** are detected with a version number on each block. The save and the check happen in one database statement.
- **Presence and the channel layer** are kept in the server's memory, which suits a single instance. Running several instances would need Redis.

## Built with

Django 6, Django Channels and Daphne, HTMX, Tailwind CSS (via django-tailwind-cli), SortableJS, PostgreSQL on Neon in production and SQLite in development, WhiteNoise, hosted on Render.

## Run it locally

```
python -m venv env
env\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py tailwind runserver
```

Then open http://127.0.0.1:8000/ and sign up. Sign-up creates your first workspace.

## Tests

```
python manage.py test workspaces
```

There are 135 tests covering the permission rules, the membership rules, the WebSocket permissions, every announcement and the conflict check.

## Deployment

Production settings come from environment variables (`DJANGO_DEBUG`, `SECRET_KEY`, `DATABASE_URL`). `build.sh` installs the requirements, builds the stylesheet, collects static files and runs migrations. Daphne serves the site:

```
daphne -b 0.0.0.0 -p $PORT Workspace.asgi:application
```

## Known limits

- Registration is open, so anyone can create an account.
- Pages can't be renamed, deleted or nested yet.
- One server instance only, until the channel layer moves to Redis.