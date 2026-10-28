"""Per-run supplementary context, kept separate from source documents."""

from __future__ import annotations

from pathlib import Path

from doc_summarizer.io import sha256_bytes


def load_context(
    text: str | None,
    path: Path | None,
    *,
    max_input_bytes: int,
) -> str | None:
    parts: list[str] = []
    if text is not None:
        parts.append(text)
    if path is not None:
        source = path.expanduser()
        try:
            with source.open("rb") as stream:
                payload = stream.read(max_input_bytes + 1)
        except OSError as exc:
            raise ValueError(f"cannot read --context-file {source}: {exc}") from exc
        if len(payload) > max_input_bytes:
            raise ValueError("--context-file exceeds max_input_bytes")
        try:
            parts.append(payload.decode("utf-8-sig"))
        except UnicodeDecodeError as exc:
            raise ValueError("--context-file must be UTF-8 text") from exc
    normalized = [part.replace("\r\n", "\n").replace("\r", "\n").strip() for part in parts]
    if any(not part for part in normalized):
        raise ValueError("--context and --context-file must not be empty")
    combined = "\n\n".join(normalized)
    if len(combined.encode("utf-8")) > max_input_bytes:
        raise ValueError("combined context exceeds max_input_bytes")
    return combined or None


def context_sha256(context: str | None) -> str | None:
    return sha256_bytes(context.encode("utf-8")) if context is not None else None
