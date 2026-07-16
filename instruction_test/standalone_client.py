"""Route-free CARLA runtime for interactive LMDrive instruction testing."""

from __future__ import annotations

import argparse
import math
import sys
import traceback
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import carla

from leaderboard.autoagents.agent_wrapper import AgentWrapper
from srunner.scenariomanager.carla_data_provider import CarlaDataProvider
from srunner.scenariomanager.timer import GameTime


TEST_DIR = Path(__file__).resolve().parent
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

from interactive_lmdriver_agent import InteractiveLMDriveAgent  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Spawn LMDrive in CARLA without a route and accept terminal instructions."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--traffic-manager-port", type=int, default=2500)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--town", default="Town05")
    parser.add_argument(
        "--spawn-point",
        default="auto",
        help="spawn point index, or 'auto' to choose a point before a junction",
    )
    parser.add_argument("--vehicle", default="vehicle.lincoln.mkz2017")
    parser.add_argument("--background-vehicles", type=int, default=0)
    parser.add_argument("--weather", default="ClearNoon")
    parser.add_argument("--fixed-delta-seconds", type=float, default=0.05)
    parser.add_argument(
        "--agent-config",
        default=str(TEST_DIR / "interactive_lmdriver_config.py"),
    )
    return parser


def distance_to_next_junction(
    carla_map,
    spawn_point,
    maximum_distance: float = 80.0,
    step_distance: float = 2.0,
) -> Optional[float]:
    """Follow the current lane locally and estimate the next junction distance."""

    waypoint = carla_map.get_waypoint(spawn_point.location)
    travelled = 0.0
    while waypoint is not None and travelled <= maximum_distance:
        if travelled >= 8.0 and waypoint.is_junction:
            return travelled
        next_waypoints = waypoint.next(step_distance)
        if not next_waypoints:
            break
        waypoint = next_waypoints[0]
        travelled += step_distance
    return None


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
        return index, spawn_points[index], None

    candidates: List[Tuple[float, int, float]] = []
    desired_distance = 25.0
    for index, spawn_point in enumerate(spawn_points):
        distance = distance_to_next_junction(carla_map, spawn_point)
        if distance is not None:
            candidates.append((abs(distance - desired_distance), index, distance))

    if not candidates:
        return 0, spawn_points[0], None
    _, index, distance = min(candidates)
    return index, spawn_points[index], distance


def set_spectator_chase_view(world, vehicle) -> None:
    transform = vehicle.get_transform()
    yaw = math.radians(transform.rotation.yaw)
    location = carla.Location(
        x=transform.location.x - 8.0 * math.cos(yaw),
        y=transform.location.y - 8.0 * math.sin(yaw),
        z=transform.location.z + 4.0,
    )
    rotation = carla.Rotation(
        pitch=-15.0,
        roll=0.0,
        yaw=transform.rotation.yaw,
    )
    world.get_spectator().set_transform(carla.Transform(location, rotation))


def describe_spawn(index, transform, junction_distance) -> None:
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
    if junction_distance is None:
        print("No nearby junction was detected from this spawn point.")
    else:
        print("Next junction is approximately {:.0f} m ahead.".format(junction_distance))


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


def run(args: argparse.Namespace) -> int:
    client = carla.Client(args.host, args.port)
    client.set_timeout(args.timeout)

    world = None
    traffic_manager = None
    ego_vehicle = None
    agent = None
    wrapper = None
    try:
        print("Loading CARLA map {} (no route)...".format(args.town), flush=True)
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

        CarlaDataProvider.set_client(client)
        CarlaDataProvider.set_traffic_manager_port(args.traffic_manager_port)
        CarlaDataProvider.set_world(world)

        spawn_index, spawn_transform, junction_distance = choose_spawn_point(
            world.get_map(), args.spawn_point
        )
        describe_spawn(spawn_index, spawn_transform, junction_distance)

        ego_vehicle = CarlaDataProvider.request_new_actor(
            args.vehicle,
            spawn_transform,
            rolename="hero",
            autopilot=False,
        )
        print("Ego vehicle: {} (actor {})".format(ego_vehicle.type_id, ego_vehicle.id))

        if args.background_vehicles < 0:
            raise ValueError("background vehicle count cannot be negative")
        if args.background_vehicles:
            background = CarlaDataProvider.request_new_batch_actors(
                "vehicle.*",
                args.background_vehicles,
                [],
                autopilot=True,
                random_location=True,
                rolename="background",
            )
            spawned = 0 if background is None else len(background)
            print("Background vehicles: {}".format(spawned))

        set_spectator_chase_view(world, ego_vehicle)

        print("Loading LMDrive model and pygame display...", flush=True)
        agent = InteractiveLMDriveAgent(args.agent_config)
        agent.town_id = args.town
        agent.sampled_scenarios = []
        agent.scenario_cofing_name = "interactive_0"

        wrapper = AgentWrapper(agent)
        wrapper.setup_sensors(ego_vehicle, debug_mode=False)
        GameTime.restart()

        # Populate every synchronous sensor once before the first model call.
        world.tick(args.timeout)
        print("CARLA, vehicle, sensors, pygame, and terminal input are ready.", flush=True)
        print("This runtime has no global route and does not terminate at a destination.", flush=True)

        while True:
            snapshot = world.get_snapshot()
            GameTime.on_carla_tick(snapshot.timestamp)
            CarlaDataProvider.on_carla_tick()
            control = agent()
            ego_vehicle.apply_control(control)
            set_spectator_chase_view(world, ego_vehicle)
            world.tick(args.timeout)

    except KeyboardInterrupt:
        print("\nInteractive instruction test stopped.", flush=True)
        return 0
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        if ego_vehicle is not None and ego_vehicle.is_alive:
            try:
                ego_vehicle.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0))
            except RuntimeError:
                pass
        if wrapper is not None:
            try:
                wrapper.cleanup()
            except RuntimeError:
                traceback.print_exc()
        if agent is not None:
            try:
                agent.destroy()
            except (AttributeError, RuntimeError):
                traceback.print_exc()
        try:
            CarlaDataProvider.cleanup()
        finally:
            restore_async_mode(world, traffic_manager)


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
