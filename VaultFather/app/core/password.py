"""
Archive password handling.

Two modes, matching the Settings idea: a fixed password reused for every
movie, or a fresh random one generated per archive. Random passwords use
`secrets` (not `random`) since these are the only thing standing between
the archive contents and anyone who gets hold of the file.
"""

import secrets
import string

# Avoid characters that are awkward in filenames, shells, or easy to
# misread (quotes, backslash, and visually ambiguous 0/O/1/l/I are kept
# in — Telegram/7z don't care, and cutting them just weakens the space —
# but we do keep it to safe, printable ASCII.
_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"


def generate_random_password(length: int = 20) -> str:
    if length < 8:
        raise ValueError("Password length should be at least 8 characters.")
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def resolve_password(config: dict) -> str:
    """
    Given the app config dict, returns the password to use for the next
    archive: the fixed one if that mode is selected (falling back to a
    random one if it's somehow empty), otherwise a fresh random password.
    """
    if config.get("password_mode") == "fixed":
        fixed = config.get("fixed_password") or ""
        if fixed.strip():
            return fixed
    return generate_random_password()
