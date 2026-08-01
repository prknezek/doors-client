from enum import Enum

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
