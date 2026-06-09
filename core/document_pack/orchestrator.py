from typing import Protocol, TypedDict

from langgraph.graph import END, StateGraph


class DocumentPackWorkflowState(TypedDict, total=False):
    pack_id: str
    content: bytes
    filename: str | None
    pack_dir: object
    capabilities: object
    tool_status: dict[str, str]
    documents: list[object]
    pages_by_document: dict[str, list[object]]
    candidates: list[object]
    processing_warnings: list[str]
    groq_rejected_fields: list[dict]
    groq_provider: str | None
    groq_fallback_used: bool | None
    spec: object
    summary: object
    qa_report: object
    memory_writeback: dict
    trace: list[dict]
    events: list[dict]


class DocumentPackNodeRunner(Protocol):
    def index(self, state: DocumentPackWorkflowState) -> dict: ...

    def extract_pdf_ocr_cad(self, state: DocumentPackWorkflowState) -> dict: ...

    def groq_extract(self, state: DocumentPackWorkflowState) -> dict: ...

    def consolidate(self, state: DocumentPackWorkflowState) -> dict: ...

    def qa(self, state: DocumentPackWorkflowState) -> dict: ...

    def write_artifacts(self, state: DocumentPackWorkflowState) -> dict: ...

    def memory_writeback(self, state: DocumentPackWorkflowState) -> dict: ...


class DocumentPackOrchestrator:
    def __init__(self, runner: DocumentPackNodeRunner) -> None:
        self.runner = runner
        self.graph = self._build_graph()

    def run(self, state: DocumentPackWorkflowState) -> DocumentPackWorkflowState:
        initial_state: DocumentPackWorkflowState = {
            **state,
            "documents": [],
            "pages_by_document": {},
            "candidates": [],
            "processing_warnings": [],
            "groq_rejected_fields": [],
            "trace": [],
            "events": [],
        }
        return self.graph.invoke(initial_state)

    def _build_graph(self):
        graph = StateGraph(DocumentPackWorkflowState)
        graph.add_node("index", self.runner.index)
        graph.add_node("extract_pdf_ocr_cad", self.runner.extract_pdf_ocr_cad)
        graph.add_node("groq_extract", self.runner.groq_extract)
        graph.add_node("consolidate", self.runner.consolidate)
        graph.add_node("qa", self.runner.qa)
        graph.add_node("write_artifacts", self.runner.write_artifacts)
        graph.add_node("memory_writeback", self.runner.memory_writeback)
        graph.set_entry_point("index")
        graph.add_edge("index", "extract_pdf_ocr_cad")
        graph.add_edge("extract_pdf_ocr_cad", "groq_extract")
        graph.add_edge("groq_extract", "consolidate")
        graph.add_edge("consolidate", "qa")
        graph.add_edge("qa", "write_artifacts")
        graph.add_edge("write_artifacts", "memory_writeback")
        graph.add_edge("memory_writeback", END)
        return graph.compile()
