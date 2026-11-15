import math
import statistics
import time

from sqlalchemy import event

from backend.app.services import course_test_events
from backend.app.services.course_research_dataset import course_research_insights, import_course_research_bundle


def test_course_research_insights_query_budget(backend_client, monkeypatch, tmp_path):
    _client, factory, _github = backend_client
    monkeypatch.setattr(course_test_events, "_snapshot", lambda: None)
    with factory() as session:
        import_course_research_bundle(session, archive_root=tmp_path / "raw")
        query_counts = []
        durations = []

        def count_query(_connection, _cursor, _statement, _parameters, _context, _executemany):
            query_counts[-1] += 1

        engine = session.get_bind()
        event.listen(engine, "before_cursor_execute", count_query)
        try:
            result = None
            for _ in range(6):
                session.expunge_all()
                query_counts.append(0)
                started = time.perf_counter()
                result = course_research_insights(session, "course-research-300-v1")
                durations.append((time.perf_counter() - started) * 1000)
        finally:
            event.remove(engine, "before_cursor_execute", count_query)
    ordered = sorted(durations)
    p95 = ordered[math.ceil(len(ordered) * 0.95) - 1]
    print(f"course_research_insights_sql_queries={query_counts} p50_ms={statistics.median(durations):.2f} p95_ms={p95:.2f}")
    assert result["sample_size"] == 300
    assert query_counts == [6] * 6, f"300 仓库研究摘要应保持固定查询预算，实际为 {query_counts}"
