Getting started
===============

Run with a virtual environment
------------------------------

.. code-block:: bash

   python3 -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env               # then edit the values
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py runserver

Open http://127.0.0.1:8000/ in a browser. Set ``DB_ENGINE=sqlite`` in
``.env`` to run without a MariaDB server.

Run with Docker
---------------

.. code-block:: bash

   docker build -t daily-brief .
   docker run -p 8000:8000 daily-brief

Roles
-----

========== ===================================== ================================
Role       Articles                              Newsletters
========== ===================================== ================================
Reader     view approved; subscribe              view
Journalist create; update/delete own             create; update/delete own
Editor     view all; update; delete; **approve** view; update; delete
========== ===================================== ================================

Approval flow
-------------

Both the web approval view and the API ``approve`` action call
:func:`news.services.approve_article`, which marks the article approved,
emails subscribers (:func:`news.services.email_subscribers`) and POSTs the
article to ``/api/approved/`` (:func:`news.services.post_to_approved_api`).

Running the tests
-----------------

.. code-block:: bash

   python manage.py test news
