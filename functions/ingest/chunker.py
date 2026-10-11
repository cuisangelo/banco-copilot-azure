import re
from dataclasses import dataclass
from datetime import date

FRONT_MATTER_KEYS = ("doc_id", "title", "valid_from")
_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_SECTION_HEADING = re.compile(r"^## +(.+?)\s*$", re.MULTILINE)
_WORD = re.compile(r"\S+")


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    doc_title: str
    section: str
    content: str
    valid_from: date


def chunk_document(text: str, max_words: int = 800, overlap: int = 100) -> list[Chunk]:
    meta, body = _split_front_matter(text)
    headings = list(_SECTION_HEADING.finditer(body))
    if not headings:
        raise ValueError(f"{meta['doc_id']}: no '## ' sections")
    preamble = body[: headings[0].start()]
    if any(line.strip() and not line.startswith("# ") for line in preamble.splitlines()):
        raise ValueError(f"{meta['doc_id']}: text before the first '## ' section")

    chunks: list[Chunk] = []
    for i, heading in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
        section_text = body[heading.end() : end].strip()
        for window in _windows(section_text, max_words, overlap):
            chunks.append(
                Chunk(
                    id=f"{meta['doc_id']}-{len(chunks)}",
                    doc_id=meta["doc_id"],
                    doc_title=meta["title"],
                    section=heading.group(1),
                    content=window,
                    valid_from=date.fromisoformat(meta["valid_from"]),
                )
            )
    return chunks


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONT_MATTER.match(text)
    if not match:
        raise ValueError("document has no front matter")
    meta = dict(line.split(":", 1) for line in match.group(1).splitlines() if line.strip())
    meta = {key.strip(): value.strip() for key, value in meta.items()}
    for key in FRONT_MATTER_KEYS:
        if not meta.get(key):
            raise ValueError(f"front matter is missing {key}")
    return meta, text[match.end() :]


def _windows(text: str, max_words: int, overlap: int) -> list[str]:
    # Slices the original text by word spans so lists and line breaks survive chunking.
    words = list(_WORD.finditer(text))
    if len(words) <= max_words:
        return [text]
    step = max_words - overlap
    starts = range(0, len(words) - overlap, step)
    return [text[words[s].start() : words[min(s + max_words, len(words)) - 1].end()] for s in starts]
