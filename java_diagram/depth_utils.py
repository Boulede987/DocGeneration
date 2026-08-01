"""Bracket/brace-depth-aware string splitting shared by the other modules."""


def close_brace(src: str, open_pos: int) -> int:
    """Return index of } that matches { at open_pos."""
    depth = 0
    for i in range(open_pos, len(src)):
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(src) - 1


def split_top_level(body: str, sep: str) -> tuple[str, str]:
    """Split body at the first occurrence of sep that is at bracket depth 0."""
    depth = 0
    for i, c in enumerate(body):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == sep and depth == 0:
            return body[:i], body[i + 1:]
    return body, ""


def split_bases_raw(raw: str) -> list[str]:
    """Split 'A, B<C,D>, E' by comma respecting <> and () depth."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for c in raw:
        if c in "<(":
            depth += 1
            current.append(c)
        elif c in ">)":
            depth -= 1
            current.append(c)
        elif c == "," and depth == 0:
            p = "".join(current).strip()
            if p:
                parts.append(p)
            current = []
        else:
            current.append(c)
    p = "".join(current).strip()
    if p:
        parts.append(p)
    return parts
