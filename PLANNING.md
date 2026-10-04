# Planning and design

## Functional requirements

1. Users register, log in and log out. Each user has one role: Reader,
   Journalist or Editor.
2. A user's role decides their group, and the group decides their
   permissions.
3. Journalists create, edit and delete their own articles, either
   independently or for a publisher they belong to.
4. New articles are unapproved. Only editors can see the review queue and
   approve articles.
5. When an article is approved, it is emailed to subscribers of its
   journalist or publisher and POSTed to `/api/approved/`.
6. Readers subscribe to publishers or journalists and have a personal feed.
7. Newsletters are curated collections of approved articles. Everyone can
   view them. Journalists and editors can create them. The author or an
   editor can edit or delete them.
8. Editors create publishers and choose their editors and journalists on
   the website. Superusers can do the same in the Django admin.
9. A token-authenticated REST API exposes articles, subscribed articles,
   newsletters and publishers, with access controlled by role.

## Non-functional requirements

- **Security:** access is checked on every web view and API endpoint.
  CSRF protection is on. Passwords are hashed by Django. The secret key
  and database credentials are loaded from a git-ignored `.env` file.
- **Reliability:** input is validated in forms and serializers. If email or
  the HTTP call fails, the error is logged and the approval still
  completes.
- **Maintainability:** code follows PEP 8, business logic lives in
  `services.py`, and permissions live in `permissions.py`.
- **Testability:** the project has 57 automated tests. External calls
  (`requests.post`) are mocked, and email uses Django's test outbox.
- **Usability:** the layout is responsive and uses one consistent template.
  The navigation shows only the actions allowed for the user's role.
- **Portability:** the app runs on MariaDB, with SQLite as a fallback for
  development.

## Database design (normalised to 3NF)

```
CustomUser (id, username, email, password, role, …)
  ├─ M2M subscribed_publishers  → Publisher     (join table)
  └─ M2M subscribed_journalists → CustomUser    (self join table)

Publisher (id, name UNIQUE, description, created_at)
  ├─ M2M editors     → CustomUser
  └─ M2M journalists → CustomUser

Article (id, title, content, author_id → CustomUser NULL,
         publisher_id → Publisher NULL, approved, approved_by_id,
         approved_at, created_at, updated_at)

Newsletter (id, title, description, author_id → CustomUser, created_at)
  └─ M2M articles → Article

ApprovedArticleLog (id, article_id → Article, title, author_name,
                    publisher_name, received_at)
```

Every many-to-many relationship has its own join table, so no column stores
a list. An article with no publisher is independent content.
`ApprovedArticleLog` stores copies of the title and names on purpose: it is
a record of what was shared at the moment of approval.

## UI plan

| Page                 | Audience   | Purpose |
|----------------------|------------|---------|
| Home `/`             | everyone   | approved articles, search, pagination |
| Article detail       | everyone   | full story; Edit/Delete/Approve shown by role |
| Publishers / Journalist pages | everyone | profile, articles, Subscribe button (readers) |
| My feed              | reader     | subscriptions and matching articles |
| Write / My articles  | journalist | submit and manage own articles (pending shown) |
| Review queue         | editor     | pending articles with Approve / Edit / Delete |
| Publisher management | editor     | create publishers; add/remove editors and journalists |
| Newsletters          | everyone   | list/detail; create/edit for journalists & editors |
| Log in / Sign up     | guests     | authentication with role selection |
