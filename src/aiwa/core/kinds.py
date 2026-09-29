"""What a website or app is (its kind), next to how it counts (its category).

The kind is mostly objective (openjev can tell that youtube.com is video
streaming); the category is personal (for one person YouTube is lectures, for
another it's entertainment). Each kind has a default category; the user
confirms each site's kind and can let a single site count differently.

The kind also tells other parts of aiwa what to expect, e.g. that on a streaming
site no input for a while means watching, not away.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiwa.core.events import Category


@dataclass(frozen=True)
class Kind:
    key: str
    label: str
    description: str  # what openjev reads to choose
    group: str
    category: Category | None  # the default; None = no default, the user decides


D, S, X, N = Category.DEEP, Category.SHALLOW, Category.DISTRACTION, Category.NEUTRAL

KINDS: list[Kind] = [
    # work tools
    Kind("ide", "Code editor / IDE", "Writing and editing code", "Work tools", D),
    Kind("terminal", "Terminal", "Command line, shells", "Work tools", D),
    Kind("code_hosting", "Code hosting & review", "Repositories, pull requests, issues (e.g. GitHub, GitLab)", "Work tools", D),
    Kind("ai_assistant", "AI assistant", "Chatting with an AI assistant (e.g. ChatGPT, Claude, Gemini)", "Work tools", D),
    Kind("docs_reference", "Documentation & reference", "Technical docs, manuals, API references, Q&A sites", "Work tools", D),
    Kind("writing", "Writing & documents", "Writing or editing documents, notes, papers (e.g. Word, Google Docs, Overleaf, Notion)", "Work tools", D),
    Kind("spreadsheets", "Spreadsheets & data", "Spreadsheets, data analysis, notebooks", "Work tools", D),
    Kind("design", "Design tools", "Graphic, UI or 3D design (e.g. Figma, Photoshop, Blender)", "Work tools", D),
    Kind("devops", "Cloud & devops", "Cloud consoles, servers, deployment, monitoring", "Work tools", D),
    Kind("project_mgmt", "Project management", "Task boards and trackers (e.g. Jira, Trello, Linear)", "Work tools", S),
    # contact
    Kind("email", "Email", "Reading and writing email", "Contact", S),
    Kind("team_chat", "Chat & messaging", "Team chat and messengers (e.g. Slack, Teams, WhatsApp, Messenger)", "Contact", S),
    Kind("video_calls", "Video calls", "Meetings and calls (e.g. Zoom, Meet)", "Contact", S),
    Kind("calendar", "Calendar", "Calendars and scheduling", "Contact", S),
    # learning & research
    Kind("search_engine", "Search engine", "Web search (e.g. Google, Bing, DuckDuckGo)", "Learning & research", N),
    Kind("research", "Research & papers", "Academic papers, journals, preprints, reading PDFs", "Learning & research", D),
    Kind("education", "Courses & education", "Online courses, lectures, university portals, learning platforms", "Learning & research", D),
    # leisure
    Kind("news", "News", "News sites and aggregators", "Leisure", X),
    Kind("social_media", "Social media", "Feeds and social networks (e.g. Instagram, Facebook, X, Reddit, TikTok)", "Leisure", X),
    Kind("video_streaming", "Video streaming", "Watching videos, films, series or anime (e.g. YouTube, Netflix)", "Leisure", X),
    Kind("music_audio", "Music & audio", "Music, podcasts, radio", "Leisure", N),
    Kind("games", "Games", "Playing games", "Leisure", X),
    Kind("shopping", "Shopping", "Online shops and marketplaces", "Leisure", X),
    # other
    Kind("finance", "Finance & banking", "Banking, payments, taxes", "Other", S),
    Kind("maps_travel", "Maps & travel", "Maps, bookings, transport", "Other", S),
    Kind("system", "System & utilities", "System settings, file manager, utilities", "Other", N),
    Kind("other", "Something else", "None of these", "Other", None),
]
BY_KEY = {k.key: k for k in KINDS}
GROUPS = list(dict.fromkeys(k.group for k in KINDS))


def in_group(group: str) -> list[Kind]:
    return [k for k in KINDS if k.group == group]


def default_category(kind: str) -> Category | None:
    return BY_KEY[kind].category if kind in BY_KEY else None


def label(kind: str | None) -> str:
    return BY_KEY[kind].label if kind in BY_KEY else "unknown"
