"""Tests cover semantic boundaries and source attribution; no model download."""
import unittest
from extract_ecc import normalize_framework


def raw_fixture():
    tables = []
    def table(page, rows):
        index = len(tables)
        tables.append({"self_ref": f"#/tables/{index}", "label": "table",
                       "prov": [{"page_no": page, "bbox": {"l": 0, "r": 100, "t": 100, "b": 0}}],
                       "data": {"table_cells": [
                           {"start_row_offset_idx": r, "start_col_offset_idx": c, "text": text}
                           for r, cells in enumerate(rows) for c, text in enumerate(cells)
                       ]}})
    table(22, [["2-2", "Access management"], ["Objective", "Protect access."],
               ["", "Restrict unauthorized users."], ["Controls", ""],
               ["2-2-1", "Document requirements."],
               ["2-2-3", "Minimum requirements:\n2.2.3.1 Use authentication."]])
    table(23, [["", "2.2.3.2 Review access."], ["2-2-4", "Review implementation."]])
    table(35, [["Term", "Definition"], ["Account", "A user identity."],
               ["", "Used to access a system."]])
    return {"body": {"children": [{"$ref": f"#/tables/{i}"} for i in range(len(tables))]},
            "tables": tables}


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.result = normalize_framework(raw_fixture(), "demo.pdf", "fixture", "success")

    def test_parent_and_subcontrols_are_distinct(self):
        records = {r["control_id"]: r for r in self.result["controls"]}
        self.assertEqual(records["2-2-3"]["requirement_text"], "Minimum requirements:")
        self.assertEqual(records["2-2-3-1"]["parent_id"], "2-2-3")
        self.assertEqual(records["2-2-3-2"]["requirement_text"], "Review access.")

    def test_cross_page_source_is_not_fabricated(self):
        rec = next(c for c in self.result["controls"] if c["control_id"] == "2-2-3-2")
        self.assertEqual(rec["source"][0]["pdf_page"], 23)
        self.assertEqual(rec["source"][0]["precision"], "table")

    def test_objective_is_not_a_requirement(self):
        self.assertEqual(self.result["subdomains"][0]["objective_text"],
                         "Protect access. Restrict unauthorized users.")
        self.assertNotIn("Protect access", str(self.result["controls"]))

    def test_definition_continuation(self):
        self.assertEqual(self.result["glossary"][0]["definition"],
                         "A user identity. Used to access a system.")

    def test_never_claims_reviewed(self):
        self.assertFalse(self.result["quality_report"]["ready_for_automatic_compliance_assessment"])
        self.assertTrue(all(c["review_status"] == "needs_review" for c in self.result["controls"]))

    def test_known_watermark_is_removed_not_content(self):
        from extract_ecc import clean
        self.assertEqual(clean("Review access. محدود - مقيد"), "Review access.")


if __name__ == "__main__":
    unittest.main()
