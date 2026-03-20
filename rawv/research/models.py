from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional


ResearchMode = Literal["quick", "normal", "deep"]


@dataclass
class SearchItem:
    title: str
    url: str


@dataclass
class SourceSnapshot:
    title: str
    url: str
    excerpt: str


@dataclass
class BrowserEvidence:
    available: bool
    details: str
    items: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ResearchStep:
    name: str
    output: str


@dataclass
class ResearchResult:
    query: str
    mode: ResearchMode
    answer: str
    spoken_summary: str
    sources: List[SourceSnapshot]
    steps: List[ResearchStep]
    browser_evidence: Optional[BrowserEvidence] = None
