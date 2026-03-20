import os
from typing import Dict, List, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph

from .browser_adapter import BrowserAdapter
from .extract import fetch_source_snapshot
from .models import BrowserEvidence, ResearchMode, ResearchResult, ResearchStep, SearchItem, SourceSnapshot
from .search import run_search


class ResearchState(TypedDict):
    query: str
    mode: ResearchMode
    max_sources: int
    search_limit: int
    search_results: List[Dict[str, str]]
    sources: List[SourceSnapshot]
    answer: str
    spoken_summary: str
    steps: List[ResearchStep]
    browser_evidence: Dict[str, object]


def _mode_config(mode: ResearchMode) -> Dict[str, int]:
    if mode == "quick":
        return {"search_limit": 4, "max_sources": 2}
    if mode == "deep":
        return {"search_limit": 10, "max_sources": 5}
    return {"search_limit": 6, "max_sources": 3}


def _shorten(text: str, max_len: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3] + "..."


def _content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: List[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunks)
    return str(content or "")


def _append_step(state: ResearchState, name: str, output: str) -> None:
    state["steps"].append(ResearchStep(name=name, output=output))


def node_search(state: ResearchState) -> ResearchState:
    results = run_search(state["query"], limit=state["search_limit"], retries=2)
    packed = [{"title": item.title, "url": item.url} for item in results]
    state["search_results"] = packed

    if packed:
        top = "\n".join([f"- {item['title']} ({item['url']})" for item in packed[:5]])
        _append_step(state, "🔎 Search", f"Found {len(packed)} candidate sources:\n{top}")
    else:
        _append_step(state, "🔎 Search", "No web results found. Will fallback to model-only response.")
    return state


def node_browse(state: ResearchState) -> ResearchState:
    snapshots: List[SourceSnapshot] = []
    for item in state["search_results"][: state["max_sources"]]:
        search_item = SearchItem(title=item["title"], url=item["url"])
        source = fetch_source_snapshot(
            item=search_item,
            timeout_seconds=10.0,
            max_chars=3000,
            retries=1,
        )
        if source:
            snapshots.append(source)

    state["sources"] = snapshots

    if snapshots:
        details = "\n".join([f"- [{idx+1}] {s.title}" for idx, s in enumerate(snapshots)])
        _append_step(state, "🌐 Browse", f"Extracted {len(snapshots)} readable sources:\n{details}")
    else:
        _append_step(state, "🌐 Browse", "Could not extract readable source text from search results.")
    return state


def node_browser_evidence(state: ResearchState) -> ResearchState:
    adapter = BrowserAdapter()
    target_url = state["sources"][0].url if state["sources"] else ""
    if target_url:
        evidence = adapter.capture(target_url=target_url, limit=10)
    else:
        evidence = BrowserEvidence(available=False, details="No source URL available for browser evidence.")
    state["browser_evidence"] = {
        "available": evidence.available,
        "details": evidence.details,
        "items": evidence.items,
    }
    _append_step(state, "👁️ Browser Evidence", evidence.details)
    return state


def _build_sources_block(sources: List[SourceSnapshot]) -> str:
    lines: List[str] = []
    for idx, source in enumerate(sources, start=1):
        lines.append(f"[{idx}] {source.title}")
        lines.append(f"URL: {source.url}")
        lines.append(f"Excerpt: {_shorten(source.excerpt, 1200)}")
    return "\n".join(lines)


def node_synthesize(state: ResearchState) -> ResearchState:
    model_name = os.getenv("RAWV_CHAT_MODEL", "llama-3.1-8b-instant")
    llm = ChatGroq(model=model_name, temperature=0.2)

    if state["sources"]:
        sources_block = _build_sources_block(state["sources"])
        user_prompt = (
            f"User question: {state['query']}\n\n"
            "Use only the provided sources. Return:\n"
            "1) A concise answer\n"
            "2) Key evidence bullets with citations [1], [2], ...\n"
            "3) Contradictions/gaps if any\n"
            "4) A one-sentence spoken summary\n\n"
            f"Sources:\n{sources_block}"
        )
    else:
        user_prompt = (
            f"User question: {state['query']}\n\n"
            "No external sources could be extracted. Answer with your best effort and clearly say this is a fallback. "
            "Also include a one-sentence spoken summary."
        )

    system_prompt = (
        "You are RAWV, a transparent research assistant. Be accurate and concise. "
        "When sources exist, do not invent citations."
    )

    response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
    answer = _content_to_text(response.content).strip()

    spoken_prompt = (
        "Convert the following assistant answer to a short spoken response (max 2 sentences), "
        "preserving factual meaning and not adding new claims:\n\n"
        + answer
    )
    spoken_response = llm.invoke(
        [
            SystemMessage(content="You rewrite text for voice output."),
            HumanMessage(content=spoken_prompt),
        ]
    )
    spoken_summary = _shorten(_content_to_text(spoken_response.content).strip(), 260)

    state["answer"] = answer
    state["spoken_summary"] = spoken_summary
    _append_step(state, "🧠 Synthesize", "Built final answer with evidence and a spoken summary.")
    return state


def node_quality_check(state: ResearchState) -> ResearchState:
    flags: List[str] = []
    if state["sources"] and "[1]" not in state["answer"]:
        flags.append("Answer may be missing citation formatting.")
    if len(state["spoken_summary"]) < 10:
        flags.append("Spoken summary is too short; fallback to first sentence of answer.")
        state["spoken_summary"] = _shorten(state["answer"], 220)

    if not flags:
        _append_step(state, "✅ Quality Check", "Checks passed (citations/summary/fallback).")
    else:
        _append_step(state, "✅ Quality Check", "\n".join([f"- {f}" for f in flags]))
    return state


def build_graph():
    builder = StateGraph(ResearchState)
    builder.add_node("search", node_search)
    builder.add_node("browse", node_browse)
    builder.add_node("browser_evidence", node_browser_evidence)
    builder.add_node("synthesize", node_synthesize)
    builder.add_node("quality_check", node_quality_check)

    builder.add_edge(START, "search")
    builder.add_edge("search", "browse")
    builder.add_edge("browse", "browser_evidence")
    builder.add_edge("browser_evidence", "synthesize")
    builder.add_edge("synthesize", "quality_check")
    builder.add_edge("quality_check", END)
    return builder.compile()


class ResearchEngine:
    def __init__(self) -> None:
        self.graph = build_graph()

    def run(self, query: str, mode: ResearchMode = "normal") -> ResearchResult:
        cfg = _mode_config(mode)
        state: ResearchState = {
            "query": query,
            "mode": mode,
            "max_sources": cfg["max_sources"],
            "search_limit": cfg["search_limit"],
            "search_results": [],
            "sources": [],
            "answer": "",
            "spoken_summary": "",
            "steps": [],
            "browser_evidence": {"available": False, "details": "", "items": []},
        }

        result = self.graph.invoke(state)
        return ResearchResult(
            query=result["query"],
            mode=result["mode"],
            answer=result["answer"],
            spoken_summary=result["spoken_summary"],
            sources=result["sources"],
            steps=result["steps"],
            browser_evidence=BrowserEvidence(
                available=bool(result["browser_evidence"].get("available", False)),
                details=str(result["browser_evidence"].get("details", "")),
                items=list(result["browser_evidence"].get("items", [])),
            ),
        )


def run_transparent_research(query: str, mode: ResearchMode = "normal") -> ResearchResult:
    return ResearchEngine().run(query=query, mode=mode)
