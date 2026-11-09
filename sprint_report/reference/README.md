# Compact comparison references

[Package index](../README.md) · [Workflow guide](../REPRODUCIBILITY.md)

These three files let readers check fresh results without downloading the manuscript, old plot images, full derived-data snapshots or saved bootstrap/null arrays.

| File | Purpose |
| --- | --- |
| [claims.json](claims.json) | Full-precision numerical targets, protocol/history checks and declared hypothetical teaching inputs |
| [tables.json](tables.json) | Headers, captions, display order and expected cells for all fifteen tables |
| [figure_values.json](figure_values.json) | Coordinates for the main plots and H5 comparison, eight network topologies, five maximum matchings and outside-option values |

The code first calculates empirical estimates from the saved study logs, then compares them with these targets. Table headings/order may guide presentation; expected empirical cells do not supply the generated estimates. Hypothetical teaching sequences are intentionally declared inputs and are labeled separately from study observations.

[verification.py](../reproduction/verification.py), [tables.py](../reproduction/tables.py) and [figures.py](../reproduction/figures.py) perform the comparisons. Historical source paths and hashes embedded in the JSON record attribution; reproducing results does not open those private/archive paths. The [method specification](../provenance/reproduction_spec.json) records the scientific procedures that the fresh calculations preserve.
