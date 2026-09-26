#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# import-all.sh — Import all Issue Tracker tools and the agent into
#                 IBM watsonx Orchestrate.
#
# Usage:
#   export DATABASE_URL="postgresql://postgres:<password>@<host>:5432/postgres"
#   ./import-all.sh
#
#   Or simply run ./import-all.sh and enter the URL when prompted.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
TOOLS_DIR="${SCRIPT_DIR}/tools"
AGENTS_DIR="${SCRIPT_DIR}/agents"
CONNECTIONS_DIR="${SCRIPT_DIR}/connections"
REQUIREMENTS="${TOOLS_DIR}/requirements.txt"

# Read DATABASE_URL from the environment, or prompt the user securely
if [ -z "${DATABASE_URL:-}" ]; then
  read -rsp "Enter DATABASE_URL (Supabase PostgreSQL connection string): " DATABASE_URL
  echo
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "Error: DATABASE_URL is required." >&2
  exit 1
fi

echo "==> Importing Issue Tracker connection..."
orchestrate connections import -f "${CONNECTIONS_DIR}/issue_tracker_connection.yaml"

echo "==> Setting connection credentials..."
orchestrate connections set-credentials \
  -a issue_tracker_db \
  --env draft \
  -e "database_url=${DATABASE_URL}"
orchestrate connections set-credentials \
  -a issue_tracker_db \
  --env live \
  -e "database_url=${DATABASE_URL}"

echo "==> Importing Issue Tracker tools..."
orchestrate tools import \
  -k python \
  -f "${TOOLS_DIR}/issue_tracker_tools.py" \
  -r "${REQUIREMENTS}" \
  -a issue_tracker_db

echo "==> Importing Issue Tracker agent..."
orchestrate agents import -f "${AGENTS_DIR}/issue_tracker_agent.yaml"

echo ""
echo "✅  Done! The 'issue_tracker_agent' is ready to use."
