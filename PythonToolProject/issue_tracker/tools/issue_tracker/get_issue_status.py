"""
Tool: get_issue_status
Returns the current status and full details of a single issue.
"""

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


class IssueStatusResponse(BaseModel):
    """Current status and details of a tracked issue."""
    issue_id: str = Field(..., description="Unique internal ID of the issue")
    issue_number: str = Field(..., description="Human-readable issue number, e.g. ISSUE-0001")
    title: str = Field(..., description="Title of the issue")
    description: str = Field(..., description="Full description of the issue")
    status: str = Field(..., description="Current status: open | in_progress | resolved | closed")
    priority: str = Field(..., description="Priority level: low | medium | high | critical")
    reporter_email: str = Field(..., description="Email of the reporter")
    created_at: str = Field(..., description="ISO-8601 timestamp when the issue was created")
    updated_at: str = Field(..., description="ISO-8601 timestamp of the last update")
    comment_count: int = Field(..., description="Number of comments on the issue")


@tool(permission=ToolPermission.READ_ONLY, expected_credentials=_EXPECTED_CREDENTIALS)
def get_issue_status(issue_identifier: str) -> IssueStatusResponse:
    """Returns the current status and full details of a tracked issue.

    Args:
        issue_identifier (str): The issue number (e.g. ``ISSUE-0001``) or the
            internal UUID of the issue to look up.

    Returns:
        IssueStatusResponse: Full details including status, priority, reporter,
            timestamps, and comment count.

    Raises:
        ValueError: If no issue matching ``issue_identifier`` is found.
    """
    upper = issue_identifier.strip().upper()

    with _conn() as con:
        with con.cursor() as cur:
            _init_db(cur)
            cur.execute(
                """
                SELECT i.issue_id, i.issue_number, i.title, i.description,
                       i.status, i.priority, i.reporter_email,
                       i.created_at::text, i.updated_at::text,
                       COUNT(c.comment_id)::int AS comment_count
                  FROM it_issues i
                  LEFT JOIN it_issue_comments c ON c.issue_id = i.issue_id
                 WHERE i.issue_number = %s OR i.issue_id = %s
                 GROUP BY i.issue_id
                """,
                (upper, issue_identifier.strip()),
            )
            row = cur.fetchone()

    if row is None:
        raise ValueError(
            f"No issue found with identifier '{issue_identifier}'. "
            "Please provide a valid issue number (e.g. ISSUE-0001) or issue ID."
        )

    return IssueStatusResponse(**dict(row))
