"""LMDrive symbolic-instruction catalog and prompt rendering helpers.

This module intentionally depends only on the Python standard library so its
mapping and parsing behavior can be tested without importing CARLA or PyTorch.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# The order is the authoritative ID order used by
# The order matches LMDrive's official instruction dictionary and data parsers.
INSTRUCTION_SYMBOLS: Tuple[str, ...] = (
    "Turn-01-L",
    "Turn-01-R",
    "Turn-01-L-dis",
    "Turn-01-R-dis",
    "Turn-02-L",
    "Turn-02-R",
    "Turn-02-S",
    "Turn-02-L-dis",
    "Turn-02-R-dis",
    "Turn-02-S-dis",
    "Turn-03-L",
    "Turn-03-R",
    "Turn-03-S",
    "Turn-03-L-dis",
    "Turn-03-R-dis",
    "Turn-03-S-dis",
    "Turn-04-L",
    "Turn-04-R",
    "Turn-04-S",
    "Turn-04-L-dis",
    "Turn-04-R-dis",
    "Turn-04-S-dis",
    "Turn-05-1",
    "Turn-05-2",
    "Turn-05-3",
    "Turn-06-L-L",
    "Turn-06-L-R",
    "Turn-06-L-S",
    "Turn-06-R-L",
    "Turn-06-R-R",
    "Turn-06-R-S",
    "Turn-06-S-L",
    "Turn-06-S-R",
    "Turn-06-S-S",
    "Follow-01-L",
    "Follow-01-R",
    "Follow-01-L-dis",
    "Follow-01-R-dis",
    "Follow-02-s1",
    "Follow-02-s2",
    "Follow-02-s1-dis",
    "Follow-02-s2-dis",
    "Follow-03-s1",
    "Follow-03-s2",
    "Follow-03-s1-dis",
    "Follow-03-s2-dis",
    "Follow-04-L",
    "Follow-04-R",
    "Follow-04-L-dis",
    "Follow-04-R-dis",
    "Notice-01",
    "Notice-02",
    "Notice-03",
    "Notice-04",
    "Notice-05",
    "Notice-06",
    "Notice-07",
    "Notice-08-R",
    "Notice-08-G",
    "Notice-08-Y",
    "Other-01",
    "Other-02",
    "Other-03",
    "Other-04",
    "Other-05",
)


class InstructionResolutionError(ValueError):
    """Raised when a terminal instruction cannot be resolved safely."""


@dataclass(frozen=True)
class InstructionSpec:
    instruction_id: int
    symbol: str
    category: str
    argument_names: Tuple[str, ...]
    templates: Tuple[str, ...]

    @property
    def usage(self) -> str:
        suffix = "".join(" <{}>".format(name) for name in self.argument_names)
        return "{}{}".format(self.symbol, suffix)


@dataclass(frozen=True)
class ResolvedInstruction:
    instruction_id: Optional[int]
    symbol: str
    category: str
    arguments: Tuple[str, ...]
    template_index: Optional[int]
    text: str


def _argument_names(symbol: str) -> Tuple[str, ...]:
    if symbol == "Other-05":
        return ("forward_meters", "left/right/straight", "lateral_meters")
    if symbol.endswith("-dis"):
        return ("meters",)
    return ()


class InstructionCatalog:
    """Resolve official symbolic IDs to the natural-language model prompts."""

    def __init__(self, instruction_dict_path: Path) -> None:
        self.instruction_dict_path = Path(instruction_dict_path)
        with self.instruction_dict_path.open("r", encoding="utf-8") as handle:
            raw_templates = json.load(handle)

        expected_ids = {str(index) for index in range(len(INSTRUCTION_SYMBOLS))}
        actual_ids = set(raw_templates)
        if actual_ids != expected_ids:
            missing = sorted(expected_ids - actual_ids)
            extra = sorted(actual_ids - expected_ids)
            raise InstructionResolutionError(
                "instruction_dict ID mismatch; missing={}, extra={}".format(
                    missing, extra
                )
            )

        specs: List[InstructionSpec] = []
        for instruction_id, symbol in enumerate(INSTRUCTION_SYMBOLS):
            templates = tuple(raw_templates[str(instruction_id)])
            if len(templates) != 8 or not all(
                isinstance(item, str) for item in templates
            ):
                raise InstructionResolutionError(
                    "ID {} ({}) must have exactly eight string templates".format(
                        instruction_id, symbol
                    )
                )
            specs.append(
                InstructionSpec(
                    instruction_id=instruction_id,
                    symbol=symbol,
                    category=symbol.split("-", 1)[0],
                    argument_names=_argument_names(symbol),
                    templates=templates,
                )
            )

        self.specs: Tuple[InstructionSpec, ...] = tuple(specs)
        self._by_id: Dict[int, InstructionSpec] = {
            spec.instruction_id: spec for spec in self.specs
        }
        self._by_symbol: Dict[str, InstructionSpec] = {
            spec.symbol.lower(): spec for spec in self.specs
        }

    def resolve(self, command_line: str, template_index: int = 0) -> ResolvedInstruction:
        """Resolve ``Turn-02-L``, ``id 4``, ``4``, or ``text ...`` input."""

        try:
            tokens = shlex.split(command_line.strip())
        except ValueError as exc:
            raise InstructionResolutionError(str(exc)) from exc
        if not tokens:
            raise InstructionResolutionError("empty instruction")

        if tokens[0].lower() == "text":
            text = " ".join(tokens[1:])
            if not text:
                raise InstructionResolutionError("usage: text <natural language>")
            return ResolvedInstruction(
                instruction_id=None,
                symbol="TEXT",
                category="Text",
                arguments=(),
                template_index=None,
                text=text,
            )

        if tokens[0].lower() == "id":
            if len(tokens) < 2:
                raise InstructionResolutionError("usage: id <0-64> [arguments]")
            spec = self._lookup_id(tokens[1])
            arguments = tokens[2:]
        elif tokens[0].isdigit():
            spec = self._lookup_id(tokens[0])
            arguments = tokens[1:]
        else:
            spec = self._by_symbol.get(tokens[0].lower())
            if spec is None:
                raise InstructionResolutionError(
                    "unknown instruction {!r}; type 'list' to show symbols".format(
                        tokens[0]
                    )
                )
            arguments = tokens[1:]

        return self.render(spec, arguments, template_index)

    def render(
        self,
        spec: InstructionSpec,
        arguments: Sequence[str],
        template_index: int = 0,
    ) -> ResolvedInstruction:
        if len(arguments) != len(spec.argument_names):
            raise InstructionResolutionError("usage: {}".format(spec.usage))
        if template_index < 0 or template_index >= len(spec.templates):
            raise InstructionResolutionError(
                "template index {} is invalid for {}; use 0-{}".format(
                    template_index, spec.symbol, len(spec.templates) - 1
                )
            )

        text = spec.templates[template_index]
        if spec.symbol == "Other-05":
            direction = arguments[1].lower()
            if direction not in ("left", "right", "straight"):
                raise InstructionResolutionError(
                    "Other-05 direction must be left, right, or straight"
                )
            text = text.replace("[x]", arguments[0])
            text = text.replace("left/right", direction)
            text = text.replace("[y]", arguments[2])
        elif spec.argument_names:
            text = text.replace("[x]", arguments[0])

        return ResolvedInstruction(
            instruction_id=spec.instruction_id,
            symbol=spec.symbol,
            category=spec.category,
            arguments=tuple(arguments),
            template_index=template_index,
            text=text,
        )

    def rerender(
        self, instruction: ResolvedInstruction, template_index: int
    ) -> ResolvedInstruction:
        if instruction.instruction_id is None:
            return instruction
        return self.render(
            self._by_id[instruction.instruction_id],
            instruction.arguments,
            template_index,
        )

    def format_catalog(self, category: Optional[str] = None) -> str:
        normalized = category.lower() if category else None
        selected: Iterable[InstructionSpec] = self.specs
        if normalized:
            selected = (
                spec
                for spec in self.specs
                if spec.category.lower() == normalized
                or spec.symbol.lower().startswith(normalized)
            )
        lines = [
            "{:>2}  {}".format(spec.instruction_id, spec.usage)
            for spec in selected
        ]
        if not lines:
            raise InstructionResolutionError(
                "unknown category {!r}; use turn, follow, notice, or other".format(
                    category
                )
            )
        return "\n".join(lines)

    def _lookup_id(self, raw_id: str) -> InstructionSpec:
        try:
            instruction_id = int(raw_id)
        except ValueError as exc:
            raise InstructionResolutionError(
                "instruction ID must be an integer from 0 to 64"
            ) from exc
        spec = self._by_id.get(instruction_id)
        if spec is None:
            raise InstructionResolutionError(
                "instruction ID {} is outside 0-64".format(instruction_id)
            )
        return spec
