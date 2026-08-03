import csv
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel


def to_csv(
    data: Sequence[BaseModel],
    output_path: Path | str = "export.csv",
    sep: str = ",",
    columns: Sequence[str] | None = None,
    header: bool = True,
    quoting: int = csv.QUOTE_ALL,
) -> None:
    """Exports a list of DOORS Pydantic models to a CSV file."""
    if not data:
        return

    output_path = Path(output_path)

    # Get the raw field definitions to access their aliases
    model_fields = type(data[0]).model_fields
    all_field_names = list(model_fields.keys())

    # Determine which columns to export based on the 'columns' parameter
    if columns is not None:
        fieldnames = [col for col in columns if col in all_field_names]
        dump_kwargs = {"mode": "json", "include": set(fieldnames)}
    else:
        fieldnames = all_field_names
        dump_kwargs = {"mode": "json"}

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            delimiter=sep,
            quoting=quoting,
            extrasaction="ignore",
        )

        if header:
            # Map the snake_case keys to the original DOORS attribute names (alias)
            header_mapping = {
                col: (model_fields[col].alias or col.replace("_", " ").title())
                for col in fieldnames
            }

            writer.writerow(header_mapping)

        for obj in data:
            row_dict = obj.model_dump(**dump_kwargs)

            # Clean up complex types for the DOORS CSV importer
            for key, value in row_dict.items():
                if isinstance(value, list):
                    # DOORS requires newlines (\n) for multi-select enumerations
                    row_dict[key] = "\n".join(str(item) for item in value)
                elif value is None:
                    # Prevent writing the literal string "None" into empty DOORS cells
                    row_dict[key] = ""

            writer.writerow(row_dict)
