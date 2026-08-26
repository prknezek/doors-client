# DOORS-to-Python ORM

![PyPI](https://img.shields.io/pypi/v/doors-client)
![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![Pydantic](https://img.shields.io/badge/pydantic-v2-FF43A1)
![DOORS](https://img.shields.io/badge/IBM_DOORS-9.7-0530ad)

## Installation

Ensure you have Python 3.10+ installed. You can install the package directly from [PyPI](https://pypi.org/project/doors-client/):

```bash
pip install doors-client
```

If you are cloning the repository for local development, install the required Python dependencies with:

```bash
pip install -e .
```

## Highlights

- **Automated ORM Generation**: Dynamically maps DOORS formal modules into strictly typed Python objects.
- **Pydantic Type Safety**: Automatically converts DOORS drop-down choices into strict Python `Literal` types, providing IDE autocomplete and validation.
- **Headless DXL Execution**: Interacts directly with the DOORS database in batch mode (no GUI required) with built-in memory management.
- **Agnostic Core Engine**: Completely decouples project-specific business logic from the core DOORS extraction mechanics.

## Overview

Integrating Python data pipelines with legacy IBM Rational DOORS databases is difficult. Developers are often forced to write raw DXL scripts or deal with fragile, untyped dictionaries. 

This project acts as an automated Object-Relational Mapper (ORM) for DOORS. It uses headless DXL scripts to extract the attribute schema of any DOORS Formal Module, converts that schema into a standard JSON Schema, and leverages `datamodel-codegen` to build Pydantic models.

## Usage

Generate models and extract data directly from the CLI:

```bash
# Extract the schema, generate models, and pull data using an absolute DOORS path
doors-client --module-path "/Project Name/System Subfolder/Requirements/Target Formal Module"
```

### Fast Lookups and Data Filtering
Extract objects efficiently using an O(1) index or filter by exact attributes. The custom list natively handles complex DOORS enumerations, lists, and string normalization.

```py
from doors_client import load_module

module = load_module("/Project Name/System/Requirements")

# Retrieve an object by its DOORS absolute number
req = module.get(1024)

# Filter out DOORS tables and headings to isolate pure requirement objects
pure_reqs = module.filter(is_object=True)

# Search object headings and text for specific keywords
safety_reqs = pure_reqs.search("safety critical", case_sensitive=False)
```

### Link Traceability Analysis
Evaluate incoming and outgoing DOORS links dynamically. The generated base models provide built-in properties to identify link statuses and traverse relationships across different formal modules.

```py
system_module = load_module("/Project Name/System/Requirements")
software_module = load_module("/Project Name/Software/Requirements")

parent_req = system_module.get(50)

# Quickly check a requirement's link status without needing to load external modules
if parent_req.is_linked and not parent_req.is_orphan:
    print(f"Object {parent_req.absolute_number} has active links.")

# Resolve outgoing links directly into fully instantiated Pydantic objects
downstream_objects = parent_req.get_downstream_objects(target_module=software_module)

for child in downstream_objects:
    child.print_summary()
```

### Pandas DataFrame Integration
```py
module = load_module("/Project Name/System/Requirements")

# Export all loaded Pydantic objects directly to a Pandas DataFrame
df = module.to_dataframe()

# Perform analytics, such as identifying the deletion status of objects
deleted_counts = df.groupby('is_deleted').size()
print(deleted_counts)
```

## System Requirements

- IBM Rational DOORS: The DOORS client must be installed on your local machine.
- DOORS Executable: Set the `DOORS_EXE_PATH` environment variable to point to your `doors.exe` installation (e.g., `C:/Program Files/IBM/Rational/DOORS/9.7/bin/doors.exe`), or explicitly pass the `--doors-exe` flag to the CLI when running the script.

## License

doors-client is distributed under the MIT license. See the included LICENSE file for details.

I am providing code in the repository to you under an open source license. Because this is my personal repository, the license you receive to my code is from me and not my employer.