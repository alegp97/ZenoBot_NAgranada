"""
Tests for telegram_excel_bot.bot — handler logic.
Uses mocks instead of real Telegram / LLM connections.
"""
import json
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from telegram_excel_bot.bot import (
    fmt_row,
    resolve_ref_to_id,
    send_long_message,
    allowed,
    process_natural_language,
)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


def _make_update(text="", chat_id=123):
    """Build a minimal mock Telegram Update."""
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.message.reply_document = AsyncMock()
    return update


def _make_context(store, llm_action=None, disable_auth=True):
    """Build a minimal mock context with store + optional llm mock."""
    ctx = MagicMock()

    settings = MagicMock()
    settings.disable_auth = disable_auth
    settings.allowed_chat_ids = {123}

    ctx.application.bot_data = {
        "settings": settings,
        "store": store,
    }

    if llm_action is not None:
        llm = MagicMock()
        llm.to_action.return_value = llm_action
        ctx.application.bot_data["llm"] = llm

    return ctx


# ═══════════════════════════════════════════════════════════════
# fmt_row
# ═══════════════════════════════════════════════════════════════


class TestFmtRow:
    def test_basic_output(self):
        row = {
            "id": 1,
            "Título": "República",
            "Autor": "Platón",
            "Procedencia": "Donación",
            "Categoría": "Filosofía",
            "Editorial": "Gredos",
            "Año": 380,
            "Columna": 2,
            "Fila": 5,
            "ISBN": "978-84-249-1027-3",
            "F_revision": "",
            "Comentarios": "",
        }
        result = fmt_row(row)
        assert "Id-1" in result
        assert "República" in result
        assert "Platón" in result
        assert "Gredos" in result

    def test_with_changes(self):
        prev = {"id": 1, "Título": "Old", "Autor": "A", "Procedencia": "", "Categoría": "", "Editorial": "", "Año": None, "Columna": None, "Fila": None, "ISBN": "", "F_revision": "", "Comentarios": ""}
        curr = {"id": 1, "Título": "New", "Autor": "A", "Procedencia": "", "Categoría": "", "Editorial": "", "Año": None, "Columna": None, "Fila": None, "ISBN": "", "F_revision": "", "Comentarios": ""}
        result = fmt_row(curr, prev=prev, changed_keys={"titulo"})
        assert "→" in result  # changed indicator

    def test_empty_fields_show_nothing(self):
        row = {"id": 1, "Título": "Test", "Autor": "", "Procedencia": None, "Categoría": "None", "Editorial": "", "Año": None, "Columna": None, "Fila": None, "ISBN": "", "F_revision": "", "Comentarios": ""}
        result = fmt_row(row)
        assert "Autor" not in result  # empty → omitted


# ═══════════════════════════════════════════════════════════════
# allowed()
# ═══════════════════════════════════════════════════════════════


class TestAllowed:
    def test_allowed_when_disabled(self):
        update = _make_update(chat_id=999)
        settings = MagicMock()
        settings.disable_auth = True
        assert allowed(update, settings)

    def test_allowed_in_allowlist(self):
        update = _make_update(chat_id=123)
        settings = MagicMock()
        settings.disable_auth = False
        settings.allowed_chat_ids = {123, 456}
        assert allowed(update, settings)

    def test_not_allowed(self):
        update = _make_update(chat_id=999)
        settings = MagicMock()
        settings.disable_auth = False
        settings.allowed_chat_ids = {123}
        assert not allowed(update, settings)


# ═══════════════════════════════════════════════════════════════
# send_long_message
# ═══════════════════════════════════════════════════════════════


class TestSendLongMessage:
    @pytest.mark.asyncio
    async def test_short_message(self):
        update = _make_update()
        await send_long_message(update, "Hola")
        update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_long_message_splits(self):
        update = _make_update()
        text = "A" * 5000  # exceeds 4000 limit
        await send_long_message(update, text)
        assert update.message.reply_text.call_count >= 2


# ═══════════════════════════════════════════════════════════════
# resolve_ref_to_id
# ═══════════════════════════════════════════════════════════════


class TestResolveRef:
    def test_ref_by_id(self, store_with_books):
        store, ids = store_with_books
        result = resolve_ref_to_id(store, {"type": "id", "value": str(ids[0])})
        assert int(result) == int(ids[0])

    def test_ref_by_titulo_unique(self, store_with_books):
        store, _ = store_with_books
        result = resolve_ref_to_id(store, {"type": "titulo", "value": "República"})
        assert result is not None

    def test_ref_by_titulo_ambiguous(self, store_with_books):
        """Two books by Platón → cannot resolve."""
        store, _ = store_with_books
        result = resolve_ref_to_id(store, {"type": "autor", "value": "Platón"})
        assert result is None

    def test_ref_invalid(self, store_with_books):
        store, _ = store_with_books
        result = resolve_ref_to_id(store, {"type": "autor", "value": "ZZZZZ"})
        assert result is None

    def test_ref_empty(self, store):
        assert resolve_ref_to_id(store, None) is None
        assert resolve_ref_to_id(store, {}) is None
        assert resolve_ref_to_id(store, "not a dict") is None


# ═══════════════════════════════════════════════════════════════
# process_natural_language — op=find (integration test with store)
# ═══════════════════════════════════════════════════════════════


class TestProcessNLFind:
    @pytest.mark.asyncio
    async def test_find_by_categoria(self, store_with_books):
        store, _ = store_with_books
        action = {"op": "find", "query": {"categoria": "Filosofía"}}
        ctx = _make_context(store, llm_action=action)
        update = _make_update()
        await process_natural_language(update, ctx, "busca por categoría Filosofía")
        update.message.reply_text.assert_called()
        text_sent = update.message.reply_text.call_args_list[0][0][0]
        assert "3 resultado" in text_sent

    @pytest.mark.asyncio
    async def test_find_by_procedencia(self, store_with_books):
        store, _ = store_with_books
        action = {"op": "find", "query": {"procedencia": "Donación"}}
        ctx = _make_context(store, llm_action=action)
        update = _make_update()
        await process_natural_language(update, ctx, "busca por procedencia Donación")
        update.message.reply_text.assert_called()
        text_sent = update.message.reply_text.call_args_list[0][0][0]
        assert "3 resultado" in text_sent

    @pytest.mark.asyncio
    async def test_find_by_comentarios(self, store_with_books):
        store, _ = store_with_books
        action = {"op": "find", "query": {"comentarios": "manuscrito"}}
        ctx = _make_context(store, llm_action=action)
        update = _make_update()
        await process_natural_language(update, ctx, "busca por comentarios manuscrito")
        update.message.reply_text.assert_called()
        text_sent = update.message.reply_text.call_args_list[0][0][0]
        assert "1 resultado" in text_sent

    @pytest.mark.asyncio
    async def test_find_no_results(self, store_with_books):
        store, _ = store_with_books
        action = {"op": "find", "query": {"titulo": "ZZZZZ"}}
        ctx = _make_context(store, llm_action=action)
        update = _make_update()
        await process_natural_language(update, ctx, "busca título ZZZZZ")
        text_sent = update.message.reply_text.call_args_list[0][0][0]
        assert "Sin resultados" in text_sent


# ═══════════════════════════════════════════════════════════════
# process_natural_language — op=add
# ═══════════════════════════════════════════════════════════════


class TestProcessNLAdd:
    @pytest.mark.asyncio
    async def test_add_book(self, store):
        action = {
            "op": "add",
            "book": {
                "titulo": "Nuevo Libro",
                "autor": "Nuevo Autor",
            }
        }
        ctx = _make_context(store, llm_action=action)
        update = _make_update()
        await process_natural_language(update, ctx, "añade libro Nuevo Libro de Nuevo Autor")
        text_sent = update.message.reply_text.call_args_list[0][0][0]
        assert "Añadido" in text_sent

    @pytest.mark.asyncio
    async def test_add_missing_titulo(self, store):
        action = {
            "op": "add",
            "book": {"titulo": "", "autor": "Alguien"}
        }
        ctx = _make_context(store, llm_action=action)
        update = _make_update()
        await process_natural_language(update, ctx, "añade libro sin título")
        text_sent = update.message.reply_text.call_args_list[0][0][0]
        assert "Falta Título" in text_sent


# ═══════════════════════════════════════════════════════════════
# process_natural_language — op=chat
# ═══════════════════════════════════════════════════════════════


class TestProcessNLChat:
    @pytest.mark.asyncio
    async def test_chat_passthrough(self, store):
        action = {"op": "chat", "message": "Saludos, mortal."}
        ctx = _make_context(store, llm_action=action)
        update = _make_update()
        await process_natural_language(update, ctx, "hola bot")
        text_sent = update.message.reply_text.call_args_list[0][0][0]
        assert "Saludos, mortal" in text_sent


# ═══════════════════════════════════════════════════════════════
# process_natural_language — op=update
# ═══════════════════════════════════════════════════════════════


class TestProcessNLUpdate:
    @pytest.mark.asyncio
    async def test_update_field(self, store_with_books):
        store, ids = store_with_books
        action = {
            "op": "update",
            "ref": {"type": "id", "value": str(ids[0])},
            "changes": {"editorial": "Penguin"},
        }
        ctx = _make_context(store, llm_action=action)
        update = _make_update()
        await process_natural_language(update, ctx, "cambia editorial del 1 a Penguin")
        text_sent = update.message.reply_text.call_args_list[0][0][0]
        assert "Actualizado" in text_sent

    @pytest.mark.asyncio
    async def test_update_not_found(self, store):
        action = {
            "op": "update",
            "ref": {"type": "id", "value": "9999"},
            "changes": {"titulo": "X"},
        }
        ctx = _make_context(store, llm_action=action)
        update = _make_update()
        await process_natural_language(update, ctx, "cambia título del 9999")
        text_sent = update.message.reply_text.call_args_list[0][0][0]
        assert "No" in text_sent  # "No encontrado" or "No pude identificar"


# ═══════════════════════════════════════════════════════════════
# process_natural_language — op=delete
# ═══════════════════════════════════════════════════════════════


class TestProcessNLDelete:
    @pytest.mark.asyncio
    async def test_delete_book(self, store_with_books):
        store, ids = store_with_books
        action = {
            "op": "delete",
            "ref": {"type": "id", "value": str(ids[0])},
        }
        ctx = _make_context(store, llm_action=action)
        update = _make_update()
        await process_natural_language(update, ctx, "borra el libro 1")
        text_sent = update.message.reply_text.call_args_list[0][0][0]
        assert "Borrado" in text_sent


# ═══════════════════════════════════════════════════════════════
# Authorization
# ═══════════════════════════════════════════════════════════════


class TestAuth:
    @pytest.mark.asyncio
    async def test_unauthorized_user(self, store):
        action = {"op": "chat", "message": "hola"}
        ctx = _make_context(store, llm_action=action, disable_auth=False)
        ctx.application.bot_data["settings"].allowed_chat_ids = {456}
        update = _make_update(chat_id=999)
        await process_natural_language(update, ctx, "hola")
        text_sent = update.message.reply_text.call_args_list[0][0][0]
        assert "No autorizado" in text_sent
