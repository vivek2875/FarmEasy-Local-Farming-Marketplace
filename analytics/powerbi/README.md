# Power BI assets

This folder intentionally does not claim to include a `.pbix` file. Power BI
workbooks are binary and user/environment specific; the version-controlled SQL
views, DAX measures, theme, and build guide make the dashboard reproducible.

Use:

- `farmeasy_mandi_measures.dax` for reusable measures.
- `farmeasy_mandi_theme.json` for the accessible FarmEasy visual palette.
- [`../docs/powerbi-build-guide.md`](../docs/powerbi-build-guide.md) for the
  model, page-by-page specification, and Windows import steps.

Do not add the Supply and Arrivals page or its measures until the optional
verified-arrivals source has been approved and loaded. The default Data.gov.in
daily price resource has no documented arrival quantity/unit.
