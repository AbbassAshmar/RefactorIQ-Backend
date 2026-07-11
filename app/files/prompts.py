from __future__ import annotations


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
