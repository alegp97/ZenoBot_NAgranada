import os
from openai import OpenAI

class Speech2Text:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini-transcribe"):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def transcribe_file(self, path: str, language: str | None = None) -> str:
        # language opcional: "es" si quieres forzar español
        with open(path, "rb") as f:
            resp = self.client.audio.transcriptions.create(
                model=self.model,
                file=f,
                language=language,
            )
        return resp.text
