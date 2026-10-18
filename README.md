# GapSight: Docling Framework Extraction

Extract the specified 56-page English NCA ECC-2:2024 PDF into a source-traceable JSON representation for subsequent GapSight data preparation.

## Scope and status

This module performs document extraction and normalization. It does not assess organizational compliance and does not report RAG benchmark results. It is edition-specific: another framework, edition, or language requires a reviewed parser profile.

## Run in Google Colab

1. Open `GapSight_Docling.ipynb` in Colab.
2. Download the framework PDF from the official source below and upload it through the Files panel as `ECC-2-2024-EN.pdf`.
3. Run the notebook cells in order. The full extraction script is embedded in the notebook.
4. Inspect the JSON and quality report, then download the output archive.

The first run downloads model weights. No paid LLM API key is required. If Colab requests a session restart after installation, restart and continue from the script-creation cell.

## Run locally

Python 3.12 was used for the original extraction run. Create and activate a virtual environment, then run:

```bash
python -m pip install -r requirements.txt
python extract_ecc.py ECC-2-2024-EN.pdf --out gapsight_output
```

The requests pin addresses the reported target Colab runtime requirement. Future runtimes may need a different pin; verify compatibility before updating dependencies.

## Output files

| File | Purpose |
| --- | --- |
| `framework.json` | Framework metadata, domains, subdomains, controls, glossary, and source context |
| `quality_report.json` | Extraction counts and warnings |
| `docling_raw.json` | Native Docling structure for review and reprocessing |
| `document.md` | Readable document export |
| `source_manifest.json` | Source PDF identity and conversion status |

Controls retain canonical and original identifiers, parent-child links, and source provenance. Objectives and definitions remain separate from control requirements. Applicability is preserved as source context rather than an automatic legal determination. Unclassified units remain available for inspection.

## Review requirements

Every record initially uses `needs_review`. Check control wording, identifiers, parents, pages, definitions, and unclassified content against the source PDF before using the output in a compliance workflow. Table coordinates provide table-level provenance rather than exact cell locations.

The English-edition cleanup normalizes Unicode and removes known Arabic watermark text. The Arabic literals in the matching expression and test fixture are intentional. Do not reuse those cleanup rules for an Arabic edition without revision. The native Docling export preserves the unmodified conversion output.

## Verification

The original run with Docling 2.140.0 extracted 108 main controls, 92 sub-controls, 28 subdomains, and 70 glossary entries. Main and sub-control identifier sets matched an independent extraction. Six parser tests passed. Eighteen unclassified units were retained. This does not certify all extracted text or glossary completeness. See `verification_report.json` for limitations.

This revision translates notebook prose and checks notebook syntax and packaging; it does not rerun the full model conversion in Colab.

```bash
python -m unittest -v test_parser
```

To reprocess a native export without rerunning the models:

```bash
python extract_ecc.py ECC-2-2024-EN.pdf --from-docling-json gapsight_output/docling_raw.json --out gapsight_output
```

Keep `source_manifest.json` beside the native export. The script checks the source PDF hash before reusing cached data.

## References

- [Official NCA ECC PDF](https://cdn.nca.gov.sa/api/files/public/upload/86e09090-44e4-481f-bc28-355673607654_ECC--2024-EN.pdf)
- [Docling documentation](https://docling-project.github.io/docling/)
