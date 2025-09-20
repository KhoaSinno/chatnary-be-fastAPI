from typing import List

# chunks = [ "Chapter 1: Introduction\n\nThis chapter explains the design goals... (continues up to ~1000 chars)", "...(overlap 200 chars continues) Chapter 2: Architecture\n\nComponents include db, llm, chunker... (next ~1000 chars)",...
# ]


def chunk_text(text: str, max_chars: int = 1000, overlap: int = 200) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        chunk = text[start:end]
        # avoid cutting middle of a paragraph if possible
        if end < n:
            last_nl = chunk.rfind("\n")
            if last_nl > max_chars * 0.5:
                end = start + last_nl
                chunk = text[start:end]
        chunks.append(chunk.strip())
        start = max(end - overlap, end)
    return [c for c in chunks if c]
