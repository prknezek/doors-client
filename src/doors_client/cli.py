import argparse
import getpass
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from pydantic import TypeAdapter

CURRENT_WORKING_DIR = Path.cwd()

# Template Paths
PACKAGE_DIR = Path(__file__).resolve().parent
SCHEMA_DXL_TEMPLATE_PATH = PACKAGE_DIR / "templates" / "schema.dxl"
EXPORT_DXL_TEMPLATE_PATH = PACKAGE_DIR / "templates" / "export.dxl"
PATHS_DXL_TEMPLATE_PATH = PACKAGE_DIR / "templates" / "paths.dxl"

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


def _render_dxl_template(template_path: Path, replacements: dict[str, str]) -> Path:
    """Reads a DXL template, replaces variables, and writes to a secure OS temp file."""
    with template_path.open("r", encoding="utf-8") as f:
        dxl = f.read()

    for key, value in replacements.items():
        dxl = dxl.replace(key, value)

    temp_fd, temp_path = tempfile.mkstemp(suffix=".dxl", text=True)

    with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
        f.write(dxl)

    return Path(temp_path)


def _run_dxl(dxl_path: Path, doors_exe: Path, user: str, password: str) -> None:
    """Generic function to execute any given DXL script via the DOORS batch CLI."""
    cmd = [str(doors_exe), "-u", user, "-P", password, "-b", str(dxl_path)]
    try:
        print(f"Running DXL script via OS temp file...")
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"FAILED to run DXL script.", file=sys.stderr)
        print(f"ERROR:\n{e.stderr}", file=sys.stderr)
        sys.exit(1)
    finally:
        if dxl_path.exists():
            dxl_path.unlink()


def generate_paths(
    doors_exe: Path, output_file_path: Path, root_folder_path: str
) -> None:
    """Generates the database paths JSON via DOORS."""
    print(f"Generating database paths from DOORS folder '{root_folder_path}'...")
    user, password = _get_credentials()

    replacements = {
        "%OUTPUT_FILE_PATH%": output_file_path.resolve().as_posix(),
        "%ROOT_FOLDER_PATH%": root_folder_path,
    }
    dxl_path = _render_dxl_template(PATHS_DXL_TEMPLATE_PATH, replacements)

    _run_dxl(dxl_path, doors_exe, user, password)
    print(
        f"Paths generated successfully to {output_file_path.relative_to(CURRENT_WORKING_DIR)}\n"
    )


def generate_models(target_dir: Path) -> None:
    """Triggers datamodel-codegen targeted at a specific output directory."""
    print(
        f"Generating Python models in {target_dir.relative_to(CURRENT_WORKING_DIR)}..."
    )
    schema_path = target_dir / "schema.json"
    models_path = target_dir / "models.py"

    try:
        subprocess.run(
            [
                "datamodel-codegen",
                "--input",
                str(schema_path),
                "--input-file-type",
                "jsonschema",
                "--output",
                str(models_path),
                "--output-model-type",
                "pydantic_v2.BaseModel",
                "--class-name",
                "DoorsObject",
                "--snake-case-field",
            ],
            cwd=CURRENT_WORKING_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
        print("Models generated successfully!")
    except subprocess.CalledProcessError as e:
        print("FAILED to generate models.", file=sys.stderr)
        print(f"ERROR:\n{e.stderr}", file=sys.stderr)
        sys.exit(1)


def get_doors_schema(module_path: str, doors_exe: Path, output_file_path: Path) -> None:
    """Coordinates the extraction of the schema from DOORS."""
    replacements = {
        "%OUTPUT_FILE_PATH%": output_file_path.resolve().as_posix(),
        "%MODULE_PATH%": module_path,
    }
    dxl_path = _render_dxl_template(
        SCHEMA_DXL_TEMPLATE_PATH, replacements
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
        EXPORT_DXL_TEMPLATE_PATH, replacements
    )

    user, password = _get_credentials()
    print(f"Extracting data from {module_path}...")
    _run_dxl(dxl_path, doors_exe, user, password)


def load_data_into_models(
    json_file_path: Path, models_module_path: str = "generated.models"
) -> list:
    """Loads the extracted DOORS JSON into Pydantic models from a given module path."""
    if str(CURRENT_WORKING_DIR) not in sys.path:
        sys.path.insert(0, str(CURRENT_WORKING_DIR))

    try:
        import importlib

        mod = importlib.import_module(models_module_path)
        DoorsObject = getattr(mod, "DoorsObject")
    except (ImportError, AttributeError) as e:
        raise ImportError(
            f"Models not found at '{models_module_path}'. Run with '--profile models' first."
        ) from e

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
        "-o",
        "--output-dir",
        type=str,
        default="generated",
        help="Target output directory relative to working folder (e.g. 'generated/MODULE').",
    )
    parser.add_argument(
        "-r",
        "--root-path",
        type=str,
        default="/",
        help="Absolute DOORS path to root folder for paths profile.",
    )
    parser.add_argument(
        "-e",
        "--doors-exe",
        type=str,
        default=os.getenv("DOORS_EXE_PATH"),
        help="Path to doors.exe (defaults to DOORS_EXE_PATH env var).",
    )

    return parser.parse_args()


def main() -> None:
    args = _get_args()

    target_dir: Path = CURRENT_WORKING_DIR / args.output_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    schema_output_path = target_dir / "schema.json"
    data_output_path = target_dir / "module_data.json"
    paths_output_path = target_dir / "doors_paths.json"

    requires_doors = args.profile in ["schema", "data", "paths", "all"]
    doors_exe_path = None

    if requires_doors:
        if not args.doors_exe:
            print(
                "ERROR: DOORS executable path missing. Set DOORS_EXE_PATH env var or use '--doors-exe'.",
                file=sys.stderr,
            )
            sys.exit(1)

        doors_exe_path = Path(args.doors_exe)
        if not doors_exe_path.exists():
            print(
                f"ERROR: DOORS executable not found at '{doors_exe_path}'",
                file=sys.stderr,
            )
            sys.exit(1)

    try:
        if args.profile == "paths":
            generate_paths(doors_exe_path, paths_output_path, args.root_path)
            return

        if args.profile in ["schema", "all"]:
            if not args.module_path:
                print(
                    "ERROR: '--module-path' is required to generate schema.",
                    file=sys.stderr,
                )
                sys.exit(1)

            get_doors_schema(args.module_path, doors_exe_path, schema_output_path)
            print(
                f"Schema saved to {schema_output_path.relative_to(CURRENT_WORKING_DIR)}\n"
            )

        if args.profile in ["models", "all"]:
            if not schema_output_path.exists():
                print(
                    f"ERROR: Cannot generate models. '{schema_output_path.name}' not found at {target_dir}.",
                    file=sys.stderr,
                )
                sys.exit(1)

            generate_models(target_dir)

        if args.profile in ["data", "all"]:
            if not args.module_path:
                print(
                    "ERROR: '--module-path' is required to extract data.",
                    file=sys.stderr,
                )
                sys.exit(1)

            extract_module_data(args.module_path, doors_exe_path, data_output_path)
            print(
                f"Data saved to {data_output_path.relative_to(CURRENT_WORKING_DIR)}\n"
            )

    except Exception as e:
        print(f"\nExecution Aborted: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
