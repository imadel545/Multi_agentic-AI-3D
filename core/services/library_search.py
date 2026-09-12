"""Explainable lexical retrieval over source metadata, never geometry qualification."""

import math
import re
import unicodedata
from collections import Counter

# Domain vocabulary translates concepts; manufacturer names and references remain exact.
_CONCEPTS = (
    {"antenna", "antennas", "antenne", "antennes"},
    {"tower", "towers", "pylone", "pylones"},
    {"lattice", "treillis"},
    {"bracket", "brackets", "support", "supports", "fixation", "fixations"},
    {"cabinet", "cabinets", "armoire", "armoires"},
    {"staircase", "stairs", "stair", "escalier", "escaliers"},
    {"spiral", "helicoidal", "helicoidale", "colimacon", "colimasson"},
    {"tree", "trees", "arbre", "arbres"},
    {"bench", "benches", "banc", "bancs"},
    {"platform", "platforms", "plateforme", "plateformes"},
)
_STOP = {"a", "an", "the", "de", "du", "des", "la", "le", "les", "un", "une", "with", "avec"}


def metadata_tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    normalized = re.sub(r"(\d+)\s+(mm|cm|m)\b", r"\1\2", normalized)
    return set(re.findall(r"[a-z0-9]+", normalized)) - _STOP


class LibraryMetadataSearch:
    def __init__(self, entries: list[dict]):
        self.entries = entries
        self.tokens = [metadata_tokens(entry["relative_path"]) for entry in entries]
        self.filename_tokens = [
            metadata_tokens(entry["relative_path"].rsplit("/", 1)[-1].rsplit(".", 1)[0])
            for entry in entries
        ]
        frequency = Counter(token for tokens in self.tokens for token in tokens)
        self.idf = {token: math.log1p(len(entries) / count) for token, count in frequency.items()}

    def rank(self, query: str, *, claimed_dimension: str | None, extension: str | None):
        requested = metadata_tokens(query)
        groups = {
            token: next((group for group in _CONCEPTS if token in group), {token})
            for token in requested
        }
        ranked = []
        for entry, tokens, filename_tokens in zip(
            self.entries, self.tokens, self.filename_tokens, strict=True
        ):
            if entry["relative_path"].rsplit("/", 1)[-1].startswith("."):
                continue
            if claimed_dimension and entry["claimed_dimension"] != claimed_dimension:
                continue
            if extension and entry["extension"] != extension.lower().lstrip("."):
                continue
            matches = {
                token: sorted(group & tokens) for token, group in groups.items() if group & tokens
            }
            if requested and not matches:
                continue
            # Reference-like tokens carry a strong exact signal; no substring matching.
            score = sum(
                max(self.idf.get(term, 0) for term in terms)
                * (1.2 if token in tokens else 1)
                * (2 if len(groups[token]) == 1 else 1)
                for token, terms in matches.items()
            )
            coverage = len(matches) / len(requested) if requested else 1
            score *= coverage
            # A request that exactly names a file stem must outrank sibling
            # detail drawings with the same path vocabulary. This remains a
            # metadata signal; it never implies geometry qualification.
            if requested and requested == filename_tokens:
                score += sum(self.idf.get(token, 0) for token in requested) * 3
            ranked.append(
                (
                    score,
                    entry,
                    {
                        "method": "corpus_idf_metadata",
                        "matched_terms": matches,
                        "query_coverage": round(coverage, 3),
                        "geometry_verified": False,
                    },
                )
            )
        ranked.sort(
            key=lambda item: (-item[0], bool(item[1].get("duplicate_of")), item[1]["relative_path"])
        )
        seen = set()
        result = []
        for score, entry, evidence in ranked:
            identity = entry.get("content_sha256") or entry["file_id"]
            if identity in seen:
                continue
            seen.add(identity)
            result.append((score, entry, evidence))
        return result
