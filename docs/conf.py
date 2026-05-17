"""Sphinx configuration for Supply Chain Control Tower."""

project = "Supply Chain Control Tower"
author = "Vijaya Supreetha Gurrala"
copyright = "2026, Vijaya Supreetha Gurrala"

extensions = [
    "myst_parser",
    "sphinx_copybutton",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

templates_path = ["_templates"]
exclude_patterns = ["_build"]

html_theme = "furo"
html_title = "Supply Chain Control Tower — Docs"
