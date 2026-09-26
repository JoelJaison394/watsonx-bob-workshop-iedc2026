"""
Tool: create_issue
Creates a new issue in the issue tracker.

If no account exists for the supplied email address one is automatically
created before the issue is recorded.
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


class CreateIssueResponse(BaseModel):
    """Response returned after a new issue is created."""
    issue_id: str = Field(..., description="Unique internal ID of the issue")
    issue_number: str = Field(..., description="Human-readable issue number, e.g. ISSUE-0001")
    title: str = Field(..., description="Title of the issue")
    description: str = Field(..., description="Full description of the issue")
    status: str = Field(..., description="Current status (always 'open' on creation)")
    priority: str = Field(..., description="Priority level: low | medium | high | critical")
    reporter_email: str = Field(..., description="Email of the reporter")
    account_id: str = Field(..., description="Account ID of the reporter")
    created_at: str = Field(..., description="ISO-8601 timestamp when the issue was created")
    account_created: bool = Field(..., description="True if a new account was automatically created for the reporter")


@tool(permission=ToolPermission.READ_WRITE, expected_credentials=_EXPECTED_CREDENTIALS)
def create_issue(
    email: str,
    title: str,
    description: str,
    priority: Optional[str] = "medium",
) -> CreateIssueResponse:
    """Creates a new issue in the issue tracker.

    If no account exists for the provided email address, one is automatically
    created before the issue is recorded.

    Args:
        email (str): Email address of the person reporting the issue.
        title (str): Short, descriptive title for the issue.
        description (str): Detailed description of the issue.
        priority (str, optional): One of ``low``, ``medium``, ``high``, or
            ``critical``. Defaults to ``medium``.

    Returns:
        CreateIssueResponse: Details of the newly created issue, including the
            issue number, status, priority, and whether a new account was
            automatically created for the reporter.
    """
    if priority not in ("low", "medium", "high", "critical"):
        priority = "medium"

    email_lower = email.strip().lower()
    display_name = email_lower.split("@")[0].replace(".", " ").replace("_", " ").title()

    with _conn() as con:
        with con.cursor() as cur:
            _init_db(cur)

            # Upsert account
            cur.execute(
                """
                INSERT INTO it_accounts (account_id, email, display_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (email) DO NOTHING
                """,
                (str(uuid.uuid4()), email_lower, display_name),
            )
            account_created = cur.rowcount == 1

            cur.execute(
                "SELECT account_id FROM it_accounts WHERE email = %s",
                (email_lower,),
            )
            account_id = cur.fetchone()["account_id"]

            # Insert issue
            issue_id = str(uuid.uuid4())
            cur.execute("SELECT nextval('it_issue_seq')")
            issue_number = f"ISSUE-{int(cur.fetchone()['nextval']):04d}"

            cur.execute(
                """
                INSERT INTO it_issues
                    (issue_id, issue_number, title, description,
                     status, priority, reporter_email, account_id)
                VALUES (%s, %s, %s, %s, 'open', %s, %s, %s)
                RETURNING issue_id, issue_number, title, description,
                          status, priority, reporter_email, account_id,
                          created_at::text
                """,
                (issue_id, issue_number, title.strip(), description.strip(),
                 priority, email_lower, account_id),
            )
            row = dict(cur.fetchone())
        con.commit()

    return CreateIssueResponse(**row, account_created=account_created)
