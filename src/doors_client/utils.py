import csv
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel


def to_csv(data: Sequence[BaseModel], output_path: Path | str) -> None:
    """Exports a list of DOORS Pydantic models to a CSV file ready for DOORS import."""
    if not data:
        return

    output_path = Path(output_path)

    # Dynamically grab the column headers from the first object's Pydantic schema
    fieldnames = list(data[0].model_fields.keys())

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()

        for obj in data:
            # Dump the model to a dictionary
            row_dict = obj.model_dump(mode="json")

            # Clean up complex types for the DOORS CSV importer
            for key, value in row_dict.items():
                if isinstance(value, list):
                    # DOORS requires newlines (\n) for multi-select enumerations
                    row_dict[key] = "\n".join(str(item) for item in value)
                elif value is None:
                    # Prevent writing the literal string "None" into empty DOORS cells
                    row_dict[key] = ""

            writer.writerow(row_dict)
