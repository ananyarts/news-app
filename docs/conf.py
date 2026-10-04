"""Sphinx configuration for The Daily Brief documentation.

For the full list of built-in configuration values, see
https://www.sphinx-doc.org/en/master/usage/configuration.html
"""

import os
import sys

import django
from django.conf import settings
from django.core.management import call_command

# -- Django set-up -----------------------------------------------------------
# Make the project importable and load its settings so autodoc can import
# models and views.
sys.path.insert(0, os.path.abspath('..'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'news_project.settings'
os.environ['DB_ENGINE'] = 'sqlite'
django.setup()

# Use an empty in-memory database: autodoc evaluates class attributes such
# as ``queryset``, which needs the tables to exist but no real data.
settings.DATABASES['default']['NAME'] = ':memory:'
call_command('migrate', verbosity=0)

# -- Project information -----------------------------------------------------

project = 'The Daily Brief'
copyright = '2026, Ananya Singh'
author = 'Ananya Singh'
version = '1.0'
release = '1.0'

# -- General configuration ---------------------------------------------------

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',  # Google-style "Args:" / "Returns:" sections
    'sphinx.ext.viewcode',  # "[source]" links next to each object
]

autodoc_default_options = {
    'members': True,
    'undoc-members': False,
    'show-inheritance': True,
    'member-order': 'bysource',
}
napoleon_google_docstring = True
napoleon_numpy_docstring = False

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
language = 'en'

# -- Options for HTML output -------------------------------------------------

html_theme = 'alabaster'
html_static_path = ['_static']
html_theme_options = {
    'description': 'A Django news application',
    'fixed_sidebar': True,
}
