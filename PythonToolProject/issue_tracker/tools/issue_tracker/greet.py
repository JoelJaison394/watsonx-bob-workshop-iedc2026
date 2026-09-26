"""
Tool: greet
Returns a personalised greeting for a user by their name or email.
"""

from pydantic import BaseModel, Field

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission


class GreetResponse(BaseModel):
    """Response returned by the greet tool."""
    message: str = Field(..., description="The personalised greeting message")


@tool(permission=ToolPermission.READ_ONLY)
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
