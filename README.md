# The Daily Brief: a Django news application

Readers follow articles from publishers and independent journalists.
Journalists write articles and newsletters. Editors review and approve
articles. When an editor approves an article, it is emailed to subscribers
and logged through the project's own REST endpoint, `/api/approved/`.

Design notes (requirements, database schema and UI plan) are in
[PLANNING.md](PLANNING.md).

Contents: [Run with venv](#option-1-run-with-a-virtual-environment-venv) ·
[Run with Docker](#option-2-run-with-docker) ·
[Secrets](#secrets-and-configuration) ·
[Documentation](#documentation)

## Requirements

- Python 3.12 or newer (for the venv option)
- [Docker](https://docs.docker.com/get-docker/) (for the Docker option)
- Git, to clone the repository:

```bash
git clone <repository-url>
cd <repository-folder>
```

## Option 1: Run with a virtual environment (venv)

### 1. Create the environment and install packages

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows, activate the virtual environment with
`.venv\Scripts\activate` instead.

### 2. Configuration: the `.env` file

Settings such as the secret key and database credentials are read from a
`.env` file in the project root (loaded with `python-dotenv`). Copy the
example file and edit the values:

```bash
cp .env.example .env
```

`.env` is listed in `.gitignore`, so secrets are never committed. Real
environment variables override values in `.env`.

| Variable | Purpose | Default |
|----------|---------|---------|
| `DJANGO_SECRET_KEY` | Django secret key (see [Secrets](#secrets-and-configuration)) | random key generated at start-up |
| `DJANGO_DEBUG` | `True` or `False` | `True` |
| `DJANGO_ALLOWED_HOSTS` | comma-separated host names | `127.0.0.1,localhost,testserver` |
| `DB_ENGINE` | `mariadb` or `sqlite` | `mariadb` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | MariaDB connection | `news_app`, `news_user`, `news_pass`, `127.0.0.1`, `3306` |
| `DEFAULT_FROM_EMAIL` | sender for subscriber emails | `newsroom@news-app.local` |
| `APPROVED_API_URL` | endpoint the approval flow POSTs to | `http://127.0.0.1:8000/api/approved/` |

### 3. Database: MariaDB (default)

Create the database and user named in your `.env`:

```sql
CREATE DATABASE news_app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'news_user'@'127.0.0.1' IDENTIFIED BY 'news_pass';
GRANT ALL PRIVILEGES ON news_app.* TO 'news_user'@'127.0.0.1';
GRANT ALL PRIVILEGES ON test_news_app.* TO 'news_user'@'127.0.0.1';
```

Then create the tables:

```bash
python manage.py migrate
```

To run on SQLite instead (useful for quick local testing), set
`DB_ENGINE=sqlite` in `.env`.

`migrate` creates the **Reader**, **Journalist** and **Editor** groups and
their permissions automatically.

### 4. Run

```bash
python manage.py createsuperuser  # site administrator, for /admin/
python manage.py runserver
```

Open <http://127.0.0.1:8000/> and use **Sign up** to create Reader,
Journalist and Editor accounts. Emails are printed to the console.

Demo data is optional. `python manage.py seed_demo` creates the logins
`reader`, `journalist` and `editor` (password `NewsDemo123!`) plus one
publisher and some articles. The app does not need it: publishers can be
created and managed as described below.

## Option 2: Run with Docker

The repository includes a `Dockerfile`. The container uses SQLite by
default, so no database server is needed. This also works on
[Play with Docker](https://labs.play-with-docker.com/).

### 1. Build the image

From the project root (the folder containing `Dockerfile`):

```bash
docker build -t daily-brief .
```

### 2. Start a container

```bash
docker run -d --name daily-brief -p 8000:8000 -e DJANGO_SECRET_KEY="<your-secret-key>" daily-brief
```

The container runs `migrate` and then starts the server. Open
<http://127.0.0.1:8000/> (on Play with Docker, click the **8000** port
badge). If you leave out `DJANGO_SECRET_KEY`, a random key is generated
each time the container starts.

### 3. Optional: demo data and an admin account

```bash
docker exec -it daily-brief python manage.py seed_demo
docker exec -it daily-brief python manage.py createsuperuser
```

### 4. Stop and remove the container

```bash
docker stop daily-brief
docker rm daily-brief
```

To use MariaDB instead of SQLite, pass `-e DB_ENGINE=mariadb` and the
`DB_*` variables (for example with `--env-file .env`).

## Secrets and configuration

No passwords, keys or tokens are stored in this repository. `.env` is
listed in `.gitignore`; only the template `.env.example` is committed.
To set up your own values:

1. Copy the template: `cp .env.example .env`.
2. Generate a secret key and paste it in as `DJANGO_SECRET_KEY`:

   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

3. Choose your own database name, user and password (`DB_*`) and use the
   same values when you create the MariaDB user (Option 1, step 3).
4. For Docker, pass the values with `-e NAME=value` or `--env-file .env`.

API tokens are created per user at `POST /api/token/` and are never
committed.

## Documentation

Developer documentation is generated from the code's docstrings with
Sphinx. The built HTML is committed in `docs/_build/html/`, so open
`docs/_build/html/index.html` in a browser to read it.

To rebuild it after changing docstrings:

```bash
sphinx-build -b html docs docs/_build/html
```

## Managing publishers

A publisher has its own editors and journalists. A journalist can only file
articles under publishers they belong to, and can always publish
independently. There are two ways to manage publishers.

### On the website (editors)

1. Log in as an **Editor** and open **Publishers** in the top menu.
2. Click **New publisher**. Enter a name and description, and tick the
   editors and journalists who belong to it. You are added as one of its
   editors automatically.
3. To change it later, open the publisher's page and click
   **Manage publisher & staff**. Tick or untick editors and journalists and
   click **Save**. Only users with the matching role are listed.
4. **Delete publisher** removes the publisher. Its articles are kept and
   become independent articles.

Only a publisher's own editors (and superusers) can manage or delete it.

### In the Django admin (superusers)

1. Create an administrator with `python manage.py createsuperuser`.
2. Go to <http://127.0.0.1:8000/admin/> and log in.
3. Under **News > Publishers**, click **Add publisher** (or click an
   existing one to edit it).
4. Fill in the name and description. Use the **Editors** and
   **Journalists** pickers to move users into the publisher. Only users
   with the Editor or Journalist role are offered.
5. Click **Save**.

To change a user's role, edit the user under **News > Users** and set
**Role**. The user moves to the matching group automatically.

## Writing articles (journalists)

Click **Write**. Leave **Publisher** empty to publish independently, or
pick one of your publishers. Either way the article waits in the editors'
**Review queue** until it is approved.

### Tests

```bash
python manage.py test news
```

## Roles

| Role       | Articles                           | Newsletters                  | Other                    |
|------------|------------------------------------|------------------------------|--------------------------|
| Reader     | view approved                      | view                         | subscribe to publishers / journalists |
| Journalist | create, view, update/delete own    | create, view, update/delete own | —                     |
| Editor     | view all, update, delete, **approve** | view, update, delete      | review queue; create and manage publishers |

Users join the group that matches their role automatically. If a user's
role changes, fields that don't apply to the new role are cleared.

## REST API

Authenticate with `POST /api/token/` (`username`, `password`), then send
the header `Authorization: Token <key>`.

| Method | Endpoint                        | Who                     |
|--------|---------------------------------|-------------------------|
| GET    | `/api/articles/`                | any signed-in user (approved only) |
| GET    | `/api/articles/subscribed/`     | readers                 |
| GET    | `/api/articles/<id>/`           | any signed-in user      |
| POST   | `/api/articles/`                | journalists             |
| PUT/PATCH/DELETE | `/api/articles/<id>/` | editors, owning journalist |
| POST   | `/api/articles/<id>/approve/`   | editors                 |
| GET/POST/PUT/DELETE | `/api/newsletters/…` | view: all; write: journalists & editors |
| GET    | `/api/publishers/…`             | any signed-in user      |
| GET/POST | `/api/approved/`              | editors                 |

## Approval flow (Option 2: no signals)

Both the web approval view and the API `approve` action call
`news.services.approve_article`. This function:

1. marks the article approved and records the approving editor and time;
2. emails the article (by Bcc) to readers subscribed to its journalist or
   publisher;
3. uses `requests` to POST the article to `APPROVED_API_URL`
   (`/api/approved/`) with the editor's token.

If sending the email or the POST fails, the error is logged and the approval
still goes through.
