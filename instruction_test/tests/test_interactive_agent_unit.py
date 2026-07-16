import sys
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TEST_DIR))

from command_catalog import InstructionCatalog  # noqa: E402
from raw_instruction_evaluator import (  # noqa: E402
    DrivingObservation,
    RawInstructionEvaluator,
    classify_turn,
    expected_turns,
)
from terminal_commands import (  # noqa: E402
    InteractiveCommandState,
    TerminalCommandConsole,
)


class InteractiveLayerUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = InstructionCatalog(TEST_DIR / "instruction_dict.json")

    def make_state(self):
        return InteractiveCommandState(self.catalog, "Other-03", 0, False)

    def make_console(self, state=None):
        quit_calls = []
        console = TerminalCommandConsole(
            state or self.make_state(),
            request_quit=lambda: quit_calls.append(True),
            evaluation_status_getter=lambda: "RAW model",
        )
        return console, quit_calls

    def test_repeated_command_increments_revision(self):
        state = self.make_state()
        resolved = self.catalog.resolve("Turn-02-L")
        initial_revision = state.snapshot().navigation_revision
        state.set_navigation(resolved)
        first_revision = state.snapshot().navigation_revision
        state.set_navigation(resolved)
        second_revision = state.snapshot().navigation_revision

        self.assertEqual(initial_revision + 1, first_revision)
        self.assertEqual(first_revision + 1, second_revision)

    def test_template_change_rerenders_current_prompt(self):
        state = self.make_state()
        state.set_navigation(self.catalog.resolve("Turn-02-L", 0))
        old = state.snapshot()
        new = state.set_template_index(1)

        self.assertEqual(1, new.template_index)
        self.assertEqual("Turn-02-L", new.navigation.symbol)
        self.assertNotEqual(old.navigation.text, new.navigation.text)
        self.assertGreater(new.navigation_revision, old.navigation_revision)

    def test_notice_is_separate_from_navigation(self):
        state = self.make_state()
        notice = self.catalog.resolve("Notice-01")
        state.set_notice(notice)

        self.assertEqual("Other-03", state.snapshot().navigation.symbol)
        self.assertEqual(notice, state.snapshot().notice)
        state.set_notice(None)
        self.assertIsNone(state.snapshot().notice)

    def test_terminal_turn_updates_model_prompt(self):
        state = self.make_state()
        console, _ = self.make_console(state)

        should_exit = console.handle_line("Turn-02-L")

        self.assertFalse(should_exit)
        current = state.snapshot().navigation
        self.assertEqual(4, current.instruction_id)
        self.assertEqual("Turn-02-L", current.symbol)
        self.assertIn("left", current.text.lower())

    def test_terminal_quit_requests_native_loop_shutdown(self):
        console, quit_calls = self.make_console()

        self.assertTrue(console.handle_line("quit"))
        self.assertEqual([True], quit_calls)

    def test_turn_classifier_uses_carla_yaw_convention(self):
        self.assertEqual("left", classify_turn(-75.0))
        self.assertEqual("straight", classify_turn(10.0))
        self.assertEqual("right", classify_turn(80.0))

    def test_raw_evaluator_passes_matching_left_turn(self):
        instruction = self.catalog.resolve("Turn-02-L")
        evaluator = RawInstructionEvaluator()

        evaluator.update(instruction, 1, DrivingObservation(0.0, False))
        evaluator.update(instruction, 1, DrivingObservation(-10.0, True))
        status = evaluator.update(
            instruction, 1, DrivingObservation(-82.0, False)
        )

        self.assertEqual("passed", status.phase)
        self.assertEqual("left", status.observed)
        self.assertAlmostEqual(-82.0, status.yaw_delta_deg)

    def test_raw_evaluator_reports_model_failure_without_changing_control(self):
        instruction = self.catalog.resolve("Turn-02-L")
        evaluator = RawInstructionEvaluator()

        evaluator.update(instruction, 2, DrivingObservation(0.0, False))
        evaluator.update(instruction, 2, DrivingObservation(5.0, True))
        status = evaluator.update(
            instruction, 2, DrivingObservation(88.0, False)
        )

        self.assertEqual("failed", status.phase)
        self.assertEqual("left", status.expected)
        self.assertEqual("right", status.observed)

    def test_command_entered_inside_junction_is_not_scored(self):
        instruction = self.catalog.resolve("Turn-02-R")
        evaluator = RawInstructionEvaluator()

        status = evaluator.update(
            instruction, 3, DrivingObservation(20.0, True)
        )

        self.assertEqual("invalid-entered-late", status.phase)

    def test_distance_command_is_not_mis_scored_at_first_junction(self):
        instruction = self.catalog.resolve("Turn-02-L-dis 20")
        self.assertEqual((), expected_turns(instruction))

    def test_two_turn_instruction_is_scored_across_two_junctions(self):
        instruction = self.catalog.resolve("Turn-06-L-R")
        evaluator = RawInstructionEvaluator()

        evaluator.update(instruction, 4, DrivingObservation(0.0, False))
        evaluator.update(instruction, 4, DrivingObservation(-5.0, True))
        first = evaluator.update(
            instruction, 4, DrivingObservation(-80.0, False)
        )
        self.assertEqual("waiting-next-junction", first.phase)
        self.assertEqual("right", first.expected)

        evaluator.update(instruction, 4, DrivingObservation(-75.0, True))
        final = evaluator.update(
            instruction, 4, DrivingObservation(5.0, False)
        )
        self.assertEqual("passed", final.phase)
        self.assertEqual(2, final.completed_steps)


if __name__ == "__main__":
    unittest.main()
