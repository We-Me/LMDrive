import importlib
import ast
import sys
import types
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TEST_DIR))
sys.modules.setdefault("carla", types.ModuleType("carla"))
standalone_client = importlib.import_module("standalone_client")


class FakeRotation:
    def __init__(self, yaw=0.0):
        self.yaw = yaw


class FakeLocation:
    def __init__(self, key=0):
        self.key = key


class FakeTransform:
    def __init__(self, key=0, yaw=0.0):
        self.location = FakeLocation(key)
        self.rotation = FakeRotation(yaw)


class FakeWaypoint:
    _next_id = 0

    def __init__(self, yaw=0.0, is_junction=False):
        self.transform = FakeTransform(yaw=yaw)
        self.is_junction = is_junction
        self.road_id = FakeWaypoint._next_id
        FakeWaypoint._next_id += 1
        self.section_id = 0
        self.lane_id = 1
        self.s = float(self.road_id)
        self.successors = []

    def next(self, step_distance):
        del step_distance
        return self.successors


def make_junction_path(steps, exit_yaws):
    start = FakeWaypoint(yaw=0.0)
    current = start
    for _ in range(steps - 1):
        successor = FakeWaypoint(yaw=0.0)
        current.successors = [successor]
        current = successor
    junction = FakeWaypoint(yaw=0.0, is_junction=True)
    current.successors = [junction]
    junction.successors = [FakeWaypoint(yaw=yaw) for yaw in exit_yaws]
    return start


class FakeSpawnPoint(FakeTransform):
    pass


class FakeMap:
    def __init__(self, roots):
        self.roots = roots
        self.spawn_points = [FakeSpawnPoint(index) for index in range(len(roots))]

    def get_spawn_points(self):
        return self.spawn_points

    def get_waypoint(self, location):
        return self.roots[location.key]


class FakeVector:
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z


class FakeVehicle:
    @staticmethod
    def get_velocity():
        return FakeVector(3.0, 4.0, 0.0)


class FakeSensorData:
    def __init__(self, frame):
        self.frame = frame


class StandaloneClientUnitTests(unittest.TestCase):
    def test_native_runtime_has_no_leaderboard_or_navigation_target_dependency(self):
        runtime_path = TEST_DIR / "native_lmdrive_runtime.py"
        client_path = TEST_DIR / "standalone_client.py"
        runtime_source = runtime_path.read_text(encoding="utf-8")
        self.assertNotIn("target_point", runtime_source)

        imported_roots = set()
        for path in (runtime_path, client_path):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_roots.update(
                        alias.name.split(".", 1)[0] for alias in node.names
                    )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_roots.add(node.module.split(".", 1)[0])
        self.assertTrue({"leaderboard", "srunner"}.isdisjoint(imported_roots))

    def test_auto_spawn_prefers_three_way_test_coverage(self):
        one_action = make_junction_path(12, [0.0])
        all_actions = make_junction_path(12, [-90.0, 0.0, 90.0])
        fake_map = FakeMap([one_action, all_actions])

        index, spawn_point, topology = standalone_client.choose_spawn_point(
            fake_map, "auto"
        )

        self.assertEqual(1, index)
        self.assertIs(fake_map.spawn_points[1], spawn_point)
        self.assertEqual(24.0, topology.distance_m)
        self.assertEqual(("left", "straight", "right"), topology.maneuvers)

    def test_explicit_spawn_only_inspects_scene_and_creates_no_route(self):
        fake_map = FakeMap([make_junction_path(5, [-90.0, 90.0])])

        index, spawn_point, topology = standalone_client.choose_spawn_point(
            fake_map, "0"
        )

        self.assertEqual(0, index)
        self.assertIs(fake_map.spawn_points[0], spawn_point)
        self.assertEqual(("left", "right"), topology.maneuvers)
        self.assertFalse(hasattr(topology, "route"))

    def test_invalid_spawn_index_is_rejected(self):
        fake_map = FakeMap([make_junction_path(5, [0.0])])
        with self.assertRaises(ValueError):
            standalone_client.choose_spawn_point(fake_map, "8")

    def test_speed_is_read_directly_from_native_vehicle_velocity(self):
        self.assertEqual(5.0, standalone_client.vehicle_speed_mps(FakeVehicle()))

    def test_sensor_hub_returns_same_native_carla_frame(self):
        hub = standalone_client.SensorHub(("camera", "lidar"))
        hub.callback("camera")(FakeSensorData(42))
        hub.callback("lidar")(FakeSensorData(42))

        result = hub.wait_for_frame(42, timeout=0.01)

        self.assertEqual(42, result["camera"].frame)
        self.assertEqual(42, result["lidar"].frame)


if __name__ == "__main__":
    unittest.main()
