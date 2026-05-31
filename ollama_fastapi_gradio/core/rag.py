from dataclasses import dataclass

@dataclass(frozen=True)
class Evidence:
    source_id: str
    text: str

async def rag_retrieve(_queries: list[str]) -> list[Evidence]:
    return []
