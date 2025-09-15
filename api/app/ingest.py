import argparse
import os
import pathlib
from typing import List, Tuple
from pypdf import PdfReader
from .chunker import chunk_text
from .llm import embed_texts
from .db import get_conn
TEXT_EXT = {".txt", ".md"}


def _read_file(path: pathlib.Path) -> str:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        pages = [p.extract_text() or "" for p in reader.pages]
        return "\n\n".join(pages)
    elif path.suffix.lower() in TEXT_EXT:
        return path.read_text(encoding="utf-8", errors="ignore")
    else:
        return ""


def _upsert_document(conn, source: str, title: str) -> int:
    row = conn.execute("SELECT id FROM documents WHERE source = %s",
                       (source,)).fetchone()
    if row:
        return row[0]
    row = conn.execute(
        "INSERT INTO documents (source, title) VALUES (%s, %s) RETURNING id",
        (source, title)
    ).fetchone()
    return row[0]


def _insert_chunks(conn, doc_id: int, chunks: List[str], vectors: List[List[float]]):
    assert len(chunks) == len(vectors)
    for i, (text, vec) in enumerate(zip(chunks, vectors)):
        vec_literal = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
        conn.execute(
            """
                INSERT INTO chunks (document_id, chunk_index, content, embedding)
                VALUES (%s, %s, %s, %s::vector)
                """,

            (doc_id, i, text, vec_literal)
        )


def ingest_dir(root: str, chunk_size: int, overlap: int):
    root_path = pathlib.Path(root)
    paths = [p for p in root_path.rglob(
        "*") if p.suffix.lower() in {".pdf", ".txt", ".md"}]
    print(f"Found {len(paths)} files under {root}")
    with get_conn() as conn:
        with conn.transaction():
            for path in paths:
                text = _read_file(path)
                if not text.strip():
                    print(f"Skip empty: {path}")
                    continue
                doc_id = _upsert_document(conn, str(path), path.stem)
                chunks = chunk_text(
                    text, max_chars=chunk_size, overlap=overlap)
                if not chunks:
                    continue
                # embed in batches to minimize API calls
                batch = 64
                for s in range(0, len(chunks), batch):
                    sub = chunks[s:s+batch]
                    vecs = embed_texts(sub)
                    _insert_chunks(conn, doc_id, sub, vecs)
        print("Ingestion complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="Directory containing PDFs/TXT/MD")
    parser.add_argument("--chunk", type=int, default=int(os.getenv("CHUNK_SIZE",
                                                                   "1000")))
    parser.add_argument("--overlap", type=int,
                        default=int(os.getenv("CHUNK_OVERLAP", "200")))
    args = parser.parse_args()

    import os
    chunk = args.chunk
    overlap = args.overlap
    ingest_dir(args.root, chunk, overlap)
