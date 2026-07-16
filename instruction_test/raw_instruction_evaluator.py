"""Read-only outcome evaluation for route-free LMDrive instruction tests.

Nothing in this module changes throttle, brake, steering, model waypoints, or
the CARLA world.  It only observes whether the ego vehicle entered a junction
and how its yaw changed after leaving it.
"""

from __future__ import annotations

import threading
from typing import NamedTuple, Optional, Tuple


class DrivingObservation(NamedTuple):
    yaw_deg: float
    inside_junction: bool


class EvaluationStatus(NamedTuple):
    phase: str
    expected: str
    observed: str
    yaw_delta_deg: Optional[float]
    completed_steps: int
    total_steps: int


def normalize_yaw_delta(delta_deg: float) -> float:
    return (delta_deg + 180.0) % 360.0 - 180.0


def classify_turn(yaw_delta_deg: float, threshold_deg: float = 30.0) -> str:
    """Classify a CARLA yaw change (positive yaw is a right turn)."""

    delta = normalize_yaw_delta(yaw_delta_deg)
    if delta <= -threshold_deg:
        return "left"
    if delta >= threshold_deg:
        return "right"
    return "straight"


def expected_turns(instruction) -> Tuple[str, ...]:
    """Return locally measurable turn actions for an official instruction."""

    symbol = instruction.symbol
    if symbol.endswith("-dis"):
        # A distance-qualified command needs a separate distance protocol;
        # classifying the first junction would produce a misleading result.
        return ()
    parts = symbol.split("-")
    directions = {"L": "left", "R": "right", "S": "straight"}
    if symbol.startswith("Turn-06-") and len(parts) >= 4:
        return tuple(directions[item] for item in parts[2:4])
    if symbol.startswith(("Turn-01-", "Turn-02-", "Turn-03-", "Turn-04-")):
        direction = directions.get(parts[2]) if len(parts) >= 3 else None
        return () if direction is None else (direction,)
    return ()


class RawInstructionEvaluator:
    """Evaluate raw model behaviour without altering the returned control."""

    def __init__(self, turn_threshold_deg: float = 30.0) -> None:
        self.turn_threshold_deg = turn_threshold_deg
        self._lock = threading.Lock()
        self._revision = -1
        self._expected: Tuple[str, ...] = ()
        self._step_index = 0
        self._phase = "idle"
        self._previous_yaw: Optional[float] = None
        self._entry_yaw: Optional[float] = None
        self._observed = "none"
        self._yaw_delta: Optional[float] = None

    def update(
        self,
        instruction,
        revision: int,
        observation: Optional[DrivingObservation],
    ) -> EvaluationStatus:
        with self._lock:
            if revision != self._revision:
                self._reset(instruction, revision, observation)

            if not self._expected:
                self._phase = "not-evaluated"
                return self._status()
            if observation is None:
                self._phase = "no-vehicle-data"
                return self._status()
            if self._phase in ("passed", "failed", "invalid-entered-late"):
                return self._status()

            if self._phase in ("waiting-junction", "waiting-next-junction"):
                if observation.inside_junction:
                    if self._previous_yaw is None:
                        self._phase = "invalid-entered-late"
                        return self._status()
                    self._entry_yaw = self._previous_yaw
                    self._phase = "in-junction"
                self._previous_yaw = observation.yaw_deg
                return self._status()

            if self._phase == "in-junction":
                if observation.inside_junction:
                    self._previous_yaw = observation.yaw_deg
                    return self._status()
                if self._entry_yaw is None:
                    self._phase = "invalid-entered-late"
                    return self._status()

                self._yaw_delta = normalize_yaw_delta(
                    observation.yaw_deg - self._entry_yaw
                )
                self._observed = classify_turn(
                    self._yaw_delta, self.turn_threshold_deg
                )
                expected = self._expected[self._step_index]
                if self._observed != expected:
                    self._phase = "failed"
                    return self._status()

                self._step_index += 1
                if self._step_index >= len(self._expected):
                    self._phase = "passed"
                    return self._status()

                self._phase = "waiting-next-junction"
                self._entry_yaw = None
                self._previous_yaw = observation.yaw_deg
                self._observed = "none"
                self._yaw_delta = None
            return self._status()

    def status(self) -> EvaluationStatus:
        with self._lock:
            return self._status()

    def format_status(self) -> str:
        status = self.status()
        if status.phase == "not-evaluated":
            return "RAW model | command not auto-scored"
        expected = "none"
        if status.expected != "none":
            expected = status.expected
        if status.phase == "failed":
            return "RAW fail | expected {}, observed {} (yaw {:+.0f} deg)".format(
                expected,
                status.observed,
                status.yaw_delta_deg or 0.0,
            )
        if status.phase == "passed":
            return "RAW pass | observed {} (yaw {:+.0f} deg)".format(
                status.observed,
                status.yaw_delta_deg or 0.0,
            )
        return "RAW model | {}:{}".format(status.phase, expected)

    def _reset(self, instruction, revision, observation) -> None:
        self._revision = revision
        self._expected = expected_turns(instruction)
        self._step_index = 0
        self._phase = "waiting-junction"
        self._previous_yaw = None
        self._entry_yaw = None
        self._observed = "none"
        self._yaw_delta = None
        if observation is not None:
            if observation.inside_junction and self._expected:
                self._phase = "invalid-entered-late"
            else:
                self._previous_yaw = observation.yaw_deg

    def _status(self) -> EvaluationStatus:
        expected = "none"
        if self._expected and self._step_index < len(self._expected):
            expected = self._expected[self._step_index]
        return EvaluationStatus(
            self._phase,
            expected,
            self._observed,
            self._yaw_delta,
            self._step_index,
            len(self._expected),
        )
