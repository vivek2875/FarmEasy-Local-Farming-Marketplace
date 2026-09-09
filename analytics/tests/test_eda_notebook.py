import json
from pathlib import Path


def test_eda_notebook_is_valid_and_contains_required_analysis_sections() -> None:
    notebook_path = Path(__file__).resolve().parents[1] / "notebooks/mandi_price_eda.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    markdown = "\n".join(
        "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "markdown"
    )
    code_cells = [
        "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"
    ]

    for heading in (
        "Dataset overview",
        "Missing values",
        "Price distribution",
        "Commodity-level analysis",
        "Market, state, and district comparison",
        "Time-series analysis",
        "Volatility and outlier investigation",
        "Data-quality conclusions",
        "Generated findings and actionable recommendations",
    ):
        assert heading in markdown
    assert len(code_cells) >= 8
    assert "findings = [" in "\n".join(code_cells)
    assert "recommendations = [" in "\n".join(code_cells)
    assert "arrival quantity" in markdown.lower()
    code_source = "\n".join(code_cells)
    assert code_source.count("plt.title") >= 5
    assert code_source.count("plt.xlabel") >= 5
    assert code_source.count("plt.ylabel") >= 5
    for position, code in enumerate(code_cells):
        compile(code, f"eda-cell-{position}", "exec")
