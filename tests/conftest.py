"""
Shared fixtures for ZenoBot tests.
"""
import os
import sys
import tempfile
import shutil

import pytest

# Ensure project root is on sys.path so imports work
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture
def tmp_excel(tmp_path):
    """Create a temporary Excel file path for tests.
    Returns (path_str, sheet_name) — the file does NOT exist yet
    so ExcelStore._init_book will create it.
    """
    path = str(tmp_path / "test_catalogo.xlsx")
    yield path, "Catalogo"


@pytest.fixture
def store(tmp_excel):
    """Return a fresh ExcelStore backed by a temp file."""
    from telegram_excel_bot.excel_store import ExcelStore
    path, sheet = tmp_excel
    return ExcelStore(path, sheet)


@pytest.fixture
def sample_book():
    """A minimal book dict for add()."""
    return {
        "titulo": "República",
        "autor": "Platón",
        "editorial": "Gredos",
        "ano": 380,
        "columna": 2,
        "fila": 5,
        "isbn": "978-84-249-1027-3",
        "procedencia": "Donación",
        "categoria": "Filosofía",
        "comentarios": "Edición anotada",
        "f_revision": "",
    }


@pytest.fixture
def store_with_books(store, sample_book):
    """Store pre-loaded with several books for search/filter tests."""
    books = [
        {**sample_book},
        {
            "titulo": "Ética a Nicómaco",
            "autor": "Aristóteles",
            "editorial": "Gredos",
            "ano": 350,
            "columna": 2,
            "fila": 6,
            "isbn": "978-84-249-1028-0",
            "procedencia": "Compra",
            "categoria": "Filosofía",
            "comentarios": "",
            "f_revision": "01/01/2025",
        },
        {
            "titulo": "Meditaciones",
            "autor": "Marco Aurelio",
            "editorial": "Alianza",
            "ano": 180,
            "columna": 3,
            "fila": 1,
            "isbn": "978-84-206-3850-5",
            "procedencia": "Donación",
            "categoria": "Estoicismo",
            "comentarios": "Manuscrito incompleto",
            "f_revision": "",
        },
        {
            "titulo": "Enquiridión",
            "autor": "Epicteto",
            "editorial": "Gredos",
            "ano": 135,
            "columna": 3,
            "fila": 2,
            "isbn": "",
            "procedencia": "Legado",
            "categoria": "Estoicismo",
            "comentarios": "",
            "f_revision": "15/02/2024",
        },
        {
            "titulo": "Fedón",
            "autor": "Platón",
            "editorial": "Alianza",
            "ano": 370,
            "columna": 2,
            "fila": 7,
            "isbn": "978-84-206-3900-7",
            "procedencia": "Donación",
            "categoria": "Filosofía",
            "comentarios": "",
            "f_revision": "",
        },
    ]

    ids = []
    for b in books:
        ids.append(store.add(b))

    return store, ids
