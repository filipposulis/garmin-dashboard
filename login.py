"""Login una tantum a Garmin Connect.

Esegui:  .venv/bin/python login.py
Salva i token in ~/.garminconnect così la dashboard non ha bisogno della password.
I token durano circa un anno; se scadono, rilancia questo script.
"""
import getpass
import os

from garminconnect import Garmin

TOKENSTORE = os.path.expanduser(os.getenv("GARMINTOKENS", "~/.garminconnect"))


def main() -> None:
    email = input("Email Garmin: ").strip()
    password = getpass.getpass("Password Garmin: ")

    garmin = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("Codice MFA: ").strip(),
    )
    garmin.login(TOKENSTORE)
    garmin.client.dump(TOKENSTORE)  # la libreria lo fa già, ma ignora gli errori in silenzio
    print(f"OK, token salvati in {TOKENSTORE}")
    print(f"Connesso come: {garmin.get_full_name()}")


if __name__ == "__main__":
    main()
