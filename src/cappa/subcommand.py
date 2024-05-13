from __future__ import annotations

import dataclasses
import typing

from type_lens import TypeView
from typing_extensions import Annotated, Self, TypeAlias

from cappa.class_inspect import Field, extract_dataclass_metadata
from cappa.completion.types import Completion
from cappa.typing import (
    MISSING,
    T,
    assert_type,
    find_type_annotation,
    missing,
)

if typing.TYPE_CHECKING:
    from cappa.command import Command


@dataclasses.dataclass
class Subcommand:
    """Describe a CLI subcommand.

    Arguments:
        name: Defaults to the name of the class, converted to dash case, but
            can be overridden here.
        types: Defaults to the class's annotated types, but can be overridden here.
        required: Defaults to automatically inferring requiredness, based on whether the
            class's value has a default. By setting this, you can force a particular value.
        hidden: Whether the argument should be hidden in help text. Defaults to False.
    """

    field_name: str | MISSING = ...
    required: bool | None = None
    group: str | tuple[int, str] = (3, "Subcommands")
    hidden: bool = False

    types: typing.Iterable[type] | MISSING = ...
    options: dict[str, Command] = dataclasses.field(default_factory=dict)

    @classmethod
    def collect(cls, field: Field, type_hint: type) -> Self | None:
        object_annotation = find_type_annotation(type_hint, cls)
        subcommand = object_annotation.obj

        field_metadata = extract_dataclass_metadata(field)
        if field_metadata:
            if not isinstance(field_metadata, Subcommand):
                return None

            subcommand = field_metadata  # type: ignore

        if subcommand is None:
            return None

        return subcommand.normalize(
            TypeView(type_hint),
            field_name=field.name,
        )

    def normalize(
        self,
        annotation: TypeView | None = None,
        field_name: str | None = None,
    ) -> Self:
        if annotation is None:
            annotation = TypeView(...)

        field_name = field_name or assert_type(self.field_name, str)
        types = infer_types(self, annotation)
        required = infer_required(self, annotation)
        options = infer_options(self, types)
        group = infer_group(self)

        return dataclasses.replace(
            self,
            field_name=field_name,
            types=types,
            required=required,
            options=options,
            group=group,
        )

    def map_result(self, prog: str, parsed_args):
        option_name = parsed_args.pop("__name__")
        option = self.options[option_name]
        return option.map_result(option, prog, parsed_args)

    def available_options(self) -> list[Command]:
        return [o for o in self.options.values() if not o.hidden]

    def names(self) -> list[str]:
        return [n for n, o in self.options.items() if not o.hidden]

    def names_str(self, delimiter: str = ", ") -> str:
        return f"{delimiter.join(self.names())}"

    def completion(self, partial: str):
        return [Completion(o) for o in self.options if partial in o]


def infer_types(arg: Subcommand, annotation: TypeView) -> typing.Iterable[type]:
    if arg.types is not missing:
        return typing.cast(typing.Iterable[type], arg.types)

    if annotation.is_union:
        return tuple(
            [t.annotation for t in annotation.inner_types if not t.is_optional]
        )

    return (annotation.annotation,)


def infer_required(arg: Subcommand, annotation: TypeView) -> bool:
    if arg.required is not None:
        return arg.required

    return not annotation.is_optional


def infer_options(arg: Subcommand, types: typing.Iterable[type]) -> dict[str, Command]:
    from cappa.command import Command

    if arg.options:
        return {
            name: Command.collect(type_command)
            for name, type_command in arg.options.items()
        }

    options = {}
    for type_ in types:
        type_command: Command = Command.get(type_)
        type_name = type_command.real_name()
        options[type_name] = Command.collect(type_command)

    return options


def infer_group(arg: Subcommand) -> str | tuple[int, str]:
    group: str | tuple[int, str] | MISSING = arg.group
    group_name = None
    if isinstance(group, str):
        group_name = group
        group = missing

    if group is missing:
        return (3, group_name or "Subcommands")

    return typing.cast(typing.Tuple[int, str], group)


Subcommands: TypeAlias = Annotated[T, Subcommand]
