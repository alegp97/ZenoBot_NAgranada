import os
from pathlib import Path

from dotenv import load_dotenv

# 1) Base dir = carpeta donde está zenobot.py
BASE_DIR = Path(__file__).resolve().parent

# 2) Carga .env desde BASE_DIR 
env_path = BASE_DIR / "telegram_excel_bot" / ".env"
load_dotenv(dotenv_path=env_path)

# 3) Excel: por defecto al lado de zenobot.py
default_excel = BASE_DIR / "catalogo.xlsx"

excel_env = os.getenv("EXCEL_PATH", "").strip()
if not excel_env:
    print("Usando EXCEL_PATH por defecto:", default_excel)
    # No hay EXCEL_PATH -> usa el default al lado de zenobot.py
    os.environ["EXCEL_PATH"] = str(default_excel)
else:
    print("Usando EXCEL_PATH de .env:", excel_env)
    # Si EXCEL_PATH es relativo, hazlo relativo a BASE_DIR
    p = Path(excel_env)
    if not p.is_absolute():
        os.environ["EXCEL_PATH"] = str((BASE_DIR / p).resolve())

# 4) Arranca el bot real
from telegram_excel_bot.bot import main

if __name__ == "__main__":
    main()
