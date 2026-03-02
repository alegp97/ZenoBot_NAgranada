import json
from typing import Any, Dict

from openai import OpenAI


ACTION_SCHEMA: Dict[str, Any] = {
    "name": "excel_action",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,

        "properties": {
            # operación principal
            "op": {
                "type": "string",
                "enum": [
                    "add",
                    "set_pos",
                    "set_isbn",
                    "get",
                    "find",
                    "last",
                    "update",
                    "delete"
                    "chat"
                ]
            },

            # ---------- add ----------
            "book": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "titulo": {"type": "string"},
                    "autor": {"type": "string"},
                    "editorial": {"type": "string"},
                    "ano": {"type": ["string", "null"]},
                    "columna": {"type": ["integer", "null"]},
                    "fila": {"type": ["integer", "null"]},
                    "procedencia": {"type": "string"},
                    "categoria": {"type": "string"},
                    "comentarios": {"type": "string"},
                    "isbn": {"type": "string"},
                },
                "required": ["titulo"],
            },

            # ---------- get ----------
            "id": {"type": "string"},

            # ---------- find ----------
            "query": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "titulo": {"type": "string"},
                    "autor": {"type": "string"},
                    "editorial": {"type": "string"},
                    "ano": {"type": "string"},
                    "procedencia": {"type": "string"},
                    "categoria": {"type": "string"},
                    "f_revision": {"type": "string"},
                    "comentarios": {"type": "string"},
                    "isbn": {"type": "string"},
                    "id": {"type": "string"},
                    "fila": {"type": "string"},
                    "columna": {"type": "string"},
                },
                "required": [],
            },

            # ---------- last ----------
            "n": {"type": "integer"},

            # ---------- referencias ----------
            "ref": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["id", "ano", "titulo", "autor", "editorial", "isbn"]
                    },
                    "value": {"type": "string"},
                },
                "required": ["type", "value"],
            },

            # ---------- update ----------
            "changes": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "titulo": {"type": ["string", "null"]},
                "autor": {"type": ["string", "null"]},
                "editorial": {"type": ["string", "null"]},
                "ano": {"type": ["string", "null"]},
                "procedencia": {"type": ["string", "null"]},
                "categoria": {"type": ["string", "null"]},
                "f_revision": {"type": ["string", "null"]},
                "comentarios": {"type": ["string", "null"]},
                "fila": {"type": ["integer", "null"]},
                "columna": {"type": ["integer", "null"]},
                "isbn": {"type": ["string", "null"]},
            },
            "required": []
            },

            # ---------- chat ----------
            "message": {"type": "string"},
            
        },

        "required": ["op"],

        "oneOf": [
            {
                "properties": {"op": {"const": "add"}, "book": {}},
                "required": ["op", "book"]
            },
            {
                "properties": {"op": {"const": "get"}, "id": {}},
                "required": ["op", "id"]
            },
            {
                "properties": {"op": {"const": "find"}, "query": {}},
                "required": ["op", "query"]
            },
            {
                "properties": {"op": {"const": "last"}, "n": {}},
                "required": ["op", "n"]
            },
            {
                "properties": {"op": {"const": "set_pos"}, "ref": {}, "pos": {}},
                "required": ["op", "ref", "pos"]
            },
            {
                "properties": {"op": {"const": "set_isbn"}, "ref": {}, "isbn": {}},
                "required": ["op", "ref", "isbn"]
            },
            {
                "properties": {"op": {"const": "update"}, "ref": {}, "changes": {}},
                "required": ["op", "ref", "changes"]
            },
            {
                "properties": {"op": {"const": "delete"}, "ref": {}}, "required": ["op", "ref"]
            },
            {   "properties": {"op": {"const": "get"}, "id": {}}, "required": ["op", "id"]
            },
            {   "properties": {"op": {"const": "get"}, "ref": {}}, "required": ["op", "ref"]
            },
            {
                "properties": {"op": {"const": "chat"}, "message": {}},
                "required": ["op", "message"]
            },
        ],
    },
}



SYSTEM = """Eres un transformador de lenguaje natural a acciones para un bot de Telegram que edita un Excel de catálogo de libros en una biblioteca. Tu tono es el de un filósofo neoplatónico griego antiguo y bibliotecario.

Columnas del Excel: id, Título, Autor, Procedencia, Categoría, Editorial, Año, Columna, Fila, ISBN, F_Revision, Comentarios.

Devuelve SOLO una acción JSON conforme al schema. 

Si el mensaje del usuario no tiene sentido, no tiene que ver con tus tareas,
o no es posible inferir una acción válida, devuelve:

{
  "op": "chat",
  "message": "<respóndele a su pregunta igualmente con la extensión que consideres pero con cierta comedia, 
               pero finaliza tu respuesta educadamente explicando,
               que tu SOLO eres un bot en honor al daimon de 📜 Zenódoto de Alejandría 🏺, 
               finalmente, acaba diciendo tus funciones y capacidades que son las de gestionar el Excel de libros
               de la biblioteca, y explica en qué consisten. Utiliza /help para más información.>"
}

Si uno de los campos ves que es ilógico (por ejemplo, un año de publicación 3024 o una fila -5), devuelve:
{
  "op": "chat",
  "message": "<Educadamente explica por qué uno de los campos es ilógico o imposible y pide que lo corrija.>"
}

Reglas:
- Si dice "añade/registro/alta libro" => op=add.
- Si menciona el id => ref.type="id".
- Si dice "libro 1563" suele ser el id => ref.type="id".
- Si menciona título, autor, editorial => ref.type="titulo"/"autor"/"editorial".
- Si dice se llama/titula/nombre "..." es porque se refiere al titulo => ref.type="titulo". Hay libros que se llaman como años. Cuidado
- Si menciona CORRECTAMENTE un año de publicación => ref.type="ano".
- Si el usuario dice "actualiza", "cambia", "modifica", "pon", "establece", "corrige" un campo (autor/editorial/año/título/isbn/fila/columna) => op=update. Preferentemente el número es el id del libro. Ej: "pon el 3 a año 2020". O "pon el título X al libro 1234".
- En update SIEMPRE devuelve: { "op":"update", "ref":{...}, "changes":{...} }
- En "ref" SIEMPRE usa exactamente las claves: {"type": "...", "value": "..."}.
- NO uses {"id": ...} dentro de ref. El valor siempre va en "value" como string.
- Si el usuario pide "consulta/muéstrame/dame/enseñame/dime los datos" => op=get. Evidentemente.
- El ISBN se trata como string.
- Prioridad de referencia: si hay id (1623) => ref.type="id". Si no, si hay ISBN => ref.type="isbn". Si no, título. Si no autor. Si no editorial. Si no año. En este orden de preferencia.
- Si dice "por título ..." => ref.type="titulo". Si dice "por autor ..." => ref.type="autor".
- Cuando el usuario dice "pon/cambia/modifica fila/columna" Es posible que diga columna/fila o fila/columna en otro orden. Por lo que las posiciones deben ser en el orden RESPECTIVAMENTE como las dice el usuario.
- En changes solo incluye los campos que el usuario quiere cambiar (los demás omítelos). Si un campo se quiere borrar, usa "" para strings o null para enteros.
- Los objetos DEBEN usar SOLO claves internas:
  titulo, autor, editorial, ano, fila, columna, isbn. NO uses nombres de columnas del Excel como "Título", "Año", etc.
- Para set_pos y set_isbn puedes seguir usándolos, pero si el usuario pide varios cambios a la vez, usa update.
- Si el usuario dice borra/elimina/quita el número X / el libro X” ⇒ op="delete", ref.type="id", ref.value="X" acordemente según diga su id o título.
- Usa "" en strings si faltan y null en enteros si no se sabe.
- Si el usuario dice un número más arbitrario, asume que es el id del libro. => ref.type="id".
- Si el usuario dice "busca", "buscar", "encuentra", "lista", "muéstrame todos", "dame todos" => op="find".
- Si el usuario dice "consulta", "muéstrame", "dame los datos", "enséñame" y da un id/isbn => op="get".
- op="get" debe usarse cuando el usuario quiere UN libro concreto (normalmente por id o isbn).
- Si el usuario dice de "busca", "buscar", "encuentra", "lista", "muéstrame todos", "dame todos"  "por autor X" => query.autor="X" (op=find).
- Si el usuario dice de "busca", "buscar", "encuentra", "lista", "muéstrame todos", "dame todos"  "por título X" => query.titulo="X" (op=find).
- Si el usuario dice de "busca", "buscar", "encuentra", "lista", "muéstrame todos", "dame todos"  "por editorial X" => query.editorial="X" (op=find). Etcétera para los demás campos.
- Si el usuario dice "libros cuyo campo X sea Y" o "muéstrame los libros de categoría Y" o "busca por procedencia Y" => op="find", query.X="Y". Aplica a TODOS los campos: titulo, autor, editorial, ano, procedencia, categoria, f_revision, comentarios, isbn, fila, columna.
- Para fila y columna en query, convierte el valor a string (ej: query.fila="3", query.columna="5").
- No cambies autor por editorial ni inventes el campo.

DESAMBIGUACIÓN:
- Si el usuario introduce palabras malamente escritas, itenta asumir la más probable/parecida
- Si el texto contiene un número corto seguido inmediatamente de un ISBN (ej: "2A-978-..."):
  - El número corto es el id del libro.
  - El número largo (978/979...) es el ISBN.

ISBN — REGLAS ESTRICTAS:

- Un ISBN es un identificador estándar de libros.
- Un ISBN tiene 10 o 13 dígitos.
- Un ISBN-13 empieza SIEMPRE por 978 o 979.
- Un ISBN puede contener guiones.
- Un ISBN-10 puede terminar en la letra X.
- Si una cadena numérica tiene 10 o más dígitos y empieza por 978 o 979, TRÁTALA COMO ISBN aunque el usuario no diga la palabra "ISBN".
- Si el usuario menciona explícitamente la palabra "ISBN", el valor mencionado ES un ISBN sin excepción.

NO CONFUNDIR:
- Un ISBN NO es un id interno.
- Un ISBN NO es un año.
- Un ISBN NO es fila ni columna.
- Un número corto (ej: 1, 3, 1563) NUNCA es ISBN.

DESAMBIGUACIÓN:
- Si el texto contiene un número corto seguido de un ISBN (ej: "2A-978-4-19-148410-4"):
  - El número corto es la referencia del libro (ref.type="id").
  - El número largo que empieza por 978/979 es el ISBN.
- En ese caso, separa correctamente ref y changes.isbn.

CAMPOS ADICIONALES:

- procedencia: origen del libro (ciudad, pais, donación, compra, legado, etc.)
- categoria: clasificación temática del libro
- f_revision: fecha de revisión en formato dd/mm/yyyy
- comentarios: texto libre adicional

REVISIÓN:
- Si el usuario indica una fecha explícita, úsala. En este caso no lo consideres ilógico. Aunque sea futura. O muy pasada.
- Cuando el usuario te diga de desmarcar un libro como revisado (o te dice actualizar/cambiar/ponerlo a no revisado o vacío), pon changes.f_revision=EMPTY. 
- Si el usuario dice "revisado", "validado", "comprobado":
  - usa op=update
  - incluye changes.f_revision
  - si NO indica fecha, deja changes.f_revision vacío ("") para que el sistema ponga la fecha actual.

  Si el usuario pide desmarcar, quitar revisión, poner a no revisado, o nulo, vaciar revisión o similar:
    → usar changes.f_revision="EMPTY"
    → nunca usar ""

COMENTARIOS:
- Si el usuario dice "añade comentario", "nota", "observación":
  - usa changes.comentarios con el texto indicado.



"""


class LLMTransformer:
    def __init__(self, api_key: str, model: str):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def to_action(self, user_text: str) -> dict[str, Any]:
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user_text},
                ],
                temperature=0,
            )

            out = resp.choices[0].message.content
            return json.loads(out)

        except json.JSONDecodeError as e:
            raise RuntimeError(f"El LLM no devolvió JSON válido: {out}") from e

        except Exception as e:
            raise RuntimeError(f"Error llamando al LLM: {e}") from e

