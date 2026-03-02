"""
Tests for telegram_excel_bot.llm_transformer — LLMTransformer.
We mock the OpenAI client so no real API key or network is required.
"""
import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from telegram_excel_bot.llm_transformer import LLMTransformer, SYSTEM, ACTION_SCHEMA


# ═══════════════════════════════════════════════════════════════
# SYSTEM prompt
# ═══════════════════════════════════════════════════════════════


class TestSystemPrompt:
    """Verify the system prompt contains essential keywords."""

    def test_mentions_all_ops(self):
        for op in ["add", "get", "find", "update", "delete", "chat"]:
            assert op in SYSTEM

    def test_mentions_new_filter_fields(self):
        for field in ["procedencia", "categoria", "f_revision", "comentarios"]:
            assert field in SYSTEM.lower()

    def test_mentions_fila_columna_in_query(self):
        assert "query.fila" in SYSTEM or "fila" in SYSTEM
        assert "query.columna" in SYSTEM or "columna" in SYSTEM


# ═══════════════════════════════════════════════════════════════
# ACTION_SCHEMA
# ═══════════════════════════════════════════════════════════════


class TestSchema:
    def test_query_has_all_fields(self):
        query_props = ACTION_SCHEMA["schema"]["properties"]["query"]["properties"]
        expected = [
            "titulo", "autor", "editorial", "ano",
            "procedencia", "categoria", "f_revision",
            "comentarios", "isbn", "id", "fila", "columna",
        ]
        for f in expected:
            assert f in query_props, f"Missing query field: {f}"

    def test_changes_has_all_fields(self):
        changes_props = ACTION_SCHEMA["schema"]["properties"]["changes"]["properties"]
        expected = [
            "titulo", "autor", "editorial", "ano",
            "procedencia", "categoria", "f_revision",
            "comentarios", "isbn", "fila", "columna",
        ]
        for f in expected:
            assert f in changes_props, f"Missing changes field: {f}"

    def test_ops_enum(self):
        ops = ACTION_SCHEMA["schema"]["properties"]["op"]["enum"]
        for op in ["add", "get", "find", "last", "update"]:
            assert op in ops, f"Missing op: {op}"


# ═══════════════════════════════════════════════════════════════
# to_action with mocked OpenAI
# ═══════════════════════════════════════════════════════════════


class TestToAction:
    def _make_llm(self, response_json: dict) -> LLMTransformer:
        """Return an LLMTransformer whose OpenAI call returns the given JSON."""
        llm = LLMTransformer(api_key="fake-key", model="gpt-test")

        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(response_json, ensure_ascii=False)
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]

        llm.client = MagicMock()
        llm.client.chat.completions.create.return_value = mock_resp
        return llm

    def test_add_action(self):
        llm = self._make_llm({
            "op": "add",
            "book": {"titulo": "República", "autor": "Platón"}
        })
        action = llm.to_action("añade libro República de Platón")
        assert action["op"] == "add"
        assert action["book"]["titulo"] == "República"

    def test_find_action_with_categoria(self):
        llm = self._make_llm({
            "op": "find",
            "query": {"categoria": "Filosofía"}
        })
        action = llm.to_action("busca por categoría Filosofía")
        assert action["op"] == "find"
        assert action["query"]["categoria"] == "Filosofía"

    def test_find_action_with_procedencia(self):
        llm = self._make_llm({
            "op": "find",
            "query": {"procedencia": "Donación"}
        })
        action = llm.to_action("busca por procedencia Donación")
        assert action["op"] == "find"
        assert action["query"]["procedencia"] == "Donación"

    def test_get_action(self):
        llm = self._make_llm({
            "op": "get",
            "ref": {"type": "id", "value": "42"}
        })
        action = llm.to_action("dame el 42")
        assert action["op"] == "get"

    def test_update_action(self):
        llm = self._make_llm({
            "op": "update",
            "ref": {"type": "id", "value": "5"},
            "changes": {"editorial": "Gredos"}
        })
        action = llm.to_action("cambia editorial del 5 a Gredos")
        assert action["op"] == "update"
        assert action["changes"]["editorial"] == "Gredos"

    def test_chat_action(self):
        llm = self._make_llm({
            "op": "chat",
            "message": "Saludos, mortal."
        })
        action = llm.to_action("hola")
        assert action["op"] == "chat"
        assert "Saludos" in action["message"]

    def test_delete_action(self):
        llm = self._make_llm({
            "op": "delete",
            "ref": {"type": "id", "value": "12"}
        })
        action = llm.to_action("borra el 12")
        assert action["op"] == "delete"

    def test_invalid_json_raises(self):
        llm = LLMTransformer(api_key="fake-key", model="gpt-test")
        mock_choice = MagicMock()
        mock_choice.message.content = "not json"
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        llm.client = MagicMock()
        llm.client.chat.completions.create.return_value = mock_resp

        with pytest.raises(RuntimeError, match="JSON"):
            llm.to_action("whatever")

    def test_system_prompt_is_passed(self):
        """Verify the system prompt is actually sent to the API."""
        llm = self._make_llm({"op": "chat", "message": "ok"})
        llm.to_action("hola")

        call_args = llm.client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        system_msg = [m for m in messages if m["role"] == "system"]
        assert len(system_msg) == 1
        assert "Zenódoto" in system_msg[0]["content"]

    def test_find_with_fila_columna(self):
        llm = self._make_llm({
            "op": "find",
            "query": {"fila": "3", "columna": "5"}
        })
        action = llm.to_action("busca libros en fila 3 columna 5")
        assert action["query"]["fila"] == "3"
        assert action["query"]["columna"] == "5"
