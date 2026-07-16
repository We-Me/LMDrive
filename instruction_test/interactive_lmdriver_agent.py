"""Interactive terminal-controlled LMDrive Leaderboard agent.

The original LMDrive implementation remains untouched. This subclass swaps the
automatic instruction planner for a thread-safe terminal instruction source,
while reusing the original sensor suite, model inference, PID control, and
pygame display.
"""

from __future__ import annotations

import os
import signal
import sys
import threading
from pathlib import Path
from typing import NamedTuple, Optional

import numpy as np


TEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEST_DIR.parent
TEAM_CODE_DIR = REPO_ROOT / "leaderboard" / "team_code"
for import_path in (str(TEST_DIR), str(TEAM_CODE_DIR)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

import lmdriver_agent as base_agent_module  # noqa: E402
from command_catalog import (  # noqa: E402
    InstructionCatalog,
    InstructionResolutionError,
    ResolvedInstruction,
)


def _env_enabled(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class StateSnapshot(NamedTuple):
    navigation: ResolvedInstruction
    notice: Optional[ResolvedInstruction]
    template_index: int
    navigation_revision: int
    notice_revision: int


class InteractiveCommandState:
    def __init__(
        self,
        catalog: InstructionCatalog,
        initial_command: str,
        template_index: int,
        notice_enabled: bool,
    ) -> None:
        self.catalog = catalog
        self.notice_enabled = notice_enabled
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        if template_index < 0 or template_index > 7:
            raise InstructionResolutionError("template index must be from 0 to 7")
        self._template_index = template_index
        self._navigation = catalog.resolve(initial_command, template_index)
        if self._navigation.category == "Notice":
            raise InstructionResolutionError(
                "LMDRIVE_INITIAL_COMMAND must be a navigation/Other command"
            )
        self._notice: Optional[ResolvedInstruction] = None
        self._navigation_revision = 0
        self._notice_revision = 0

    def snapshot(self) -> StateSnapshot:
        with self._lock:
            return StateSnapshot(
                navigation=self._navigation,
                notice=self._notice,
                template_index=self._template_index,
                navigation_revision=self._navigation_revision,
                notice_revision=self._notice_revision,
            )

    def set_navigation(self, instruction: ResolvedInstruction) -> None:
        if instruction.category == "Notice":
            raise InstructionResolutionError(
                "Notice commands must be set with 'notice <command>'"
            )
        with self._lock:
            self._navigation = instruction
            self._navigation_revision += 1

    def set_notice(self, instruction: Optional[ResolvedInstruction]) -> None:
        with self._lock:
            self._notice = instruction
            self._notice_revision += 1

    def set_template_index(self, template_index: int) -> StateSnapshot:
        if template_index < 0 or template_index > 7:
            raise InstructionResolutionError("template index must be from 0 to 7")
        with self._lock:
            if template_index == self._template_index:
                return self.snapshot_unlocked()
            self._template_index = template_index
            rerendered_navigation = self.catalog.rerender(
                self._navigation, template_index
            )
            if rerendered_navigation != self._navigation:
                self._navigation = rerendered_navigation
                self._navigation_revision += 1
            if self._notice is not None:
                rerendered_notice = self.catalog.rerender(
                    self._notice, template_index
                )
                if rerendered_notice != self._notice:
                    self._notice = rerendered_notice
                    self._notice_revision += 1
            return self.snapshot_unlocked()

    def snapshot_unlocked(self) -> StateSnapshot:
        return StateSnapshot(
            navigation=self._navigation,
            notice=self._notice,
            template_index=self._template_index,
            navigation_revision=self._navigation_revision,
            notice_revision=self._notice_revision,
        )

    def stop(self) -> None:
        self._stopped.set()

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()


class InteractivePlannerProxy:
    """Expose manual prompts through the interface used by LMDrive.run_step."""

    def __init__(self, automatic_planner, state: InteractiveCommandState) -> None:
        self._automatic_planner = automatic_planner
        self._state = state

    def command2instruct(self, town_id, tick_data, routes=None, dis_on=True):
        del town_id, tick_data, routes, dis_on
        return self._state.snapshot().navigation.text

    def pos2notice(self, sampled_scenarios, tick_data):
        del sampled_scenarios, tick_data
        notice = self._state.snapshot().notice
        return "" if notice is None else notice.text

    def traffic_notice(self, tick_data):
        del tick_data
        return ""

    def command2mislead(self, town_id, tick_data):
        del town_id, tick_data
        return ""

    def __getattr__(self, name):
        if self._automatic_planner is None:
            raise AttributeError(name)
        return getattr(self._automatic_planner, name)


class NeutralTargetPlanner:
    """Minimal planner interface used by the original agent's sensor pipeline.

    LMDrive's configured ``return_feature`` visual encoder does not consume
    ``target_point``, and its language waypoint decoder currently uses ``x``
    rather than ``x + target_point``. The base agent still requires the field
    structurally, so this planner supplies a constant zero target without
    defining or following a route.
    """

    def __init__(self) -> None:
        self.mean = np.zeros(2, dtype=np.float64)
        self.scale = np.ones(2, dtype=np.float64)
        self.route = []

    def run_step(self, position):
        # The base transformation computes target_point = next_wp - position.
        # Returning the current position therefore creates neutral [0, 0].
        command = type("LaneFollowCommand", (), {"value": 4})()
        return np.asarray(position, dtype=np.float64), command


class InteractiveDisplay:
    """Add the symbolic command to the existing LMDrive pygame overlay."""

    def __init__(self, delegate, state: InteractiveCommandState) -> None:
        self._delegate = delegate
        self._state = state

    def run_interface(self, display_data):
        snapshot = self._state.snapshot()
        decorated = dict(display_data)
        decorated["instruction"] = "Command: {} | Prompt: {}".format(
            snapshot.navigation.symbol, snapshot.navigation.text
        )
        if snapshot.notice is not None:
            decorated["notice"] = "Notice command: {} | {}".format(
                snapshot.notice.symbol, snapshot.notice.text
            )
        return self._delegate.run_interface(decorated)

    def _quit(self):
        return self._delegate._quit()

    def __getattr__(self, name):
        return getattr(self._delegate, name)


def get_entry_point():
    return "InteractiveLMDriveAgent"


class InteractiveLMDriveAgent(base_agent_module.LMDriveAgent):
    def setup(self, path_to_conf_file):
        # Frame dumps are large and are not needed for interactive testing.
        # The launcher can opt back in with LMDRIVE_SAVE_FRAMES=1.
        if not _env_enabled("LMDRIVE_SAVE_FRAMES", False):
            base_agent_module.SAVE_PATH = None
        else:
            # The base saver uses ROUTES only to construct an output folder
            # name. This is a label, not an actual route in this runtime.
            os.environ.setdefault("ROUTES", "interactive_no_route.xml")

        super().setup(path_to_conf_file)

        instruction_dict_path = (
            REPO_ROOT
            / "leaderboard"
            / "leaderboard"
            / "envs"
            / "instruction_dict.json"
        )
        catalog = InstructionCatalog(instruction_dict_path)
        try:
            template_index = int(os.environ.get("LMDRIVE_TEMPLATE_INDEX", "0"))
        except ValueError as exc:
            raise InstructionResolutionError(
                "LMDRIVE_TEMPLATE_INDEX must be an integer from 0 to 7"
            ) from exc

        initial_command = os.environ.get("LMDRIVE_INITIAL_COMMAND", "Other-03")
        self._interactive_state = InteractiveCommandState(
            catalog=catalog,
            initial_command=initial_command,
            template_index=template_index,
            notice_enabled=self.agent_use_notice,
        )
        self._applied_navigation_revision = -1
        self._applied_notice_revision = -1
        self._hic = InteractiveDisplay(self._hic, self._interactive_state)
        self._terminal_thread = threading.Thread(
            target=self._terminal_loop,
            name="lmdrive-terminal",
            daemon=True,
        )
        self._terminal_thread.start()

    def _init(self):
        self._route_planner = NeutralTargetPlanner()
        self._instruction_planner = InteractivePlannerProxy(
            None, self._interactive_state
        )
        self.initialized = True

    def run_step(self, input_data, timestamp):
        snapshot = self._interactive_state.snapshot()
        if snapshot.navigation_revision != self._applied_navigation_revision:
            # Force the base agent to treat even a repeated symbol as a fresh
            # instruction clip and discard visual history from the old prompt.
            self.curr_instruction = ""
            self.visual_feature_buffer = []
            self.curr_notice = ""
            self.curr_notice_frame_id = -1
            self._applied_navigation_revision = snapshot.navigation_revision
        if snapshot.notice_revision != self._applied_notice_revision:
            self.curr_notice = ""
            self.curr_notice_frame_id = -1
            self._applied_notice_revision = snapshot.notice_revision
        return super().run_step(input_data, timestamp)

    def destroy(self):
        if hasattr(self, "_interactive_state"):
            self._interactive_state.stop()
        try:
            if hasattr(self, "_hic"):
                self._hic._quit()
        finally:
            super().destroy()

    def _terminal_loop(self):
        snapshot = self._interactive_state.snapshot()
        print("\n[Interactive LMDrive] terminal instruction input is ready.")
        print("Type 'help' for syntax. The initial command is a full stop.")
        self._print_navigation(snapshot.navigation)
        while not self._interactive_state.stopped:
            try:
                line = input("lmdrive> ").strip()
            except EOFError:
                print("\n[Interactive LMDrive] stdin closed; keeping current command.")
                return
            except KeyboardInterrupt:
                self._request_quit()
                return
            if not line:
                continue
            try:
                if self._handle_terminal_line(line):
                    return
            except InstructionResolutionError as exc:
                print("[command error] {}".format(exc), flush=True)
            except Exception as exc:  # keep a malformed console command non-fatal
                print("[command error] {}: {}".format(type(exc).__name__, exc), flush=True)

    def _handle_terminal_line(self, line: str) -> bool:
        head, _, remainder = line.partition(" ")
        command = head.lower()
        state = self._interactive_state
        snapshot = state.snapshot()

        if command in ("quit", "exit"):
            print("Stopping the interactive client and CARLA launcher...", flush=True)
            self._request_quit()
            return True
        if command in ("help", "?"):
            self._print_help()
            return False
        if command == "status":
            self._print_status(snapshot)
            return False
        if command == "list":
            category = remainder.strip() or None
            print(state.catalog.format_catalog(category), flush=True)
            return False
        if command == "template":
            if not remainder.strip():
                print("Current template index: {}".format(snapshot.template_index))
                return False
            try:
                template_index = int(remainder.strip())
            except ValueError as exc:
                raise InstructionResolutionError("usage: template <0-7>") from exc
            updated = state.set_template_index(template_index)
            print("Template index set to {}.".format(updated.template_index), flush=True)
            self._print_navigation(updated.navigation)
            return False
        if command in ("clear-notice", "clear_notice"):
            state.set_notice(None)
            print("Notice cleared.", flush=True)
            return False
        if command == "notice":
            notice_line = remainder.strip()
            if not notice_line:
                raise InstructionResolutionError(
                    "usage: notice <Notice-XX | text ... | clear>"
                )
            if notice_line.lower() == "clear":
                state.set_notice(None)
                print("Notice cleared.", flush=True)
                return False
            notice = state.catalog.resolve(notice_line, snapshot.template_index)
            if notice.category not in ("Notice", "Text"):
                raise InstructionResolutionError(
                    "'notice' expects a Notice-* symbol or 'notice text ...'"
                )
            state.set_notice(notice)
            self._print_notice(notice)
            return False

        aliases = {
            "start": "Other-01",
            "stop": "Other-03",
            "free": "Other-04",
        }
        instruction_line = aliases.get(command, line)
        instruction = state.catalog.resolve(
            instruction_line, snapshot.template_index
        )
        if instruction.category == "Notice":
            state.set_notice(instruction)
            self._print_notice(instruction)
        else:
            state.set_navigation(instruction)
            self._print_navigation(instruction)
        return False

    def _print_navigation(self, instruction: ResolvedInstruction) -> None:
        print(
            "[navigation] {} -> {}".format(instruction.symbol, instruction.text),
            flush=True,
        )

    def _print_notice(self, instruction: ResolvedInstruction) -> None:
        suffix = ""
        if not self._interactive_state.notice_enabled:
            suffix = " (display only; set LMDRIVE_USE_NOTICE=1 to feed the model)"
        print(
            "[notice] {} -> {}{}".format(
                instruction.symbol, instruction.text, suffix
            ),
            flush=True,
        )

    def _print_status(self, snapshot: StateSnapshot) -> None:
        print(
            "Navigation: {} (ID {})\nPrompt: {}\nTemplate: {}".format(
                snapshot.navigation.symbol,
                snapshot.navigation.instruction_id,
                snapshot.navigation.text,
                snapshot.template_index,
            )
        )
        if snapshot.notice is None:
            print("Notice: <none>", flush=True)
        else:
            self._print_notice(snapshot.notice)

    @staticmethod
    def _print_help() -> None:
        print(
            """
Commands:
  Turn-02-L                  set an official symbolic navigation command
  Turn-02-L-dis 20           fill a distance template
  Other-05 30 left 5         fill forward/direction/lateral arguments
  id 4                       set a command by official ID (0-64)
  text <English prompt>       send custom natural language as navigation
  notice Notice-01           set a notice prompt
  notice text <prompt>       set a custom notice prompt
  notice clear               clear the current notice
  start | stop | free        aliases for Other-01/03/04
  template <0-7>             choose one of the eight official paraphrases
  list [turn|follow|notice|other]
  status
  quit                       stop this test
""".strip(),
            flush=True,
        )

    @staticmethod
    def _request_quit() -> None:
        # Signals are handled by the standalone client's main thread and by the
        # launcher's cleanup trap, which also terminates the CARLA process group.
        os.kill(os.getpid(), signal.SIGINT)
