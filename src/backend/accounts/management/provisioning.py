"""Shared command helpers; secrets are prompted, never command-line arguments."""
from getpass import GetPassWarning, getpass
import warnings

from django.core.management.base import CommandError


def hidden_password(prompt):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            return getpass(prompt)
    except (GetPassWarning, EOFError, KeyboardInterrupt):
        raise CommandError("Run this command in an interactive terminal with hidden password input. No provisioning was completed.") from None


def prompt_new_password():
    password = hidden_password("New account password: ")
    if password != hidden_password("Confirm new account password: "):
        raise CommandError("Passwords do not match. No account was created.")
    return password


def readable_error(exc):
    return CommandError("; ".join(exc.messages))
