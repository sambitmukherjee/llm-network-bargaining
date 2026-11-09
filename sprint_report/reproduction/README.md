# Reproduction code and outputs

[Package index](../README.md) · [Workflow guide](../REPRODUCIBILITY.md) · [File inventory](../files_for_reproducibility.md)

Use [run.py](run.py) as the entry point. Its stages connect the selected scripts in the required order; generated files go under `../results/`. The experimental engine and core analysis/theory modules remain in the repository's existing `src/` tree.

| Files | Responsibility |
| --- | --- |
| [context.py](context.py), [run.py](run.py) | Paths, exact study roots and stage orchestration |
| [replay_saved.py](replay_saved.py) | Offline replay of saved episode decisions |
| [selected_analysis.py](selected_analysis.py), [statistical_helpers.py](adapted/statistical_helpers.py) | Retained estimates, bootstrap intervals, exact/Monte Carlo tests and independent null audits |
| [tables.py](tables.py), [late_prompt.py](late_prompt.py) | Fifteen tables, exact protocol examples and scripted late-game history |
| [figures.py](figures.py) | Six-figure generation and numerical/structural checks |
| [main_figures.py](main_figures.py) | Main Figures 1 and 2 |
| [draw_networks.py](draw_networks.py), [draw_matching.py](draw_matching.py) | Figures B1 and D1 |
| [draw_knowledge.py](adapted/draw_knowledge.py), [draw_outside_options.py](adapted/draw_outside_options.py) | Figures C1 and D2 |
| [provenance.py](provenance.py), [verification.py](verification.py) | Chronology/fingerprints, artifact integrity and retained narrative/theory checks |
| [release_files.txt](release_files.txt) | Exact report-file selection |

The `adapted/` subfolder identifies selected helpers copied before adaptation. Their origins are recorded in [helper_origins.json](../provenance/helper_origins.json). The statistical-helper bodies and original seeded procedures were preserved during the results-only refactor.

## Find a generated paper item

Paths below are relative to `sprint_report/results/` and are created by the workflow.

| Paper material | Generated files |
| --- | --- |
| Main Tables 1 and 2 | `tables/Table_1.md`, `tables/Table_2.md` |
| Appendix C Tables C1–C8 | `tables/Table_C1.md` through `tables/Table_C8.md` |
| Appendix B network/settings tables | `tables/B1_network_specification.md`, `tables/B3_request_settings.md` |
| Appendix D teaching tables | `tables/D1_four_round_example.md`, `tables/D2_link_contributions.md`, `tables/D4_episode_example.md` |
| Main Figures 1 and 2 | `figures/figure_1_completed_links.*`, `figures/figure_2_earnings.*` |
| Appendix Figures B1 and C1 | `figures/figure_b1_networks.*`, `figures/figure_c1_knowledge_differences.*` |
| Appendix Figures D1 and D2 | `figures/figure_d1_maximum_matchings_print.*`, `figures/figure_d2_outside_options.*` |
| Full-precision summaries and tests | `data/section_6/`, `data/appendices/`, `data/completed_links/` |
| Verification receipt and item-by-item map | `verification/receipt.json`, `verification/output_map.json` |

Every figure has PNG and SVG exports; four also have Matplotlib-generated PDF exports. These are individual plot exports, separate from the submitted paper. The [output map](../provenance/output_map.csv) provides the complete 40-route mapping. Generated outputs, receipts and draw archives are excluded from the file selection.

The generated `data/section_6/` path preserves the original analysis namespace. Its results support the shortened paper's Results Section 5 and Appendix C; it does not refer to the current Discussion Section 6.
