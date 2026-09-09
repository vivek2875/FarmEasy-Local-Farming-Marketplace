from pathlib import Path


def test_business_analysis_file_contains_documented_decision_queries() -> None:
    query_path = Path(__file__).resolve().parents[1] / "sql/analysis/01_business_queries.sql"
    query_file = query_path.read_text(encoding="utf-8")
    query_blocks = query_file.split("-- Query ")[1:]

    assert len(query_blocks) >= 15
    for block in query_blocks:
        assert "-- Business question:" in block
        assert "-- Why it matters:" in block
        assert "-- Expected interpretation:" in block
        assert ";" in block
    assert "LAG(" in query_file
    assert "LEAD(" in query_file
    assert "DENSE_RANK(" in query_file
    assert "COUNT(*) FILTER" in query_file
    assert "EXPLAIN (ANALYZE, BUFFERS)" in query_file
