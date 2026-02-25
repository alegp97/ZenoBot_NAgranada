import logging
import json
import os
import tempfile

from pathlib import Path
from typing import Any
from datetime import datetime
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from telegram_excel_bot.config import get_settings
from telegram_excel_bot.excel_store import ExcelStore
from telegram_excel_bot.llm_transformer import LLMTransformer
from telegram_excel_bot.speech2text import Speech2Text


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("catalogo-bot")



async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Unhandled exception", exc_info=context.error)

def allowed(update: Update, settings) -> bool:
    if settings.disable_auth:
        return True
    chat_id = update.effective_chat.id if update.effective_chat else None
    return chat_id is not None and chat_id in settings.allowed_chat_ids

async def send_long_message(update, text: str):
    MAX = 4000  # margen seguro bajo 4096

    if len(text) <= MAX:
        await update.message.reply_text(text, parse_mode="HTML")
        return

    parts = []
    current = ""

    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX:
            parts.append(current)
            current = line
        else:
            if current:
                current += "\n" + line
            else:
                current = line

    if current:
        parts.append(current)

    for p in parts:
        await update.message.reply_text(p, parse_mode="HTML")

def fmt_row(r: dict, prev: dict | None = None, changed_keys: set[str] | None = None) -> str:
    lines = [f"📚 <b>Id-{r.get('id')}</b>"]

    internal_to_rowkey = {
        "titulo": "Título",
        "autor": "Autor",
        "procedencia": "Procedencia",
        "categoria": "Categoría",
        "editorial": "Editorial",
        "ano": "Año",
        "columna": "Columna",
        "fila": "Fila",
        "isbn": "ISBN",
        "f_revision": "F_revision",
        "comentarios": "Comentarios",
    }

    rowkey_to_label = {
        "Título": "Título",
        "Autor": "Autor",
        "Procedencia": "Procedencia",
        "Categoría": "Categoría",
        "Editorial": "Editorial",
        "Año": "Año",
        "Columna": "Columna",
        "Fila": "Fila",
        "ISBN": "ISBN",
        "F_revision": "F. revisión",
        "Comentarios": "Comentarios",
    }

    def norm(v) -> str:
        if v in (None, "", "None"):
            return ""
        return str(v).strip()

    def disp(v) -> str:
        s = norm(v)
        return s if s != "" else "∅"   # si prefieres vacío literal, cambia "∅" por ""

    # Para saber qué rowkeys son candidatos a mostrar como diff
    changed_rowkeys: set[str] = set()
    if changed_keys:
        for k in changed_keys:
            rk = internal_to_rowkey.get(k)
            if rk:
                changed_rowkeys.add(rk)

    def add(rowkey: str):
        label = rowkey_to_label[rowkey]
        new_v = r.get(rowkey)

        # Si hay "prev" y este campo estaba en changes, intenta imprimir old->new si realmente cambió
        if prev is not None and rowkey in changed_rowkeys:
            old_v = prev.get(rowkey)
            if norm(old_v) != norm(new_v):
                lines.append(f"<b>{label}</b>: {disp(old_v)}  →  {disp(new_v)}")
                return

        # Si no cambió (o no aplica), imprimir normal si hay valor
        if norm(new_v) != "":
            lines.append(f"<b>{label}</b>: {norm(new_v)}")

    add("Título")
    add("Autor")
    add("Procedencia")
    add("Categoría")
    add("Editorial")
    add("Año")
    add("Columna")
    add("Fila")
    add("ISBN")
    add("F_revision")
    add("Comentarios")

    return "\n".join(lines)



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user

    name = user.first_name if user and user.first_name else "bibliotecario"

    msg = (
        f"¡👋 Saludos {name}!\n\n"
        "Soy ZenoBot, el asistente para catalogar libros en la biblioteca de NA Granada. 🏛️\n\n"
        "Escríbeme en lenguaje natural pero claro, por ejemplo:\n"
        "“pon la fila y la columna del libro 1463 a 3 - 4”\n\n"
        "ℹ️ Usa /help para ver más ejemplos."
    )

    # Si se usa allowlist, añade el chat_id al final
    if chat:
        msg += f"\n\n🔐 Tu chat_id es: `{chat.id}`"

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


def update_env_allowed_chat_ids(env_path: str, allowed_ids: set[int]) -> None:
    p = Path(env_path)

    if not p.exists():
        raise RuntimeError(f"No existe el .env en {env_path}")

    lines = p.read_text(encoding="utf-8").splitlines()

    new_value = ",".join(str(i) for i in sorted(allowed_ids))
    key = "ALLOWED_CHAT_IDS="

    found = False
    new_lines = []

    for line in lines:
        if line.strip().startswith(key):
            new_lines.append(f"{key}{new_value}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key}{new_value}")

    p.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


async def authorize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = context.application.bot_data["settings"]

    admin_id = settings.admin_chat_id
    if admin_id is None or update.effective_chat.id != admin_id:
        await update.message.reply_text("❌ No autorizado (solo admin).")
        return

    if not context.args:
        await update.message.reply_text("Uso: /authorize <chat_id>")
        return

    try:
        new_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("chat_id inválido.")
        return

    if new_id in settings.allowed_chat_ids:
        await update.message.reply_text("ℹ️ Ese chat_id ya estaba autorizado.")
        return

    settings.allowed_chat_ids.add(new_id)

    try:
        update_env_allowed_chat_ids(settings.env_path, settings.allowed_chat_ids)
    except Exception as e:
        await update.message.reply_text(f"❌ Error guardando en .env: {e}")
        return

    await update.message.reply_text(f"✅ chat_id {new_id} autorizado y persistido.")





async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_long_message(update,
        "🤖 <b>ZenoBot – Ayuda rápida</b>\n\n"

       "(Escribir /start para ver tu chatid y usarlo en allowlist si está habilitada la autenticación)\n"
       "(Escribir /authorize <chat_id> para que el admin autorice un nuevo chat_id)\n\n"

        "Los campos del catálogo son:\n"
        "• id: identificador único del libro\n"
        "• Título: título del libro\n"
        "• Autor: autor del libro\n"
        "• Editorial: editorial del libro\n"
        "• Año: año de publicación del libro\n"
        "• Columna: columna en la que se encuentra el libro en el catálogo\n"
        "• Fila: fila en la que se encuentra el libro en el catálogo\n"
        "• ISBN: número ISBN del libro\n"
        "• Procedencia: origen del libro (ciudad, país, donación, compra, legado, etc.)\n"
        "• Categoría: clasificación temática del libro\n"   
        "• F. revisión: fecha de la última revisión del libro\n"
        "• Comentarios: notas adicionales sobre el libro\n\n"

        "<b>Escribe en lenguaje natural</b>. Algunos ejemplos:\n\n"

        "📘 <b>Añadir libros</b>\n"
        "• añade un libro: Título=Manual de vida, Autor=Epicteto, Editorial=Gredos\n"
        "• registra libro con título Ética a Nicómaco y autor Aristóteles\n\n"

        "✏️ <b>Modificar datos (update)</b>\n"
        "• cambia la editorial del libro 6 a Gredos\n"
        "• pon la fila 6 y columna 8 al libro 6\n"
        "• actualiza la procedencia del 4 a Donación privada\n"
        "• añade comentario al libro 3: manuscrito incompleto\n"
        "• marca como revisado el libro 6\n"
        "• corrige la fecha de revisión del 6 a 12/03/2022\n\n"

        "🔍 <b>Buscar y consultar</b>\n"
        "• dame el 3756\n"
        "• busca por autor Platon\n"
        "• encuentra por editorial Nueva Acrópolis\n"
        "• busca por año 1950\n\n"

        "🗑️ <b>Eliminar</b>\n"
        "• borra el libro número 12\n\n"

        "📤 <b>Utilidades</b>\n"
        "• /export → envía el Excel actual\n\n"

        "ℹ️ <i> Si separas por frases las instrucciones, las ejecutaré una a una secuencialmente.</i>",
        parse_mode="HTML"
    )


async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    store: ExcelStore = context.application.bot_data["store"]
    if not allowed(update, settings):
        await update.message.reply_text("No autorizado.")
        return
    await update.message.reply_document(document=open(store.path, "rb"), filename=get_settings().excel_path)


def resolve_ref_to_id(store: ExcelStore, ref: dict[str, Any]) -> str | None:
    if not isinstance(ref, dict):
        return None

    rtype = (ref.get("type") or "").strip().lower()
    if not rtype:
        return None

    # value puede venir como "value", o mal como "id" cuando type=="id"
    raw_value = ref.get("value")
    if raw_value is None and rtype == "id":
        raw_value = ref.get("id")

    if raw_value is None:
        return None

    value = str(raw_value).strip()
    if not value:
        return None

    # --- resolver por id directamente ---
    if rtype == "id":
        return int(value)

    # --- resolver por búsqueda y exigir único ---
    if rtype == "isbn":
        res = store.find({"isbn": value}, limit=10)
    elif rtype == "ano":
        res = store.find({"ano": value}, limit=10)
    elif rtype == "titulo":
        res = store.find({"titulo": value}, limit=10)
    elif rtype == "autor":
        res = store.find({"autor": value}, limit=10)
    else:
        return None, []

    if len(res) == 1:
        rid = res[0].get("id")
        return str(rid).strip() if rid is not None else None

    return None


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    raw = update.message.text.strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    # Si hay varias líneas, ejecuta una a una
    if len(lines) > 1:
        for i, ln in enumerate(lines, start=1):
            await send_long_message(update, f"➡️ ({i}/{len(lines)}) {ln}")
            await process_natural_language(update, context, ln)
        return

    # Caso normal: una sola línea
    await process_natural_language(update, context, raw)


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    stt: Speech2Text = context.application.bot_data["stt"]

    if not update.message:
        return
    if not allowed(update, settings):
        await send_long_message(update, "No autorizado. Pásame tu chat_id para allowlist.")
        return

    # Detecta voice (nota de voz) o audio (archivo)
    tg_file = None
    suffix = ".ogg"

    if update.message.voice:
        tg_file = await update.message.voice.get_file()
        # voice suele ser OGG/OPUS
        suffix = ".ogg"
    elif update.message.audio:
        tg_file = await update.message.audio.get_file()
        suffix = ".mp3"
    else:
        await update.message.reply_text("No veo un audio/nota de voz.")
        return

    # Descarga a temporal
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name

    try:
        await tg_file.download_to_drive(custom_path=tmp_path)  # PTB v21+ :contentReference[oaicite:3]{index=3}
        transcript = stt.transcribe_file(tmp_path, language="es")
        transcript = (transcript or "").strip()

        if not transcript:
            await send_long_message(update, "No pude transcribir el audio.")
            return

        await send_long_message(update, f"📝 Transcripción:\n{transcript}")

        # Reusa el mismo flujo de NL→acción→excel
        try:
            await process_natural_language(update, context, transcript)
        except Exception as e:
            await send_long_message(update, f"❌ Falló process_natural_language: {e}")


    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass



async def process_natural_language(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    print("🔍 Procesando NL:", text)
    settings = context.application.bot_data["settings"]
    store: ExcelStore = context.application.bot_data["store"]
    llm: LLMTransformer = context.application.bot_data["llm"]

    if not text or not text.strip():
        print("No hay texto a procesar")
        return

    if not allowed(update, settings):
        await update.message.reply_text("No autorizado. Pásame tu chat_id para allowlist.")
        return
    
    try:
        action = llm.to_action(text)
        op = action["op"]

        log.info("🧠 LLM ACTION:\n%s", json.dumps(action, indent=2, ensure_ascii=False))

        if op == "chat":
            await send_long_message(update, action["message"])
            return

        if op == "add":
            book = action.get("book")

            # 1) Si no viene "book", intenta con "data"
            if not isinstance(book, dict):
                d = action.get("data")
                if isinstance(d, dict):
                    # data con claves internas (nuevo)
                    if "titulo" in d:
                        book = d
                    # data con cabeceras Excel (viejo)
                    elif "Título" in d:
                        book = {
                            "titulo": (d.get("Título") or "").strip(),
                            "autor": (d.get("Autor") or "").strip(),
                            "procedencia": (d.get("Procedencia") or "").strip(),
                            "categoria": (d.get("Categoría") or d.get("Categoria") or "").strip(),
                            "editorial": (d.get("Editorial") or "").strip(),
                            "ano": d.get("Año"),
                            "columna": d.get("Columna"),
                            "fila": d.get("Fila"),
                            "isbn": (d.get("ISBN") or "").strip(),
                            "f_revision": (d.get("F_revision") or d.get("F_revisión") or "").strip(),
                            "comentarios": (d.get("Comentarios") or "").strip(),
                        }
                    else:
                        book = None
                else:
                    # 2) compat campos raíz
                    book = {
                        "titulo": str(action.get("titulo") or "").strip(),
                        "autor": str(action.get("autor") or "").strip(),
                        "procedencia": str(action.get("procedencia") or "").strip(),
                        "categoria": str(action.get("categoria") or "").strip(),
                        "editorial": str(action.get("editorial") or "").strip(),
                        "ano": action.get("ano"),
                        "columna": action.get("columna"),
                        "fila": action.get("fila"),
                        "isbn": str(action.get("isbn") or "").strip(),
                        "f_revision": str(action.get("f_revision") or "").strip(),
                        "comentarios": str(action.get("comentarios") or "").strip(),
                    }

            if not isinstance(book, dict):
                await update.message.reply_text("No entiendo los datos del alta (book/data).")
                return

            # Requisito mínimo
            if not str(book.get("titulo") or "").strip():
                await update.message.reply_text("Falta Título para dar de alta.")
                return

            # Normaliza al modelo interno completo
            book_norm = {
                "titulo": str(book.get("titulo") or "").strip(),
                "autor": str(book.get("autor") or "").strip(),
                "procedencia": str(book.get("procedencia") or "").strip(),
                "categoria": str(book.get("categoria") or "").strip(),
                "editorial": str(book.get("editorial") or "").strip(),
                "ano": book.get("ano"),
                "columna": book.get("columna"),
                "fila": book.get("fila"),
                "isbn": str(book.get("isbn") or "").strip(),
                "f_revision": str(book.get("f_revision") or "").strip(),
                "comentarios": str(book.get("comentarios") or "").strip(),
            }

            new_id = store.add(book_norm)
            saved = store.get_by_id(new_id)
            await send_long_message(update,
                "✅📝 Añadido\n\n" + fmt_row(saved or {"id": new_id})
            )
            return



        if op == "get":
            ref = action.get("ref")
            if not ref:
                await send_long_message(update, "No puedo identificar el libro. Indica un id o una referencia clara.")
                return

            book_id = resolve_ref_to_id(store, ref)
            if not book_id:
                await send_long_message(update,
                    "No pude identificar un único libro con esa referencia.\n"
                    "Dame el id (ej: 3659) o más precisión."
                )
                return

            row = store.get_by_id(book_id)
            if not row:
                await send_long_message(update, "No encontrado.")
            else:
                await send_long_message(update, fmt_row(row))
            return


        if op == "find":
            q = action.get("query") or {}

            criteria = {
                "id": (q.get("id") or "").strip(),
                "titulo": (q.get("titulo") or "").strip(),
                "autor": (q.get("autor") or "").strip(),
                "editorial": (q.get("editorial") or "").strip(),
                "ano": str(q.get("ano") or "").strip(),
                "isbn": (q.get("isbn") or "").strip(),
            }
            criteria = {k: v for k, v in criteria.items() if v}
            res = store.find(criteria, limit=20)
            if not res:
                await send_long_message(update, "Sin resultados.")
                return
            lines = [f"• <code>{r['id']}</code> — {r.get('Título','')} ({r.get('Autor','')})" for r in res]
            await send_long_message(update, "\n".join(lines))
            return

        if op == "last":
            n = int(action["n"])
            res = store.last(n)
            if not res:
                await send_long_message(update, "Sin registros.")
                return
            lines = [f"• <code>{r['id']}</code> — {r.get('Título','')} ({r.get('Autor','')})" for r in res]
            await send_long_message(update, "\n".join(lines))
            return

        if op == "set_pos":
            ref = action.get("ref")
            pos = action.get("pos")

            # compat: si viene fila/columna en raíz
            if not isinstance(pos, dict):
                pos = {
                    "fila": action.get("fila"),
                    "columna": action.get("columna"),
                }

            if not ref:
                await send_long_message(update, "No puedo identificar el libro. Dame un id o referencia.")
                return
            if pos.get("fila") is None or pos.get("columna") is None:
                await send_long_message(update, "Me falta fila y/o columna. Ej: 'pon la fila 3 y columna 4 del libro 2'")
                return

            book_id = resolve_ref_to_id(store, ref)
            if not book_id:
                await send_long_message(update, 
                    "No pude identificar un único libro con esa referencia.\n"
                    "Dame el id o más precisión."
                )
                return

            ok = store.set_pos(book_id, fila=int(pos["fila"]), columna=int(pos["columna"]))
            if not ok:
                await send_long_message(update, "No encontrado para actualizar posición.")
                return

            row = store.get_by_id(book_id)
            await send_long_message(update, "✅ Posición actualizada\n\n" + fmt_row(row or {"id": book_id}))
            return


        if op == "set_isbn":
            ref = action["ref"]
            isbn = action["isbn"].strip()
            if not isbn:
                await send_long_message(update, "ISBN vacío.")
                return
            book_id = resolve_ref_to_id(store, ref)
            if not book_id:
                await send_long_message(update, 
                    "No pude identificar un único libro con esa referencia.\n"
                    "Dame el id (ej: 1453) o más precisión."
                )
                return
            ok = store.set_isbn(book_id, isbn=isbn)
            if not ok:
                await send_long_message(update, "No encontrado para actualizar ISBN.")
                return
            row = store.get_by_id(book_id)
            await send_long_message(update, "✅ ISBN actualizado\n\n" + fmt_row(row or {"id": book_id}))
            return
        
        if op == "update":
            ref = action.get("ref")
            changes = action.get("changes") or {}

            if not ref:
                await send_long_message(update, "No puedo identificar el libro. Dame un id o una referencia.")
                return
            if not isinstance(changes, dict) or not changes:
                await send_long_message(update, "No veo cambios a aplicar. Dime qué campo quieres actualizar.")
                return

            book_id = resolve_ref_to_id(store, ref)
            row_before = store.get_by_id(book_id)

            if not book_id:
                await send_long_message(update, 
                    "No pude identificar un único libro con esa referencia.\n"
                    "Dame el id (ej: 1452) o más precisión."
                )
                return
            
            if "f_revision" in changes:
                v = changes["f_revision"]

                if v == "EMPTY": # Desmarcar como no revisado → vacío sin fecha
                    changes["f_revision"] = ""

                else:
                    if isinstance(v, str):
                        v_norm = v.strip().lower()
                    else:
                        v_norm = v

                    # Marcar como revisado sin fecha explícita → HOY
                    if v_norm in ("", "revisado", "true", True, "sí", "si"):
                        changes["f_revision"] = datetime.now().strftime("%d/%m/%Y")
                    # Fecha explícita → se respeta
                    else:
                        changes["f_revision"] = v

            ok = store.update_fields(book_id, changes)
            if not ok:
                await send_long_message(update, "No encontrado para actualizar.")
                return

            row_after = store.get_by_id(book_id)
            await send_long_message(update, 
                "✅ Actualizado\n\n" + fmt_row(row_after or {"id": book_id}, prev=row_before, changed_keys=set(changes.keys()))
            )
            return

        if op == "get":
            # 1) Si viene id directo => un libro
            book_id = (action.get("id") or "").strip()
            if book_id:
                row = store.get_by_id(book_id)
                if not row:
                    await send_long_message(update, "No encontrado.")
                else:
                    await send_long_message(update, fmt_row(row))
                return

            ref = action.get("ref")
            if not ref:
                await send_long_message(update, "No entiendo qué libro consultar. Prueba con id, ISBN, título o autor.")
                return

            rtype = ref.get("type")
            value = (ref.get("value") or "").strip()

            # Si la referencia NO es id/isbn, entonces es una consulta tipo búsqueda => lista resultados
            if rtype in {"autor", "titulo", "editorial", "ano"}:
                # Mapea ref -> criteria interna del store
                criteria = {}
                if rtype == "autor":
                    criteria["autor"] = value
                elif rtype == "titulo":
                    criteria["titulo"] = value
                elif rtype == "editorial":
                    criteria["editorial"] = value
                elif rtype == "ano":
                    criteria["ano"] = value

                res = store.find(criteria, limit=20)
                if not res:
                    await send_long_message(update, "No hay resultados.")
                    return

                # Si hay 1 solo, puedes mostrar ficha completa
                if len(res) == 1:
                    await send_long_message(update, fmt_row(res[0]))
                    return

                # Si hay varios, lista
                lines = [f"Encontré {len(res)} resultados:\n"]
                for r in res[:20]:
                    lines.append(f"• <code>{r['id']}</code> — {r.get('Título','')} ({r.get('Autor','')})")
                await send_long_message(update, "\n".join(lines))
                return

            # Si ref es id/isbn => intentar resolver a único y mostrar ficha
            resolved_id, candidates = resolve_ref_to_id(store, ref)
            if resolved_id:
                row = store.get_by_id(resolved_id)
                if not row:
                    await send_long_message(update, "No encontrado.")
                else:
                    await send_long_message(update, fmt_row(row))
                return

            # ISBN duplicado o id no encontrado
            if not candidates:
                await send_long_message(update, "No hay resultados.")
                return

            lines = ["Encontré varios. Indícame el id exacto, por ejemplo: 723\n"]
            for r in candidates[:10]:
                lines.append(f"• <code>{r['id']}</code> — {r.get('Título','')} ({r.get('Autor','')})")
            await send_long_message(update, "\n".join(lines))
            return


        
        if op == "delete":
            ref = action.get("ref")
            if not ref:
                await send_long_message(update, "Dime qué libro borrar (por id).")
                return

            book_id = resolve_ref_to_id(store, ref)
            if book_id is None:
                await send_long_message(update, "No pude identificar ese libro para borrarlo.")
                return

            ok = store.delete_and_compact(book_id)
            if not ok:
                await send_long_message(update, "No encontrado para borrar.")
                return

            await send_long_message(update, f"🗑️ Borrado el libro {book_id} y compactado el catálogo.")
            return



        await send_long_message(update, f"Operación no soportada: {op}")

    except Exception as e:
        log.exception("Error")
        await send_long_message(update, f"❌ Error: {e}")



##################################################################################################
####################################### MAIN  ####################################################
##################################################################################################   

def main() -> None:
    s = get_settings()
    print("📄 Excel en uso:", s.excel_path)
    print("📑 Hoja en uso:", s.excel_sheet)

    store = ExcelStore(s.excel_path, s.excel_sheet)
    llm = LLMTransformer(api_key=s.openai_api_key, model=s.openai_model)

    app = Application.builder().token(s.telegram_token).build()
    app.bot_data["settings"] = s
    app.bot_data["store"] = store
    app.bot_data["llm"] = llm

    stt = Speech2Text(api_key=s.openai_api_key, model="gpt-4o-mini-transcribe")
    app.bot_data["stt"] = stt


    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CommandHandler("authorize", authorize))
    app.add_handler(MessageHandler(filters.TEXT, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_audio))
    app.add_error_handler(error_handler)


    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
