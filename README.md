# DOORS-to-Python ORM

![PyPI](https://img.shields.io/pypi/v/doors-client)
![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![Pydantic](https://img.shields.io/badge/pydantic-v2-FF43A1)
![DOORS](https://img.shields.io/badge/IBM_DOORS-9.7-0530ad)

## Highlights

- Automated ORM Generation: Dynamically maps DOORS formal modules into strictly typed Python objects.
- Pydantic Type Safety: Automatically converts DOORS drop-down choices into strict Python `Literal` types, providing IDE autocomplete and validation.
- Headless DXL Execution: Interacts directly with the DOORS database in batch mode (no GUI required) with built-in memory management.
- Agnostic Core Engine: Completely decouples project-specific business logic from the core DOORS extraction mechanics.

## Overview

Integrating Python data pipelines with legacy IBM Rational DOORS databases is difficult. Developers are often forced to write raw DXL scripts or deal with fragile, untyped dictionaries. 

This project acts as an automated Object-Relational Mapper (ORM) for DOORS. It uses headless DXL scripts to extract the attribute schema of any DOORS Formal Module, converts that schema into a standard JSON Schema, and leverages `datamodel-codegen` to build Pydantic models.

## Usage

Generate models and extract data directly from the CLI using the newly installed terminal command:

```bash
# Extract the schema, generate models, and pull data using an absolute DOORS path
doors-client --profile all --module-path "/Project Name/System Subfolder/Requirements/Target Formal Module"
```

Once extracted, interact with your DOORS data natively in Python:

```py
>>> from pathlib import Path
>>> from pydantic import TypeAdapter
>>> from generated.models import DoorsObject

# Load your extracted data natively
>>> adapter = TypeAdapter(list[DoorsObject])
>>> reqs = adapter.validate_json(Path("generated/module_data.json").read_text(encoding="cp1252"))

# Enjoy full IDE autocomplete and strict type validation!
>>> print(reqs[0].absolute_number)
155
>>> reqs[0].verification_status = "Invalid Status"
ValidationError: 1 validation error for DoorsObject
verification_status
  Input should be 'Passed', 'Failed', 'Pending', or '' [type=literal_error, input_value='Invalid Status', input_type=str]
```

## Installation

Ensure you have Python 3.10+ installed. You can install the package directly from PyPI:

```bash
pip install doors-client
```

If you are cloning the repository for local development, install the required Python dependencies with:

```bash
pip install -e .
```

## System Requirements

- IBM Rational DOORS: The DOORS client must be installed on your local machine.
- DOORS Executable: Set the `DOORS_EXE_PATH` environment variable to point to your `doors.exe` installation (e.g., `C:/Program Files/IBM/Rational/DOORS/9.7/bin/doors.exe`), or explicitly pass the `--doors-exe` flag to the CLI when running the script.

## License

doors-client is distributed under the MIT license. See the included LICENSE file for details.

I am providing code in the repository to you under an open source license. Because this is my personal repository, the license you receive to my code is from me and not my employer.