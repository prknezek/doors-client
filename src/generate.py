import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path

from pydantic import TypeAdapter

ROOT_DIR = Path(__file__).resolve().parent.parent
TMP_DIR = ROOT_DIR / "tmp"
GENERATED_DIR = ROOT_DIR / "generated"

# Template Paths
SCHEMA_DXL_TEMPLATE_PATH = ROOT_DIR / "src" / "templates" / "schema.dxl"
EXPORT_DXL_TEMPLATE_PATH = ROOT_DIR / "src" / "templates" / "export.dxl"
PATHS_DXL_TEMPLATE_PATH = ROOT_DIR / "src" / "templates" / "paths.dxl"

# Global variables to cache credentials
_cached_user = None
_cached_password = None


def _get_credentials() -> tuple[str, str]:
    """Prompts for DOORS credentials once and caches them for subsequent DXL runs."""
    global _cached_user, _cached_password
    if _cached_user is None or _cached_password is None:
        _cached_user = input("DOORS Username: ")
        _cached_password = getpass.getpass("DOORS Password: ")
    return _cached_user, _cached_password


def _render_dxl_template(
    template_path: Path, temp_filename: str, replacements: dict[str, str]
) -> Path:
    """Generic function to read a DXL template, replace variables, and save to tmp."""
    with template_path.open("r", encoding="utf-8") as f:
        dxl = f.read()

    for key, value in replacements.items():
        dxl = dxl.replace(key, value)

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    temp_dxl_path = TMP_DIR / temp_filename

    with temp_dxl_path.open("w", encoding="utf-8") as f:
        f.write(dxl)

    return temp_dxl_path


def _run_dxl(dxl_path: Path, doors_exe: Path, user: str, password: str) -> None:
    """Generic function to execute any given DXL script via the DOORS batch CLI."""
    cmd = [str(doors_exe), "-u", user, "-P", password, "-b", str(dxl_path)]
    try:
        print(f"Running DXL script: {dxl_path.name}...")
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"FAILED to run DXL script: {dxl_path.name}", file=sys.stderr)
        print(f"ERROR:\n{e.stderr}", file=sys.stderr)
        raise


def generate_paths(doors_exe: Path, output_file_path: Path) -> None:
    """Generates the database paths JSON via DOORS."""
    print("Generating database paths from DOORS...")
    user, password = _get_credentials()

    replacements = {"%OUTPUT_FILE_PATH%": output_file_path.resolve().as_posix()}
    dxl_path = _render_dxl_template(PATHS_DXL_TEMPLATE_PATH, "paths.dxl", replacements)

    _run_dxl(dxl_path, doors_exe, user, password)
    print(f"Paths generated successfully to {output_file_path.relative_to(ROOT_DIR)}\n")


def generate_models() -> None:
    """Triggers datamodel-codegen to build the Python models."""
    print("Generating Python models via datamodel-codegen...")
    try:
        subprocess.run(
            ["datamodel-codegen"],
            cwd=ROOT_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
        print("Models generated successfully!")
    except subprocess.CalledProcessError as e:
        print("FAILED to generate models.")
        print(f"ERROR:\n{e.stderr}")
        raise


def get_doors_schema(module_path: str, doors_exe: Path, output_file_path: Path) -> None:
    """Coordinates the extraction of the schema from DOORS."""
    replacements = {
        "%OUTPUT_FILE_PATH%": output_file_path.resolve().as_posix(),
        "%MODULE_PATH%": module_path,
    }
    dxl_path = _render_dxl_template(
        SCHEMA_DXL_TEMPLATE_PATH, "schema.dxl", replacements
    )

    user, password = _get_credentials()
    print(f"Extracting DOORS schema for {module_path}...")
    _run_dxl(dxl_path, doors_exe, user, password)


def extract_module_data(module_path: str, doors_exe: Path, output_file_path: Path):
    """Extracts actual requirement data from DOORS into a JSON file."""
    replacements = {
        "%OUTPUT_FILE_PATH%": output_file_path.resolve().as_posix(),
        "%MODULE_PATH%": module_path,
    }
    dxl_path = _render_dxl_template(
        EXPORT_DXL_TEMPLATE_PATH, "export.dxl", replacements
    )

    user, password = _get_credentials()
    print(f"Extracting data from {module_path}...")
    _run_dxl(dxl_path, doors_exe, user, password)


def load_data_into_models(json_file_path: Path) -> list:
    """Loads the extracted DOORS JSON into Pydantic models."""

    # Delayed import to prevent crash if models haven't been generated yet
    try:
        from generated.models import DoorsObject
    except ImportError as e:
        raise ImportError("Models not found. Run with '--profile models' first.") from e

    with json_file_path.open("r", encoding="cp1252") as f:
        raw_json_string = f.read()

    adapter = TypeAdapter(list[DoorsObject])
    return adapter.validate_json(raw_json_string)


def _get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agnostic DOORS ORM Generator and Extractor."
    )
    parser.add_argument(
        "-p",
        "--profile",
        type=str,
        choices=["schema", "models", "data", "paths", "all"],
        default="all",
        help="Target to execute. 'all' runs schema and models.",
    )
    parser.add_argument(
        "-m",
        "--module-path",
        type=str,
        help="Absolute DOORS path to the target module.",
    )
    parser.add_argument(
        "-e",
        "--doors-exe",
        type=str,
        default=os.getenv(
            "DOORS_EXE_PATH", "C:/BHTProgramFiles/IBM/Rational/DOORS/9.7/bin/doors.exe"
        ),
        help="Path to doors.exe (defaults to DOORS_EXE_PATH environment variable).",
    )

    return parser.parse_args()


def main() -> None:
    args = _get_args()

    GENERATED_DIR.mkdir(exist_ok=True)
    schema_output_path = GENERATED_DIR / "schema.json"
    data_output_path = GENERATED_DIR / "module_data.json"
    paths_output_path = GENERATED_DIR / "doors_paths.json"

    doors_exe_path = Path(args.doors_exe)
    if not doors_exe_path.exists() and args.profile in [
        "schema",
        "data",
        "paths",
        "all",
    ]:
        print(
            f"ERROR: DOORS executable not found at '{doors_exe_path}'", file=sys.stderr
        )
        sys.exit(1)

    try:
        # Generate Database Paths
        if args.profile == "paths":
            generate_paths(doors_exe_path, paths_output_path)
            return

        # Extract Schema from DOORS
        if args.profile in ["schema", "all"]:
            if not args.module_path:
                print(
                    "ERROR: '--module-path' is required to generate schema.",
                    file=sys.stderr,
                )
                sys.exit(1)

            get_doors_schema(args.module_path, doors_exe_path, schema_output_path)
            print(f"Schema saved to {schema_output_path.relative_to(ROOT_DIR)}\n")

        # Generate Python Models
        if args.profile in ["models", "all"]:
            if not schema_output_path.exists():
                print(
                    f"ERROR: Cannot generate models. \
                    '{schema_output_path.name}' not found.",
                    file=sys.stderr,
                )
                print(
                    "Run with '--profile schema' first to extract it from DOORS.",
                    file=sys.stderr,
                )
                sys.exit(1)

            generate_models()

        # Extract Actual Data
        if args.profile == "data":
            if not args.module_path:
                print(
                    "ERROR: '--module-path' is required to extract data.",
                    file=sys.stderr,
                )
                sys.exit(1)

            extract_module_data(args.module_path, doors_exe_path, data_output_path)
            print(f"Data saved to {data_output_path.relative_to(ROOT_DIR)}\n")

    except Exception as e:
        print(f"\nExecution Aborted: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
