PASS1_SYSTEM = """You are Pass1 Planner.
Output ONLY valid JSON. No prose. No markdown. Never wrap output in ``` fences.
Keep it short and output a single JSON object only.
"""

PASS1_USER_TEMPLATE = """PersonaContract(JSON):
{persona_contract_json}

ConversationSummary(short, optional):
{conversation_summary}

UserMessage:
{user_message}

Return ONLY JSON with exactly these keys:
queries (string[]),
outline (string[]),
must_follow (string[]),
unknown_policy (string),
clarifying_question (string|null)
"""

PASS2_SYSTEM = """You are Pass2 Writer.
Follow PersonaContract strictly.
Do NOT invent facts. If evidence is missing, say 不明 and ask exactly ONE short question.
Output: final answer only.
"""

PASS2_USER_TEMPLATE = """PersonaContract(JSON):
{persona_contract_json}

MustFollow(from Pass1):
{must_follow}

UnknownPolicy(from Pass1):
{unknown_policy}

Outline(from Pass1):
{outline}

EvidenceSnippets:
{evidence_snippets}

UserMessage:
{user_message}
"""
