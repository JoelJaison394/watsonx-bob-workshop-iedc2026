"""
Issue Tracker Tools
===================
All six tools in one self-contained file:

  - greet                 : greet a user by name or email
  - create_account        : create or look up a user account by email
  - create_issue          : file a new issue (auto-creates account if needed)
  - get_issue_status      : fetch full details + status of a single issue
  - list_my_issues        : list all issues for a reporter, with optional status filter
  - update_issue_status   : transition an issue to a new status

Database: Supabase PostgreSQL (connection pooler).
Tables are created automatically on first use.
"""

import uuid
from datetime import datetime, timezone
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

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

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
    """Open a Postgres connection using credentials from the WXO connection store.

    Uses the URL exactly as supplied (pooler or direct). The Supabase pooler
    (port 6543, IPv4) is recommended — the direct host (port 5432) may resolve
    to an IPv6 address that is unreachable on some networks.
    """
    creds: KeyValueConnectionCredentials = get_application_connection_credentials(
        type=ConnectionType.KEY_VALUE, app_id="issue_tracker_db",
    )
    database_url = creds.get("database_url")
    return psycopg2.connect(
        database_url,
        sslmode="require",
        connect_timeout=10,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def _init_db(cur):
    cur.execute(_DDL)


# ---------------------------------------------------------------------------
# Tool 1 – greet
# ---------------------------------------------------------------------------

class GreetResponse(BaseModel):
    """Response returned by the greet tool."""
    message: str = Field(..., description="The personalised greeting message")


@tool(permission=ToolPermission.READ_ONLY, expected_credentials=_EXPECTED_CREDENTIALS)
def greet(name: str) -> GreetResponse:
    """Greets a user by name.

    Args:
        name (str): The name or email address of the user to greet.

    Returns:
        GreetResponse: A personalised greeting message.
    """
    display = name.strip()
    # If an email is passed, extract the local part for a friendlier greeting
    if "@" in display:
        display = display.split("@")[0].replace(".", " ").replace("_", " ").title()

    return GreetResponse(message=f"Hello, {display}! Welcome to the Issue Tracker. How can I help you today?")


# ---------------------------------------------------------------------------
# Tool 2 – create_account
# ---------------------------------------------------------------------------

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

    If an account already exists for the given email address the existing
    account is returned and ``already_existed`` is set to ``True``.

    Args:
        email (str): Email address of the user — used as the unique account key.
        display_name (str, optional): Human-readable name. If omitted, derived
            from the email local part (e.g. "John Doe" from "john.doe@…").

    Returns:
        AccountResponse: Account ID, email, display name, creation timestamp,
            and whether the account already existed.
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
                "SELECT account_id, email, display_name, created_at::text"
                "  FROM it_accounts WHERE email = %s",
                (email_lower,),
            )
            row = dict(cur.fetchone())
        con.commit()

    return AccountResponse(**row, already_existed=already_existed)


# ---------------------------------------------------------------------------
# Tool 3 – create_issue
# ---------------------------------------------------------------------------

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
        CreateIssueResponse: Full details of the created issue, including the
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


# ---------------------------------------------------------------------------
# Tool 4 – get_issue_status
# ---------------------------------------------------------------------------

class IssueStatusResponse(BaseModel):
    """Current status and full details of a tracked issue."""
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


# ---------------------------------------------------------------------------
# Tool 5 – list_my_issues
# ---------------------------------------------------------------------------

class IssueSummary(BaseModel):
    """A compact summary of a single issue."""
    issue_number: str = Field(..., description="Human-readable issue number, e.g. ISSUE-0001")
    title: str = Field(..., description="Title of the issue")
    status: str = Field(..., description="Current status: open | in_progress | resolved | closed")
    priority: str = Field(..., description="Priority level: low | medium | high | critical")
    created_at: str = Field(..., description="ISO-8601 timestamp when the issue was created")
    updated_at: str = Field(..., description="ISO-8601 timestamp of the last update")


@tool(permission=ToolPermission.READ_ONLY, expected_credentials=_EXPECTED_CREDENTIALS)
def list_my_issues(email: str, status_filter: Optional[str] = None) -> List[IssueSummary]:
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


# ---------------------------------------------------------------------------
# Tool 6 – update_issue_status
# ---------------------------------------------------------------------------

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
                        (comment_id, issue_id, created_at, comment_type,
                         text, status_from, status_to)
                    VALUES (%s, %s, %s, 'status_change', %s, %s, %s)
                    """,
                    (str(uuid.uuid4()), issue_id, now,
                     comment, previous_status, new_status_lower),
                )
        con.commit()

    return UpdateIssueStatusResponse(
        issue_number=issue_number,
        previous_status=previous_status,
        new_status=new_status_lower,
        updated_at=now.isoformat(),
    )
