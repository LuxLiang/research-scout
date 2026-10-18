"""Offline and mocked-HTTP tests. All scientific statements here are SYNTHETIC."""
from datetime import date
from hashlib import sha256
import json

import httpx
import pytest

from research_scout.comparison import ComparisonEngine
from research_scout.discovery import ArxivClient, InterestProfile, OpenAlexClient, SourcePaper
from research_scout.domain.models import (
    AssessmentStatus, Coverage, DeltaKind, Evidence, Mechanism, PreciseProblem, Result, Scope,
)
from research_scout.extraction import (
    ConfigurationError, FixtureProvider, OpenAICompatibleProvider, PaperPipeline,
)
from research_scout.ingestion import PaperIngestor
from research_scout.storage import Archive


@pytest.fixture
def archive(tmp_path):
    return Archive(tmp_path / "knowledge")


def source(version="v1", text="SYNTHETIC: A contraction argument proves a rate."):
    return SourcePaper(title="SYNTHETIC contraction", arxiv_id="2601.12345", version=version,
                       text=text, coverage=Coverage.FULL_TEXT, published=date(2026, 1, 1))


def scope(**changes):
    value = dict(domain="synthetic sampling", model="synthetic dynamics", objective="convergence",
                 assumptions=["smooth", "convex"], quantifiers=["all times"],
                 metric="total variation", guarantee="exponential decay")
    value.update(changes)
    return Scope(**value)


def extracted(ingested, text, suffix="a", problem_id=None, mechanism_id=None):
    paper, version = ingested.paper, ingested.version
    evidence = Evidence(id="evidence-" + suffix, title="SYNTHETIC quote", paper_id=paper.id,
                        version_id=version.id, locator=f"char:0-{len(text)}", quotation=text,
                        coverage=version.coverage, source_hash=version.content_hash, synthetic=True)
    mechanism = Mechanism(id=mechanism_id or "mechanism-" + suffix, title="SYNTHETIC coupling",
                          principle="shared synthetic noise", construction="same construction",
                          evidence_ids=[evidence.id], synthetic=True)
    problem = PreciseProblem(id=problem_id or "problem-" + suffix, title="SYNTHETIC problem",
                             statement="SYNTHETIC convergence question", scope=scope(),
                             desired_result="synthetic rate", evidence_ids=[evidence.id], synthetic=True)
    result = Result(id="result-" + suffix, title="SYNTHETIC theorem", paper_id=paper.id,
                    version_id=version.id, result_type="THEOREM", statement="synthetic decay",
                    scope=scope(), mechanism_ids=[mechanism.id], problem_ids=[problem.id],
                    evidence_ids=[evidence.id], synthetic=True)
    return [evidence, mechanism, problem, result]


def test_arxiv_http_adapter_retains_version_and_multilabels():
    content = '''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:x="http://arxiv.org/schemas/atom">
    <entry><id>http://arxiv.org/abs/2601.12345v2</id><title>SYNTHETIC\n title</title>
    <summary>SYNTHETIC abstract</summary><published>2026-01-02T00:00:00Z</published>
    <author><name>Fixture Author</name></author><x:doi>10.1234/SYNTHETIC</x:doi>
    <category term="cs.LG"/><category term="math.PR"/>
    <link href="https://arxiv.org/abs/2601.12345v2"/></entry></feed>'''

    def handle(request):
        assert "submittedDate" in request.url.params["search_query"]
        return httpx.Response(200, text=content)
    papers = ArxivClient(httpx.Client(transport=httpx.MockTransport(handle))).search(
        "cat:cs.LG", since=date(2026, 1, 1))
    assert papers[0].arxiv_id == "2601.12345"
    assert papers[0].version == "v2"
    assert papers[0].doi == "10.1234/synthetic"
    assert papers[0].labels == ["cs.LG", "math.PR"]
    assert papers[0].coverage == Coverage.ABSTRACT_ONLY


def test_openalex_metadata_and_citing_expansion():
    data = {"id": "https://openalex.org/W123", "title": "SYNTHETIC work",
            "doi": "https://doi.org/10.1234/SYNTHETIC", "publication_date": "2026-01-01",
            "abstract_inverted_index": {"SYNTHETIC": [0], "abstract": [1]},
            "locations": [{"landing_page_url": "https://arxiv.org/abs/2601.12345v2"}]}
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.params.get("filter"):
            assert request.url.params["filter"] == "cites:W123"
            return httpx.Response(200, json={"results": [data]})
        return httpx.Response(200, json=data)
    client = OpenAlexClient(httpx.Client(transport=httpx.MockTransport(handle)))
    work = client.lookup("10.1234/SYNTHETIC")
    assert work.abstract == "SYNTHETIC abstract"
    assert work.arxiv_id == "2601.12345" and work.version == "v2"
    assert len(client.expand_citations(work.doi)) == 1
    assert len(requests) == 3


def test_identity_aliases_versions_and_reingestion(archive, tmp_path):
    ingestor = PaperIngestor(archive, tmp_path / "cache")
    first = ingestor.ingest(source())
    repeated = ingestor.ingest(source())
    assert not repeated.is_new_version
    assert first.paper.id == repeated.paper.id
    second = ingestor.ingest(source(version="v2", text="SYNTHETIC: changed theorem."))
    assert second.paper.id == first.paper.id
    assert second.version.id != first.version.id
    assert second.version.supersedes_version_id == first.version.id
    assert len(archive.list("paper")) == 1 and len(archive.list("paper_version")) == 2
    assert archive.get(first.version.id).content_hash == sha256(source().text.encode()).hexdigest()


def test_local_content_dedup_and_partial_coverage(archive, tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("SYNTHETIC local source")
    second.write_text(first.read_text())
    ingestor = PaperIngestor(archive, tmp_path / "cache")
    a, b = ingestor.ingest(first), ingestor.ingest(second)
    assert a.paper.id == b.paper.id and not b.is_new_version
    assert a.version.coverage == Coverage.PARTIAL_TEXT
    assert b.paper.aliases == sorted(b.paper.aliases)


def test_missing_model_explicit_and_no_partial_publication(archive, tmp_path, monkeypatch):
    monkeypatch.delenv("SCOUT_MODEL", raising=False)
    monkeypatch.delenv("SCOUT_API_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        OpenAICompatibleProvider()
    with pytest.raises(ConfigurationError):
        PaperPipeline(archive, tmp_path / "cache").process(source())
    assert archive.list() == []
    outcome = PaperPipeline(archive, tmp_path / "cache").process(source(), extract=False)
    assert outcome.version.coverage == Coverage.FULL_TEXT


def test_structured_model_adapter_is_real_http_and_validated():
    def handle(request):
        payload = json.loads(request.content)
        assert payload["model"] == "synthetic-model"
        assert payload["response_format"] == {"type": "json_object"}
        assert request.headers["authorization"] == "Bearer dummy-test-key"
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "records": [], "labels": ["synthetic topic"], "limitations": ["no theorem supplied"],
        })}}]})
    provider = OpenAICompatibleProvider(model="synthetic-model", api_key="dummy-test-key",
                                       http_client=httpx.Client(transport=httpx.MockTransport(handle)))
    from research_scout.domain.models import Paper, PaperVersion
    paper = Paper(id="paper-test", title="SYNTHETIC paper")
    version = PaperVersion(id="version-test", title="SYNTHETIC version", paper_id=paper.id,
                           version="v1")
    assert provider.extract(paper, version, "SYNTHETIC text") == []
    assert provider.last_envelope.labels == ["synthetic topic"]


def test_pipeline_atomic_extraction_and_idempotence(archive, tmp_path):
    original = source()
    first = PaperIngestor(archive, tmp_path / "cache").ingest(original)
    records = extracted(first, original.text)
    pipeline = PaperPipeline(archive, tmp_path / "cache", FixtureProvider(records))
    output = pipeline.process(original)
    counts = len(archive.list())
    pipeline.process(original)
    assert len(archive.list()) == counts
    assert archive.get(first.paper.id).extraction_status == "EXTRACTED"
    assert len(archive.list("event")) == 1
    assert json.loads(open(output.stage_path).read())["status"] == "PUBLISHED"
    assert archive.validate() == []


def test_invented_evidence_rejected_without_scientific_update(archive, tmp_path):
    original = source()
    first = PaperIngestor(archive, tmp_path / "cache").ingest(original)
    records = extracted(first, original.text)
    records[0].quotation = "invented theorem"
    with pytest.raises(ValueError, match="absent from the source"):
        PaperPipeline(archive, tmp_path / "cache", FixtureProvider(records)).process(original)
    assert archive.list("result") == [] and archive.list("event") == []
    assert len(list((tmp_path / "cache" / "staging").glob("*.rejected-*.json"))) == 1


def test_extraction_cannot_promote_theorem_verification(archive, tmp_path):
    original = source()
    first = PaperIngestor(archive, tmp_path / "cache").ingest(original)
    records = extracted(first, original.text)
    records[-1].verification_status = "VERIFIED_BY_MODEL"
    with pytest.raises(ValueError, match="cannot verify"):
        PaperPipeline(archive, tmp_path / "cache", FixtureProvider(records)).process(original)
    assert not archive.list("result")


def test_abstract_coverage_never_silently_upgraded(archive, tmp_path):
    original = SourcePaper(title="SYNTHETIC abstract", abstract="SYNTHETIC abstract statement",
                           doi="10.1234/synthetic-abstract", coverage=Coverage.ABSTRACT_ONLY)
    first = PaperIngestor(archive, tmp_path / "cache").ingest(original)
    records = extracted(first, original.abstract)
    records[0].coverage = Coverage.FULL_TEXT
    with pytest.raises(ValueError, match="coverage/hash"):
        PaperPipeline(archive, tmp_path / "cache", FixtureProvider(records)).process(original)


def test_mechanism_reuse_keeps_distinct_applications_and_evidence(archive, tmp_path):
    original = source()
    first = PaperIngestor(archive, tmp_path / "cache").ingest(original)
    PaperPipeline(archive, tmp_path / "cache", FixtureProvider(extracted(first, original.text))).process(original)
    newer = source(text="SYNTHETIC: same mechanism for a different application.")
    newer.arxiv_id = "2602.12345"
    second = PaperIngestor(archive, tmp_path / "cache").ingest(newer)
    records = extracted(second, newer.text, suffix="b")
    result = PaperPipeline(archive, tmp_path / "cache", FixtureProvider(records)).process(newer)
    assert len(archive.list("mechanism")) == 1
    assert archive.get("result-b").mechanism_ids == ["mechanism-a"]
    assert len(archive.list("evidence")) == 2
    assert len(archive.list("application")) == 2
    assert all(item.outcome == "UNASSESSED" for item in archive.list("application"))
    assert DeltaKind.NEW_APPLICATION in result.comparisons[0].delta_kinds


def test_comparison_unknown_logical_implication_is_not_improvement(archive, tmp_path):
    original = source()
    first = PaperIngestor(archive, tmp_path / "cache").ingest(original)
    records = extracted(first, original.text)
    archive.put_many(records)
    old = records[-1]
    new = old.model_copy(update={"id": "result-different", "scope": scope(
        assumptions=["geodesic convexity"], guarantee="polynomial decay")})
    archive.put(new)
    comparison = ComparisonEngine(archive).compare_result(new, [old])
    assert DeltaKind.INCOMPARABLE_RESULTS in comparison.delta_kinds
    assert DeltaKind.STRONGER_GUARANTEE not in comparison.delta_kinds
    assert comparison.proof_obligations
    assert ComparisonEngine(archive).compare_result(new, [old]).id == comparison.id


def test_revision_flags_prior_comparison_and_preserves_history(archive, tmp_path):
    original = source()
    first = PaperIngestor(archive, tmp_path / "cache").ingest(original)
    PaperPipeline(archive, tmp_path / "cache", FixtureProvider(extracted(first, original.text))).process(original)
    previous = archive.list("comparison")[0]
    changed = PaperIngestor(archive, tmp_path / "cache").ingest(
        source(version="v2", text="SYNTHETIC revised theorem has stronger assumptions"))
    assert previous.id in changed.affected_ids
    comparison = archive.get(previous.id)
    assert comparison.needs_review and comparison.assessment_status == AssessmentStatus.NEEDS_REVIEW
    assert archive.get(first.version.id).id == first.version.id
    assert len(archive.list("event")) == 1


def test_profile_is_configurable_and_validated(tmp_path):
    path = tmp_path / "interest.json"
    path.write_text(json.dumps({"name": "synthetic", "arxiv_queries": ["cat:math.PR"],
                                "max_results": 5, "labels": ["probability"]}))
    assert InterestProfile.load(path).max_results == 5
    path.write_text('{"max_results": 0}')
    with pytest.raises(ValueError):
        InterestProfile.load(path)


def test_fixture_provider_explicit_synthetic_gate():
    mechanism = Mechanism(id="mechanism-real", title="Not a fixture", principle="x")
    with pytest.raises(ValueError, match="synthetic"):
        FixtureProvider([mechanism])


def test_identical_abstracts_do_not_merge_distinct_external_identities(archive, tmp_path):
    ingestor = PaperIngestor(archive, tmp_path / "cache")
    a = SourcePaper(title="SYNTHETIC first", doi="10.1234/first", abstract="Identical abstract",
                    coverage=Coverage.ABSTRACT_ONLY)
    b = SourcePaper(title="SYNTHETIC second", doi="10.1234/second", abstract="Identical abstract",
                    coverage=Coverage.ABSTRACT_ONLY)
    assert ingestor.ingest(a).paper.id != ingestor.ingest(b).paper.id
    assert len(archive.list("paper")) == 2


def test_source_enrichment_retains_abstract_and_fulltext_snapshots(archive, tmp_path):
    ingestor = PaperIngestor(archive, tmp_path / "cache")
    abstract = source()
    abstract.abstract, abstract.text = abstract.text, None
    abstract.coverage = Coverage.ABSTRACT_ONLY
    first = ingestor.ingest(abstract)
    full = source(text="SYNTHETIC complete paper text with main theorem.")
    second = ingestor.ingest(full)
    repeated = ingestor.ingest(full)
    assert first.paper.id == second.paper.id and first.version.id != second.version.id
    assert second.version.version.startswith("v1+content-")
    assert not repeated.is_new_version
    assert archive.get(first.version.id).coverage == Coverage.ABSTRACT_ONLY
    assert archive.get(second.version.id).coverage == Coverage.FULL_TEXT


def test_comparison_cache_invalidates_on_scientific_content_change(archive, tmp_path):
    original = source()
    first = PaperIngestor(archive, tmp_path / "cache").ingest(original)
    records = extracted(first, original.text)
    archive.put_many(records)
    old = records[-1]
    new = old.model_copy(update={"id": "result-cache"})
    archive.put(new)
    engine = ComparisonEngine(archive)
    before = engine.compare_result(new, [old])
    modified = old.model_copy(update={"rate": "SYNTHETIC different rate"})
    archive.put(modified)
    after = engine.compare_result(new, [modified])
    assert before.id != after.id
    assert DeltaKind.SAME_RESULT in before.delta_kinds
    assert DeltaKind.INCOMPARABLE_RESULTS in after.delta_kinds
    assert archive.get(before.id).delta_kinds == before.delta_kinds


def test_future_results_are_excluded_from_directional_comparison(archive, tmp_path):
    ingestor = PaperIngestor(archive, tmp_path / "cache")
    original = source()
    first = ingestor.ingest(original)
    records = extracted(first, original.text)
    archive.put_many(records)
    future_source = source(text="SYNTHETIC future source")
    future_source.arxiv_id, future_source.published = "2602.99999", date(2026, 2, 1)
    future = ingestor.ingest(future_source)
    future_records = extracted(future, future_source.text, suffix="future")
    archive.put_many(future_records)
    comparison = ComparisonEngine(archive).compare_result(records[-1], [future_records[-1]])
    assert comparison.compared_result_ids == []
    assert DeltaKind.INSUFFICIENT_EVIDENCE in comparison.delta_kinds


def test_same_construction_reused_across_applicable_models_and_domains(archive, tmp_path):
    ingestor = PaperIngestor(archive, tmp_path / "cache")
    first_source = source()
    first = ingestor.ingest(first_source)
    first_records = extracted(first, first_source.text, suffix="domain-a")
    first_records[1].applicable_models = ["synthetic sampling dynamics"]
    first_records[1].proof_role = "establish mixing of the synthetic chain"
    PaperPipeline(archive, tmp_path / "cache", FixtureProvider(first_records)).process(first_source)

    second_source = source(text="SYNTHETIC same construction applied to online prediction.")
    second_source.arxiv_id = "2603.12345"
    second = ingestor.ingest(second_source)
    second_records = extracted(second, second_source.text, suffix="domain-b")
    second_records[1].applicable_models = ["synthetic online prediction"]
    second_records[1].proof_role = "control cumulative synthetic prediction error"
    target_scope = scope(domain="synthetic online learning", model="synthetic online prediction",
                         objective="prediction", metric="regret", guarantee="sublinear regret")
    second_records[2].scope = target_scope
    second_records[3].scope = target_scope
    outcome = PaperPipeline(archive, tmp_path / "cache", FixtureProvider(second_records)).process(second_source)

    assert len(archive.list("mechanism")) == 1
    assert archive.get("result-domain-b").mechanism_ids == ["mechanism-domain-a"]
    applications = archive.list("application")
    assert len(applications) == 2
    assert {item.scope.domain for item in applications} == {
        "synthetic sampling", "synthetic online learning",
    }
    assert DeltaKind.NEW_APPLICATION in outcome.comparisons[0].delta_kinds


def _write_synthetic_pdf(path, with_text=True, extra_blank_page=False):
    """Generate an actual minimal PDF, not a mock PDF extraction result."""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    if with_text:
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 72 720 Td (SYNTHETIC local PDF theorem text.) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
    if extra_blank_page:
        writer.add_blank_page(width=612, height=792)
    writer.write(path)


def test_actual_local_pdf_text_extraction_and_hash(archive, tmp_path):
    pytest.importorskip("pypdf")
    path = tmp_path / "synthetic.pdf"
    _write_synthetic_pdf(path)
    ingested = PaperIngestor(archive, tmp_path / "cache").ingest(path)
    assert ingested.version.coverage == Coverage.FULL_TEXT
    from pathlib import Path
    assert "SYNTHETIC local PDF theorem text." in Path(ingested.version.text_path).read_text()
    assert ingested.version.content_hash == sha256(path.read_bytes()).hexdigest()
    assert Path(ingested.version.source_path).read_bytes() == path.read_bytes()
    assert archive.validate() == []


def test_actual_blank_pdf_rejected_without_records(archive, tmp_path):
    pytest.importorskip("pypdf")
    path = tmp_path / "synthetic-blank.pdf"
    _write_synthetic_pdf(path, with_text=False)
    with pytest.raises(ValueError, match="no extractable text; OCR is required"):
        PaperIngestor(archive, tmp_path / "cache").ingest(path)
    assert archive.list() == []


def test_actual_pdf_with_unreadable_page_retains_partial_coverage(archive, tmp_path):
    pytest.importorskip("pypdf")
    path = tmp_path / "synthetic-partial.pdf"
    _write_synthetic_pdf(path, extra_blank_page=True)
    ingested = PaperIngestor(archive, tmp_path / "cache").ingest(path)
    assert ingested.version.coverage == Coverage.PARTIAL_TEXT


def test_structured_paper_metadata_is_persisted(tmp_path):
    from research_scout.extraction import ExtractionEnvelope, PaperPipeline
    from research_scout.discovery import SourcePaper
    from research_scout.storage import Archive
    from research_scout.domain.models import Coverage
    class MetadataProvider:
        last_envelope=ExtractionEnvelope(research_questions=['SYNTHETIC question'],
            methods=['SYNTHETIC energy method'],proof_techniques=['SYNTHETIC coercivity estimate'],
            contributions=['SYNTHETIC scoped finding'])
        def extract(self,paper,version,text):
            return []
    archive=Archive(tmp_path/'knowledge')
    source=SourcePaper(title='SYNTHETIC metadata extraction',text='SYNTHETIC prose',
        coverage=Coverage.FULL_TEXT,provenance='explicit test source')
    result=PaperPipeline(archive,tmp_path/'cache',MetadataProvider()).process(source)
    saved=archive.get(result.paper.id)
    assert saved.research_questions==['SYNTHETIC question']
    assert saved.methods==['SYNTHETIC energy method']
    assert saved.proof_techniques==['SYNTHETIC coercivity estimate']
    assert saved.contributions==['SYNTHETIC scoped finding']


def test_reverse_revision_ingestion_keeps_scientific_order(tmp_path):
    from research_scout.discovery import SourcePaper
    from research_scout.domain.models import Coverage
    from research_scout.ingestion import PaperIngestor
    from research_scout.storage import Archive
    archive=Archive(tmp_path/'knowledge')
    ingestor=PaperIngestor(archive,tmp_path/'cache')
    for version in ['v3','v2','v1']:
        result=ingestor.ingest(SourcePaper(title='SYNTHETIC reverse versions',
            arxiv_id='2601.99999',version=version,text=f'SYNTHETIC text {version}',
            coverage=Coverage.FULL_TEXT))
    paper=archive.get(result.paper.id)
    assert [archive.get(v).version for v in paper.version_ids]==['v1','v2','v3']
    assert archive.get(paper.version_ids[0]).supersedes_version_id is None


def test_cached_ingestion_resumes_without_source_download(tmp_path,monkeypatch):
    from research_scout.discovery import SourcePaper
    from research_scout.domain.models import Coverage
    from research_scout.extraction import ExtractionEnvelope, PaperPipeline
    from research_scout.storage import Archive
    archive=Archive(tmp_path/'knowledge')
    class Provider:
        last_envelope=ExtractionEnvelope()
        def extract(self,paper,version,text):
            assert text=='cached source'
            return []
    pipeline=PaperPipeline(archive,tmp_path/'sources',Provider())
    ingested=pipeline.ingestor.ingest(SourcePaper(title='Cached source',text='cached source',coverage=Coverage.FULL_TEXT))
    def no_download(*args,**kwargs):
        raise AssertionError('Cached source must not be fetched again')
    monkeypatch.setattr(pipeline.ingestor,'ingest',no_download)
    out=pipeline.process(ingested)
    assert out.version.id==ingested.version.id
    assert archive.get(ingested.paper.id).extraction_status=='EXTRACTED'
