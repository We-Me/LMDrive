"""Inspect a nearby CARLA junction for scenario selection, not navigation."""

from __future__ import annotations

from collections import deque
from typing import NamedTuple, Optional, Tuple

from raw_instruction_evaluator import classify_turn, normalize_yaw_delta


class JunctionTopology(NamedTuple):
    distance_m: Optional[float]
    maneuvers: Tuple[str, ...]


def _waypoint_key(waypoint):
    if hasattr(waypoint, "road_id"):
        return (
            waypoint.road_id,
            getattr(waypoint, "section_id", None),
            getattr(waypoint, "lane_id", None),
            round(float(getattr(waypoint, "s", 0.0)), 1),
        )
    return (id(waypoint),)


def _waypoint_yaw(waypoint):
    return float(waypoint.transform.rotation.yaw)


def inspect_forward_junction(
    start_waypoint,
    maximum_distance: float = 80.0,
    step_distance: float = 2.0,
) -> JunctionTopology:
    """Return available actions at the nearest forward junction.

    All reachable successors are inspected only to validate the test scene.
    No successor is selected for the ego vehicle and no path is returned.
    """

    if start_waypoint is None:
        return JunctionTopology(None, ())

    # waypoint, distance, entered junction, incoming yaw, previous yaw
    frontier = deque(
        [(start_waypoint, 0.0, False, None, _waypoint_yaw(start_waypoint))]
    )
    visited = set()
    nearest_entry_distance = None
    maneuvers = set()

    while frontier:
        waypoint, distance, entered, incoming_yaw, previous_yaw = frontier.popleft()
        if distance > maximum_distance:
            continue
        inside = bool(getattr(waypoint, "is_junction", False))

        if inside and not entered:
            if nearest_entry_distance is None:
                nearest_entry_distance = distance
            if distance > nearest_entry_distance + step_distance * 2:
                continue
            entered = True
            incoming_yaw = previous_yaw
        elif entered and not inside:
            yaw_delta = normalize_yaw_delta(_waypoint_yaw(waypoint) - incoming_yaw)
            if abs(yaw_delta) < 150.0:
                maneuvers.add(classify_turn(yaw_delta))
            continue

        state_key = (_waypoint_key(waypoint), entered)
        if state_key in visited:
            continue
        visited.add(state_key)

        try:
            successors = waypoint.next(step_distance)
        except (AttributeError, RuntimeError):
            successors = []
        current_yaw = _waypoint_yaw(waypoint)
        for successor in successors:
            frontier.append(
                (
                    successor,
                    distance + step_distance,
                    entered,
                    incoming_yaw,
                    current_yaw,
                )
            )

    action_order = ("left", "straight", "right")
    ordered = tuple(action for action in action_order if action in maneuvers)
    return JunctionTopology(nearest_entry_distance, ordered)
