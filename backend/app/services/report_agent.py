"""
Report Agent service
Uses LangChain + Zep to implement ReACT-mode simulation report generation

Functions:
1. Generate reports based on simulation requirements and Zep graph information
2. Plan table of contents structure first, then generate section by section
3. Each section uses the ReACT multi-round thinking and reflection mode
4. Supports user conversation, autonomously calling retrieval tools during conversation
"""

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..models.project import ProjectManager
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .claim_ledger import ClaimLedgerBuilder
from .editorial_consolidator import EditorialConsolidator
from .evidence_brief_builder import EvidenceBriefBuilder
from .missing_input_detector import MissingInputDetector
from .quality_gate_evaluator import QualityGateEvaluator
from .quantitative_validator import QuantitativeValidator
from .report_artifacts import (
    ClaimLedgerEntry,
    EvidenceBriefArtifact,
    MissingCriticalInputArtifact,
    QualityGateArtifact,
    QuantitativeCheckArtifact,
    ReportIntentArtifact,
    RunTraceArtifact,
    SearchExecutionArtifact,
)
from .report_intent_analyzer import ReportIntentAnalyzer
from .report_schema_registry import ReportSchema, ReportSchemaRegistry, SchemaSection
from .run_trace_builder import RunTraceBuilder
from .search_plan_builder import SearchPlanBuilder
from .search_service import SearchService
from .verification_manager import VerificationManager
from .zep_tools import (
    ZepToolsService, 
    SearchResult, 
    InsightForgeResult, 
    PanoramaResult,
    InterviewResult
)

logger = get_logger('mirofish.report_agent')


class ReportLogger:
    """
    Report Agent detailed logger

    Generates an agent_log.jsonl file in the report folder, recording every step in detail.
    Each line is a complete JSON object containing timestamp, action type, detailed content, etc.
    """

    def __init__(self, report_id: str):
        """
        Initialize logger

        Args:
            report_id: Report ID, used to determine log file path
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """Ensure the directory containing the log file exists"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _get_elapsed_time(self) -> float:
        """Get elapsed time in seconds from start to now"""
        return (datetime.now() - self.start_time).total_seconds()
    
    def log(
        self,
        action: str,
        stage: str,
        details: Dict[str, Any],
        section_title: str = None,
        section_index: int = None
    ):
        """
        Record a log entry

        Args:
            action: Action type, e.g. 'start', 'tool_call', 'llm_response', 'section_complete', etc.
            stage: Current stage, e.g. 'planning', 'generating', 'completed'
            details: Detailed content dictionary, not truncated
            section_title: Current section title (optional)
            section_index: Current section index (optional)
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details
        }
        
        # Append to JSONL file
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        """Record report generation start"""
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": "Report generation task started"
            }
        )

    def log_planning_start(self):
        """Record outline planning start"""
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": "Starting to plan report outline"}
        )

    def log_planning_context(self, context: Dict[str, Any]):
        """Record context information obtained during planning"""
        self.log(
            action="planning_context",
            stage="planning",
            details={
                "message": "Getting simulation context information",
                "context": context
            }
        )

    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        """Record outline planning completion"""
        self.log(
            action="planning_complete",
            stage="planning",
            details={
                "message": "Outline planning complete",
                "outline": outline_dict
            }
        )

    def log_section_start(self, section_title: str, section_index: int):
        """Record section generation start"""
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": f"Starting to generate section: {section_title}"}
        )
    
    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        """Record ReACT thought process"""
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": f"ReACT round {iteration} thought"
            }
        )
    
    def log_tool_call(
        self, 
        section_title: str, 
        section_index: int,
        tool_name: str, 
        parameters: Dict[str, Any],
        iteration: int
    ):
        """Record tool call"""
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"Calling tool: {tool_name}"
            }
        )
    
    def log_tool_result(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        result: str,
        iteration: int
    ):
        """Record tool call result (complete content, not truncated)"""
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,  # Complete result, not truncated
                "result_length": len(result),
                "message": f"Tool {tool_name} returned result"
            }
        )
    
    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool
    ):
        """Record LLM response (complete content, not truncated)"""
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,  # Complete response, not truncated
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": f"LLM response (tool calls: {has_tool_calls}, final answer: {has_final_answer})"
            }
        )
    
    def log_section_content(
        self,
        section_title: str,
        section_index: int,
        content: str,
        tool_calls_count: int
    ):
        """Record section content generation complete (only records content, does not indicate entire section is complete)"""
        self.log(
            action="section_content",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,  # Complete content, not truncated
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "message": f"Section {section_title} content generation complete"
            }
        )
    
    def log_section_full_complete(
        self,
        section_title: str,
        section_index: int,
        full_content: str
    ):
        """
        Record section generation complete

        Frontend should listen to this log to determine when a section is truly complete and get the full content
        """
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "message": f"Section {section_title} generation complete"
            }
        )
    
    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        """Record report generation complete"""
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": "Report generation complete"
            }
        )

    def log_error(self, error_message: str, stage: str, section_title: str = None):
        """Record error"""
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={
                "error": error_message,
                "message": f"Error occurred: {error_message}"
            }
        )


class ReportConsoleLogger:
    """
    Report Agent console logger

    Writes console-style logs (INFO, WARNING, etc.) to a console_log.txt file in the report folder.
    These logs differ from agent_log.jsonl in that they are plain text console-style output.
    """

    def __init__(self, report_id: str):
        """
        Initialize console logger

        Args:
            report_id: Report ID, used to determine log file path
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        self._ensure_log_file()
        self._file_handler = None
        self._setup_file_handler()
    
    def _ensure_log_file(self):
        """Ensure the directory containing the log file exists"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _setup_file_handler(self):
        """Set up file handler to also write logs to file"""
        import logging

        # Create file handler
        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode='a',
            encoding='utf-8'
        )
        self._file_handler.setLevel(logging.INFO)
        
        # Use the same concise format as console
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self._file_handler.setFormatter(formatter)
        
        # Add to report_agent-related loggers
        loggers_to_attach = [
            'mirofish.report_agent',
            'mirofish.zep_tools',
        ]
        
        for logger_name in loggers_to_attach:
            target_logger = logging.getLogger(logger_name)
            # Avoid adding duplicate handlers
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)
    
    def close(self):
        """Close file handler and remove from logger"""
        import logging
        
        if self._file_handler:
            loggers_to_detach = [
                'mirofish.report_agent',
                'mirofish.zep_tools',
            ]
            
            for logger_name in loggers_to_detach:
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)
            
            self._file_handler.close()
            self._file_handler = None
    
    def __del__(self):
        """Ensure file handler is closed on destruction"""
        self.close()


class ReportStatus(str, Enum):
    """Report status"""
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """Report section"""
    title: str
    content: str = ""
    key: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "key": self.key,
            "description": self.description,
        }

    def to_markdown(self, level: int = 2) -> str:
        """Convert to Markdown format"""
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        return md


@dataclass
class ReportOutline:
    """Report outline"""
    title: str
    summary: str
    sections: List[ReportSection]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections]
        }
    
    def to_markdown(self) -> str:
        """Convert to Markdown format"""
        md = f"# {self.title}\n\n"
        md += f"> {self.summary}\n\n"
        for section in self.sections:
            md += section.to_markdown()
        return md


@dataclass
class Report:
    """Complete report"""
    report_id: str
    simulation_id: str
    graph_id: str
    simulation_requirement: str
    status: ReportStatus
    project_id: str = ""
    outline: Optional[ReportOutline] = None
    markdown_content: str = ""
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    intent: Optional[Dict[str, Any]] = None
    schema: Optional[Dict[str, Any]] = None
    evidence_summary: Optional[Dict[str, Any]] = None
    verification_summary: Optional[Dict[str, Any]] = None
    missing_critical_inputs: List[Dict[str, Any]] = field(default_factory=list)
    quantitative_checks: List[Dict[str, Any]] = field(default_factory=list)
    quality_gates: List[Dict[str, Any]] = field(default_factory=list)
    run_trace: Optional[Dict[str, Any]] = None
    search_plan: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "project_id": self.project_id,
            "status": self.status.value,
            "outline": self.outline.to_dict() if self.outline else None,
            "markdown_content": self.markdown_content,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "intent": self.intent,
            "schema": self.schema,
            "evidence_summary": self.evidence_summary,
            "verification_summary": self.verification_summary,
            "missing_critical_inputs": self.missing_critical_inputs,
            "quantitative_checks": self.quantitative_checks,
            "quality_gates": self.quality_gates,
            "run_trace": self.run_trace,
            "search_plan": self.search_plan,
        }


# ═══════════════════════════════════════════════════════════════
# Prompt Template Constants
# ═══════════════════════════════════════════════════════════════

# ── Tool descriptions ──

TOOL_DESC_INSIGHT_FORGE = """\
[Deep Insight Retrieval - Powerful Research Tool]
This is our powerful retrieval function, designed specifically for deep analysis of research data. It will:
1. Automatically decompose your question into multiple sub-questions
2. Retrieve information from the research data graph across multiple dimensions
3. Integrate the results of semantic search, entity analysis, and relationship chain tracking
4. Return the most comprehensive and in-depth retrieval content

[Use Cases]
- Need to deeply analyze a topic
- Need to understand multiple aspects of an event
- Need to obtain rich material to support report sections

[Return Content]
- Relevant facts verbatim (can be quoted directly)
- Core entity insights
- Relationship chain analysis"""

TOOL_DESC_PANORAMA_SEARCH = """\
[Breadth Search - Get Full View]
This tool is used to get a complete panoramic view of research data, especially suitable for understanding event evolution. It will:
1. Get all relevant nodes and relationships
2. Distinguish between currently valid facts and historical/expired facts
3. Help you understand how the situation has evolved

[Use Cases]
- Need to understand the complete development timeline of an event
- Need to compare changes at different stages
- Need to obtain comprehensive entity and relationship information

[Return Content]
- Currently valid facts (latest research data)
- Historical/expired facts (evolution records)
- All involved entities"""

TOOL_DESC_QUICK_SEARCH = """\
[Simple Search - Quick Retrieval]
A lightweight fast retrieval tool, suitable for simple and direct information queries.

[Use Cases]
- Need to quickly find specific information
- Need to verify a fact
- Simple information retrieval

[Return Content]
- List of facts most relevant to the query"""

TOOL_DESC_INTERVIEW_AGENTS = """\
[Deep Interview - Real Agent Interview (Dual Platform)]
Calls the OASIS simulation environment's interview API to conduct real interviews with running simulation Agents!
This is not LLM simulation, but calling real interview interfaces to get raw answers from simulation Agents.
By default interviews simultaneously on both Twitter and Reddit platforms for more comprehensive perspectives.

Function flow:
1. Automatically reads persona files to understand all simulation Agents
2. Intelligently selects Agents most relevant to the interview topic (e.g., students, media, officials, etc.)
3. Automatically generates interview questions
4. Calls /api/simulation/interview/batch to conduct real interviews on both platforms
5. Integrates all interview results to provide multi-perspective analysis

[Use Cases]
- Need to understand event opinions from different role perspectives (what do students think? media? officials?)
- Need to collect opinions and positions from multiple parties
- Need to get real answers from simulation Agents (from OASIS simulation environment)
- Want to make reports more vivid with "interview transcripts"

[Return Content]
- Identity information of interviewed Agents
- Interview answers from each Agent on Twitter and Reddit platforms
- Key quotes (can be cited directly)
- Interview summary and perspective comparison

[Important] Requires OASIS simulation environment to be running to use this feature!"""

TOOL_DESC_WEB_SEARCH = """\
[Web Search - Real-World Data Grounding]
Search the real-world web to ground simulation predictions against actual data, news, and expert analysis.

[Use Cases]
- Cross-reference simulation predictions with real-world data
- Find background context and recent developments related to the research topic
- Verify whether simulation outcomes align with real-world trends
- Add verifiable citations (URLs) to the report

[Return Content]
- Web search answer synthesized from multiple sources
- Citations with URLs, titles, and snippets
- Real-world context to complement simulation data"""

TOOL_DESC_FACT_CHECK = """\
[Fact Check - Verify Claims]
Verify a specific claim by searching for supporting or contradicting evidence on the web.

[Use Cases]
- Verify whether a simulation-derived prediction is supported by real-world evidence
- Check factual claims before including them in the report
- Identify claims that should be flagged as [UNVERIFIED — SIMULATION-DERIVED]

[Return Content]
- Verdict: supported, contradicted, or inconclusive
- Confidence score (0.0 to 1.0)
- Explanation of the evidence
- Supporting and contradicting sources with URLs"""

TOOL_DESC_DELIBERATION_DATA = """\
[Deliberation Data - Debate, Voting, and Synthesis]
Retrieve the structured adversarial council outputs tied to this simulation.

[Use Cases]
- Quote arguments from the debate directly
- Inspect voting splits and contested dimensions
- Pull the synthesis without relying only on the saved report text
- Compare simulation-world retrieval with the council's internal deliberation

[Return Content]
- Debate summary with round-by-round arguments
- Voting dimensions, percentages, and contested flags
- Final synthesis text when available"""

# ── Outline planning prompt ──

PLAN_SYSTEM_PROMPT = """\
You are designing an evidence-first report outline.

Choose a structure that fits the task and the available evidence.

Rules:
- Do not assume the report is a prediction report.
- Treat simulation as optional exploratory evidence unless the task is clearly forecast or scenario-oriented.
- Prefer structures that separate verified facts, inference, missing inputs, constraints, and uncertainty.
- Keep the outline useful for real decision-making.

Return valid JSON:
{
  "title": "Report title",
  "summary": "One-sentence report summary",
  "sections": [
    {
      "title": "Section title",
      "description": "Why this section exists"
    }
  ]
}"""

PLAN_USER_PROMPT_TEMPLATE = """\
Requirement: {simulation_requirement}

Evidence context:
- Graph nodes: {total_nodes}
- Graph edges: {total_edges}
- Entity types: {entity_types}
- Active entities: {total_entities}
- Sample graph facts:
{related_facts_json}

Design the most appropriate report structure for this task."""

# ── Section generation prompt ──

SECTION_SYSTEM_PROMPT_TEMPLATE = """\
You are an analytical report engine writing one section of a domain-agnostic report.

Report title: {report_title}
Report summary: {report_summary}
Requirement: {simulation_requirement}
Current section: {section_title}

Rules:
- Use uploaded source material and externally grounded evidence as the primary anchors.
- Use graph retrieval as structured context.
- Use simulation only when it genuinely adds value, and never present simulation-only claims as verified facts.
- Separate verified facts from inference.
- State uncertainty honestly when evidence is weak, stale, narrow, or contradictory.
- Avoid repetition with prior sections.
- Do not use Markdown headings inside the section body; the system adds the section heading.

Tool policy:
- Tools are optional when the supplied evidence is already sufficient.
- If you need missing evidence, prefer web_search or fact_check for fresh external grounding.
- Use simulation or deliberation tools only when the section explicitly needs stress-testing, stakeholder reactions, or objections.

Available tools:
{tools_description}

Reply either with one tool call or with `Final Answer:` followed by the section body."""

SECTION_USER_PROMPT_TEMPLATE = """\
Completed section content:
{previous_content}

Current section: {section_title}

Use the curated evidence context supplied below. Keep the section distinct from prior sections, do not invent unsupported claims, and do not include headings inside the body.

If the supplied evidence is sufficient, output `Final Answer:` directly. If evidence is missing and likely recoverable, call one tool."""

# ── ReACT loop message templates ──

REACT_OBSERVATION_TEMPLATE = """\
Observation (retrieval result):

═══ Tool {tool_name} returned ═══
{result}

═══════════════════════════════════════════════════════════════
Tools called {tool_calls_count}/{max_tool_calls} times (used: {used_tools_str}){unused_hint}
- If information is sufficient: output section content beginning with "Final Answer:"
- If more information needed: call a tool to continue retrieval
═══════════════════════════════════════════════════════════════"""

REACT_INSUFFICIENT_TOOLS_MSG = (
    "[Note] The section still appears under-evidenced. You called {tool_calls_count} tools and the target is {min_tool_calls}. "
    "If you still need evidence, call another tool; otherwise finalize with explicit uncertainty. {unused_hint}"
)

REACT_INSUFFICIENT_TOOLS_MSG_ALT = (
    "The section may still need more evidence. You called {tool_calls_count} tools and the target is {min_tool_calls}. "
    "Call another tool if needed, or finalize with clear uncertainty labeling. {unused_hint}"
)

REACT_TOOL_LIMIT_MSG = (
    "Tool call limit reached ({tool_calls_count}/{max_tool_calls}), cannot call more tools. "
    'Please immediately output section content beginning with "Final Answer:" based on obtained information.'
)

REACT_UNUSED_TOOLS_HINT = "\n💡 You haven't used yet: {unused_list}, suggest trying different tools to get multi-perspective information"

REACT_FORCE_FINAL_MSG = "Tool call limit reached, please output Final Answer: directly and generate section content."

SECTION_REPAIR_SYSTEM_PROMPT = """\
You repair malformed analytical report section drafts.

Rules:
- Preserve the existing meaning unless the draft is clearly broken.
- Do not add new facts not already present in the draft or evidence context.
- Remove raw note fragments, orphan markdown markers, duplicate headings, and truncated endings.
- Return only the repaired section body, with no heading and no commentary."""

SECTION_REPAIR_USER_PROMPT_TEMPLATE = """\
Section title: {section_title}

Evidence context:
{evidence_context}

Draft to repair:
{draft}

Return a clean, complete section body."""

# ── Chat prompt ──

CHAT_SYSTEM_PROMPT_TEMPLATE = """\
You are a concise report intelligence assistant.

Requirement: {simulation_requirement}

Generated report:
{report_content}

Rules:
1. Prioritize answers grounded in the report and its evidence.
2. Distinguish verified facts from inference when relevant.
3. Only call tools when the report content is insufficient.
4. When using web_search or fact_check, surface the most relevant source URLs.
5. Use deliberation or simulation tools only when the question is explicitly about those artifacts.

Available tools:
{tools_description}

Tool call format:
<tool_call>
{{"name": "tool_name", "parameters": {{"param_name": "param_value"}}}}
</tool_call>

Answer style:
- Concise and direct
- Conclusion first, then support
- Mention uncertainty honestly"""

CHAT_OBSERVATION_SUFFIX = "\n\nPlease answer the question concisely."


# ═══════════════════════════════════════════════════════════════
# ReportAgent Main Class
# ═══════════════════════════════════════════════════════════════


class ReportAgent:
    """
    Report Agent - Simulation report generation agent

    Uses ReACT (Reasoning + Acting) mode:
    1. Planning phase: Analyze simulation requirements, plan report table of contents structure
    2. Generation phase: Generate content section by section, each section can call tools multiple times to get information
    3. Reflection phase: Check content completeness and accuracy
    """

    # Maximum tool calls per section
    MAX_TOOL_CALLS_PER_SECTION = 5

    # Maximum reflection rounds
    MAX_REFLECTION_ROUNDS = 3

    # Maximum tool calls per chat
    MAX_TOOL_CALLS_PER_CHAT = 2
    
    def __init__(
        self,
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        zep_tools: Optional[ZepToolsService] = None,
        deliberation_session_id: Optional[str] = None,
        include_quality_assessment: bool = True,
        project_id: str = "",
        search_service: Optional[SearchService] = None,
    ):
        """
        Initialize Report Agent

        Args:
            graph_id: Graph ID
            simulation_id: Simulation ID
            simulation_requirement: Simulation requirement description
            llm_client: LLM client (optional)
            zep_tools: Zep tools service (optional)
            deliberation_session_id: Optional deliberation session to include in report
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement
        self.deliberation_session_id = deliberation_session_id
        self.include_quality_assessment = include_quality_assessment
        self.project_id = project_id

        self.llm = llm_client or LLMClient()
        self.zep_tools = zep_tools or ZepToolsService()
        self.search_service = search_service or SearchService()
        self.intent_analyzer = ReportIntentAnalyzer()
        self.schema_registry = ReportSchemaRegistry()
        self.search_plan_builder = SearchPlanBuilder(self.llm)
        self.evidence_brief_builder = EvidenceBriefBuilder()
        self.claim_ledger_builder = ClaimLedgerBuilder()
        self.missing_input_detector = MissingInputDetector()
        self.quantitative_validator = QuantitativeValidator()
        self.editorial_consolidator = EditorialConsolidator()
        self.quality_gate_evaluator = QualityGateEvaluator()
        self.run_trace_builder = RunTraceBuilder()
        self.verification_manager = VerificationManager(self.search_service)

        self.current_intent: Optional[ReportIntentArtifact] = None
        self.current_schema: Optional[ReportSchema] = None
        self.current_evidence_brief: Optional[EvidenceBriefArtifact] = None
        self.current_claim_ledger: List[ClaimLedgerEntry] = []
        self.current_missing_inputs: List[MissingCriticalInputArtifact] = []
        self.current_quantitative_checks: List[QuantitativeCheckArtifact] = []
        self.current_quality_gates: List[QualityGateArtifact] = []
        self.current_run_trace: Optional[RunTraceArtifact] = None
        self.current_search_plan: List[Dict[str, Any]] = []

        # Tool definitions
        self.tools = self._define_tools()

        # Logger (initialized in generate_report)
        self.report_logger: Optional[ReportLogger] = None
        # Console logger (initialized in generate_report)
        self.console_logger: Optional[ReportConsoleLogger] = None

        logger.info(f"ReportAgent initialized: graph_id={graph_id}, simulation_id={simulation_id}")
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """Define available tools"""
        return {
            "insight_forge": {
                "name": "insight_forge",
                "description": TOOL_DESC_INSIGHT_FORGE,
                "parameters": {
                    "query": "The question or topic you want to deeply analyze",
                    "report_context": "Current report section context (optional, helps generate more precise sub-questions)"
                }
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": TOOL_DESC_PANORAMA_SEARCH,
                "parameters": {
                    "query": "Search query, used for relevance ranking",
                    "include_expired": "Whether to include expired/historical content (default True)"
                }
            },
            "quick_search": {
                "name": "quick_search",
                "description": TOOL_DESC_QUICK_SEARCH,
                "parameters": {
                    "query": "Search query string",
                    "limit": "Number of results to return (optional, default 10)"
                }
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": TOOL_DESC_INTERVIEW_AGENTS,
                "parameters": {
                    "interview_topic": "Interview topic or requirement description (e.g., 'understand student views on the dormitory formaldehyde incident')",
                    "max_agents": "Maximum number of Agents to interview (optional, default 5, max 10)"
                }
            },
            "web_search": {
                "name": "web_search",
                "description": TOOL_DESC_WEB_SEARCH,
                "parameters": {
                    "query": "Web search query string",
                    "context": "Optional context to guide the search (e.g., research topic or section being written)"
                }
            },
            "fact_check": {
                "name": "fact_check",
                "description": TOOL_DESC_FACT_CHECK,
                "parameters": {
                    "claim": "The specific claim to fact-check"
                }
            },
            "deliberation_data": {
                "name": "deliberation_data",
                "description": TOOL_DESC_DELIBERATION_DATA,
                "parameters": {
                    "focus": "Optional focus: debate, voting, synthesis, or all",
                    "max_arguments": "Maximum number of debate arguments to include (optional, default 12)"
                }
            }
        }
    
    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """
        Execute tool call

        Args:
            tool_name: Tool name
            parameters: Tool parameters
            report_context: Report context (for InsightForge)

        Returns:
            Tool execution result (text format)
        """
        logger.info(f"Executing tool: {tool_name}, parameters: {parameters}")
        
        try:
            if tool_name == "insight_forge":
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                result = self.zep_tools.insight_forge(
                    graph_id=self.graph_id,
                    query=query,
                    simulation_requirement=self.simulation_requirement,
                    report_context=ctx
                )
                return result.to_text()
            
            elif tool_name == "panorama_search":
                # Breadth search - get full view
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                result = self.zep_tools.panorama_search(
                    graph_id=self.graph_id,
                    query=query,
                    include_expired=include_expired
                )
                return result.to_text()
            
            elif tool_name == "quick_search":
                # Simple search - quick retrieval
                query = parameters.get("query", "")
                limit = parameters.get("limit", 10)
                if isinstance(limit, str):
                    limit = int(limit)
                result = self.zep_tools.quick_search(
                    graph_id=self.graph_id,
                    query=query,
                    limit=limit
                )
                return result.to_text()
            
            elif tool_name == "interview_agents":
                # Deep interview - call real OASIS interview API to get simulation Agent answers (dual platform)
                interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = parameters.get("max_agents", 5)
                if isinstance(max_agents, str):
                    max_agents = int(max_agents)
                max_agents = min(max_agents, 10)
                result = self.zep_tools.interview_agents(
                    simulation_id=self.simulation_id,
                    interview_requirement=interview_topic,
                    simulation_requirement=self.simulation_requirement,
                    max_agents=max_agents
                )
                return result.to_text()
            
            elif tool_name == "web_search":
                # Web search - ground claims in real-world data
                query = parameters.get("query", "")
                context = parameters.get("context", "")
                result = self.search_service.search(
                    query=query,
                    context=context,
                    intent=parameters.get("intent", "discovery"),
                    report_question=parameters.get("report_question", self.simulation_requirement),
                    evidence_type=parameters.get("evidence_type", "section_support"),
                )
                output = f"### Web Search: {query}\n\n{result.answer}\n"
                if result.citations:
                    output += "\n**Sources:**\n"
                    for c in result.citations:
                        output += f"- [{c.title}]({c.url}): {c.snippet}\n"
                return output

            elif tool_name == "fact_check":
                # Fact check - verify claims against web evidence
                claim = parameters.get("claim", "")
                result = self.search_service.fact_check(claim=claim)
                output = f"### Fact Check: {claim}\n\n"
                output += f"**Verdict:** {result.verdict} (confidence: {result.confidence:.1%})\n"
                output += f"**Explanation:** {result.explanation}\n"
                if result.supporting_sources:
                    output += "\n**Supporting Sources:**\n"
                    for c in result.supporting_sources:
                        output += f"- [{c.title}]({c.url}): {c.snippet}\n"
                if result.contradicting_sources:
                    output += "\n**Contradicting Sources:**\n"
                    for c in result.contradicting_sources:
                        output += f"- [{c.title}]({c.url}): {c.snippet}\n"
                return output

            elif tool_name == "deliberation_data":
                focus = parameters.get("focus", "all")
                max_arguments = parameters.get("max_arguments", 12)
                if isinstance(max_arguments, str):
                    max_arguments = int(max_arguments)
                return self._build_deliberation_tool_output(
                    focus=str(focus or "all"),
                    max_arguments=max(1, min(int(max_arguments), 24)),
                )

            # ========== Backward-compatible old tools (internally redirected to new tools) ==========

            elif tool_name == "search_graph":
                # Redirect to quick_search
                logger.info("search_graph redirected to quick_search")
                return self._execute_tool("quick_search", parameters, report_context)
            
            elif tool_name == "get_graph_statistics":
                result = self.zep_tools.get_graph_statistics(self.graph_id)
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_entity_summary":
                entity_name = parameters.get("entity_name", "")
                result = self.zep_tools.get_entity_summary(
                    graph_id=self.graph_id,
                    entity_name=entity_name
                )
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_simulation_context":
                # Redirect to insight_forge, as it is more powerful
                logger.info("get_simulation_context redirected to insight_forge")
                query = parameters.get("query", self.simulation_requirement)
                return self._execute_tool("insight_forge", {"query": query}, report_context)
            
            elif tool_name == "get_entities_by_type":
                entity_type = parameters.get("entity_type", "")
                nodes = self.zep_tools.get_entities_by_type(
                    graph_id=self.graph_id,
                    entity_type=entity_type
                )
                result = [n.to_dict() for n in nodes]
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            else:
                return f"Unknown tool: {tool_name}. Please use one of: insight_forge, panorama_search, quick_search, interview_agents, web_search, fact_check, deliberation_data"

        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}, error: {str(e)}")
            return f"Tool execution failed: {str(e)}"

    # Set of valid tool names, used to validate bare JSON fallback parsing
    VALID_TOOL_NAMES = {"insight_forge", "panorama_search", "quick_search", "interview_agents", "web_search", "fact_check", "deliberation_data"}

    def _get_deliberation_session(self):
        try:
            from ..models.deliberation_manager import DeliberationManager

            if self.deliberation_session_id:
                return DeliberationManager.get(self.deliberation_session_id)

            delib_session = DeliberationManager.get_by_simulation(self.simulation_id)
            if delib_session:
                self.deliberation_session_id = delib_session.session_id
            return delib_session
        except Exception as e:
            logger.warning(f"Failed to load deliberation session: {e}")
            return None

    def _build_deliberation_tool_output(self, focus: str = "all", max_arguments: int = 12) -> str:
        delib_session = self._get_deliberation_session()
        if not delib_session:
            return "### Deliberation Data\n\nNo deliberation session is available for this simulation."

        focus_value = (focus or "all").strip().lower()
        include_debate = focus_value in {"all", "debate"}
        include_voting = focus_value in {"all", "voting"}
        include_synthesis = focus_value in {"all", "synthesis"}

        output = [
            "### Deliberation Data",
            "",
            f"- Session ID: {delib_session.session_id}",
            f"- Topic: {delib_session.topic}",
            f"- Status: {delib_session.status.value}",
            f"- Debate rounds: {len(delib_session.rounds)}",
        ]

        if include_debate:
            output.extend(["", "#### Debate"])
            argument_count = 0
            for rnd in delib_session.rounds:
                output.append(f"- Round {rnd.round_number}")
                for arg in rnd.arguments:
                    if argument_count >= max_arguments:
                        break
                    label = "OPTIMIST" if arg.position == "optimist" else "PESSIMIST"
                    output.append(
                        f"  - [{label}] {arg.member_id} ({arg.confidence:.0%} confidence): {arg.content[:300]}"
                    )
                    argument_count += 1
                if argument_count >= max_arguments:
                    break
            if argument_count == 0:
                output.append("- No debate arguments recorded yet.")

        if include_voting:
            output.extend(["", "#### Voting Results"])
            dims = delib_session.vote_results.get("dimensions", {}) if delib_session.vote_results else {}
            if dims:
                for dim_name, dim_data in dims.items():
                    pct = dim_data.get("raw_percentage", {})
                    output.append(
                        "- "
                        + f"{dim_name}: "
                        + f"{dim_data.get('position_a_label', 'A')}={pct.get('position_a', 0)}%, "
                        + f"{dim_data.get('position_b_label', 'B')}={pct.get('position_b', 0)}%, "
                        + f"Neither={pct.get('neither', 0)}% "
                        + f"(votes={dim_data.get('total_votes', 0)})"
                    )
                contested = delib_session.vote_results.get("contested_dimensions", [])
                neither = delib_session.vote_results.get("neither_triggered", [])
                if contested:
                    output.append(f"- Contested dimensions: {', '.join(contested)}")
                if neither:
                    output.append(f"- Neither threshold triggered: {', '.join(neither)}")
            else:
                output.append("- No voting results recorded yet.")

        if include_synthesis:
            output.extend(["", "#### Synthesis"])
            if delib_session.synthesis:
                output.append(delib_session.synthesis[:2500])
            else:
                output.append("No synthesis recorded yet.")

        return "\n".join(output)

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        Parse tool calls from LLM response

        Supported formats (by priority):
        1. <tool_call>{"name": "tool_name", "parameters": {...}}</tool_call>
        2. Bare JSON (entire response or single line is a tool call JSON)
        """
        tool_calls = []

        # Format 1: XML style (standard format)
        xml_pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            try:
                call_data = json.loads(match.group(1))
                tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        if tool_calls:
            return tool_calls

        # Format 2: Fallback - LLM outputs bare JSON directly (without <tool_call> tags)
        # Only tried when format 1 fails to match, to avoid false matches in body JSON
        stripped = response.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                call_data = json.loads(stripped)
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
                    return tool_calls
            except json.JSONDecodeError:
                pass

        # Response may contain thinking text + bare JSON, try to extract the last JSON object
        json_pattern = r'(\{"(?:name|tool)"\s*:.*?\})\s*$'
        match = re.search(json_pattern, stripped, re.DOTALL)
        if match:
            try:
                call_data = json.loads(match.group(1))
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        return tool_calls

    def _is_valid_tool_call(self, data: dict) -> bool:
        """Validate whether the parsed JSON is a valid tool call"""
        # Supports both {"name": ..., "parameters": ...} and {"tool": ..., "params": ...} key formats
        tool_name = data.get("name") or data.get("tool")
        if tool_name and tool_name in self.VALID_TOOL_NAMES:
            # Normalize key names to name / parameters
            if "tool" in data:
                data["name"] = data.pop("tool")
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            return True
        return False
    
    def _build_deliberation_context_for_section(self, section_title: str) -> str:
        """Build deliberation context to inject into section generation when relevant."""
        # Check if the section title suggests it needs deliberation data
        deliberation_keywords = [
            'council', 'deliberation', 'debate', 'adversarial', 'voting',
            'consensus', 'synthesis', 'forecast', 'contested', 'optimist',
            'pessimist', 'bull', 'bear', 'argument', 'position',
            'risk', 'opportunity', 'outlook', 'assessment', 'conclusion',
            'recommendation', 'summary', 'executive'
        ]
        title_lower = section_title.lower()
        if not any(kw in title_lower for kw in deliberation_keywords):
            return ""

        try:
            delib_session = self._get_deliberation_session()
            if not delib_session:
                return ""

            ctx = "\n\n[Adversarial Council Deliberation Data - USE THIS for writing this section]\n"
            ctx += f"Topic: {delib_session.topic}\n"
            ctx += f"Debate Rounds: {len(delib_session.rounds)}\n"

            # Include council members
            if delib_session.optimist_council:
                ctx += "\nOptimist Council Members:\n"
                for m in delib_session.optimist_council:
                    ctx += f"  - {m.name} ({m.tier})\n"
            if delib_session.pessimist_council:
                ctx += "\nPessimist Council Members:\n"
                for m in delib_session.pessimist_council:
                    ctx += f"  - {m.name} ({m.tier})\n"

            # Include arguments (more generous than the planning phase)
            for rnd in delib_session.rounds:
                ctx += f"\n--- Round {rnd.round_number} ---\n"
                for arg in rnd.arguments:
                    label = "OPTIMIST" if arg.position == "optimist" else "PESSIMIST"
                    cred = f" [credibility: {arg.credibility_score:.0%}]" if arg.credibility_score is not None else ""
                    ctx += f"[{label} - {arg.member_id}]{cred} (confidence: {arg.confidence:.0%})\n"
                    ctx += f"{arg.content[:500]}\n"
                    if arg.evidence:
                        ctx += "Evidence: " + "; ".join(arg.evidence[:5]) + "\n"

            # Include voting results
            if delib_session.vote_results:
                ctx += "\n[Voting Results]\n"
                dims = delib_session.vote_results.get("dimensions", {})
                for dim_name, dim_data in dims.items():
                    pct = dim_data.get("raw_percentage", {})
                    ctx += f"  {dim_name}: "
                    ctx += f"{dim_data.get('position_a_label', 'A')}={pct.get('position_a', 0)}%, "
                    ctx += f"{dim_data.get('position_b_label', 'B')}={pct.get('position_b', 0)}%, "
                    ctx += f"Neither={pct.get('neither', 0)}%\n"

                contested = delib_session.vote_results.get("contested_dimensions", [])
                if contested:
                    ctx += f"Contested dimensions (40-60% split): {', '.join(contested)}\n"
                neither = delib_session.vote_results.get("neither_triggered", [])
                if neither:
                    ctx += f"Neither threshold triggered (>20%): {', '.join(neither)}\n"

            # Include synthesis
            if delib_session.synthesis:
                ctx += f"\n[Synthesis]\n{delib_session.synthesis[:2000]}\n"

            # Include quality signals
            if delib_session.quality_signals:
                ctx += f"\n[Quality Signals]\n"
                for signal in delib_session.quality_signals:
                    if isinstance(signal, dict):
                        for key, val in signal.items():
                            ctx += f"  {key}: {val}\n"
                    else:
                        ctx += f"  {signal}\n"

            logger.info(f"Deliberation context injected for section: {section_title}")
            return ctx

        except Exception as e:
            logger.warning(f"Failed to build deliberation context for section '{section_title}': {e}")
            return ""

    def _get_tools_description(self) -> str:
        """Generate tool description text"""
        desc_parts = ["Available tools:"]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  Parameters: {params_desc}")
        return "\n".join(desc_parts)

    def _load_project(self):
        if not self.project_id:
            return None
        return ProjectManager.get_project(self.project_id)

    def _get_graph_context(self) -> Dict[str, Any]:
        try:
            return self.zep_tools.get_simulation_context(
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement,
            )
        except Exception as exc:
            logger.warning(f"Failed to load graph context: {exc}")
            return {}

    def _get_deliberation_outputs(self) -> List[str]:
        session = self._get_deliberation_session()
        if not session:
            return []
        outputs = []
        for rnd in session.rounds[:3]:
            for arg in rnd.arguments[:4]:
                outputs.append(arg.content[:400])
        if session.synthesis:
            outputs.append(session.synthesis[:1000])
        return outputs[:12]

    def _build_search_source_material(self, project_summary: str, extracted_text: str, graph_context: dict) -> List[Dict[str, str]]:
        chunks: List[Dict[str, str]] = []
        if self.simulation_requirement:
            chunks.append({
                "id": "requirement",
                "label": "requirement",
                "text": self.simulation_requirement,
            })
        if project_summary:
            chunks.append({
                "id": "project_summary",
                "label": "project_summary",
                "text": project_summary,
            })
        if extracted_text:
            paragraphs = [part.strip() for part in re.split(r"\n\s*\n", extracted_text) if part.strip()]
            for index, paragraph in enumerate(paragraphs[:4], start=1):
                chunks.append({
                    "id": f"source_document_{index}",
                    "label": "source_document",
                    "text": paragraph[:900],
                })
        for index, fact in enumerate(graph_context.get("related_facts", [])[:4], start=1):
            fact_text = str(fact.get("fact") or fact.get("content") or fact.get("text") or fact) if isinstance(fact, dict) else str(fact)
            if fact_text.strip():
                chunks.append({
                    "id": f"graph_fact_{index}",
                    "label": "graph_fact",
                    "text": fact_text[:600],
                })
        for index, output in enumerate(self._get_deliberation_outputs()[:3], start=1):
            if output.strip():
                chunks.append({
                    "id": f"deliberation_{index}",
                    "label": "deliberation",
                    "text": output[:700],
                })
        return chunks

    def _prepare_report_intelligence(self) -> None:
        project = self._load_project()
        graph_context = self._get_graph_context()
        project_summary = getattr(project, "analysis_summary", "") if project else ""
        extracted_text = ProjectManager.get_extracted_text(project.project_id) if project else ""

        self.current_intent = self.intent_analyzer.analyze(
            requirement=self.simulation_requirement,
            project_summary=project_summary or "",
            document_context=extracted_text or "",
        )
        self.current_schema = self.schema_registry.get_schema(self.current_intent)

        search_source_material = self._build_search_source_material(
            project_summary=project_summary or "",
            extracted_text=extracted_text or "",
            graph_context=graph_context,
        )
        search_plan_objects = self.search_plan_builder.build(
            self.current_intent,
            source_material=search_source_material,
        )
        self.current_search_plan = [query.to_dict() for query in search_plan_objects]

        search_results = self.search_service.search_plan(self.current_search_plan)
        self.current_search_plan = [
            {**query.to_dict(), "produced_usable_evidence": result.usable_evidence, "citations_used": len(result.citations)}
            for query, result in zip(search_plan_objects, search_results)
        ]

        simulation_outputs = []
        if self.current_intent.simulation_mode in {"required", "optional", "useful_but_optional"}:
            simulation_outputs = [
                str(item) for item in graph_context.get("related_facts", [])[:8]
            ]

        self.current_evidence_brief = self.evidence_brief_builder.build(
            project=project,
            requirement=self.simulation_requirement,
            graph_context=graph_context,
            search_results=search_results,
            simulation_outputs=simulation_outputs,
            deliberation_outputs=self._get_deliberation_outputs(),
        )
        self.current_claim_ledger = self.claim_ledger_builder.build(
            self.current_intent,
            self.current_evidence_brief,
            schema_sections=[section.title for section in self.current_schema.sections] if self.current_schema else [],
        )
        self.current_claim_ledger = self.verification_manager.verify_claims(
            self.current_claim_ledger,
            search_plan_objects,
        )
        self.current_missing_inputs = self.missing_input_detector.detect(
            self.current_intent,
            self.current_evidence_brief,
            search_plan=self.current_search_plan,
            claim_ledger=self.current_claim_ledger,
        )

    def _build_report_title_and_summary(self) -> Dict[str, str]:
        intent = self.current_intent
        schema = self.current_schema
        evidence = self.current_evidence_brief
        if not intent or not schema or not evidence:
            return {
                "title": "Report",
                "summary": "Evidence-grounded analytical report.",
            }

        entity_part = evidence.key_entities[0] if evidence.key_entities else self.simulation_requirement[:60]
        entity_part = self._clean_structured_text(entity_part) or entity_part.strip() or "Subject"
        title = f"{schema.title_prefix}: {entity_part[:80]}"
        verified = sum(1 for entry in self.current_claim_ledger if entry.verification_status.startswith("verified"))
        unresolved = sum(1 for entry in self.current_claim_ledger if entry.verification_status == "unresolved")
        report_type_label = intent.report_type.replace('_', ' ')
        if self.current_missing_inputs:
            top_gaps = ", ".join(item.item for item in self.current_missing_inputs[:2])
            summary = (
                f"Evidence-grounded {report_type_label} for {entity_part}. "
                f"Verification remains incomplete; main gaps include {top_gaps}."
            )
        elif unresolved:
            summary = (
                f"Evidence-grounded {report_type_label} for {entity_part}. "
                f"{unresolved} major claim(s) remain unresolved."
            )
        elif verified:
            summary = f"Evidence-grounded {report_type_label} for {entity_part} with verified support for the main claims."
        else:
            summary = f"Evidence-grounded {report_type_label} for {entity_part}."
        return {"title": title[:160], "summary": summary}

    def _render_structured_section(self, section: ReportSection) -> str:
        title = section.title
        if title == "What Is Verified":
            verified = [
                entry for entry in self.current_claim_ledger
                if entry.verification_status in {"verified_by_source_material", "verified_by_external_search"}
            ]
            if not verified:
                return "- No claims cleared verification against directly relevant source material or external evidence."
            return "\n".join(
                f"- {self._clean_structured_text(entry.canonical_claim_text or entry.claim_text)} "
                f"({entry.verification_status.replace('_', ' ')})"
                for entry in verified[:8]
            )

        if title == "What Is Inferred":
            inferred = [
                entry for entry in self.current_claim_ledger
                if entry.claim_category in {"inferred", "assumption"} or entry.verification_status == "unresolved"
            ]
            if not inferred:
                return "- No major inference-only claims were tracked."
            return "\n".join(
                f"- {self._clean_structured_text(entry.canonical_claim_text or entry.claim_text)} ({entry.claim_category})"
                for entry in inferred[:8]
                if self._clean_structured_text(entry.canonical_claim_text or entry.claim_text)
            )

        if title == "Constraints and Dependencies":
            lines = []
            for entry in self.current_claim_ledger[:6]:
                clean_claim = self._clean_structured_text(entry.canonical_claim_text or entry.claim_text)
                if not clean_claim:
                    continue
                lines.append(f"**{clean_claim}**")
                for label, values in [
                    ("Enabling", entry.constraint_map.enabling_conditions),
                    ("Limiting", entry.constraint_map.limiting_conditions),
                    ("Platform", entry.constraint_map.platform_dependencies),
                    ("Operational", entry.constraint_map.operational_dependencies),
                    ("Regulatory", entry.constraint_map.regulatory_dependencies),
                ]:
                    if values:
                        lines.append(f"- {label}: {', '.join(values[:3])}")
            return "\n".join(lines) if lines else "- No major constraint maps were generated."

        if title == "Missing Critical Inputs":
            if not self.current_missing_inputs:
                unresolved = sum(1 for entry in self.current_claim_ledger if entry.verification_status == "unresolved")
                return (
                    "- No explicit missing-input artifact was generated, "
                    f"but {unresolved} unresolved claim(s) still limit confidence."
                )
            return "\n".join(
                f"- **{item.item}**: {item.why_it_matters} Search attempted: {'yes' if item.search_attempted else 'no'}."
                for item in self.current_missing_inputs
            )

        if title == "Quantitative Checks":
            if not self.current_quantitative_checks:
                return "- No deterministic quantitative checks were triggered."
            return "\n".join(
                f"- **{check.status.upper()}** {check.name}: {check.details}"
                for check in self.current_quantitative_checks
            )

        if title == "What Would Change the Conclusion":
            if not self.current_missing_inputs:
                return "- A materially stronger contradictory source or new primary data would be the main trigger to change the conclusion."
            return "\n".join(
                f"- Better evidence on {item.item} could materially change the conclusion."
                for item in self.current_missing_inputs[:5]
            )

        if title == "Sources":
            evidence = self.current_evidence_brief
            if not evidence:
                return "- No source summary available."
            lines = []
            seen_links = set()
            for document in evidence.source_documents[:5]:
                lines.append(f"- Source document: {document.title}")
            for item in evidence.external_evidence[:5]:
                top_sources = item.source_quality_summary.get("top_sources", []) if item.source_quality_summary else []
                source_candidates = top_sources or item.citations[:3]
                for citation in source_candidates:
                    link = citation.get("url", "")
                    label = citation.get("title") or item.query
                    if not link or link in seen_links:
                        continue
                    seen_links.add(link)
                    lines.append(f"- External: [{label}]({link})")
            if not lines:
                return "- No directly relevant sources survived source-quality filtering."
            return "\n".join(lines) if lines else "- No source summary available."

        if title == "Uncertainties and Blind Spots":
            lines = []
            for item in self.current_missing_inputs[:5]:
                lines.append(f"- Gap: {item.item}")
            for gate in self.current_quality_gates:
                if gate.status in {"warn", "fail"}:
                    lines.append(f"- {gate.name}: {gate.summary}")
            if not lines:
                unresolved = sum(1 for entry in self.current_claim_ledger if entry.verification_status == "unresolved")
                return f"- Residual uncertainty remains material because {unresolved} claim(s) remain unresolved."
            return "\n".join(lines)

        if title == "Methodology Note":
            trace = self.current_run_trace
            if not trace:
                return "- Methodology trace unavailable."
            return "\n".join([
                f"- Primary anchor: uploaded source documents and extracted text.",
                f"- Graph usage: {trace.graph_usage or 'structured context'}",
                f"- Simulation used: {'yes' if trace.simulation_used else 'no'}",
                f"- Simulation role: {trace.simulation_reason or 'not required'}",
                f"- Web searches run: {trace.search_queries_run}",
            ])

        if title == "Run Trace":
            trace = self.current_run_trace
            if not trace:
                return "- Run trace unavailable."
            lines = [
                f"- Source inputs used: {', '.join(trace.source_inputs_used) or 'none recorded'}",
                f"- Simulation used: {'yes' if trace.simulation_used else 'no'}",
                f"- Search categories: {', '.join(trace.search_categories) or 'none'}",
                f"- Claims externally verified: {trace.externally_verified_claims}",
                f"- Claims unresolved after search: {trace.unresolved_claims}",
            ]
            for gate in trace.quality_gates:
                lines.append(f"- Quality gate `{gate.name}`: {gate.status}")
            return "\n".join(lines)

        return ""

    def _clean_structured_text(self, text: str) -> str:
        cleaned = " ".join((text or "").replace("*", " ").split()).strip()
        if not cleaned:
            return ""
        if len(cleaned) < 20 and not cleaned.endswith((".", "?", "!", "%")):
            return ""
        if cleaned.endswith((" n't", " isn", " aspir", " n")):
            return ""
        return cleaned

    def _section_needs_repair(self, title: str, content: str) -> bool:
        defects = self.editorial_consolidator.review([{"title": title, "content": content}])
        return any(defect.defect_type in {"formatting_artifact", "truncated_section"} for defect in defects)

    def _finalize_section_content(
        self,
        section: ReportSection,
        content: str,
        previous_sections: List[str],
    ) -> str:
        cleaned = self.editorial_consolidator.clean_section_content(section.title, content)
        draft = cleaned or (content or "").strip()
        if not draft:
            return ""

        repair_needed = not bool(cleaned) or self._section_needs_repair(section.title, draft)
        if not repair_needed:
            return draft

        evidence_context = self._build_section_evidence_context(section, previous_sections)
        repair_prompt = SECTION_REPAIR_USER_PROMPT_TEMPLATE.format(
            section_title=section.title,
            evidence_context=evidence_context[:5000] or "(No additional evidence context available)",
            draft=draft[:5000],
        )
        repaired = self.llm.chat(
            messages=[
                {"role": "system", "content": SECTION_REPAIR_SYSTEM_PROMPT},
                {"role": "user", "content": repair_prompt},
            ],
            temperature=0.2,
            max_tokens=2048,
        )
        repaired_text = repaired or cleaned
        if "Final Answer:" in repaired_text:
            repaired_text = repaired_text.split("Final Answer:")[-1].strip()
        repaired_text = self.editorial_consolidator.clean_section_content(section.title, repaired_text)
        return repaired_text or cleaned

    def _refresh_structured_sections(self, outline: ReportOutline) -> None:
        if not self.current_schema:
            return

        structured_titles = {
            schema_section.title
            for schema_section in self.current_schema.sections
            if schema_section.render_mode == "structured"
        }
        for section in outline.sections:
            if section.title in structured_titles:
                section.content = self._render_structured_section(section)

    def _build_section_evidence_context(self, section: ReportSection, previous_sections: List[str]) -> str:
        evidence = self.current_evidence_brief
        if not evidence:
            return ""

        relevant_claims = self.claim_ledger_builder.consolidate_for_section(
            self.current_claim_ledger,
            section.title,
            prior_sections=previous_sections,
        )
        if not relevant_claims:
            relevant_claims = self.claim_ledger_builder.filter_for_section(self.current_claim_ledger, section.title)
        context_parts = [
            "\n\n[Curated Evidence Context]",
            f"Report intent: {self.current_intent.report_type if self.current_intent else 'unknown'}",
            f"Simulation mode: {self.current_intent.simulation_mode if self.current_intent else 'unknown'}",
            "Use only the claim clusters listed below unless you explicitly search for more evidence.",
            "Do not restate the same underlying graph fact with slightly different wording across sections.",
            "",
            "Key entities:",
            ", ".join(evidence.key_entities[:10]) or "None",
            "",
            "Claim ledger entries:",
        ]
        for entry in relevant_claims[:8]:
            context_parts.append(
                f"- Canonical claim: {entry.canonical_claim_text or entry.claim_text} | cluster: {entry.cluster_id} | "
                f"primary section: {entry.primary_section or section.title} | duplicates consolidated: {entry.duplicate_count} | "
                f"verification: {entry.verification_status} | provenance: {', '.join(entry.source_provenance)}"
            )
            if entry.supporting_evidence:
                context_parts.append(f"  Evidence anchors: {'; '.join(entry.supporting_evidence[:2])}")

        if evidence.key_numbers:
            context_parts.extend(["", "Key numbers:"])
            context_parts.extend(f"- {item}" for item in evidence.key_numbers[:10])

        if evidence.contradictions:
            context_parts.extend(["", "Known contradictions:"])
            context_parts.extend(f"- {item}" for item in evidence.contradictions[:5])

        if self.current_missing_inputs:
            context_parts.extend(["", "Missing critical inputs:"])
            context_parts.extend(f"- {item.item}" for item in self.current_missing_inputs[:5])

        if evidence.external_evidence:
            context_parts.extend(["", "External evidence summary:"])
            for item in evidence.external_evidence[:4]:
                context_parts.append(f"- {item.query}: {item.answer[:240]}")

        return "\n".join(context_parts)

    def _build_verification_summary(self) -> Dict[str, Any]:
        statuses: Dict[str, int] = {}
        for entry in self.current_claim_ledger:
            statuses[entry.verification_status] = statuses.get(entry.verification_status, 0) + 1

        release_recommendation = "pass"
        if any(gate.status == "fail" and gate.blocking for gate in self.current_quality_gates):
            release_recommendation = "fail"
        elif any(gate.status == "warn" for gate in self.current_quality_gates):
            release_recommendation = "warn"

        return {
            "status_counts": statuses,
            "release_recommendation": release_recommendation,
            "verified_claims": sum(
                1 for entry in self.current_claim_ledger
                if entry.verification_status in {"verified_by_source_material", "verified_by_external_search"}
            ),
            "unresolved_claims": sum(1 for entry in self.current_claim_ledger if entry.verification_status == "unresolved"),
        }

    def _save_pipeline_artifacts(self, report_id: str) -> None:
        if self.current_intent:
            ReportManager.save_artifact(report_id, "intent", self.current_intent.to_dict())
        if self.current_schema:
            ReportManager.save_artifact(report_id, "schema", self.current_schema.to_dict())
        if self.current_search_plan:
            ReportManager.save_artifact(report_id, "search_plan", self.current_search_plan)
        if self.current_evidence_brief:
            ReportManager.save_artifact(report_id, "evidence_brief", self.current_evidence_brief.to_dict())
        if self.current_claim_ledger:
            ReportManager.save_artifact(
                report_id,
                "claim_ledger",
                [entry.to_dict() for entry in self.current_claim_ledger],
            )
        if self.current_missing_inputs:
            ReportManager.save_artifact(
                report_id,
                "missing_inputs",
                [item.to_dict() for item in self.current_missing_inputs],
            )
        if self.current_quantitative_checks:
            ReportManager.save_artifact(
                report_id,
                "quantitative_checks",
                [check.to_dict() for check in self.current_quantitative_checks],
            )
        if self.current_quality_gates:
            ReportManager.save_artifact(
                report_id,
                "quality_gates",
                [gate.to_dict() for gate in self.current_quality_gates],
            )
        if self.current_run_trace:
            ReportManager.save_artifact(report_id, "run_trace", self.current_run_trace.to_dict())

    def plan_outline(
        self,
        progress_callback: Optional[Callable] = None
    ) -> ReportOutline:
        """
        Plan report outline

        Uses LLM to analyze simulation requirements and plan the report table of contents structure

        Args:
            progress_callback: Progress callback function

        Returns:
            ReportOutline: Report outline
        """
        logger.info("Starting to plan report outline...")

        if not self.current_intent or not self.current_schema or not self.current_evidence_brief:
            self._prepare_report_intelligence()

        if progress_callback:
            progress_callback("planning", 0, "Analyzing report intent and evidence...")

        title_summary = self._build_report_title_and_summary()
        sections = [
            ReportSection(
                title=schema_section.title,
                content="",
                key=schema_section.key,
                description=schema_section.description,
            )
            for schema_section in self.current_schema.sections
        ]

        outline = ReportOutline(
            title=title_summary["title"],
            summary=title_summary["summary"],
            sections=sections,
        )

        if progress_callback:
            progress_callback("planning", 100, "Outline planning complete")

        logger.info(f"Outline planning complete: {len(sections)} sections")
        return outline
    
    def _generate_section_react(
        self, 
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        """
        Generate single section content using ReACT mode

        ReACT loop:
        1. Thought - Analyze what information is needed
        2. Action - Call tools to get information
        3. Observation - Analyze tool return results
        4. Repeat until information is sufficient or maximum count reached
        5. Final Answer - Generate section content

        Args:
            section: Section to generate
            outline: Complete outline
            previous_sections: Content of previous sections (for maintaining coherence)
            progress_callback: Progress callback
            section_index: Section index (for logging)

        Returns:
            Section content (Markdown format)
        """
        logger.info(f"ReACT generating section: {section.title}")
        
        # Log section start
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)

        if section.key in {
            "verified",
            "inferred",
            "constraints",
            "missing_inputs",
            "quant_checks",
            "what_changes",
            "sources",
            "uncertainties",
            "methodology",
            "run_trace",
        }:
            content = self._render_structured_section(section)
            if self.report_logger:
                self.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=content,
                    tool_calls_count=0,
                )
            return content
        
        system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            report_summary=outline.summary,
            simulation_requirement=self.simulation_requirement,
            section_title=section.title,
            tools_description=self._get_tools_description(),
        )

        # Build user prompt - pass max 4000 characters per completed section
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                # Maximum 4000 characters per section
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "(This is the first section)"
        
        user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content=previous_content,
            section_title=section.title,
        )
        user_prompt += self._build_section_evidence_context(section, previous_sections)

        # Inject deliberation context for sections that need it
        if self.deliberation_session_id or self._get_deliberation_session():
            delib_context = self._build_deliberation_context_for_section(section.title)
            if delib_context:
                user_prompt += delib_context

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # ReACT loop
        tool_calls_count = 0
        max_iterations = 5  # Maximum iterations
        min_tool_calls = 0
        if self.current_intent and self.current_intent.fresh_external_information_required:
            min_tool_calls = 1
        if self.current_intent and self.current_intent.simulation_mode == "required":
            min_tool_calls = 2
        conflict_retries = 0  # Number of consecutive conflicts where tool call and Final Answer appeared simultaneously
        used_tools = set()  # Track tools already called
        all_tools = {
            "insight_forge",
            "panorama_search",
            "quick_search",
            "interview_agents",
            "web_search",
            "fact_check",
            "deliberation_data",
        }

        # Report context, used for InsightForge sub-question generation
        report_context = (
            f"Section title: {section.title}\n"
            f"Simulation requirement: {self.simulation_requirement}\n"
            f"Intent: {self.current_intent.report_type if self.current_intent else 'unknown'}"
        )
        
        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating", 
                    int((iteration / max_iterations) * 100),
                    f"Deep retrieval and writing ({tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION})"
                )
            
            # Call LLM
            response = self.llm.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=4096
            )

            # Check if LLM returned None (API error or empty content)
            if response is None:
                logger.warning(f"Section {section.title} iteration {iteration + 1}: LLM returned None")
                # If there are more iterations, add message and retry
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "(Response was empty)"})
                    messages.append({"role": "user", "content": "Please continue generating content."})
                    continue
                # Last iteration also returned None, break out of loop to force completion
                break

            logger.debug(f"LLM response: {response[:200]}...")

            # Parse once, reuse result
            tool_calls = self._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

            # ── Conflict handling: LLM output both tool call and Final Answer ──
            if has_tool_calls and has_final_answer:
                conflict_retries += 1
                logger.warning(
                    f"Section {section.title} round {iteration+1}: "
                    f"LLM output both tool call and Final Answer (conflict #{conflict_retries})"
                )

                if conflict_retries <= 2:
                    # First two times: discard this response, ask LLM to reply again
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "[Format error] You included both a tool call and a Final Answer in one reply, which is not allowed.\n"
                            "Each reply can only do ONE of the following:\n"
                            "- Call a tool (output a <tool_call> block, do not write Final Answer)\n"
                            "- Output final content (beginning with 'Final Answer:', do not include <tool_call>)\n"
                            "Please reply again, doing only one of these things."
                        ),
                    })
                    continue
                else:
                    # Third time: degrade, truncate to first tool call, force execute
                    logger.warning(
                        f"Section {section.title}: {conflict_retries} consecutive conflicts, "
                        "degrading to truncate and execute first tool call"
                    )
                    first_tool_end = response.find('</tool_call>')
                    if first_tool_end != -1:
                        response = response[:first_tool_end + len('</tool_call>')]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool_calls = bool(tool_calls)
                    has_final_answer = False
                    conflict_retries = 0

            # Log LLM response
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )

            # ── Case 1: LLM output Final Answer ──
            if has_final_answer:
                # Tool call count insufficient, reject and ask to continue calling tools
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    unused_tools = all_tools - used_tools
                    unused_hint = f"(These tools haven't been used, recommend trying them: {', '.join(unused_tools)})" if unused_tools else ""
                    messages.append({
                        "role": "user",
                        "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                            tool_calls_count=tool_calls_count,
                            min_tool_calls=min_tool_calls,
                            unused_hint=unused_hint,
                        ),
                    })
                    continue

                # Normal completion
                final_answer = response.split("Final Answer:")[-1].strip()
                final_answer = self._finalize_section_content(section, final_answer, previous_sections)
                logger.info(f"Section {section.title} generation complete (tool calls: {tool_calls_count})")

                if self.report_logger:
                    self.report_logger.log_section_content(
                        section_title=section.title,
                        section_index=section_index,
                        content=final_answer,
                        tool_calls_count=tool_calls_count
                    )
                return final_answer

            # ── Case 2: LLM tried to call a tool ──
            if has_tool_calls:
                # Tool quota exhausted → explicitly notify, ask to output Final Answer
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_TOOL_LIMIT_MSG.format(
                            tool_calls_count=tool_calls_count,
                            max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        ),
                    })
                    continue

                # Only execute the first tool call
                call = tool_calls[0]
                if len(tool_calls) > 1:
                    logger.info(f"LLM tried to call {len(tool_calls)} tools, only executing first: {call['name']}")

                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        iteration=iteration + 1
                    )

                result = self._execute_tool(
                    call["name"],
                    call.get("parameters", {}),
                    report_context=report_context
                )

                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        result=result,
                        iteration=iteration + 1
                    )

                tool_calls_count += 1
                used_tools.add(call['name'])

                # Build unused tools hint
                unused_tools = all_tools - used_tools
                unused_hint = ""
                if unused_tools and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION:
                    unused_hint = REACT_UNUSED_TOOLS_HINT.format(unused_list=", ".join(unused_tools))

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REACT_OBSERVATION_TEMPLATE.format(
                        tool_name=call["name"],
                        result=result,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        used_tools_str=", ".join(used_tools),
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # ── Case 3: Neither tool call nor Final Answer ──
            messages.append({"role": "assistant", "content": response})

            if tool_calls_count < min_tool_calls:
                # Tool call count insufficient, recommend unused tools
                unused_tools = all_tools - used_tools
                unused_hint = f"(These tools haven't been used, recommend trying them: {', '.join(unused_tools)})" if unused_tools else ""

                messages.append({
                    "role": "user",
                    "content": REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # Tool calls sufficient, LLM output content without "Final Answer:" prefix
            # Directly accept this content as the final answer, no need for additional iterations
            logger.info(f"Section {section.title}: 'Final Answer:' prefix not detected, directly accepting LLM output as final content (tool calls: {tool_calls_count})")
            final_answer = self._finalize_section_content(section, response.strip(), previous_sections)

            if self.report_logger:
                self.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count
                )
            return final_answer
        
        # Maximum iterations reached, force generate content
        logger.warning(f"Section {section.title} reached maximum iterations, forcing generation")
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})
        
        response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )

        # Check if LLM returned None during forced completion
        if response is None:
            logger.error(f"Section {section.title}: LLM returned None during forced completion, using default error message")
            final_answer = f"(This section generation failed: LLM returned empty response, please try again later)"
        elif "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response
        final_answer = self._finalize_section_content(section, final_answer, previous_sections)
        
        # Log section content generation complete
        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count
            )
        
        return final_answer
    
    def generate_report(
        self, 
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        """
        Generate complete report (section-by-section real-time output)

        Each section is saved to the folder immediately after generation, without waiting for the entire report to complete.
        File structure:
        reports/{report_id}/
            meta.json       - Report metadata
            outline.json    - Report outline
            progress.json   - Generation progress
            section_01.md   - Section 1
            section_02.md   - Section 2
            ...
            full_report.md  - Complete report

        Args:
            progress_callback: Progress callback function (stage, progress, message)
            report_id: Report ID (optional, auto-generated if not provided)

        Returns:
            Report: Complete report
        """
        import uuid

        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()

        report = Report(
            report_id=report_id,
            simulation_id=self.simulation_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            project_id=self.project_id,
            status=ReportStatus.PENDING,
            created_at=datetime.now().isoformat(),
        )

        completed_section_titles: List[str] = []

        try:
            ReportManager._ensure_report_folder(report_id)

            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement,
            )
            self.console_logger = ReportConsoleLogger(report_id)

            ReportManager.update_progress(
                report_id,
                "pending",
                0,
                "Initializing report intelligence pipeline...",
                completed_sections=[],
            )
            ReportManager.save_report(report)

            report.status = ReportStatus.PLANNING
            self.report_logger.log_planning_start()
            if progress_callback:
                progress_callback("planning", 0, "Analyzing report intent and evidence...")

            self._prepare_report_intelligence()
            self._save_pipeline_artifacts(report_id)

            report.intent = self.current_intent.to_dict() if self.current_intent else None
            report.schema = self.current_schema.to_dict() if self.current_schema else None
            report.evidence_summary = self.current_evidence_brief.to_dict() if self.current_evidence_brief else None
            report.search_plan = self.current_search_plan
            report.missing_critical_inputs = [item.to_dict() for item in self.current_missing_inputs]

            if self.report_logger:
                self.report_logger.log(
                    action="intent_analysis_complete",
                    stage="planning",
                    details={
                        "intent": report.intent,
                        "search_plan": report.search_plan,
                        "missing_critical_inputs": report.missing_critical_inputs,
                    },
                )

            ReportManager.update_progress(
                report_id,
                "planning",
                10,
                "Intent analysis, search plan, and evidence brief complete",
                completed_sections=[],
            )
            ReportManager.save_report(report)

            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg:
                    progress_callback(stage, prog, msg) if progress_callback else None
            )
            report.outline = outline
            if self.report_logger:
                self.report_logger.log_planning_complete(outline.to_dict())

            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(
                report_id,
                "planning",
                18,
                f"Outline planning complete, {len(outline.sections)} sections",
                completed_sections=[],
            )
            ReportManager.save_report(report)

            report.status = ReportStatus.GENERATING
            total_sections = len(outline.sections)
            generated_sections: List[str] = []

            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / max(total_sections, 1)) * 60)

                ReportManager.update_progress(
                    report_id,
                    "generating",
                    base_progress,
                    f"Generating section: {section.title} ({section_num}/{total_sections})",
                    current_section=section.title,
                    completed_sections=completed_section_titles,
                )

                if progress_callback:
                    progress_callback(
                        "generating",
                        base_progress,
                        f"Generating section: {section.title} ({section_num}/{total_sections})",
                    )

                section_content = self._generate_section_react(
                    section=section,
                    outline=outline,
                    previous_sections=generated_sections,
                    progress_callback=lambda stage, prog, msg:
                        progress_callback(
                            stage,
                            min(92, base_progress + int(prog * 0.5 / max(total_sections, 1))),
                            msg,
                        ) if progress_callback else None,
                    section_index=section_num,
                )

                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")
                ReportManager.save_section(report_id, section_num, section)
                completed_section_titles.append(section.title)

                if self.report_logger:
                    self.report_logger.log_section_full_complete(
                        section_title=section.title,
                        section_index=section_num,
                        full_content=f"## {section.title}\n\n{section_content}".strip(),
                    )

                ReportManager.update_progress(
                    report_id,
                    "generating",
                    min(92, base_progress + int(55 / max(total_sections, 1))),
                    f"Section {section.title} complete",
                    current_section=None,
                    completed_sections=completed_section_titles,
                )

            section_dicts = [{"title": section.title, "content": section.content} for section in outline.sections]

            if self.include_quality_assessment:
                from .quality_validator import validate_text
                quality_signals = validate_text("\n\n".join(generated_sections), section_dicts)
            else:
                quality_signals = []

            self.current_quantitative_checks = self.quantitative_validator.validate(
                section_dicts,
                self.current_claim_ledger,
            )
            deduped_sections, editorial_defects = self.editorial_consolidator.deduplicate_sections(section_dicts)

            for section, updated in zip(outline.sections, deduped_sections):
                section.content = updated["content"]

            for index, section in enumerate(outline.sections, start=1):
                ReportManager.save_section(report_id, index, section)

            generated_sections = [f"## {section.title}\n\n{section.content}" for section in outline.sections]

            for entry in self.current_claim_ledger:
                entry.report_sections = [
                    section.title for section in outline.sections
                    if section.title in entry.report_sections or entry.claim_text[:24].lower() in section.content.lower()
                ] or entry.report_sections

            self.current_quality_gates = self.quality_gate_evaluator.evaluate(
                claim_ledger=self.current_claim_ledger,
                missing_inputs=self.current_missing_inputs,
                quantitative_checks=self.current_quantitative_checks,
                editorial_defects=editorial_defects,
            )

            if quality_signals and self.current_quality_gates:
                self.current_quality_gates[0].details.extend(signal.title for signal in quality_signals[:5])

            source_inputs_used = ["uploaded_documents", "graph_context", "external_search"]
            if self.current_intent and self.current_intent.simulation_mode in {"required", "optional", "useful_but_optional"}:
                source_inputs_used.append("simulation_outputs")
            if self.deliberation_session_id:
                source_inputs_used.append("deliberation_outputs")

            self.current_run_trace = self.run_trace_builder.build(
                source_inputs_used=source_inputs_used,
                simulation_used=self.current_intent.simulation_mode in {"required", "optional", "useful_but_optional"},
                simulation_reason=self.current_intent.simulation_mode,
                graph_usage="Used as structured context and graph facts for evidence briefing.",
                search_plan=self.current_search_plan,
                claim_ledger=self.current_claim_ledger,
                missing_inputs=self.current_missing_inputs,
                quality_gates=self.current_quality_gates,
            )

            self._refresh_structured_sections(outline)
            for index, section in enumerate(outline.sections, start=1):
                ReportManager.save_section(report_id, index, section)

            report.quantitative_checks = [check.to_dict() for check in self.current_quantitative_checks]
            report.quality_gates = [gate.to_dict() for gate in self.current_quality_gates]
            report.run_trace = self.current_run_trace.to_dict() if self.current_run_trace else None
            report.verification_summary = self._build_verification_summary()
            report.evidence_summary = self.current_evidence_brief.to_dict() if self.current_evidence_brief else None
            report.search_plan = self.current_search_plan
            report.missing_critical_inputs = [item.to_dict() for item in self.current_missing_inputs]

            self._save_pipeline_artifacts(report_id)

            if self.report_logger:
                self.report_logger.log(
                    action="quality_gate_complete",
                    stage="generating",
                    details={
                        "quality_gates": report.quality_gates,
                        "quantitative_checks": report.quantitative_checks,
                        "verification_summary": report.verification_summary,
                    },
                )

            if progress_callback:
                progress_callback("generating", 95, "Assembling complete report...")

            ReportManager.update_progress(
                report_id,
                "generating",
                95,
                "Assembling complete report...",
                completed_sections=completed_section_titles,
            )

            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()

            total_time_seconds = (datetime.now() - start_time).total_seconds()
            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds,
                )

            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id,
                "completed",
                100,
                "Report generation complete",
                completed_sections=completed_section_titles,
            )

            if progress_callback:
                progress_callback("completed", 100, "Report generation complete")

            logger.info(f"Report generation complete: {report_id}")
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            return report

        except Exception as e:
            logger.error(f"Report generation failed: {str(e)}")
            report.status = ReportStatus.FAILED
            report.error = str(e)

            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")

            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id,
                    "failed",
                    -1,
                    f"Report generation failed: {str(e)}",
                    completed_sections=completed_section_titles,
                )
            except Exception:
                pass

            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            return report
    
    def _extract_citations_from_text(self, content: str) -> List[Dict[str, str]]:
        sources = []
        citation_pattern = re.compile(r"^- \[(?P<title>[^\]]+)\]\((?P<url>[^)]+)\):\s*(?P<snippet>.*)$", re.MULTILINE)
        for match in citation_pattern.finditer(content or ""):
            sources.append({
                "title": match.group("title").strip(),
                "url": match.group("url").strip(),
                "snippet": match.group("snippet").strip(),
            })
        return sources

    def _merge_sources(
        self,
        existing_sources: List[Dict[str, str]],
        new_sources: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        seen = {
            (
                (item.get("title") or "").strip().lower(),
                (item.get("url") or "").strip().lower(),
                (item.get("snippet") or "").strip().lower(),
            )
            for item in existing_sources
        }
        merged = list(existing_sources)
        for source in new_sources:
            key = (
                (source.get("title") or "").strip().lower(),
                (source.get("url") or "").strip().lower(),
                (source.get("snippet") or "").strip().lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(source)
        return merged

    def _build_sources_from_tool_result(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        result: str,
    ) -> List[Dict[str, str]]:
        if tool_name in {"web_search", "fact_check"}:
            return self._extract_citations_from_text(result)

        if tool_name == "deliberation_data" and self.deliberation_session_id:
            return [{
                "title": f"Deliberation Session {self.deliberation_session_id}",
                "url": "",
                "snippet": f"Focus: {parameters.get('focus', 'all')}",
            }]

        return []

    def chat(
        self, 
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Chat with Report Agent

        Agent can autonomously call retrieval tools to answer questions during conversation

        Args:
            message: User message
            chat_history: Conversation history

        Returns:
            {
                "response": "Agent reply",
                "tool_calls": [list of tools called],
                "sources": [information sources]
            }
        """
        logger.info(f"Report Agent conversation: {message[:50]}...")

        chat_history = chat_history or []

        # Get generated report content
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                # Limit report length to avoid overly long context
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [Report content truncated] ..."
        except Exception as e:
            logger.warning(f"Failed to get report content: {e}")

        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            report_content=report_content if report_content else "(No report available)",
            tools_description=self._get_tools_description(),
        )

        delib_session = self._get_deliberation_session()
        if delib_session:
            deliberation_preview = self._build_deliberation_tool_output(focus="all", max_arguments=6)
            system_prompt += f"\n\n[Deliberation Context Preview]\n{deliberation_preview[:4000]}"

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history
        for h in chat_history[-10:]:  # Limit history length
            messages.append(h)

        # Add user message
        messages.append({
            "role": "user",
            "content": message
        })

        # ReACT loop (simplified)
        tool_calls_made = []
        source_entries: List[Dict[str, str]] = []
        max_iterations = 2  # Reduced iteration count

        for iteration in range(max_iterations):
            response = self.llm.chat(
                messages=messages,
                temperature=0.5
            )

            # Parse tool calls
            tool_calls = self._parse_tool_calls(response)

            if not tool_calls:
                # No tool calls, return response directly
                clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)

                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": source_entries,
                }

            # Execute tool calls (limit count)
            tool_results = []
            for call in tool_calls[:1]:  # Execute at most 1 tool call per iteration
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]  # Limit result length
                })
                tool_calls_made.append(call)
                source_entries = self._merge_sources(
                    source_entries,
                    self._build_sources_from_tool_result(
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        result=result,
                    ),
                )

            # Add results to messages
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']} result]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user",
                "content": observation + CHAT_OBSERVATION_SUFFIX
            })

        # Maximum iterations reached, get final response
        final_response = self.llm.chat(
            messages=messages,
            temperature=0.5
        )

        # Clean up response
        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
        
        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": source_entries,
        }


class ReportManager:
    """
    Report manager

    Responsible for persistent storage and retrieval of reports

    File structure (section-by-section output):
    reports/
      {report_id}/
        meta.json          - Report metadata and status
        outline.json       - Report outline
        progress.json      - Generation progress
        section_01.md      - Section 1
        section_02.md      - Section 2
        ...
        full_report.md     - Complete report
    """

    # Report storage directory
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')
    
    @classmethod
    def _ensure_reports_dir(cls):
        """Ensure reports root directory exists"""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)
    
    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """Get report folder path"""
        return os.path.join(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """Ensure report folder exists and return path"""
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder
    
    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """Get report metadata file path"""
        return os.path.join(cls._get_report_folder(report_id), "meta.json")
    
    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """Get complete report Markdown file path"""
        return os.path.join(cls._get_report_folder(report_id), "full_report.md")
    
    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """Get outline file path"""
        return os.path.join(cls._get_report_folder(report_id), "outline.json")
    
    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """Get progress file path"""
        return os.path.join(cls._get_report_folder(report_id), "progress.json")

    @classmethod
    def _get_artifact_path(cls, report_id: str, artifact_name: str) -> str:
        return os.path.join(cls._get_report_folder(report_id), f"{artifact_name}.json")
    
    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """Get section Markdown file path"""
        return os.path.join(cls._get_report_folder(report_id), f"section_{section_index:02d}.md")
    
    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """Get Agent log file path"""
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")
    
    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """Get console log file path"""
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")
    
    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Get console log content

        This is the console output log (INFO, WARNING, etc.) during report generation,
        different from the structured logs in agent_log.jsonl.

        Args:
            report_id: Report ID
            from_line: Start reading from this line (for incremental retrieval, 0 means from beginning)

        Returns:
            {
                "logs": [list of log lines],
                "total_lines": total line count,
                "from_line": starting line number,
                "has_more": whether there are more logs
            }
        """
        log_path = cls._get_console_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    # Keep original log line, remove trailing newline
                    logs.append(line.rstrip('\n\r'))

        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Read to end
        }
    
    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """
        Get complete console log (retrieve all at once)

        Args:
            report_id: Report ID

        Returns:
            List of log lines
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Get Agent log content

        Args:
            report_id: Report ID
            from_line: Start reading from this line (for incremental retrieval, 0 means from beginning)

        Returns:
            {
                "logs": [list of log entries],
                "total_lines": total line count,
                "from_line": starting line number,
                "has_more": whether there are more logs
            }
        """
        log_path = cls._get_agent_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    try:
                        log_entry = json.loads(line.strip())
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        # Skip lines that fail to parse
                        continue

        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Read to end
        }
    
    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Get complete Agent log (retrieve all at once)

        Args:
            report_id: Report ID

        Returns:
            List of log entries
        """
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """
        Save report outline

        Called immediately after planning phase is complete
        """
        cls._ensure_report_folder(report_id)

        with open(cls._get_outline_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(outline.to_dict(), f, ensure_ascii=False, indent=2)

        logger.info(f"Outline saved: {report_id}")
    
    @classmethod
    def save_section(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection
    ) -> str:
        """
        Save a single section

        Called immediately after each section is generated, enabling section-by-section output

        Args:
            report_id: Report ID
            section_index: Section index (starting from 1)
            section: Section object

        Returns:
            Saved file path
        """
        cls._ensure_report_folder(report_id)

        # Build section Markdown content - clean up possible duplicate headings
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"

        # Save file
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(f"Section saved: {report_id}/{file_suffix}")
        return file_path

    @classmethod
    def save_artifact(cls, report_id: str, artifact_name: str, payload: Any) -> None:
        cls._ensure_report_folder(report_id)
        with open(cls._get_artifact_path(report_id, artifact_name), 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    @classmethod
    def get_artifact(cls, report_id: str, artifact_name: str) -> Optional[Any]:
        path = cls._get_artifact_path(report_id, artifact_name)
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        Clean section content

        1. Remove Markdown heading lines at the beginning of content that duplicate the section title
        2. Convert all ### and below level headings to bold text

        Args:
            content: Original content
            section_title: Section title

        Returns:
            Cleaned content
        """
        import re
        
        if not content:
            return content
        
        content = content.strip()
        lines = content.split('\n')
        cleaned_lines = []
        skip_next_empty = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Check if it's a Markdown heading line
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title_text = heading_match.group(2).strip()
                
                # Check if it's a heading that duplicates the section title (skip duplicates within first 5 lines)
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue
                
                # Convert all heading levels (#, ##, ###, #### etc.) to bold
                # Because section title is added by the system, content should not have any headings
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # Add blank line
                continue
            
            # If previous line was a skipped heading and current line is empty, skip it too
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue
            
            skip_next_empty = False
            cleaned_lines.append(line)
        
        # Remove leading blank lines
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)

        # Remove leading horizontal rules
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
            # Also remove blank lines after horizontal rules
            while cleaned_lines and cleaned_lines[0].strip() == '':
                cleaned_lines.pop(0)
        
        return '\n'.join(cleaned_lines)
    
    @classmethod
    def update_progress(
        cls, 
        report_id: str, 
        status: str, 
        progress: int, 
        message: str,
        current_section: str = None,
        completed_sections: List[str] = None
    ) -> None:
        """
        Update report generation progress

        Frontend can get real-time progress by reading progress.json
        """
        cls._ensure_report_folder(report_id)
        
        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(cls._get_progress_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """Get report generation progress"""
        path = cls._get_progress_path(report_id)
        
        if not os.path.exists(path):
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Get list of generated sections

        Returns information about all saved section files
        """
        folder = cls._get_report_folder(report_id)
        
        if not os.path.exists(folder):
            return []
        
        sections = []
        for filename in sorted(os.listdir(folder)):
            if filename.startswith('section_') and filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Parse section index from filename
                parts = filename.replace('.md', '').split('_')
                section_index = int(parts[1])

                sections.append({
                    "filename": filename,
                    "section_index": section_index,
                    "content": content
                })

        return sections
    
    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """
        Assemble complete report

        Assembles complete report from saved section files and cleans headings
        """
        folder = cls._get_report_folder(report_id)

        # Build report header
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += f"---\n\n"

        # Read all section files in order
        sections = cls.get_generated_sections(report_id)
        for section_info in sections:
            md_content += section_info["content"]

        # Post-process: clean heading issues in the complete report
        md_content = cls._post_process_report(md_content, outline)

        # Save complete report
        full_path = cls._get_report_markdown_path(report_id)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(f"Complete report assembled: {report_id}")
        return md_content
    
    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        Post-process report content

        1. Remove duplicate headings
        2. Keep report main title (#) and section titles (##), remove other heading levels (###, #### etc.)
        3. Clean up excess blank lines and horizontal rules

        Args:
            content: Original report content
            outline: Report outline

        Returns:
            Processed content
        """
        import re
        
        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False
        
        # Collect all section titles from outline
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Check if it's a heading line
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                
                # Check if it's a duplicate heading (same content heading within 5 consecutive lines)
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r'^(#{1,6})\s+(.+)$', prev_line)
                    if prev_match:
                        prev_title = prev_match.group(2).strip()
                        if prev_title == title:
                            is_duplicate = True
                            break
                
                if is_duplicate:
                    # Skip duplicate heading and its following blank lines
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue
                
                # Heading level handling:
                # - # (level=1) only keep report main title
                # - ## (level=2) keep section titles
                # - ### and below (level>=3) convert to bold text

                if level == 1:
                    if title == outline.title:
                        # Keep report main title
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # Section title incorrectly used #, correct to ##
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        # Other level-1 headings convert to bold
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        # Keep section titles
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        # Non-section level-2 headings convert to bold
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    # ### and below heading levels convert to bold text
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False

                i += 1
                continue

            elif stripped == '---' and prev_was_heading:
                # Skip horizontal rules immediately following headings
                i += 1
                continue
            
            elif stripped == '' and prev_was_heading:
                # Keep only one blank line after headings
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False
            
            else:
                processed_lines.append(line)
                prev_was_heading = False
            
            i += 1
        
        # Clean up multiple consecutive blank lines (keep at most 2)
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == '':
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    @classmethod
    def save_report(cls, report: Report) -> None:
        """Save report metadata and complete report"""
        cls._ensure_report_folder(report.report_id)

        # Save metadata JSON
        with open(cls._get_report_path(report.report_id), 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

        # Save outline
        if report.outline:
            cls.save_outline(report.report_id, report.outline)

        # Save complete Markdown report
        if report.markdown_content:
            with open(cls._get_report_markdown_path(report.report_id), 'w', encoding='utf-8') as f:
                f.write(report.markdown_content)

        logger.info(f"Report saved: {report.report_id}")
    
    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """Get report"""
        path = cls._get_report_path(report_id)

        if not os.path.exists(path):
            # Backward compatibility: check for files stored directly in reports directory
            old_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
            if os.path.exists(old_path):
                path = old_path
            else:
                return None
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Rebuild Report object
        outline = None
        if data.get('outline'):
            outline_data = data['outline']
            sections = []
            for s in outline_data.get('sections', []):
                sections.append(ReportSection(
                    title=s['title'],
                    content=s.get('content', ''),
                    key=s.get('key', ''),
                    description=s.get('description', ''),
                ))
            outline = ReportOutline(
                title=outline_data['title'],
                summary=outline_data['summary'],
                sections=sections
            )
        
        # If markdown_content is empty, try to read from full_report.md
        markdown_content = data.get('markdown_content', '')
        if not markdown_content:
            full_report_path = cls._get_report_markdown_path(report_id)
            if os.path.exists(full_report_path):
                with open(full_report_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
        
        return Report(
            report_id=data['report_id'],
            simulation_id=data['simulation_id'],
            graph_id=data['graph_id'],
            simulation_requirement=data['simulation_requirement'],
            project_id=data.get('project_id', ''),
            status=ReportStatus(data['status']),
            outline=outline,
            markdown_content=markdown_content,
            created_at=data.get('created_at', ''),
            completed_at=data.get('completed_at', ''),
            error=data.get('error'),
            intent=data.get('intent'),
            schema=data.get('schema'),
            evidence_summary=data.get('evidence_summary') or cls.get_artifact(report_id, "evidence_brief"),
            verification_summary=data.get('verification_summary'),
            missing_critical_inputs=data.get('missing_critical_inputs') or cls.get_artifact(report_id, "missing_inputs") or [],
            quantitative_checks=data.get('quantitative_checks') or cls.get_artifact(report_id, "quantitative_checks") or [],
            quality_gates=data.get('quality_gates') or cls.get_artifact(report_id, "quality_gates") or [],
            run_trace=data.get('run_trace') or cls.get_artifact(report_id, "run_trace"),
            search_plan=data.get('search_plan') or cls.get_artifact(report_id, "search_plan") or [],
        )
    
    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """Get report by simulation ID"""
        cls._ensure_reports_dir()

        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # New format: folder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    return report
            # Backward compatibility: JSON file
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    return report
        
        return None
    
    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[Report]:
        """List reports"""
        cls._ensure_reports_dir()

        reports = []
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # New format: folder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # Backward compatibility: JSON file
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
        
        # Sort by creation time in descending order
        reports.sort(key=lambda r: r.created_at, reverse=True)
        
        return reports[:limit]
    
    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """Delete report (entire folder)"""
        import shutil

        folder_path = cls._get_report_folder(report_id)

        # New format: delete entire folder
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info(f"Report folder deleted: {report_id}")
            return True

        # Backward compatibility: delete individual files
        deleted = False
        old_json_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
        old_md_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.md")
        
        if os.path.exists(old_json_path):
            os.remove(old_json_path)
            deleted = True
        if os.path.exists(old_md_path):
            os.remove(old_md_path)
            deleted = True
        
        return deleted
