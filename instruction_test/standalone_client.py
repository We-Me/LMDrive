"""Native CARLA Client runtime for raw LMDrive terminal-instruction testing."""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import carla


TEST_DIR = Path(__file__).resolve().parent
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

from command_catalog import InstructionCatalog  # noqa: E402
from junction_topology import JunctionTopology, inspect_forward_junction  # noqa: E402
from raw_instruction_evaluator import (  # noqa: E402
    DrivingObservation,
    RawInstructionEvaluator,
)
from terminal_commands import InteractiveCommandState, TerminalCommandConsole  # noqa: E402


SENSOR_IDS = ("rgb_front", "rgb_left", "rgb_right", "rgb_rear", "lidar")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run LMDrive through native CARLA Client APIs without Leaderboard, "
            "a route, or a navigation target."
        )
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--traffic-manager-port", type=int, default=2500)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--sensor-timeout", type=float, default=10.0)
    parser.add_argument("--town", default="Town05")
    parser.add_argument(
        "--spawn-point",
        default="auto",
        help=(
            "spawn point index, or 'auto' to prefer a nearby intersection "
            "with left/straight/right exits"
        ),
    )
    parser.add_argument("--vehicle", default="vehicle.lincoln.mkz2017")
    parser.add_argument("--background-vehicles", type=int, default=0)
    parser.add_argument("--weather", default="ClearNoon")
    parser.add_argument("--fixed-delta-seconds", type=float, default=0.05)
    return parser


def inspect_spawn(carla_map, spawn_point) -> JunctionTopology:
    waypoint = carla_map.get_waypoint(spawn_point.location)
    return inspect_forward_junction(waypoint)


def choose_spawn_point(carla_map, selector: str):
    spawn_points = carla_map.get_spawn_points()
    if not spawn_points:
        raise RuntimeError("The selected map has no vehicle spawn points")

    if selector.strip().lower() != "auto":
        try:
            index = int(selector)
        except ValueError as exc:
            raise ValueError("spawn point must be 'auto' or an integer index") from exc
        if index < 0 or index >= len(spawn_points):
            raise ValueError(
                "spawn point {} is outside 0-{}".format(
                    index, len(spawn_points) - 1
                )
            )
        return index, spawn_points[index], inspect_spawn(carla_map, spawn_points[index])

    candidates = []
    desired_distance = 25.0
    for index, spawn_point in enumerate(spawn_points):
        topology = inspect_spawn(carla_map, spawn_point)
        if topology.distance_m is None:
            continue
        # Prefer a scene where L/S/R can all be tested.  This validates the
        # scene only; no outgoing branch is selected for the vehicle.
        score = (
            -len(topology.maneuvers),
            abs(topology.distance_m - desired_distance),
            index,
        )
        candidates.append((score, index, spawn_point, topology))

    if not candidates:
        return 0, spawn_points[0], JunctionTopology(None, ())
    _, index, spawn_point, topology = min(candidates, key=lambda item: item[0])
    return index, spawn_point, topology


def describe_spawn(index, transform, topology: JunctionTopology) -> None:
    location = transform.location
    print(
        "Spawn point {}: x={:.2f}, y={:.2f}, z={:.2f}, yaw={:.1f}".format(
            index,
            location.x,
            location.y,
            location.z,
            transform.rotation.yaw,
        )
    )
    if topology.distance_m is None:
        print("No nearby junction was detected from this spawn point.")
        return
    actions = ", ".join(topology.maneuvers) if topology.maneuvers else "unknown"
    print(
        "Test scene only: next junction {:.0f} m ahead; available actions: {}.".format(
            topology.distance_m, actions
        )
    )
    print("No action/path has been selected for LMDrive.")


class SensorHub:
    def __init__(self, sensor_ids=SENSOR_IDS):
        self._sensor_ids = tuple(sensor_ids)
        self._condition = threading.Condition()
        self._latest = {}

    def callback(self, sensor_id):
        def receive(data):
            with self._condition:
                self._latest[sensor_id] = (int(data.frame), data)
                self._condition.notify_all()

        return receive

    def wait_for_frame(self, frame, timeout):
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                ready = all(
                    sensor_id in self._latest
                    and self._latest[sensor_id][0] >= frame
                    for sensor_id in self._sensor_ids
                )
                if ready:
                    return {
                        sensor_id: self._latest[sensor_id][1]
                        for sensor_id in self._sensor_ids
                    }
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    missing = [
                        sensor_id
                        for sensor_id in self._sensor_ids
                        if sensor_id not in self._latest
                        or self._latest[sensor_id][0] < frame
                    ]
                    raise TimeoutError(
                        "Timed out waiting for CARLA frame {}; missing {}".format(
                            frame, ", ".join(missing)
                        )
                    )
                self._condition.wait(remaining)


def _set_blueprint_attributes(blueprint, attributes):
    for key, value in attributes.items():
        if blueprint.has_attribute(key):
            blueprint.set_attribute(key, str(value))


def spawn_native_sensors(world, vehicle, hub: SensorHub):
    library = world.get_blueprint_library()
    actors = []
    camera_specs = (
        ("rgb_front", 1.3, 0.0, 2.3, 0.0, 1200, 900, 100),
        ("rgb_left", 1.3, 0.0, 2.3, -60.0, 400, 300, 100),
        ("rgb_right", 1.3, 0.0, 2.3, 60.0, 400, 300, 100),
        ("rgb_rear", -1.3, 0.0, 2.3, 180.0, 400, 300, 100),
    )
    for sensor_id, x, y, z, yaw, width, height, fov in camera_specs:
        blueprint = library.find("sensor.camera.rgb")
        _set_blueprint_attributes(
            blueprint,
            {
                "image_size_x": width,
                "image_size_y": height,
                "fov": fov,
                "lens_circle_multiplier": 3.0,
                "lens_circle_falloff": 3.0,
                "chromatic_aberration_intensity": 0.5,
                "chromatic_aberration_offset": 0.0,
            },
        )
        transform = carla.Transform(
            carla.Location(x=x, y=y, z=z), carla.Rotation(yaw=yaw)
        )
        sensor = world.spawn_actor(
            blueprint,
            transform,
            attach_to=vehicle,
            attachment_type=carla.AttachmentType.Rigid,
        )
        sensor.listen(hub.callback(sensor_id))
        actors.append(sensor)

    lidar_blueprint = library.find("sensor.lidar.ray_cast")
    _set_blueprint_attributes(
        lidar_blueprint,
        {
            "range": 85,
            "rotation_frequency": 10,
            "channels": 64,
            "upper_fov": 10,
            "lower_fov": -30,
            "points_per_second": 600000,
            "atmosphere_attenuation_rate": 0.004,
            "dropoff_general_rate": 0.45,
            "dropoff_intensity_limit": 0.8,
            "dropoff_zero_intensity": 0.4,
        },
    )
    lidar_transform = carla.Transform(
        carla.Location(x=1.3, y=0.0, z=2.5), carla.Rotation(yaw=-90.0)
    )
    lidar = world.spawn_actor(
        lidar_blueprint,
        lidar_transform,
        attach_to=vehicle,
        attachment_type=carla.AttachmentType.Rigid,
    )
    lidar.listen(hub.callback("lidar"))
    actors.append(lidar)
    return actors


def spawn_ego_vehicle(world, blueprint_filter, transform):
    matches = world.get_blueprint_library().filter(blueprint_filter)
    if not matches:
        raise RuntimeError("No vehicle blueprint matches {}".format(blueprint_filter))
    blueprint = matches[0]
    if blueprint.has_attribute("role_name"):
        blueprint.set_attribute("role_name", "hero")
    vehicle = world.try_spawn_actor(blueprint, transform)
    if vehicle is None:
        raise RuntimeError("Unable to spawn ego vehicle at the selected point")
    return vehicle


def spawn_background_vehicles(world, count, traffic_manager_port, excluded_transform):
    if count < 0:
        raise ValueError("background vehicle count cannot be negative")
    if count == 0:
        return []
    blueprints = list(world.get_blueprint_library().filter("vehicle.*"))
    spawn_points = list(world.get_map().get_spawn_points())
    random.shuffle(spawn_points)
    actors = []
    for transform in spawn_points:
        if len(actors) >= count:
            break
        if transform.location.distance(excluded_transform.location) < 5.0:
            continue
        blueprint = random.choice(blueprints)
        if blueprint.has_attribute("role_name"):
            blueprint.set_attribute("role_name", "background")
        actor = world.try_spawn_actor(blueprint, transform)
        if actor is None:
            continue
        actor.set_autopilot(True, traffic_manager_port)
        actors.append(actor)
    return actors


def vehicle_speed_mps(vehicle):
    velocity = vehicle.get_velocity()
    return math.sqrt(velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2)


def driving_observation(vehicle):
    transform = vehicle.get_transform()
    waypoint = vehicle.get_world().get_map().get_waypoint(transform.location)
    return DrivingObservation(
        float(transform.rotation.yaw),
        bool(getattr(waypoint, "is_junction", False)),
    )


def set_spectator_chase_view(world, vehicle) -> None:
    transform = vehicle.get_transform()
    yaw = math.radians(transform.rotation.yaw)
    location = carla.Location(
        x=transform.location.x - 8.0 * math.cos(yaw),
        y=transform.location.y - 8.0 * math.sin(yaw),
        z=transform.location.z + 4.0,
    )
    rotation = carla.Rotation(pitch=-15.0, yaw=transform.rotation.yaw)
    world.get_spectator().set_transform(carla.Transform(location, rotation))


def restore_async_mode(world, traffic_manager) -> None:
    if traffic_manager is not None:
        try:
            traffic_manager.set_synchronous_mode(False)
        except RuntimeError:
            pass
    if world is not None:
        try:
            settings = world.get_settings()
            settings.synchronous_mode = False
            settings.fixed_delta_seconds = None
            world.apply_settings(settings)
        except RuntimeError:
            pass


def _destroy_actors(actors):
    for actor in actors:
        try:
            if actor.is_alive:
                if hasattr(actor, "stop"):
                    actor.stop()
                actor.destroy()
        except RuntimeError:
            pass


def run(args: argparse.Namespace) -> int:
    from native_lmdrive_runtime import NativeLMDriveRuntime

    client = carla.Client(args.host, args.port)
    client.set_timeout(args.timeout)
    world = None
    traffic_manager = None
    ego_vehicle = None
    sensors = []
    background_vehicles = []
    runtime = None
    quit_event = threading.Event()

    try:
        print("Loading CARLA map {} (native client, no route)...".format(args.town))
        world = client.load_world(args.town)
        settings = world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = args.fixed_delta_seconds
        world.apply_settings(settings)

        traffic_manager = client.get_trafficmanager(args.traffic_manager_port)
        traffic_manager.set_synchronous_mode(True)
        weather = getattr(carla.WeatherParameters, args.weather, None)
        if weather is None:
            raise ValueError("Unknown CARLA weather preset: {}".format(args.weather))
        world.set_weather(weather)

        index, spawn_transform, topology = choose_spawn_point(
            world.get_map(), args.spawn_point
        )
        describe_spawn(index, spawn_transform, topology)
        ego_vehicle = spawn_ego_vehicle(world, args.vehicle, spawn_transform)
        print("Ego vehicle: {} (actor {})".format(ego_vehicle.type_id, ego_vehicle.id))
        background_vehicles = spawn_background_vehicles(
            world,
            args.background_vehicles,
            args.traffic_manager_port,
            spawn_transform,
        )
        print("Background vehicles: {}".format(len(background_vehicles)))

        hub = SensorHub()
        sensors = spawn_native_sensors(world, ego_vehicle, hub)
        evaluator = RawInstructionEvaluator()
        catalog = InstructionCatalog(TEST_DIR / "instruction_dict.json")
        command_state = InteractiveCommandState(
            catalog,
            os.environ.get("LMDRIVE_INITIAL_COMMAND", "Other-03"),
            int(os.environ.get("LMDRIVE_TEMPLATE_INDEX", "0")),
            os.environ.get("LMDRIVE_USE_NOTICE", "0").lower()
            in ("1", "true", "yes", "on"),
        )
        runtime = NativeLMDriveRuntime(
            request_quit=quit_event.set,
            evaluation_status_getter=evaluator.format_status,
            save_frames=os.environ.get("LMDRIVE_SAVE_FRAMES", "0").lower()
            in ("1", "true", "yes", "on"),
            frame_output_dir=TEST_DIR / "output" / "frames",
        )
        console = TerminalCommandConsole(
            command_state,
            request_quit=quit_event.set,
            evaluation_status_getter=evaluator.format_status,
        )

        set_spectator_chase_view(world, ego_vehicle)
        console.start()
        print(
            "CARLA, native sensors, LMDrive, pygame, and terminal input are ready.",
            flush=True,
        )
        print(
            "Control is raw LMDrive output; the evaluator never changes steering.",
            flush=True,
        )

        while not quit_event.is_set():
            frame = world.tick(args.timeout)
            sensor_data = hub.wait_for_frame(frame, args.sensor_timeout)
            snapshot = command_state.snapshot()
            evaluator.update(
                snapshot.navigation,
                snapshot.navigation_revision,
                driving_observation(ego_vehicle),
            )
            world_snapshot = world.get_snapshot()
            control = runtime.run_step(
                sensor_data,
                vehicle_speed_mps(ego_vehicle),
                snapshot,
                world_snapshot.timestamp.elapsed_seconds,
            )
            ego_vehicle.apply_control(control)
            set_spectator_chase_view(world, ego_vehicle)
        return 0

    except KeyboardInterrupt:
        print("\nNative LMDrive instruction test stopped.", flush=True)
        return 0
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        if ego_vehicle is not None and ego_vehicle.is_alive:
            try:
                ego_vehicle.apply_control(
                    carla.VehicleControl(throttle=0.0, brake=1.0)
                )
            except RuntimeError:
                pass
        if runtime is not None:
            runtime.destroy()
        _destroy_actors(sensors)
        _destroy_actors(background_vehicles)
        _destroy_actors([] if ego_vehicle is None else [ego_vehicle])
        restore_async_mode(world, traffic_manager)


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
