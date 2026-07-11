from __future__ import annotations


SCAN_ID_QUERY_PARAM = "scan_id"
RISK_TREND_ENDPOINT = "/overview/risk-trend"
SCAN_SUMMARY_ENDPOINT = "/overview/scan-summary"
TOP_FILES_ENDPOINT = "/overview/top-files"
RISK_BY_DIRECTORY_ENDPOINT = "/overview/risk-by-directory"

PRIORITY_BANDS = ("critical", "high", "medium", "low")
RISKY_PRIORITY_BANDS = frozenset({"critical", "high", "medium"})
PREVIOUS_TREND_SCAN_COUNT = 3
TOP_REFACTOR_FILE_COUNT = 10
TOP_DIRECTORY_COUNT = 5
