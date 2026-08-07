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

    @property
    def is_linked(self) -> bool:
        """Returns True if the object has at least one incoming or outgoing link."""
        out_links = getattr(self, "out_links", None) or []
        in_links = getattr(self, "in_links", None) or []
        return len(out_links) > 0 or len(in_links) > 0

    @property
    def is_orphan(self) -> bool:
        """
        Returns True if the object is a standard requirement
        (not a heading, not a table) but has zero links.
        """
        return self.is_object and not self.is_linked

    def get_downstream_ids(self) -> list[int]:
        """Returns a flat list of target_id integers from out_links."""
        out_links = getattr(self, "out_links", None) or []
        ids = []
        for link in out_links:
            target = getattr(link, "target_id", None)
            if target is not None:
                ids.append(int(target))
        return ids

    def get_upstream_ids(self) -> list[int]:
        """Returns a flat list of source_id integers from in_links."""
        in_links = getattr(self, "in_links", None) or []
        ids = []
        for link in in_links:
            source = getattr(link, "source_id", None)
            if source is not None:
                ids.append(int(source))
        return ids

    def get_attr_str(self, attr_name: str, default: str | None = None) -> str | None:
        """
        Safely extracts an attribute as a string.
        Automatically unpacks Pydantic Enums and handles missing/None values.
        """
        val = getattr(self, attr_name, None)
        if val is None:
            return default
        return val.value if hasattr(val, "value") else str(val)

    def get_downstream_objects(self, target_module: "DoorsList") -> "DoorsList":
        """
        Takes a target module and resolves out_links directly into objects.
        Skips broken/missing links automatically.
        """
        target_ids = self.get_downstream_ids()

        global DoorsList
        return DoorsList(
            obj for obj in (target_module.get(i) for i in target_ids) if obj is not None
        )

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
        If a target sequence contains DOORS objects, it automatically extracts
        the matching attribute from those objects.

        Example:
            objs.filter(absolute_number=[1024, 1025])
            objs.filter(absolute_number=list_of_doors_objects)
        """
        target_sets = {}

        # Pre-process target values to fast sets
        for key, target_val in kwargs.items():
            normalized_set = set()

            # Ensure target_val is iterable for uniform processing
            if not isinstance(target_val, (list, tuple, set)):
                target_val = [target_val]

            for v in target_val:
                # If the item is a DOORS object, extract the attribute we are filtering by
                if isinstance(v, BaseDoorsObject):
                    v = getattr(v, key, None)

                # If extraction failed or value was None, skip it
                if v is None:
                    continue

                # Normalize to a string
                normalized_set.add(v.value if isinstance(v, Enum) else str(v))

            target_sets[key] = normalized_set

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

    def search(self, query: str, case_sensitive: bool = False) -> "DoorsList[T]":
        """
        Iterates through the list and returns a new DoorsList of objects
        where the query exists in either object_heading or object_text.
        """
        result = DoorsList[T]()

        # Pre-process the query for speed
        search_query = query if case_sensitive else query.lower()

        for obj in self:
            heading = getattr(obj, "object_heading", "") or ""
            text = getattr(obj, "object_text", "") or ""

            # Extract standard strings from Enums if necessary
            heading_str = heading.value if hasattr(heading, "value") else str(heading)
            text_str = text.value if hasattr(text, "value") else str(text)

            if not case_sensitive:
                heading_str = heading_str.lower()
                text_str = text_str.lower()

            if search_query in heading_str or search_query in text_str:
                result.append(obj)

        return result

    def to_dataframe(self):
        """
        Converts the DoorsList into a Pandas DataFrame.
        Requires the 'pandas' library to be installed.
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError(
                "The 'pandas' library is required to use to_dataframe(). "
                "Install it with: pip install pandas"
            ) from e

        return pd.DataFrame([obj.model_dump() for obj in self])
