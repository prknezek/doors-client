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
    """A custom list for DoorsObjects that allows keyword filtering."""

    def filter(self, **kwargs) -> "DoorsList[T]":
        """
        Filters the list by matching exact keyword arguments.
        Allows chaining multiple filters.

        Example:
            objs.filter(created_by="user1", status="Draft")
        """
        result = DoorsList[T]()

        for obj in self:
            match = True

            for key, target_val in kwargs.items():
                # Safely extract the attribute from the generated Pydantic model
                actual_val = getattr(obj, key, None)

                if actual_val is None:
                    match = False
                    break

                # Normalize the target value to a string for safe comparison
                target_str = (
                    target_val.value
                    if isinstance(target_val, Enum)
                    else str(target_val)
                )

                # Handle DOORS multi-select fields (which generate as lists)
                if isinstance(actual_val, list):
                    actual_strings = [
                        v.value if isinstance(v, Enum) else str(v) for v in actual_val
                    ]
                    if target_str not in actual_strings:
                        match = False
                        break

                # Handle standard single values (strings, ints, or single Enums)
                else:
                    actual_str = (
                        actual_val.value
                        if isinstance(actual_val, Enum)
                        else str(actual_val)
                    )
                    if target_str != actual_str:
                        match = False
                        break

            # If all keyword arguments matched successfully, keep the object
            if match:
                result.append(obj)

        return result
