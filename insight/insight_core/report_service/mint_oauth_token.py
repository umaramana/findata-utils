"""
One-time, run-it-yourself script — mints the OAuth token report_service
needs for Drive uploads (see DEPLOY.md's OAuth-delegation step).

Unlike sheets_auth.py's token.json (drive.file scope only — files the app
itself created), this service must read metadata on a file it did NOT
create (insight_pilot, to find its parent folder), which needs full
`drive` scope. That's a broader grant than the existing local token, so it
needs its own consent flow rather than reusing token.json.

Usage (run locally, opens a browser for you to log in and consent as
whichever account should own the uploaded reports):

    cd insight_core/report_service
    python mint_oauth_token.py

Writes oauth_token_for_secret.json in the current folder. Upload it to
Secret Manager per DEPLOY.md, then delete the local copy — same
temporary-file discipline as service_account_key.json in step 1.
"""

from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_HERE = Path(__file__).parent
CREDENTIALS_PATH = _HERE.parent / "credentials.json"
OUTPUT_PATH = _HERE / "oauth_token_for_secret.json"


def main():
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            f"credentials.json not found at {CREDENTIALS_PATH}\n"
            "Download it from Google Cloud Console -> APIs & Services -> "
            "Credentials -> OAuth 2.0 Client IDs (same file sheets_auth.py uses)."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)

    OUTPUT_PATH.write_text(creds.to_json())
    print(f"Wrote {OUTPUT_PATH} — upload it to Secret Manager, then delete this file.")


if __name__ == "__main__":
    main()
