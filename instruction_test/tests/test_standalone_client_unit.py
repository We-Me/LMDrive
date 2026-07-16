import importlib
import sys
import types
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TEST_DIR))


def install_import_stubs():
    sys.modules.setdefault("carla", types.ModuleType("carla"))

    leaderboard = sys.modules.setdefault("leaderboard", types.ModuleType("leaderboard"))
    autoagents = sys.modules.setdefault(
        "leaderboard.autoagents", types.ModuleType("leaderboard.autoagents")
    )
    agent_wrapper = types.ModuleType("leaderboard.autoagents.agent_wrapper")
    agent_wrapper.AgentWrapper = type("AgentWrapper", (), {})
    sys.modules.setdefault("leaderboard.autoagents.agent_wrapper", agent_wrapper)
    leaderboard.autoagents = autoagents

    sys.modules.setdefault("srunner", types.ModuleType("srunner"))
    sys.modules.setdefault(
        "srunner.scenariomanager", types.ModuleType("srunner.scenariomanager")
    )
    provider = types.ModuleType("srunner.scenariomanager.carla_data_provider")
    provider.CarlaDataProvider = type("CarlaDataProvider", (), {})
    sys.modules.setdefault("srunner.scenariomanager.carla_data_provider", provider)
    timer = types.ModuleType("srunner.scenariomanager.timer")
    timer.GameTime = type("GameTime", (), {})
    sys.modules.setdefault("srunner.scenariomanager.timer", timer)

    if "interactive_lmdriver_agent" not in sys.modules:
        interactive = types.ModuleType("interactive_lmdriver_agent")
        interactive.InteractiveLMDriveAgent = type("InteractiveLMDriveAgent", (), {})
        sys.modules["interactive_lmdriver_agent"] = interactive


install_import_stubs()
standalone_client = importlib.import_module("standalone_client")


class FakeLocation:
    def __init__(self, key):
        self.key = key


class FakeSpawnPoint:
    def __init__(self, key):
        self.location = FakeLocation(key)


class FakeWaypoint:
    def __init__(self, remaining_steps):
        self.remaining_steps = remaining_steps
        self.is_junction = remaining_steps == 0

    def next(self, step_distance):
        del step_distance
        if self.remaining_steps <= 0:
            return [self]
        return [FakeWaypoint(self.remaining_steps - 1)]


class FakeMap:
    def __init__(self, junction_steps):
        self.spawn_points = [FakeSpawnPoint(index) for index in range(len(junction_steps))]
        self.junction_steps = junction_steps

    def get_spawn_points(self):
        return self.spawn_points

    def get_waypoint(self, location):
        steps = self.junction_steps[location.key]
        if steps is None:
            return DeadEndWaypoint()
        return FakeWaypoint(steps)


class DeadEndWaypoint:
    is_junction = False

    @staticmethod
    def next(step_distance):
        del step_distance
        return []


class StandaloneClientUnitTests(unittest.TestCase):
    def test_auto_spawn_prefers_about_25_metres_before_junction(self):
        fake_map = FakeMap([5, 12, None])  # roughly 10 m, 24 m, no junction

        index, spawn_point, distance = standalone_client.choose_spawn_point(
            fake_map, "auto"
        )

        self.assertEqual(1, index)
        self.assertIs(fake_map.spawn_points[1], spawn_point)
        self.assertEqual(24.0, distance)

    def test_explicit_spawn_index_does_not_create_a_route(self):
        fake_map = FakeMap([5, 12, None])

        index, spawn_point, distance = standalone_client.choose_spawn_point(
            fake_map, "2"
        )

        self.assertEqual(2, index)
        self.assertIs(fake_map.spawn_points[2], spawn_point)
        self.assertIsNone(distance)

    def test_invalid_spawn_index_is_rejected(self):
        fake_map = FakeMap([5])
        with self.assertRaises(ValueError):
            standalone_client.choose_spawn_point(fake_map, "8")


if __name__ == "__main__":
    unittest.main()
