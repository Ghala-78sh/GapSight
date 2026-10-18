"""Docling -> source-traceable ECC-2:2024 English framework JSON.

This is an edition-specific parser, not a universal policy parser. It never
classifies organizational compliance and never invents missing source text.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path


PROFILE = {
    "name": "NCA ECC", "version": "ECC-2:2024", "language": "en",
    "controls_pages": [16, 34], "glossary_pages": [35, 43],
    "scope_pages": [12, 12], "abbreviations_pages": [44, 44],
    "framework_objective_pages": [11, 11],
    "expected_main_controls": 108, "expected_subdomains": 28,
    "source_url": "https://cdn.nca.gov.sa/api/files/public/upload/86e09090-44e4-481f-bc28-355673607654_ECC--2024-EN.pdf",
}
DOMAINS = {
    "1": "Cybersecurity Governance", "2": "Cybersecurity Defense",
    "3": "Cybersecurity Resilience",
    "4": "Third-Party and Cloud Computing Cybersecurity",
}
ID = r"[1-4](?:[.\-]\d{1,2}){2,3}"
CONTROL_ID = re.compile(rf"^{ID}$")
SECTION_ID = re.compile(r"^[1-4][.\-]\d{1,2}$")
CHILD_ID = re.compile(r"(?<![\w.\-])([1-4](?:[.\-]\d{1,2}){3})(?=\s|$)")


def clean(text):
    """Remove this edition's known watermark; preserve untouched raw export.

    NFKC joins Arabic presentation forms so the printed watermark can be matched.
    This cleanup is deliberately specific to the English ECC profile.
    """
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = re.sub(r"محدود\s*[-–—]?\s*مقيد|محدود|مقيد", "", text)
    return " ".join(text.split())


def canonical(value):
    return str(value).replace(".", "-")


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def provenance(item, row=None):
    result = []
    for prov in item.get("prov", []):
        result.append({
            "pdf_page": prov.get("page_no"),
            "bbox": prov.get("bbox"),
            "docling_ref": item.get("self_ref"),
            "table_row": row,
            "precision": "table" if row is not None else "item",
        })
    return result


def in_range(unit, bounds):
    return any(p.get("pdf_page") is not None and
               bounds[0] <= p["pdf_page"] <= bounds[1]
               for p in unit["source"])


def ordered_units(raw):
    """Walk body references in document order, retaining table row structure.

    Table provenance is deliberately table-level, not fabricated cell-level
    precision. Merged cells are read once at their starting row.
    """
    seen = set()

    def resolve(ref):
        value = raw
        for part in ref.removeprefix("#/").split("/"):
            value = value[int(part)] if isinstance(value, list) else value[part]
        return value

    def walk(item):
        ref = item.get("self_ref")
        if ref in seen:
            return
        if ref:
            seen.add(ref)
        label = str(item.get("label", ""))
        if label in {"page_header", "page_footer"}:
            return
        if "table_cells" in item.get("data", {}):
            rows = defaultdict(list)
            for cell in item["data"]["table_cells"]:
                rows[cell["start_row_offset_idx"]].append(cell)
            for index, cells in sorted(rows.items()):
                cells.sort(key=lambda c: c["start_col_offset_idx"])
                texts = [c.get("text", "") for c in cells]
                if any(clean(t) for t in texts):
                    yield {"kind": "table_row", "cells": texts,
                           "text": "\n".join(texts),
                           "source": provenance(item, index)}
        elif item.get("text"):
            yield {"kind": label, "cells": [item["text"]],
                   "text": item["text"], "source": provenance(item)}
        for child in item.get("children", []):
            yield from walk(resolve(child["$ref"]))

    yield from walk(raw["body"])


def normalize_framework(raw, source_name, fingerprint, conversion_status):
    all_units = list(ordered_units(raw))
    excluded_units = [u for u in all_units if u["kind"] != "table_row" and
                      (not clean(u["text"]).strip("-–— ") or
                       re.fullmatch(r"[\d\s-]+", clean(u["text"])))]
    units = [u for u in all_units if u not in excluded_units]
    sections, controls, glossary = {}, {}, []
    warnings = []
    current_section = current_control = None
    objective_mode = False
    used = set()

    def add_control(original_id, text, source):
        nonlocal current_control
        cid = canonical(original_id)
        sid = "-".join(cid.split("-")[:2])
        if current_section != sid:
            warnings.append(f"Control {cid} has missing/mismatched section context.")
        if cid not in controls:
            controls[cid] = {
                "control_id": cid, "source_control_id": original_id,
                "parent_id": "-".join(cid.split("-")[:-1]) if cid.count("-") == 3 else None,
                "subdomain_id": sid, "domain_id": cid.split("-")[0],
                "requirement_text": "", "source": [],
                "review_status": "needs_review",
            }
        elif clean(text) and clean(text) != controls[cid]["requirement_text"]:
            warnings.append(f"Repeated ID {cid}: inspect merged fragments.")
        current_control = cid
        append_control(text, source)

    def append_control(text, source):
        if current_control and clean(text):
            rec = controls[current_control]
            rec["requirement_text"] = clean(rec["requirement_text"] + " " + text)
            for s in source:
                if s not in rec["source"]:
                    rec["source"].append(s)

    def consume(text, source):
        """Split four-component subcontrol identifiers from parent row bodies."""
        matches = list(CHILD_ID.finditer(text))
        if not matches:
            append_control(text, source)
            return
        append_control(text[:matches[0].start()], source)
        for i, match in enumerate(matches):
            end = matches[i+1].start() if i+1 < len(matches) else len(text)
            add_control(match.group(1), text[match.end():end], source)

    for i, unit in enumerate(units):
        if not in_range(unit, PROFILE["controls_pages"]):
            continue
        cells = [clean(t) for t in unit["cells"]]
        if not cells:
            continue
        key = cells[0]
        body = "\n".join(unit["cells"][1:])
        # Text headings may contain ID and title in a single item.
        heading = re.match(r"^([1-4][.\-]\d{1,2})\s+(.+)$", key)
        if SECTION_ID.fullmatch(key) or (heading and unit["kind"] != "table_row"):
            sid = canonical(key if not heading else heading.group(1))
            title = clean(body if not heading else heading.group(2))
            current_section, current_control, objective_mode = sid, None, False
            if sid not in sections:
                sections[sid] = {"subdomain_id": sid, "domain_id": sid.split("-")[0],
                                 "title": title, "objective_text": "", "source": [],
                                 "review_status": "needs_review"}
            sections[sid]["source"].extend(unit["source"])
            used.add(i)
        elif key.lower() == "objective" and current_section:
            objective_mode = True
            current_control = None
            sections[current_section]["objective_text"] = clean(body)
            sections[current_section]["source"].extend(unit["source"])
            used.add(i)
        elif key.lower() == "controls":
            objective_mode = False
            used.add(i)
        elif CONTROL_ID.fullmatch(key):
            objective_mode = False
            add_control(key, "", unit["source"])
            consume(body, unit["source"])
            used.add(i)
        elif unit["kind"] != "table_row" and (m := re.match(rf"^({ID})\s+(.+)$", key, re.S)):
            objective_mode = False
            add_control(m.group(1), "", unit["source"])
            consume(m.group(2), unit["source"])
            used.add(i)
        elif objective_mode and current_section:
            rec = sections[current_section]
            rec["objective_text"] = clean(rec["objective_text"] + " " + unit["text"])
            rec["source"].extend(unit["source"])
            used.add(i)
        elif current_control and unit["kind"] == "table_row":
            consume(unit["text"], unit["source"])
            used.add(i)
        elif current_control and unit["kind"] in {"text", "list_item", "paragraph"}:
            consume(unit["text"], unit["source"])
            used.add(i)

    # Glossary rows retain definitions verbatim except whitespace normalization.
    for i, unit in enumerate(units):
        if not in_range(unit, PROFILE["glossary_pages"]) or unit["kind"] != "table_row":
            continue
        cells = [clean(c) for c in unit["cells"]]
        if len(cells) < 2:
            continue
        term, definition = cells[0], clean(" ".join(cells[1:]))
        if term.lower() in {"term", "terms"}:
            used.add(i)
            continue
        if term and definition:
            glossary.append({"term": term, "definition": definition,
                             "source": unit["source"], "review_status": "needs_review"})
            used.add(i)
        elif not term and definition and glossary:
            glossary[-1]["definition"] = clean(glossary[-1]["definition"] + " " + definition)
            glossary[-1]["source"].extend(unit["source"])
            used.add(i)

    # Keep applicability as sourced context, not an automatic legal decision.
    context = [u for u in units if in_range(u, PROFILE["scope_pages"])]
    abbreviations = [u for u in units if in_range(u, PROFILE["abbreviations_pages"])]
    unclassified = [u for i, u in enumerate(units)
                    if i not in used and (in_range(u, PROFILE["controls_pages"]) or
                                          in_range(u, PROFILE["glossary_pages"]))]
    for rec in controls.values():
        if not rec["requirement_text"]:
            warnings.append(f"Empty control text: {rec['control_id']}")
        if not rec["source"]:
            warnings.append(f"Missing provenance: {rec['control_id']}")
        if rec["parent_id"] and rec["parent_id"] not in controls:
            warnings.append(f"Missing parent: {rec['control_id']}")
    for sid, rec in sections.items():
        if not rec["objective_text"]:
            warnings.append(f"Missing objective: {sid}")
    if not controls:
        warnings.append("No controls found. Do not proceed to RAG.")
    if not glossary:
        warnings.append("No glossary entries found; inspect glossary tables.")
    main_count = sum(c["parent_id"] is None for c in controls.values())
    if main_count != PROFILE["expected_main_controls"]:
        warnings.append(f"Main control count {main_count} differs from the source total 108.")
    if len(sections) != PROFILE["expected_subdomains"]:
        warnings.append(f"Subdomain count {len(sections)} differs from the source total 28.")
    warnings.append("All records require source review. Extraction completeness is not certified.")
    if conversion_status != "success":
        warnings.append(f"Docling conversion status: {conversion_status}")
    docling_version = importlib.metadata.version("docling") if importlib.util.find_spec("docling") else "not installed"
    report = {
        "conversion_status": conversion_status, "controls_including_subcontrols": len(controls),
        "main_controls": sum(c["parent_id"] is None for c in controls.values()),
        "expected_main_controls": PROFILE["expected_main_controls"],
        "expected_subdomains": PROFILE["expected_subdomains"],
        "subcontrols": sum(c["parent_id"] is not None for c in controls.values()),
        "subdomains": len(sections), "glossary_entries": len(glossary),
        "unclassified_units": len(unclassified), "warnings": sorted(set(warnings)),
        "excluded_furniture_units": len(excluded_units),
        "ready_for_automatic_compliance_assessment": False,
    }
    result = {
        "schema_version": "1.0", "document_role": "requirements",
        "framework": {"name": PROFILE["name"], "version": PROFILE["version"],
                      "language": "en", "source_file": source_name,
                      "source_sha256": fingerprint, "source_url": PROFILE["source_url"],
                      "parser_profile": PROFILE, "docling_version": docling_version},
        "domains": [{"domain_id": k, "title": v} for k,v in DOMAINS.items()],
        "subdomains": list(sections.values()), "controls": list(controls.values()),
        "glossary": glossary, "scope_and_applicability_context": context,
        "framework_objective_context": [u for u in units if in_range(u, PROFILE["framework_objective_pages"])],
        "abbreviations_source_units": abbreviations,
        "unclassified_units": unclassified, "quality_report": report,
        "excluded_furniture_units": excluded_units,
    }
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf", type=Path, help="ECC-2:2024 English PDF, matching this profile")
    ap.add_argument("--out", type=Path, default=Path("gapsight_output"))
    ap.add_argument("--from-docling-json", type=Path, help="Reuse previous native Docling export")
    ap.add_argument("--ocr", action="store_true", help="Enable OCR; default off for text-based ECC")
    ap.add_argument("--artifacts-path", type=Path, help="Pre-downloaded Docling model directory")
    args = ap.parse_args()
    if not args.pdf.is_file():
        ap.error("PDF file not found.")
    args.out.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    if args.from_docling_json:
        manifest_path = args.from_docling_json.parent / "source_manifest.json"
        if not manifest_path.is_file():
            ap.error("Cached Docling JSON needs its source_manifest.json for PDF identity verification.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("source_sha256") != fingerprint:
            ap.error("Cached Docling JSON belongs to a different PDF (SHA-256 mismatch).")
        raw = json.loads(args.from_docling_json.read_text(encoding="utf-8"))
        if raw.get("origin", {}).get("filename") != args.pdf.name:
            ap.error("Cached document filename differs from PDF. Use the original matching file.")
        status = manifest.get("conversion_status", "unknown_cached_status")
    else:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
        options = PdfPipelineOptions()
        options.do_ocr = args.ocr
        options.do_table_structure = True
        options.table_structure_options.mode = TableFormerMode.ACCURATE
        options.table_structure_options.do_cell_matching = True
        if args.artifacts_path:
            options.artifacts_path = args.artifacts_path
        converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
        print("Converting PDF with Docling. The first run may download model weights.", flush=True)
        converted = converter.convert(args.pdf)
        status = getattr(converted.status, "value", str(converted.status)).lower()
        raw = converted.document.export_to_dict()
        write_json(args.out / "docling_raw.json", raw)
        write_json(args.out / "source_manifest.json", {
            "source_file": args.pdf.name, "source_sha256": fingerprint,
            "conversion_status": status,
        })
        (args.out / "document.md").write_text(converted.document.export_to_markdown(), encoding="utf-8")
    if len(raw.get("pages", {})) != 56:
        ap.error("This parser profile expects the 56-page English ECC PDF. Edit/review the profile for another edition.")
    result = normalize_framework(raw, args.pdf.name, fingerprint, status)
    write_json(args.out / "framework.json", result)
    write_json(args.out / "quality_report.json", result["quality_report"])
    print(json.dumps(result["quality_report"], indent=2))
    print("Output:", args.out / "framework.json")
    return 0 if result["controls"] else 2


if __name__ == "__main__":
    sys.exit(main())
