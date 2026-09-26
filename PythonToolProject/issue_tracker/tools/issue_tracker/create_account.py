"""
Tool: create_account
Creates a new user account in the issue tracker using the provided email address.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras
from pydantic import BaseModel, Field

from ibm_watsonx_orchestrate.agent_builder.connections import (
    ConnectionType,
    ExpectedCredentials,
    KeyValueConnectionCredentials,
    get_application_connection_credentials,
)
from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission

_EXPECTED_CREDENTIALS = [ExpectedCredentials(app_id="issue_tracker_db", type=ConnectionType.KEY_VALUE)]

_DDL = """
CREATE TABLE IF NOT EXISTS it_accounts (
    account_id   TEXT PRIMARY KEY,
    email        TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS it_issues (
    issue_id       TEXT PRIMARY KEY,
    issue_number   TEXT UNIQUE NOT NULL,
    title          TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'open',
    priority       TEXT NOT NULL DEFAULT 'medium',
    reporter_email TEXT NOT NULL,
    account_id     TEXT NOT NULL REFERENCES it_accounts(account_id),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS it_issue_comments (
    comment_id   TEXT PRIMARY KEY,
    issue_id     TEXT NOT NULL REFERENCES it_issues(issue_id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    comment_type TEXT NOT NULL DEFAULT 'note',
    text         TEXT NOT NULL,
    status_from  TEXT,
    status_to    TEXT
);
CREATE SEQUENCE IF NOT EXISTS it_issue_seq START 1;
"""


def _conn():
    creds: KeyValueConnectionCredentials = get_application_connection_credentials(
        type=ConnectionType.KEY_VALUE, app_id="issue_tracker_db",
    )
    return psycopg2.connect(creds.get("database_url"), cursor_factory=psycopg2.extras.RealDictCursor)


def _init_db(cur):
    cur.execute(_DDL)


class AccountResponse(BaseModel):
    """Details of a newly created or already existing user account."""
    account_id: str = Field(..., description="Unique identifier for the account")
    email: str = Field(..., description="Email address associated with the account")
    display_name: str = Field(..., description="Display name for the account")
    created_at: str = Field(..., description="ISO-8601 timestamp when the account was created")
    already_existed: bool = Field(..., description="True if the account already existed; False if newly created")


@tool(permission=ToolPermission.READ_WRITE, expected_credentials=_EXPECTED_CREDENTIALS)
def create_account(email: str, display_name: Optional[str] = None) -> AccountResponse:
    """Creates a new user account for the issue tracker.

    If an account already exists for the given email address the existing account
    is returned and ``already_existed`` is set to ``True``.

    Args:
        email (str): The email address of the user. Used as the unique identifier
            for the account.
        display_name (str, optional): A human-readable name for the account. If
            omitted, the local part of the email address is used (e.g. "John Doe"
            from "john.doe@example.com").

    Returns:
        AccountResponse: The account details including account ID, email,
            display name, creation timestamp, and whether the account already existed.
    """
    email_lower = email.strip().lower()
    if not display_name:
        display_name = email_lower.split("@")[0].replace(".", " ").replace("_", " ").title()

    with _conn() as con:
        with con.cursor() as cur:
            _init_db(cur)
            cur.execute(
                """
                INSERT INTO it_accounts (account_id, email, display_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (email) DO NOTHING
                """,
                (str(uuid.uuid4()), email_lower, display_name),
            )
            already_existed = cur.rowcount == 0
            cur.execute(
                "SELECT account_id, email, display_name, created_at::text FROM it_accounts WHERE email = %s",
                (email_lower,),
            )
            row = dict(cur.fetchone())
        con.commit()

    return AccountResponse(**row, already_existed=already_existed)
