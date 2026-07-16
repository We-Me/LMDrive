"""Thread-safe terminal instruction source for the native CARLA client."""

from __future__ import annotations

import threading
from typing import Callable, NamedTuple, Optional

from command_catalog import (
    InstructionCatalog,
    InstructionResolutionError,
    ResolvedInstruction,
)


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
            return self._snapshot_unlocked()

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
                return self._snapshot_unlocked()
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
            return self._snapshot_unlocked()

    def _snapshot_unlocked(self) -> StateSnapshot:
        return StateSnapshot(
            navigation=self._navigation,
            notice=self._notice,
            template_index=self._template_index,
            navigation_revision=self._navigation_revision,
            notice_revision=self._notice_revision,
        )


class TerminalCommandConsole:
    def __init__(
        self,
        state: InteractiveCommandState,
        request_quit: Callable[[], None],
        evaluation_status_getter: Optional[Callable[[], str]] = None,
    ) -> None:
        self.state = state
        self._request_quit = request_quit
        self._evaluation_status_getter = evaluation_status_getter or (lambda: "")
        self._thread = threading.Thread(
            target=self._terminal_loop,
            name="lmdrive-terminal",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def _terminal_loop(self) -> None:
        snapshot = self.state.snapshot()
        print("\n[Native LMDrive] terminal instruction input is ready.")
        print("Type 'help' for syntax. The active initial command is shown below.")
        self._print_navigation(snapshot.navigation)
        while True:
            try:
                line = input("lmdrive> ").strip()
            except EOFError:
                print("\n[Native LMDrive] stdin closed; keeping current command.")
                return
            except KeyboardInterrupt:
                self._request_quit()
                return
            if not line:
                continue
            try:
                if self.handle_line(line):
                    return
            except InstructionResolutionError as exc:
                print("[command error] {}".format(exc), flush=True)
            except Exception as exc:
                print(
                    "[command error] {}: {}".format(type(exc).__name__, exc),
                    flush=True,
                )

    def handle_line(self, line: str) -> bool:
        head, _, remainder = line.partition(" ")
        command = head.lower()
        snapshot = self.state.snapshot()

        if command in ("quit", "exit"):
            print("Stopping the native LMDrive test...", flush=True)
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
            print(self.state.catalog.format_catalog(category), flush=True)
            return False
        if command == "template":
            if not remainder.strip():
                print("Current template index: {}".format(snapshot.template_index))
                return False
            try:
                template_index = int(remainder.strip())
            except ValueError as exc:
                raise InstructionResolutionError("usage: template <0-7>") from exc
            updated = self.state.set_template_index(template_index)
            print("Template index set to {}.".format(updated.template_index), flush=True)
            self._print_navigation(updated.navigation)
            return False
        if command in ("clear-notice", "clear_notice"):
            self.state.set_notice(None)
            print("Notice cleared.", flush=True)
            return False
        if command == "notice":
            notice_line = remainder.strip()
            if not notice_line:
                raise InstructionResolutionError(
                    "usage: notice <Notice-XX | text ... | clear>"
                )
            if notice_line.lower() == "clear":
                self.state.set_notice(None)
                print("Notice cleared.", flush=True)
                return False
            notice = self.state.catalog.resolve(notice_line, snapshot.template_index)
            if notice.category not in ("Notice", "Text"):
                raise InstructionResolutionError(
                    "'notice' expects a Notice-* symbol or 'notice text ...'"
                )
            self.state.set_notice(notice)
            self._print_notice(notice)
            return False

        aliases = {"start": "Other-01", "stop": "Other-03", "free": "Other-04"}
        instruction_line = aliases.get(command, line)
        instruction = self.state.catalog.resolve(
            instruction_line, snapshot.template_index
        )
        if instruction.category == "Notice":
            self.state.set_notice(instruction)
            self._print_notice(instruction)
        else:
            self.state.set_navigation(instruction)
            self._print_navigation(instruction)
        return False

    @staticmethod
    def _print_navigation(instruction: ResolvedInstruction) -> None:
        print(
            "[navigation] {} -> {}".format(instruction.symbol, instruction.text),
            flush=True,
        )

    def _print_notice(self, instruction: ResolvedInstruction) -> None:
        suffix = ""
        if not self.state.notice_enabled:
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
            print("Notice: <none>")
        else:
            self._print_notice(snapshot.notice)
        status = self._evaluation_status_getter()
        if status:
            print("Raw-model evaluation: {}".format(status), flush=True)

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
