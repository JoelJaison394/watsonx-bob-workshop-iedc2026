"""
Tool: list_my_issues
Returns all issues filed by a specific email address, with optional status filtering.
"""

from typing import List, Optional

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


class IssueSummary(BaseModel):
    """A compact summary of a single issue."""
    issue_number: str = Field(..., description="Human-readable issue number, e.g. ISSUE-0001")
    title: str = Field(..., description="Title of the issue")
    status: str = Field(..., description="Current status: open | in_progress | resolved | closed")
    priority: str = Field(..., description="Priority level: low | medium | high | critical")
    created_at: str = Field(..., description="ISO-8601 timestamp when the issue was created")
    updated_at: str = Field(..., description="ISO-8601 timestamp of the last update")


@tool(permission=ToolPermission.READ_ONLY, expected_credentials=_EXPECTED_CREDENTIALS)
def list_my_issues(
    email: str,
    status_filter: Optional[str] = None,
) -> List[IssueSummary]:
    """Returns all issues reported by a specific email address.

    Args:
        email (str): The email address of the reporter whose issues to list.
        status_filter (str, optional): Filter by status — one of ``open``,
            ``in_progress``, ``resolved``, or ``closed``. If omitted, all
            issues are returned.

    Returns:
        List[IssueSummary]: Issues sorted by creation date (most recent first).
            Returns an empty list if no matching issues are found.
    """
    email_lower = email.strip().lower()

    if status_filter:
        status_filter = status_filter.strip().lower()
        if status_filter not in VALID_STATUSES:
            status_filter = None

    with _conn() as con:
        with con.cursor() as cur:
            _init_db(cur)
            if status_filter:
                cur.execute(
                    """
                    SELECT issue_number, title, status, priority,
                           created_at::text, updated_at::text
                      FROM it_issues
                     WHERE reporter_email = %s AND status = %s
                     ORDER BY created_at DESC
                    """,
                    (email_lower, status_filter),
                )
            else:
                cur.execute(
                    """
                    SELECT issue_number, title, status, priority,
                           created_at::text, updated_at::text
                      FROM it_issues
                     WHERE reporter_email = %s
                     ORDER BY created_at DESC
                    """,
                    (email_lower,),
                )
            rows = cur.fetchall()

    return [IssueSummary(**dict(r)) for r in rows]
