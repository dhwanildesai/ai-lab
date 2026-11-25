"""Fixture: 12 tools in confusable groups, and 48 hand-labelled requests (4 per tool)."""

from __future__ import annotations

from typing import NamedTuple


class Tool(NamedTuple):
    name: str
    description: str


class Task(NamedTuple):
    query: str
    expected: str


# Every description has the same shape: what it does. When to use it. When not to.
TOOLS: list[Tool] = [
    Tool(
        "search_files",
        "Find files by name or path pattern. Use to locate a file when you know part of its name. "
        "Do not use to look inside file contents.",
    ),
    Tool(
        "grep_text",
        "Search file contents for a text pattern. Use to find where a string or symbol appears. "
        "Do not use to find files by name.",
    ),
    Tool(
        "read_file",
        "Return the contents of one file. Use when you already know the exact path to open. "
        "Do not use to search across many files.",
    ),
    Tool(
        "web_search",
        "Search the public internet and return ranked links. Use for recent news or facts. "
        "Do not use to download a page whose URL you have.",
    ),
    Tool(
        "fetch_url",
        "Download a single web page and return its text. Use when you have a specific URL. "
        "Do not use to search for pages.",
    ),
    Tool(
        "create_event",
        "Add a new meeting to the calendar. Use to schedule or book time with attendees. "
        "Do not use to change an existing meeting.",
    ),
    Tool(
        "update_event",
        "Change an existing calendar meeting. Use to move, rename or reschedule it. "
        "Do not use to book a new meeting.",
    ),
    Tool(
        "list_events",
        "Show calendar meetings in a date range. Use to check availability or the agenda. "
        "Do not use to create or change meetings.",
    ),
    Tool(
        "send_email",
        "Send an email message to one or more recipients. Use to reply or write to people. "
        "Do not use to search old messages.",
    ),
    Tool(
        "search_email",
        "Find messages in the mailbox by sender, subject or date. Use to look up past email. "
        "Do not use to send a message.",
    ),
    Tool(
        "run_sql",
        "Execute a read-only query against the analytics database. Use to count or aggregate rows. "
        "Do not use to create charts.",
    ),
    Tool(
        "make_chart",
        "Draw a chart from tabular data. Use to plot or visualize a trend. "
        "Do not use to query the database.",
    ),
]

_QUERIES = {
    "search_files": [
        "Which files have names ending in .toml?",
        "Locate the file called settings something",
        "Is there a Dockerfile anywhere in this repo?",
        "Find every path that matches test_*.py",
    ],
    "grep_text": [
        "Where does the string TODO appear in the code?",
        "Find all usages of the symbol parse_config",
        "Which modules mention the word deprecated?",
        "Search the source contents for a hardcoded port",
    ],
    "read_file": [
        "Open src/app/main.py",
        "Show me the contents of README.md",
        "What does line 10 of config.yaml say?",
        "Return the whole file at docs/intro.md",
    ],
    "web_search": [
        "What is the latest news about battery recycling?",
        "Look online for recent facts on coral bleaching",
        "Who won the marathon yesterday?",
        "Search the internet for reviews of standing desks",
    ],
    "fetch_url": [
        "Download the page at https://example.com/pricing",
        "Get the text of this URL: https://example.org/post",
        "Summarize the article at https://example.net/a",
        "What does the page https://example.com/status say?",
    ],
    "create_event": [
        "Book a meeting with the design team on Tuesday",
        "Schedule 30 minutes with Sam tomorrow",
        "Put lunch on my calendar for Friday",
        "Set up a new recurring standup with all attendees",
    ],
    "update_event": [
        "Move my 3pm meeting to 4pm",
        "Rename the planning meeting to roadmap review",
        "Push the standup back by an hour",
        "Reschedule the existing budget meeting",
    ],
    "list_events": [
        "What is on my agenda today?",
        "Am I free on Thursday afternoon?",
        "Show my meetings for next week",
        "Check availability between Monday and Wednesday",
    ],
    "send_email": [
        "Reply to the vendor saying we accept",
        "Write to the team about the outage",
        "Send a message to the new recipients list",
        "Let Alex know by email that I am late",
    ],
    "search_email": [
        "Find the message from payroll about taxes",
        "Look up past email with subject invoice",
        "Did the landlord ever write back to me?",
        "Which sender mailed me on March 3?",
    ],
    "run_sql": [
        "Count the rows in the orders table",
        "How many users signed up last month?",
        "Query the analytics database for average order value",
        "Aggregate revenue by region",
    ],
    "make_chart": [
        "Plot monthly revenue as a line",
        "Visualize the trend in signups",
        "Draw a bar chart of this data",
        "Turn these numbers into a graph",
    ],
}

TASKS: list[Task] = [Task(q, name) for name, queries in _QUERIES.items() for q in queries]
