"""Read optional display metadata from an already verified daily attachment."""

from html.parser import HTMLParser


class _CoreCandidates(HTMLParser):
    def __init__(self):
        super().__init__()
        self.candidates = []

    def handle_starttag(self, tag, attributes):
        if tag == "article":
            attrs = dict(attributes)
            keys = ("data-core-symbol", "data-core-name", "data-core-sector")
            if all(attrs.get(key) for key in keys):
                self.candidates.append(tuple(attrs[key] for key in keys))


def read_core_candidates(body: bytes) -> tuple[tuple[str, str, str], ...]:
    parser = _CoreCandidates()
    parser.feed(body.decode("utf-8"))
    parser.close()
    return tuple(parser.candidates)
