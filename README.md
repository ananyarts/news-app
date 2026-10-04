# The Daily Brief: a Django news application

Readers follow articles from publishers and independent journalists.
Journalists write articles and newsletters. Editors review and approve
articles. When an editor approves an article, it is emailed to subscribers
and logged through the project's own REST endpoint, `/api/approved/`.

Design notes (requirements, database schema and UI plan) are in
[PLANNING.md](PLANNING.md).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows, activate the virtual environment with
`.venv\Scripts\activate` instead.

### Configuration: the `.env` file

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
| `DJANGO_SECRET_KEY` | Django secret key | development-only key |
| `DJANGO_DEBUG` | `True` or `False` | `True` |
| `DJANGO_ALLOWED_HOSTS` | comma-separated host names | `127.0.0.1,localhost,testserver` |
| `DB_ENGINE` | `mariadb` or `sqlite` | `mariadb` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | MariaDB connection | `news_app`, `news_user`, `news_pass`, `127.0.0.1`, `3306` |
| `DEFAULT_FROM_EMAIL` | sender for subscriber emails | `newsroom@news-app.local` |
| `APPROVED_API_URL` | endpoint the approval flow POSTs to | `http://127.0.0.1:8000/api/approved/` |

### Database: MariaDB (default)

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

### Run

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
