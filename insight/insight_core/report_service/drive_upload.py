"""
Drive helpers for report_service — find-or-create the "Client Reports"
subfolder next to insight_pilot, upload a PDF into it, and share it to a
single fixed recipient (never anyone-with-link, per F05-S07 card).
"""

import logging

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

log = logging.getLogger(__name__)

CLIENT_REPORTS_FOLDER_NAME = "Client Reports"


def build_drive_service(creds):
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def find_sheet_parent_folder_id(drive_service, sheet_name):
    """Locate insight_pilot's parent folder — Client Reports goes alongside it."""
    resp = drive_service.files().list(
        q=f"name = '{sheet_name}' and trashed = false",
        fields="files(id, parents)",
        pageSize=1,
    ).execute()
    files = resp.get("files", [])
    if not files:
        raise RuntimeError(f"Could not find a Drive file named {sheet_name!r}")
    parents = files[0].get("parents") or []
    return parents[0] if parents else None


def find_or_create_client_reports_folder(drive_service, parent_folder_id):
    q = (
        f"name = '{CLIENT_REPORTS_FOLDER_NAME}' and trashed = false "
        "and mimeType = 'application/vnd.google-apps.folder'"
    )
    if parent_folder_id:
        q += f" and '{parent_folder_id}' in parents"

    resp = drive_service.files().list(q=q, fields="files(id, name)", pageSize=1).execute()
    files = resp.get("files", [])
    if files:
        return files[0]["id"]

    log.info("Creating %r folder (not found)", CLIENT_REPORTS_FOLDER_NAME)
    metadata = {
        "name": CLIENT_REPORTS_FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_folder_id:
        metadata["parents"] = [parent_folder_id]
    folder = drive_service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def upload_pdf(drive_service, folder_id, pdf_path, filename):
    metadata = {"name": filename, "parents": [folder_id]}
    media = MediaFileUpload(pdf_path, mimetype="application/pdf", resumable=False)
    file = drive_service.files().create(
        body=metadata, media_body=media, fields="id, webViewLink"
    ).execute()
    return file["id"], file.get("webViewLink")


def share_with_email(drive_service, file_id, email):
    """Restricted share — reader access to one named account only, never anyone-with-link."""
    drive_service.permissions().create(
        fileId=file_id,
        body={"type": "user", "role": "reader", "emailAddress": email},
        sendNotificationEmail=False,
    ).execute()
