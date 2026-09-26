"""
Tool: update_issue_status
Updates the status of an existing issue and optionally records a comment.
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

VALID_STATUSES = ("open", "in_progress", "resolved", "closed")


def _conn():
    creds: KeyValueConnectionCredentials = get_application_connection_credentials(
        type=ConnectionType.KEY_VALUE, app_id="issue_tracker_db",
    )
    return psycopg2.connect(creds.get("database_url"), cursor_factory=psycopg2.extras.RealDictCursor)


def _init_db(cur):
    cur.execute(_DDL)


class UpdateIssueStatusResponse(BaseModel):
    """Confirmation of a status update."""
    issue_number: str = Field(..., description="Human-readable issue number")
    previous_status: str = Field(..., description="The status before this update")
    new_status: str = Field(..., description="The status after this update")
    updated_at: str = Field(..., description="ISO-8601 timestamp of this update")


@tool(permission=ToolPermission.READ_WRITE, expected_credentials=_EXPECTED_CREDENTIALS)
def update_issue_status(
    issue_identifier: str,
    new_status: str,
    comment: Optional[str] = None,
) -> UpdateIssueStatusResponse:
    """Updates the status of an existing issue.

    Args:
        issue_identifier (str): The issue number (e.g. ``ISSUE-0001``) or
            internal UUID of the issue to update.
        new_status (str): New status — one of ``open``, ``in_progress``,
            ``resolved``, or ``closed``.
        comment (str, optional): Optional comment explaining the status change.

    Returns:
        UpdateIssueStatusResponse: Confirmation with previous status, new
            status, and update timestamp.

    Raises:
        ValueError: If the identifier is unknown or ``new_status`` is invalid.
    """
    new_status_lower = new_status.strip().lower()
    if new_status_lower not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{new_status}'. Must be one of: {', '.join(VALID_STATUSES)}."
        )

    upper = issue_identifier.strip().upper()
    now = datetime.now(timezone.utc)

    with _conn() as con:
        with con.cursor() as cur:
            _init_db(cur)

            cur.execute(
                "SELECT issue_id, issue_number, status FROM it_issues"
                " WHERE issue_number = %s OR issue_id = %s",
                (upper, issue_identifier.strip()),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"No issue found with identifier '{issue_identifier}'.")

            issue_id = row["issue_id"]
            issue_number = row["issue_number"]
            previous_status = row["status"]

            cur.execute(
                "UPDATE it_issues SET status = %s, updated_at = %s WHERE issue_id = %s",
                (new_status_lower, now, issue_id),
            )

            if comment:
                cur.execute(
                    """
                    INSERT INTO it_issue_comments
                        (comment_id, issue_id, created_at, comment_type, text, status_from, status_to)
                    VALUES (%s, %s, %s, 'status_change', %s, %s, %s)
                    """,
                    (str(uuid.uuid4()), issue_id, now, comment, previous_status, new_status_lower),
                )
        con.commit()

    return UpdateIssueStatusResponse(
        issue_number=issue_number,
        previous_status=previous_status,
        new_status=new_status_lower,
        updated_at=now.isoformat(),
    )
