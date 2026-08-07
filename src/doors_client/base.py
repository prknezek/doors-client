from enum import Enum
from typing import TypeVar

from pydantic import BaseModel


class BaseDoorsObject(BaseModel):
    """Custom methods injected into all generated DOORS models."""

    @property
    def _normalized_table_type(self) -> str:
        """Helper to safely extract and normalize the table type as a lowercase string."""
        tt = getattr(self, "table_type", None)

        if tt is None:
            return "table_none"

        return tt.name.lower() if isinstance(tt, Enum) else str(tt).lower()

    @property
    def is_table(self) -> bool:
        """
        Evaluates the generated table_type attribute.
        Returns True if the object is part of a table (cell, row, or base).
        """
        return "none" not in self._normalized_table_type

    @property
    def is_table_cell(self) -> bool:
        """
        Evaluates the generated table_type attribute.
        Returns True if the object is a table cell.
        """
        return "cell" in self._normalized_table_type

    @property
    def is_table_row(self) -> bool:
        """
        Evaluates the generated table_type attribute.
        Returns True if the object is a table row.
        """
        return "row" in self._normalized_table_type

    @property
    def is_table_base(self) -> bool:
        """
        Evaluates the generated table_type attribute.
        Returns True if the object is a table base.
        """
        return "base" in self._normalized_table_type

    @property
    def is_heading(self) -> bool:
        """
        Returns True if the object is a pure heading
        (Object Heading has text and Object Text is empty/blank).
        """
        heading_val = getattr(self, "object_heading", "")
        text_val = getattr(self, "object_text", "")

        # Safely handle potential None values and whitespace-only strings
        has_heading = bool(heading_val and str(heading_val).strip())
        has_text = bool(text_val and str(text_val).strip())

        return has_heading and not has_text

    @property
    def is_object(self) -> bool:
        """
        Returns True if the item is a standard requirement or text object
        (i.e., it is NOT a table element and NOT a heading).
        """
        return not self.is_table and not self.is_heading

    def print_summary(self) -> None:
        """Prints a summary of the object."""
        text = (
            getattr(self, "object_heading", "")
            if self.is_heading
            else getattr(self, "object_text", "")
        )
        print(f"[{getattr(self, 'absolute_number', 'N/A')}]: {text}")


# Generic TypeVar bound to the BaseDoorsObject
T = TypeVar("T", bound=BaseDoorsObject)


class DoorsList(list[T]):
    """A custom list for DoorsObjects that allows keyword filtering and O(1) ID lookups."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._id_index: dict[str, T] = {}
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        """Rebuilds the lookup dictionary from the current list contents."""
        self._id_index.clear()
        for obj in self:
            abs_num = getattr(obj, "absolute_number", None)
            if abs_num is not None:
                # Store keys as strings so .get(12) and .get("12") both work
                self._id_index[str(abs_num)] = obj

    def append(self, item: T) -> None:
        """Appends an item to the list and updates the index."""
        super().append(item)
        abs_num = getattr(item, "absolute_number", None)
        if abs_num is not None:
            self._id_index[str(abs_num)] = item

    def extend(self, iterable) -> None:
        """Extends the list and rebuilds the index."""
        super().extend(iterable)
        self._rebuild_index()

    def get(self, absolute_number: int | str, default: T | None = None) -> T | None:
        """
        Retrieves an object by its absolute_number.

        Example:
            req = my_module.get(1024)
        """
        return self._id_index.get(str(absolute_number), default)

    def filter(self, **kwargs) -> "DoorsList[T]":
        """
        Filters the list by matching exact keyword arguments.
        If a target value is a list, tuple, or set, it acts as an "IN" operator.
        """
        # Pre-process target values to fast sets
        target_sets = {}
        for key, target_val in kwargs.items():
            if isinstance(target_val, (list, tuple, set)):
                target_sets[key] = {
                    v.value if isinstance(v, Enum) else str(v) for v in target_val
                }
            else:
                target_sets[key] = {
                    (
                        target_val.value
                        if isinstance(target_val, Enum)
                        else str(target_val)
                    )
                }

        # Define a matching function for the generator
        def matches(obj: T) -> bool:
            for key, target_strings in target_sets.items():
                actual_val = getattr(obj, key, None)

                if actual_val is None:
                    return False

                # Handle DOORS multi-select fields (lists)
                if isinstance(actual_val, list):
                    if not any(
                        (v.value if isinstance(v, Enum) else str(v)) in target_strings
                        for v in actual_val
                    ):
                        return False

                # Handle standard single values (strings, ints, or single Enums)
                else:
                    actual_str = (
                        actual_val.value
                        if isinstance(actual_val, Enum)
                        else str(actual_val)
                    )
                    if actual_str not in target_strings:
                        return False

            return True

        # Filter the objects based on matches
        return DoorsList(obj for obj in self if matches(obj))
