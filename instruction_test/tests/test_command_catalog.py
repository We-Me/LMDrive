import ast
import sys
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TEST_DIR.parent
sys.path.insert(0, str(TEST_DIR))

from command_catalog import (  # noqa: E402
    INSTRUCTION_SYMBOLS,
    InstructionCatalog,
    InstructionResolutionError,
)


class InstructionCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = InstructionCatalog(
            REPO_ROOT
            / "leaderboard"
            / "leaderboard"
            / "envs"
            / "instruction_dict.json"
        )

    def test_all_65_symbols_match_their_ids(self):
        self.assertEqual(65, len(INSTRUCTION_SYMBOLS))
        self.assertEqual(65, len(self.catalog.specs))
        for expected_id, spec in enumerate(self.catalog.specs):
            if spec.symbol == "Other-05":
                command = "{} 30 left 5".format(spec.symbol)
            elif spec.argument_names:
                command = "{} 20".format(spec.symbol)
            else:
                command = spec.symbol
            resolved = self.catalog.resolve(command)
            self.assertEqual(expected_id, resolved.instruction_id)
            self.assertEqual(INSTRUCTION_SYMBOLS[expected_id], resolved.symbol)

    def test_symbol_order_matches_the_project_data_parser(self):
        parser_path = REPO_ROOT / "tools" / "data_parsing" / "parse_instruction.py"
        tree = ast.parse(parser_path.read_text(encoding="utf-8"))
        registered_keys = None
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(
                isinstance(target, ast.Name)
                and target.id == "registered_class"
                for target in node.targets
            ):
                continue
            registered_keys = tuple(
                key.value for key in node.value.keys if isinstance(key, ast.Constant)
            )
            break
        self.assertIsNotNone(registered_keys)
        self.assertEqual(INSTRUCTION_SYMBOLS, registered_keys)

    def test_requested_turn_command(self):
        resolved = self.catalog.resolve("Turn-02-L")
        self.assertEqual(4, resolved.instruction_id)
        self.assertEqual("Turn", resolved.category)
        self.assertIn("left", resolved.text.lower())

    def test_symbol_lookup_is_case_insensitive(self):
        resolved = self.catalog.resolve("turn-02-l")
        self.assertEqual("Turn-02-L", resolved.symbol)

    def test_id_lookup(self):
        self.assertEqual("Turn-02-L", self.catalog.resolve("id 4").symbol)
        self.assertEqual("Turn-02-L", self.catalog.resolve("4").symbol)

    def test_distance_argument_is_substituted(self):
        resolved = self.catalog.resolve("Turn-02-L-dis 20")
        self.assertIn("20", resolved.text)
        self.assertNotIn("[x]", resolved.text)

    def test_other_05_arguments_are_substituted(self):
        resolved = self.catalog.resolve("Other-05 30 left 5")
        self.assertNotIn("[x]", resolved.text)
        self.assertNotIn("[y]", resolved.text)
        self.assertNotIn("left/right", resolved.text)
        self.assertIn("30", resolved.text)
        self.assertIn("5", resolved.text)

    def test_notice_is_classified_separately(self):
        resolved = self.catalog.resolve("Notice-01")
        self.assertEqual(50, resolved.instruction_id)
        self.assertEqual("Notice", resolved.category)

    def test_custom_text(self):
        resolved = self.catalog.resolve("text Keep to the left.")
        self.assertIsNone(resolved.instruction_id)
        self.assertEqual("Keep to the left.", resolved.text)
        quoted = self.catalog.resolve('text "Keep to the right."')
        self.assertEqual("Keep to the right.", quoted.text)

    def test_all_templates_render_without_placeholders(self):
        for spec in self.catalog.specs:
            if spec.symbol == "Other-05":
                arguments = ("30", "right", "5")
            elif spec.argument_names:
                arguments = ("20",)
            else:
                arguments = ()
            for template_index in range(len(spec.templates)):
                resolved = self.catalog.render(spec, arguments, template_index)
                self.assertNotIn("[x]", resolved.text)
                self.assertNotIn("[y]", resolved.text)
                self.assertNotIn("left/right", resolved.text)

    def test_invalid_inputs_fail_with_actionable_errors(self):
        with self.assertRaises(InstructionResolutionError):
            self.catalog.resolve("Turn-02-L-dis")
        with self.assertRaises(InstructionResolutionError):
            self.catalog.resolve("id 65")
        with self.assertRaises(InstructionResolutionError):
            self.catalog.resolve("Other-05 30 sideways 5")


if __name__ == "__main__":
    unittest.main()
