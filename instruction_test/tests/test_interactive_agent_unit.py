import importlib
import sys
import types
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TEST_DIR.parent
sys.path.insert(0, str(TEST_DIR))

# The interaction layer can be tested without CARLA/GPU by supplying only the
# base-class surface needed while the module is imported.
dummy_base_module = types.ModuleType("lmdriver_agent")
dummy_base_module.SAVE_PATH = None
dummy_base_module.LMDriveAgent = type("LMDriveAgent", (), {})
sys.modules.setdefault("lmdriver_agent", dummy_base_module)

interactive_agent = importlib.import_module("interactive_lmdriver_agent")


class DummyPlanner:
    marker = "automatic-planner"


class DummyDisplay:
    def __init__(self):
        self.last_data = None
        self.quit_called = False

    def run_interface(self, display_data):
        self.last_data = display_data
        return "surface"

    def _quit(self):
        self.quit_called = True


class InteractiveAgentUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = interactive_agent.InstructionCatalog(
            REPO_ROOT
            / "leaderboard"
            / "leaderboard"
            / "envs"
            / "instruction_dict.json"
        )

    def make_state(self):
        return interactive_agent.InteractiveCommandState(
            self.catalog, "Other-03", 0, False
        )

    def test_navigation_update_reaches_planner_proxy(self):
        state = self.make_state()
        resolved = self.catalog.resolve("Turn-02-L")
        state.set_navigation(resolved)
        proxy = interactive_agent.InteractivePlannerProxy(DummyPlanner(), state)

        self.assertEqual(
            resolved.text, proxy.command2instruct("Town05", {}, routes=[])
        )
        self.assertEqual("", proxy.command2mislead("Town05", {}))
        self.assertEqual("automatic-planner", proxy.marker)

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
        proxy = interactive_agent.InteractivePlannerProxy(DummyPlanner(), state)

        self.assertEqual(notice.text, proxy.pos2notice([], {}))
        self.assertEqual("Other-03", state.snapshot().navigation.symbol)
        state.set_notice(None)
        self.assertEqual("", proxy.pos2notice([], {}))

    def test_display_decorates_symbol_without_changing_model_prompt(self):
        state = self.make_state()
        instruction = self.catalog.resolve("Turn-02-L")
        state.set_navigation(instruction)
        delegate = DummyDisplay()
        display = interactive_agent.InteractiveDisplay(delegate, state)

        result = display.run_interface({"instruction": instruction.text})

        self.assertEqual("surface", result)
        self.assertIn("Turn-02-L", delegate.last_data["instruction"])
        self.assertIn(instruction.text, delegate.last_data["instruction"])
        display._quit()
        self.assertTrue(delegate.quit_called)

    def test_terminal_line_turn_02_l_updates_navigation(self):
        state = self.make_state()
        agent = interactive_agent.InteractiveLMDriveAgent()
        agent._interactive_state = state

        should_exit = agent._handle_terminal_line("Turn-02-L")

        self.assertFalse(should_exit)
        current = state.snapshot().navigation
        self.assertEqual(4, current.instruction_id)
        self.assertEqual("Turn-02-L", current.symbol)
        self.assertIn("left", current.text.lower())

    def test_agent_initializes_without_a_global_route(self):
        state = self.make_state()
        agent = interactive_agent.InteractiveLMDriveAgent()
        agent._interactive_state = state

        agent._init()
        next_point, command = agent._route_planner.run_step([12.0, -7.0])

        self.assertTrue(agent.initialized)
        self.assertEqual([], agent._route_planner.route)
        self.assertEqual([12.0, -7.0], next_point.tolist())
        self.assertEqual(4, command.value)
        self.assertEqual(
            state.snapshot().navigation.text,
            agent._instruction_planner.command2instruct("Town05", {}),
        )


if __name__ == "__main__":
    unittest.main()
