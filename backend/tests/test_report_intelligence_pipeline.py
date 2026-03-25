from types import SimpleNamespace

from flask import Flask

from app.api import report_bp
from app.api import report as report_api
from app.models.project import Project, ProjectStatus
from app.services.claim_ledger import ClaimLedgerBuilder
from app.services.editorial_consolidator import EditorialConsolidator
from app.services.evidence_brief_builder import EvidenceBriefBuilder
from app.services.missing_input_detector import MissingInputDetector
from app.services.quality_gate_evaluator import QualityGateEvaluator
from app.services.quantitative_validator import QuantitativeValidator
from app.services.report_agent import Report, ReportAgent, ReportOutline, ReportSection, ReportStatus
from app.services.report_artifacts import (
    ClaimLedgerEntry,
    EvidenceBriefArtifact,
    MissingCriticalInputArtifact,
    QualityGateArtifact,
    QuantitativeCheckArtifact,
    RunTraceArtifact,
    SearchExecutionArtifact,
)
from app.services.report_intent_analyzer import ReportIntentAnalyzer
from app.services.report_schema_registry import ReportSchemaRegistry
from app.services.run_trace_builder import RunTraceBuilder
from app.services.search_plan_builder import SearchPlanBuilder
from app.services.source_quality_ranker import SourceQualityRanker


def build_project():
    return Project(
        project_id="proj_1",
        name="Test Project",
        status=ProjectStatus.GRAPH_COMPLETED,
        created_at="2026-03-24T00:00:00",
        updated_at="2026-03-24T00:00:00",
        files=[{"original_filename": "brief.txt", "path": "/tmp/brief.txt", "size": 123}],
        graph_id="graph_1",
        simulation_requirement="Assess the diligence case for acquiring ExampleCo.",
        analysis_summary="Uploaded research covers finances, competition, and operating history.",
    )


def test_intent_analysis_and_schema_selection_cover_multiple_report_types():
    analyzer = ReportIntentAnalyzer()
    registry = ReportSchemaRegistry()

    diligence = analyzer.analyze("Create a due diligence report on ExampleCo and identify risks.")
    forecast = analyzer.analyze("Forecast demand for autonomous delivery over the next 24 months.")

    diligence_schema = registry.get_schema(diligence)
    forecast_schema = registry.get_schema(forecast)

    assert diligence.report_type == "due_diligence"
    assert forecast.report_type == "forecast"
    assert diligence.simulation_mode in {"optional", "useful_but_optional"}
    assert forecast.simulation_mode == "required"
    assert any(section.title == "What Is Verified" for section in diligence_schema.sections)
    assert any(section.title == "Run Trace" for section in forecast_schema.sections)
    assert any(section.title == "Sources" for section in forecast_schema.sections)


def test_search_plan_builder_builds_chunk_driven_non_overlapping_tasks():
    analyzer = ReportIntentAnalyzer()
    
    class FakePlannerLLM:
        def chat_json(self, messages, temperature=0.2, max_tokens=1800):
            return {
                "tasks": [
                    {
                        "chunk_id": "req",
                        "query": "AI copilot competitor pricing adoption",
                        "mode": "search",
                        "task": "Look for external evidence related to this chunk.",
                        "focus_terms": ["ai", "copilot", "pricing", "adoption"],
                    },
                    {
                        "chunk_id": "gap",
                        "query": "AI copilot contradictory benchmark evidence",
                        "mode": "verify",
                        "task": "Check whether benchmark claims in this chunk hold up.",
                        "focus_terms": ["ai", "copilot", "benchmark", "contradictory"],
                    },
                    {
                        "chunk_id": "pricing",
                        "query": "AI copilot user pricing feature parity",
                        "mode": "verify",
                        "task": "Verify the pricing and parity details in this chunk.",
                        "focus_terms": ["ai", "copilot", "pricing", "parity"],
                    },
                ]
            }

    builder = SearchPlanBuilder(FakePlannerLLM())
    intent = analyzer.analyze("Assess the current market landscape and competitor pricing for AI copilots.")

    queries = builder.build(
        intent,
        source_material=[
            {
                "id": "req",
                "label": "requirement",
                "text": "Competitor pricing and market shifts for AI copilots are changing quickly this year.",
            },
            {
                "id": "gap",
                "label": "source_document",
                "text": "The benchmark picture is still unclear and several claims remain unverified or contradictory.",
            },
            {
                "id": "pricing",
                "label": "graph_fact",
                "text": "Copilot vendors charge $20 to $60 per user per month with broad feature parity claims.",
            },
        ],
    )
    intents = {query.intent for query in queries}
    chunk_ids = {query.chunk_id for query in queries}

    assert "search" in intents
    assert "verify" in intents
    assert len(chunk_ids) == len(queries)
    assert all(query.source_chunk for query in queries)
    assert all(query.focus_terms for query in queries)


def test_evidence_brief_builder_extracts_entities_claims_numbers_and_unknowns(monkeypatch):
    builder = EvidenceBriefBuilder()
    project = build_project()
    extracted_text = (
        "ExampleCo reported revenue of $120 million in 2024 and plans to launch in 2026. "
        "Management expects adoption to increase, while another memo says demand may decrease."
    )
    monkeypatch.setattr("app.services.evidence_brief_builder.ProjectManager.get_extracted_text", lambda project_id: extracted_text)

    brief = builder.build(
        project=project,
        requirement=project.simulation_requirement,
        graph_context={"related_facts": [{"fact": "Competitor pricing ranges from $49 to $99 per seat."}]},
        search_results=[],
        simulation_outputs=["Agents expect strong channel friction during rollout."],
        deliberation_outputs=["The pessimist council flagged customer concentration risk."],
    )

    assert brief.source_documents
    assert "ExampleCo" in brief.key_entities
    assert any("$120 million" in item for item in brief.key_numbers)
    assert brief.contradictions
    assert brief.major_unknowns


def test_claim_ledger_builder_populates_provenance_representativeness_and_constraints():
    analyzer = ReportIntentAnalyzer()
    intent = analyzer.analyze("Produce a market landscape report on AI copilots.")
    brief = EvidenceBriefArtifact(
        source_documents=[],
        key_entities=["ExampleCo"],
        key_claims=[
            "ExampleCo could increase market share by 5% if enterprise adoption accelerates.",
            "A single campaign doubled awareness in one segment.",
        ],
        key_numbers=["5%"],
        graph_facts=["ExampleCo expanded distribution partnerships."],
        external_evidence=[
            SearchExecutionArtifact(
                query="ExampleCo market share benchmark",
                intent="verification",
                answer="Analysts estimate share gains are possible if enterprise adoption improves.",
                citations=[{"url": "https://example.com/benchmark", "title": "Benchmark", "snippet": "Share gains possible."}],
                usable_evidence=True,
            )
        ],
        simulation_outputs=["Agents predicted customer hesitation."],
        provenance_notes=["Documents and search were combined."],
        freshness_notes=["query: fresh"],
    )

    ledger = ClaimLedgerBuilder().build(intent, brief)

    assert ledger
    assert any("web_evidence" in entry.source_provenance for entry in ledger)
    assert any(entry.representativeness.evidence_class == "anecdotal_example" for entry in ledger)
    assert any(entry.constraint_map.adoption_dependencies for entry in ledger)


def test_claim_ledger_clusters_repeated_high_centrality_facts_and_assigns_one_owner():
    analyzer = ReportIntentAnalyzer()
    registry = ReportSchemaRegistry()
    intent = analyzer.analyze("Write a market landscape report on QR commerce partnerships.")
    schema = registry.get_schema(intent)
    brief = EvidenceBriefArtifact(
        key_claims=[
            "White-label partnerships unlock enterprise-scale QR deployments faster than direct sales models.",
            "Enterprise-scale QR deployments move faster through white-label partnerships than through direct sales.",
            "Direct sales models generally slow enterprise-scale QR rollout relative to white-label partnerships.",
        ],
        graph_facts=[
            "White-label partnerships unlock enterprise-scale QR deployments faster than direct sales models."
        ],
        external_evidence=[
            SearchExecutionArtifact(
                query="QR white-label partnership enterprise rollout",
                intent="verification",
                answer="Channel partnerships can accelerate rollout speed for enterprise QR deployments.",
                citations=[{"url": "https://example.com/channel", "title": "Channel study", "snippet": "Channel partnerships accelerate deployment."}],
                usable_evidence=True,
            )
        ],
    )

    ledger = ClaimLedgerBuilder().build(
        intent,
        brief,
        schema_sections=[section.title for section in schema.sections],
    )

    assert len(ledger) == 1
    assert ledger[0].duplicate_count == 3
    assert ledger[0].primary_section in {section.title for section in schema.sections}
    assert ledger[0].canonical_claim_text


def test_missing_input_detector_flags_due_diligence_gaps():
    analyzer = ReportIntentAnalyzer()
    detector = MissingInputDetector()
    intent = analyzer.analyze("Write a due diligence memo for acquiring ExampleCo.")
    brief = EvidenceBriefArtifact(
        key_claims=["The company has product momentum."],
        key_numbers=["12% growth"],
        graph_facts=["Founder reputation is strong."],
    )

    missing = detector.detect(intent, brief, search_plan=[{"intent": "missing_input", "query": "baseline metrics"}])

    assert missing
    assert any(item.item == "baseline operating metrics" for item in missing)


def test_missing_input_detector_flags_market_landscape_gaps_even_when_prompt_mentions_them():
    analyzer = ReportIntentAnalyzer()
    detector = MissingInputDetector()
    intent = analyzer.analyze(
        "Write a market landscape report on Fidget, including market size, pricing, customers, churn, proof points, and Shopify roadmap."
    )
    brief = EvidenceBriefArtifact(
        key_numbers=["$50-500/month", "200 brands", "$100M ARR"],
        graph_facts=["GS1 Sunrise 2027 may increase QR adoption."],
        external_evidence=[
            SearchExecutionArtifact(
                query="GS1 Sunrise 2027 QR adoption",
                intent="verification",
                answer="GS1 guidance discusses 2D barcode migration timelines.",
                citations=[{"url": "https://www.gs1.org/example", "title": "GS1", "snippet": "2D barcode migration."}],
                usable_evidence=True,
            )
        ],
    )
    ledger = [
        ClaimLedgerEntry(
            claim_id="claim_1",
            claim_text="Current ARR and customer count are not independently verified.",
            claim_category="factual",
            verification_status="unresolved",
        ),
        ClaimLedgerEntry(
            claim_id="claim_2",
            claim_text="No verified comparison confirms competitor feature parity or Shopify roadmap risk.",
            claim_category="factual",
            verification_status="unresolved",
        ),
    ]

    missing = detector.detect(intent, brief, search_plan=[], claim_ledger=ledger)

    missing_items = {item.item for item in missing}
    assert "current revenue or traction baseline" in missing_items
    assert "competitive feature comparison validation" in missing_items
    assert "platform dependency or roadmap intelligence" in missing_items


def test_quantitative_validator_catches_bad_percentage_and_growth_math():
    validator = QuantitativeValidator()
    sections = [
        {
            "title": "Quantitative Checks",
            "content": "Scenario weights are 60%, 50%, and 10%. Revenue grows from 100 to 150 (20%).",
        }
    ]

    checks = validator.validate(sections, [])

    assert any(check.status == "fail" and check.name == "percentage_sum" for check in checks)
    assert any(check.status == "fail" and check.name == "growth_reconciliation" for check in checks)


def test_quantitative_validator_flags_revenue_ceiling_gap():
    validator = QuantitativeValidator()
    sections = [
        {
            "title": "Bottom Line",
            "content": (
                "Pricing is $50-500/month. Direct outreach targets the top 200 Shopify beauty brands. "
                "The venture-scale threshold is $100M+ ARR within 24 months."
            ),
        }
    ]

    checks = validator.validate(sections, [])

    ceiling_checks = [check for check in checks if check.name == "addressable_revenue_ceiling"]
    assert ceiling_checks
    assert ceiling_checks[0].status == "fail"
    assert "$1,200,000" in ceiling_checks[0].details


def test_editorial_consolidator_detects_repetition_and_deduplicates():
    consolidator = EditorialConsolidator()
    sections = [
        {"title": "Bottom Line", "content": "The core risk is channel conflict. The core risk is channel conflict."},
        {"title": "Key Evidence", "content": "The core risk is channel conflict. Additional evidence supports this."},
    ]

    updated, defects = consolidator.deduplicate_sections(sections)

    assert any(defect.defect_type == "repetition" for defect in defects)
    assert updated[0]["content"].count("The core risk is channel conflict.") == 1


def test_editorial_consolidator_catches_fuzzy_repetition_clusters():
    consolidator = EditorialConsolidator()
    sections = [
        {"title": "Bottom Line", "content": "White-label partnerships unlock enterprise-scale QR deployments faster than direct sales models."},
        {
            "title": "Key Evidence",
            "content": (
                "Enterprise-scale QR deployment moves faster via white-label partnerships than direct sales. "
                "The remaining concern is whether partner margins stay attractive."
            ),
        },
    ]

    updated, defects = consolidator.deduplicate_sections(sections)

    assert any(defect.defect_type == "repetition_cluster" for defect in defects)
    assert "remaining concern" in updated[1]["content"]
    assert "moves faster via white-label partnerships" not in updated[1]["content"]


def test_editorial_consolidator_cleans_truncated_and_broken_markdown():
    consolidator = EditorialConsolidator()
    sections = [
        {
            "title": "Key Drivers and Dynamics",
            "content": "**\nShopify doesn't n",
        }
    ]

    updated, defects = consolidator.deduplicate_sections(sections)

    assert updated[0]["content"] == ""
    assert not any(defect.defect_type in {"formatting_artifact", "truncated_section"} for defect in defects)


def test_source_quality_ranker_prefers_official_recent_sources():
    from app.utils.llm_provider import Citation

    ranker = SourceQualityRanker()
    citations = [
        Citation(url="https://example-blog.com/post", title="Opinion post", snippet="Perspective from 2021"),
        Citation(url="https://www.sec.gov/example", title="SEC filing 2025", snippet="Official filing 2025"),
    ]

    ranked = ranker.rank_sources(citations, topic="ExampleCo filing")

    assert ranked[0].source_type == "official"
    assert ranked[0].freshness in {"fresh", "recent"}


def test_source_quality_ranker_demotes_ambiguous_brand_name_matches():
    from app.utils.llm_provider import Citation

    ranker = SourceQualityRanker()
    citations = [
        Citation(
            url="https://github.com/mkeeter/fidget",
            title="mkeeter/fidget",
            snippet="Implicit surface evaluation in Rust.",
        ),
        Citation(
            url="https://www.gs1.org/standards/2d-barcodes",
            title="2D barcodes and Sunrise 2027",
            snippet="GS1 guidance on QR codes and migration timelines.",
        ),
    ]

    ranked = ranker.rank_sources(
        citations,
        topic="Fidget QR code experience platform Shopify GS1 Sunrise 2027",
    )

    assert ranked[0].citation.url == "https://www.gs1.org/standards/2d-barcodes"
    assert ranked[0].relevance in {"direct", "supporting"}
    assert any(item.citation.url.endswith("/mkeeter/fidget") and item.relevance == "off_topic" for item in ranked)


def test_quality_gate_evaluator_and_run_trace_builder_surface_failures():
    gates = QualityGateEvaluator().evaluate(
        claim_ledger=[
            ClaimLedgerEntry(
                claim_id="claim_1",
                claim_text="Claim A",
                claim_category="factual",
                source_provenance=["unresolved"],
                verification_status="contradicted_by_external_search",
            ),
            ClaimLedgerEntry(
                claim_id="claim_2",
                claim_text="Claim B",
                claim_category="numeric",
                source_provenance=["web_evidence"],
                verification_status="unresolved",
            ),
            ClaimLedgerEntry(
                claim_id="claim_3",
                claim_text="Claim C",
                claim_category="numeric",
                source_provenance=["web_evidence"],
                verification_status="unresolved",
            ),
        ],
        missing_inputs=[
            MissingCriticalInputArtifact(
                item="baseline operating metrics",
                why_it_matters="Needed for diligence.",
                confidence_impact="fail",
            )
        ],
        quantitative_checks=[
            QuantitativeCheckArtifact(name="growth_reconciliation", status="fail", details="Math mismatch.")
        ],
        editorial_defects=[],
    )

    trace = RunTraceBuilder().build(
        source_inputs_used=["uploaded_documents", "external_search"],
        simulation_used=False,
        simulation_reason="irrelevant",
        graph_usage="Used for structured context.",
        search_plan=[{"intent": "verification"}, {"intent": "counterevidence"}],
        claim_ledger=[
            ClaimLedgerEntry(
                claim_id="claim_1",
                claim_text="Claim A",
                claim_category="factual",
                source_provenance=["web_evidence"],
                verification_status="verified_by_external_search",
            ),
            ClaimLedgerEntry(
                claim_id="claim_2",
                claim_text="Claim B",
                claim_category="factual",
                source_provenance=["web_evidence"],
                verification_status="unresolved",
            ),
        ],
        missing_inputs=[
            MissingCriticalInputArtifact(
                item="baseline operating metrics",
                why_it_matters="Needed for diligence.",
            )
        ],
        quality_gates=gates,
    )

    assert any(gate.name == "quantitative_validation" and gate.status == "fail" for gate in gates)
    assert trace.search_queries_run == 2
    assert trace.externally_verified_claims == 1
    assert trace.major_gaps == ["baseline operating metrics"]


def test_quality_gate_evaluator_blocks_truncated_editorial_failures():
    gates = QualityGateEvaluator().evaluate(
        claim_ledger=[],
        missing_inputs=[],
        quantitative_checks=[],
        editorial_defects=[
            SimpleNamespace(
                defect_type="truncated_section",
                severity="warning",
                description="Section ended mid-thought.",
            )
        ],
    )

    editorial_gate = next(gate for gate in gates if gate.name == "editorial_consistency")
    assert editorial_gate.status == "fail"
    assert editorial_gate.blocking is True


def test_report_agent_refreshes_structured_sections_with_final_artifacts():
    fake_llm = SimpleNamespace(
        chat=lambda *args, **kwargs: "",
        chat_json=lambda *args, **kwargs: {"tasks": []},
    )
    agent = ReportAgent(
        graph_id="graph_1",
        simulation_id="sim_1",
        simulation_requirement="Assess ExampleCo.",
        include_quality_assessment=False,
        llm_client=fake_llm,
    )
    agent.current_schema = ReportSchemaRegistry().get_schema(
        ReportIntentAnalyzer().analyze("Write a market landscape report on ExampleCo.")
    )
    agent.current_claim_ledger = [
        ClaimLedgerEntry(
            claim_id="claim_1",
            claim_text="ExampleCo still has unresolved benchmark gaps.",
            claim_category="factual",
            verification_status="unresolved",
        )
    ]
    agent.current_quantitative_checks = [
        QuantitativeCheckArtifact(
            name="addressable_revenue_ceiling",
            status="fail",
            details="Ceiling is materially below venture scale.",
        )
    ]
    agent.current_quality_gates = [
        QualityGateArtifact(
            name="claim_support",
            status="warn",
            summary="Claims remain unresolved.",
        )
    ]
    agent.current_run_trace = RunTraceArtifact(
        source_inputs_used=["uploaded_documents", "external_search"],
        simulation_used=False,
        simulation_reason="optional",
        graph_usage="Used as structured context.",
        search_queries_run=4,
        search_categories=["verification", "counterevidence"],
        externally_verified_claims=0,
        unresolved_claims=1,
        quality_gates=agent.current_quality_gates,
        major_gaps=["benchmark context"],
    )
    outline = ReportOutline(
        title="Market Report: ExampleCo",
        summary="Summary",
        sections=[
            ReportSection(title="Quantitative Checks", content="", key="quant_checks", description=""),
            ReportSection(title="Methodology Note", content="", key="methodology", description=""),
            ReportSection(title="Run Trace", content="", key="run_trace", description=""),
        ],
    )

    agent._refresh_structured_sections(outline)

    assert "FAIL" in outline.sections[0].content
    assert "Web searches run: 4" in outline.sections[1].content
    assert "Search categories: verification, counterevidence" in outline.sections[2].content


def test_report_agent_builds_concise_title_summary():
    fake_llm = SimpleNamespace(
        chat=lambda *args, **kwargs: "",
        chat_json=lambda *args, **kwargs: {"tasks": []},
    )
    agent = ReportAgent(
        graph_id="graph_1",
        simulation_id="sim_1",
        simulation_requirement="Will Fidget achieve product-market fit and become a venture-scale business within 24 months?",
        include_quality_assessment=False,
        llm_client=fake_llm,
    )
    agent.current_intent = ReportIntentAnalyzer().analyze(
        "Will Fidget achieve product-market fit and become a venture-scale business within 24 months?"
    )
    agent.current_schema = ReportSchemaRegistry().get_schema(agent.current_intent)
    agent.current_evidence_brief = EvidenceBriefArtifact(
        key_entities=["Fidget"],
    )
    agent.current_claim_ledger = [
        ClaimLedgerEntry(
            claim_id="claim_1",
            claim_text="Claim A",
            claim_category="factual",
            verification_status="unresolved",
        )
    ]
    agent.current_missing_inputs = [
        MissingCriticalInputArtifact(
            item="market size assumptions",
            why_it_matters="Needed for confidence.",
        )
    ]

    title_summary = agent._build_report_title_and_summary()

    assert title_summary["title"] == "Market Report: Fidget"
    assert "answering '" not in title_summary["summary"]
    assert "main gaps include market size assumptions" in title_summary["summary"].lower()


def build_test_app():
    app = Flask(__name__)
    app.register_blueprint(report_bp, url_prefix="/api/report")
    return app


def test_generate_report_route_passes_project_id(monkeypatch):
    app = build_test_app()
    client = app.test_client()

    monkeypatch.setattr(report_api.SimulationManager, "get_simulation", lambda self, simulation_id: SimpleNamespace(project_id="proj_1", graph_id="graph_1"))
    monkeypatch.setattr(report_api.ProjectManager, "get_project", lambda project_id: build_project())
    monkeypatch.setattr(report_api.ReportManager, "get_report_by_simulation", lambda simulation_id: None)

    created = {}

    class FakeTaskManager:
        def create_task(self, **kwargs):
            return "task_1"

        def update_task(self, *args, **kwargs):
            return None

        def complete_task(self, *args, **kwargs):
            return None

        def fail_task(self, *args, **kwargs):
            return None

    class FakeReportAgent:
        def __init__(self, **kwargs):
            created.update(kwargs)

        def generate_report(self, progress_callback=None, report_id=None):
            return Report(
                report_id=report_id or "report_1",
                simulation_id="sim_1",
                graph_id="graph_1",
                simulation_requirement="Requirement",
                project_id="proj_1",
                status=ReportStatus.COMPLETED,
            )

    class FakeThread:
        def __init__(self, target=None, daemon=None):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(report_api, "TaskManager", FakeTaskManager)
    monkeypatch.setattr(report_api, "ReportAgent", FakeReportAgent)
    monkeypatch.setattr(report_api.threading, "Thread", FakeThread)

    response = client.post("/api/report/generate", json={"simulation_id": "sim_1"})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert created["project_id"] == "proj_1"


def test_get_report_route_returns_new_metadata(monkeypatch):
    app = build_test_app()
    client = app.test_client()

    monkeypatch.setattr(
        report_api.ReportManager,
        "get_report",
        lambda report_id: Report(
            report_id=report_id,
            simulation_id="sim_1",
            graph_id="graph_1",
            simulation_requirement="Requirement",
            project_id="proj_1",
            status=ReportStatus.COMPLETED,
            intent={"report_type": "due_diligence"},
            quality_gates=[{"name": "claim_support", "status": "warn"}],
            run_trace={"search_queries_run": 4},
        ),
    )

    response = client.get("/api/report/report_1")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["data"]["intent"]["report_type"] == "due_diligence"
    assert payload["data"]["run_trace"]["search_queries_run"] == 4
