"""Runtime verification for the portfolio EDA notebook.

The notebook is executed only against a tiny deterministic fixture so the
regular suite never relies on a live government endpoint or a local database.
"""

from pathlib import Path

import pytest


def test_eda_notebook_executes_against_synthetic_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    """The documented analysis should run end-to-end with a valid CSV contract."""
    nbformat = pytest.importorskip("nbformat")
    pytest.importorskip("matplotlib")
    pytest.importorskip("seaborn")
    pytest.importorskip("ipykernel")
    from nbclient import NotebookClient

    analytics_root = Path(__file__).resolve().parents[1]
    fixture_directory = analytics_root / "tests" / "fixtures"
    notebook_path = analytics_root / "notebooks" / "mandi_price_eda.ipynb"

    monkeypatch.setenv(
        "FARMEASY_EDA_DATA_PATH", str(fixture_directory / "eda_validated_fixture.csv")
    )
    monkeypatch.setenv(
        "FARMEASY_EDA_QUALITY_REPORT_PATH",
        str(fixture_directory / "eda_quality_report_fixture.json"),
    )
    monkeypatch.setenv("MPLBACKEND", "Agg")

    notebook = nbformat.read(notebook_path, as_version=4)
    NotebookClient(notebook, timeout=120, kernel_name="python3").execute()
