"""Shared backend constants."""

SCAN_ID_QUERY_PARAM = "scan_id"
PROJECT_ID_QUERY_PARAM = "project_id"
INCLUDE_SUMMARY_QUERY_PARAM = "include_summary"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
COOKIE_NAME = "access_token"
COOKIE_MAX_AGE = 30 * 24 * 60 * 60
FRONTEND_URL = "http://localhost:3001"
GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
AES_GCM_PREFIX = "aesgcm:v1:"
AES_GCM_NONCE_SIZE = 12

LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript React",
    ".ts": "TypeScript",
    ".tsx": "TypeScript React",
    ".java": "Java",
    ".cs": "C#",
    ".cpp": "C++",
    ".cc": "C++",
    ".c": "C",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".vue": "Vue",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sql": "SQL",
    ".md": "Markdown",
}

RISK_TREND_ENDPOINT = "/overview/risk-trend"
SCAN_SUMMARY_ENDPOINT = "/overview/scan-summary"
TOP_FILES_ENDPOINT = "/overview/top-files"
RISK_BY_DIRECTORY_ENDPOINT = "/overview/risk-by-directory"
DIRECTORY_INSIGHT_ENDPOINT = "/overview/directory-insight"

PRIORITY_BANDS = ("critical", "high", "medium", "low")
RISKY_PRIORITY_BANDS = frozenset({"critical", "high", "medium"})
PREVIOUS_TREND_SCAN_COUNT = 3
SCAN_DASHBOARD_HISTORY_LIMIT = 20
TOP_REFACTOR_FILE_COUNT = 5
TOP_DIRECTORY_COUNT = 5

ROLE_PERMISSIONS = {
    "admin": [
        "manage-users",
        "manage-scans",
        "view-analytics",
        "manage-projects",
    ],
    "client": ["view-own-scans", "create-scans"],
}

GENERAL_SUMMARY_PROMPT = """
You are explaining software health to a non-developer stakeholder.
Using the JSON evidence below, write a concise plain-language summary of this file.
Do not list or restate metrics. Explain, in this order: its current state, why that state exists,
and the most useful action to take next. Avoid jargon and implementation details. Use at most 120 words.

FILE EVIDENCE:
{context}
""".strip()

ARCHITECTURAL_SUMMARY_PROMPT = """
You are explaining a file's architectural position to a non-technical stakeholder.
Using the JSON evidence below, describe the file's role, how strongly other parts rely on it,
any concentration or circular-dependency risk, and the safest architectural action to take.
Do not restate raw metrics and do not use specialist terminology without explaining it.
Use at most 120 words.

FILE EVIDENCE:
{context}
""".strip()

DIRECTORY_INSIGHT_PROMPT = """
You are explaining software risk to a non-technical stakeholder.
Use only the summarized directory evidence below. Do not invent facts, files, or priorities.
Translate the evidence into a plain-language action recommendation that answers:
Which areas need attention, and what should we do next?

Return only one valid JSON object with exactly these fields:
- title: use "Recommended focus area"
- summary: one sentence describing where risk is concentrated
- explanation: one or two plain-language sentences explaining why those areas matter
- recommendation: one direct next action, including an order when there is more than one area
- priority_directories: an array of zero to three objects with path, priority, and reason

Use priority values high, medium, or low. Keep directory paths exactly as provided.
Avoid raw metrics, percentages, metric names, and specialist terms such as centrality,
fan-in, fan-out, cyclomatic complexity, coupling, churn, or co-change frequency.
Prefer wording such as "This area is used by many parts of the app" or "Files in this
area change often and are harder to maintain." Do not use markdown or code fences.

DIRECTORY EVIDENCE:
{context}
""".strip()
