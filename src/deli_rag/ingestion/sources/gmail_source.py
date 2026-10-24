import os
import time
import base64
import logging
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

log = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Ensure these directories exist
INBOX_DIR = Path("inbox")
TOKEN_PATH = Path("token.json")
CREDENTIALS_PATH = Path("credentials.json")


def get_gmail_service():
    """Authenticate and return the Gmail API service."""
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    "Missing credentials.json. Please download it from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        TOKEN_PATH.write_text(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def download_attachments_from_query(query: str):
    """Search Gmail for a query and download attachments to the inbox folder."""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    service = get_gmail_service()

    try:
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])

        print(f"\n--- DEBUG: GMAIL API SEARCH RESULTS ---")
        print(f"Query sent: {query}")
        print(f"Messages found: {len(messages)}")
        print(f"---------------------------------------\n")

        if not messages:
            return

        for message in messages:
            msg = service.users().messages().get(userId='me', id=message['id']).execute()

            # Use a helper function to recursively find attachments
            def get_attachments(parts):
                for part in parts:
                    if part.get('filename') and part.get('body', {}).get('attachmentId'):
                        yield part
                    if 'parts' in part:
                        yield from get_attachments(part['parts'])

            payload = msg.get('payload', {})
            all_parts = payload.get('parts', [])

            # Check the top-level payload first, then dive into parts
            if payload.get('filename') and payload.get('body', {}).get('attachmentId'):
                all_parts.append(payload)

            for part in get_attachments(all_parts):
                filename = part['filename']
                attachment_id = part['body']['attachmentId']

                # Get the internal date of the email to make the filename unique
                msg_internal_date = int(msg.get('internalDate', 0)) / 1000.0
                import datetime
                dt = datetime.datetime.fromtimestamp(msg_internal_date, datetime.timezone.utc)
                date_str = dt.strftime("%Y%m%d")

                # Create a unique filename: e.g., AgentBalanceReport_20261019.pdf
                stem = Path(filename).stem
                ext = Path(filename).suffix
                unique_filename = f"{stem}_{date_str}{ext}"
                file_path = INBOX_DIR / unique_filename

                if file_path.exists():
                    log.info(f"File already exists, skipping: {unique_filename}")
                    continue

                att = service.users().messages().attachments().get(
                    userId='me', messageId=message['id'], id=attachment_id
                ).execute()

                data = base64.urlsafe_b64decode(att['data'].encode('UTF-8'))
                file_path.write_bytes(data)
                log.info(f"Downloaded: {filename}")

    except HttpError as error:
        log.error(f"An error occurred: {error}")


def run_daily_sync():
    """The main function to run daily. Adjust queries as needed."""
    log.info("Starting Gmail daily sync...")

    # 1. Download RIA Reports
    # (Using 'from:transmissions' is safer than subject matching)
    download_attachments_from_query('from:transmissions has:attachment newer_than:1d')

    time.sleep(3)

    # 2. Download Sales & Inventory CSVs
    download_attachments_from_query('subject:"Daily Sales Report" has:attachment newer_than:1d')

    log.info("Gmail daily sync complete.")
