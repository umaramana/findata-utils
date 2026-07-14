"""
OAuth user-credential auth for the report_service container.

Unlike service_account_auth.py, these credentials belong to a real Google
account (not a service account), so Drive uploads are owned by a real user
and count against their storage quota — service accounts have none and
can't create files at all (see DEPLOY.md's OAuth-delegation note).

The token is minted once locally via mint_oauth_token.py (interactive
browser consent) and stored as a Cloud Run secret — never committed to the
repo. This module only loads + refreshes it; it never runs the interactive
flow itself, since a container can't complete one.
"""

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_TOKEN_PATH_ENV = "REPORT_OAUTH_TOKEN_PATH"


def get_credentials() -> Credentials:
    token_path = os.environ.get(_TOKEN_PATH_ENV)
    if not token_path:
        raise RuntimeError(
            f"{_TOKEN_PATH_ENV} is not set — the OAuth token must be mounted "
            "and its path exported as this env var (see DEPLOY.md)."
        )
    if not os.path.exists(token_path):
        raise RuntimeError(f"OAuth token not found at {token_path}")

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return creds
