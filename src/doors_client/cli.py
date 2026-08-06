import argparse
import getpass
import logging
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import overload

from pydantic import TypeAdapter

from doors_client.base import DoorsList

CURRENT_WORKING_DIR = Path.cwd()

# Template Paths
PACKAGE_DIR = Path(__file__).resolve().parent
SCHEMA_DXL_TEMPLATE_PATH = PACKAGE_DIR / "templates" / "schema.dxl"
EXPORT_DXL_TEMPLATE_PATH = PACKAGE_DIR / "templates" / "export.dxl"
PATHS_DXL_TEMPLATE_PATH = PACKAGE_DIR / "templates" / "paths.dxl"

# Global variables to cache credentials
_cached_user = None
_cached_password = None

# Initialize logger
logger = logging.getLogger(__name__)


def _get_credentials() -> tuple[str, str]:
    """Prompts for credentials once (or reads env vars) and caches them."""
    global _cached_user, _cached_password

    if _cached_user is None:
        _cached_user = os.environ.get("DOORS_USER")
        if not _cached_user:
            _cached_user = input("DOORS Username: ")

    if _cached_password is None:
        _cached_password = os.environ.get("DOORS_PASSWORD")
        if not _cached_password:
            _cached_password = getpass.getpass("DOORS Password: ")

    return _cached_user, _cached_password


def _render_dxl_template(template_path: Path, replacements: dict[str, str]) -> Path:
    """Reads a DXL template, replaces variables, and writes to a secure OS temp file."""
    with template_path.open("r", encoding="utf-8") as f:
        dxl = f.read()

    for key, value in replacements.items():
        dxl = dxl.replace(key, value)

    temp_fd, temp_path = tempfile.mkstemp(
        prefix=f"{template_path.stem}_", suffix=".dxl", text=True
    )

    with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
        f.write(dxl)

    return Path(temp_path)


def _run_dxl(dxl_path: Path, doors_exe: Path, user: str, password: str) -> None:
    """Generic function to execute any given DXL script via the DOORS batch CLI."""
    cmd = [str(doors_exe), "-u", user, "-P", password, "-b", str(dxl_path)]
    try:
        logger.debug("Executing temporary DXL script: %s", dxl_path.name)

        result = subprocess.run(cmd, check=True, capture_output=True, text=True)

        if result.stdout.strip():
            indented_out = textwrap.indent(result.stdout.strip(), "    ")
            logger.debug("DXL standard output:\n%s", indented_out)

    except subprocess.CalledProcessError as e:
        indented_err = textwrap.indent(
            e.stderr.strip() if e.stderr else "No stderr output.", "    "
        )
        logger.error("DXL script execution failed.\n%s", indented_err)
        raise RuntimeError(f"Failed to run DXL script.\n{indented_err}") from e
    finally:
        if dxl_path.exists():
            logger.debug("Cleaning up temporary file: %s", dxl_path)
            dxl_path.unlink()


def _generate_paths(
    doors_exe: Path, output_file_path: Path, root_folder_path: str
) -> None:
    """Generates the database paths JSON via DOORS."""
    logger.info("Generating database paths for folder: '%s'", root_folder_path)
    user, password = _get_credentials()

    replacements = {
        "%OUTPUT_FILE_PATH%": output_file_path.resolve().as_posix(),
        "%ROOT_FOLDER_PATH%": root_folder_path,
    }
    dxl_path = _render_dxl_template(PATHS_DXL_TEMPLATE_PATH, replacements)

    _run_dxl(dxl_path, doors_exe, user, password)
    logger.info(
        "Database paths successfully saved to: %s",
        output_file_path.relative_to(CURRENT_WORKING_DIR),
    )


def _generate_models(target_dir: Path) -> None:
    """Triggers datamodel-codegen targeted at a specific output directory."""
    logger.info(
        "Generating Python models in: %s", target_dir.relative_to(CURRENT_WORKING_DIR)
    )
    schema_path = target_dir / "schema.json"
    models_path = target_dir / "models.py"

    try:
        result = subprocess.run(
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
                "--base-class",
                "doors_client.base.BaseDoorsObject",
            ],
            cwd=CURRENT_WORKING_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            indented_out = textwrap.indent(result.stdout.strip(), "    ")
            logger.debug("datamodel-codegen standard output:\n%s", indented_out)

        logger.info("Python models successfully generated.")
    except subprocess.CalledProcessError as e:
        indented_err = textwrap.indent(
            e.stderr.strip() if e.stderr else "No stderr output.", "    "
        )
        logger.error("Model generation failed.\n%s", indented_err)
        raise RuntimeError(f"Failed to generate models.\n{indented_err}") from e


def _extract_schema(module_path: str, doors_exe: Path, output_file_path: Path) -> None:
    """Coordinates the extraction of the schema from DOORS."""
    replacements = {
        "%OUTPUT_FILE_PATH%": output_file_path.resolve().as_posix(),
        "%MODULE_PATH%": module_path,
    }
    dxl_path = _render_dxl_template(SCHEMA_DXL_TEMPLATE_PATH, replacements)

    user, password = _get_credentials()
    logger.info("Extracting DOORS schema for module: %s", module_path)
    _run_dxl(dxl_path, doors_exe, user, password)


def _extract_module_data(module_path: str, doors_exe: Path, output_file_path: Path):
    """Extracts actual requirement data from DOORS into a JSON file."""
    replacements = {
        "%OUTPUT_FILE_PATH%": output_file_path.resolve().as_posix(),
        "%MODULE_PATH%": module_path,
    }
    dxl_path = _render_dxl_template(EXPORT_DXL_TEMPLATE_PATH, replacements)

    user, password = _get_credentials()
    logger.info("Extracting data records from module: %s", module_path)
    _run_dxl(dxl_path, doors_exe, user, password)


def _sync_module(
    profile: str,
    target_dir: Path,
    doors_exe: Path | None,
    module_path: str | None = None,
    root_path: str = "/",
) -> None:
    """Orchestrates the extraction and generation pipeline based on the requested profile."""
    schema_output_path = target_dir / "schema.json"
    data_output_path = target_dir / "module_data.json"
    paths_output_path = target_dir / "doors_paths.json"

    if profile == "paths":
        _generate_paths(doors_exe, paths_output_path, root_path)
        return

    if profile in ["schema", "all"]:
        if not module_path:
            raise ValueError("'module_path' is required to generate schema.")
        _extract_schema(module_path, doors_exe, schema_output_path)
        logger.info(
            "Schema successfully saved to: %s",
            schema_output_path.relative_to(CURRENT_WORKING_DIR),
        )

    if profile in ["models", "all"]:
        if not schema_output_path.exists():
            raise FileNotFoundError(
                f"Cannot generate models. '{schema_output_path.name}' not found at {target_dir}."
            )
        _generate_models(target_dir)

    if profile in ["data", "all"]:
        if not module_path:
            raise ValueError("'module_path' is required to extract data.")
        _extract_module_data(module_path, doors_exe, data_output_path)
        logger.info(
            "Data successfully saved to: %s",
            data_output_path.relative_to(CURRENT_WORKING_DIR),
        )


@overload
def load_module(module_dir: Path) -> DoorsList:
    """Loads data from a local directory (e.g., Path('generated/MODULE'))."""
    ...


@overload
def load_module(
    module_data_path: Path, models_path: str = "generated.models"
) -> DoorsList:
    """Loads data using explicitly provided local file paths."""
    ...


@overload
def load_module(
    doors_module_path: str,
    output_dir: Path,
    doors_exe: Path | None = None,
    force_refresh: bool = False,
) -> DoorsList:
    """
    Connects to DOORS to extract the schema and data, generates models,
    and loads the resulting objects. Caches locally to speed up future runs.
    """
    ...


def load_module(
    path_or_doors_id: Path | str,
    models_path_or_out_dir: str | Path | None = None,
    doors_exe: Path | None = None,
    force_refresh: bool = False,
) -> DoorsList:
    """Core implementation handling local loads and remote DOORS extractions."""

    if str(CURRENT_WORKING_DIR) not in sys.path:
        sys.path.insert(0, str(CURRENT_WORKING_DIR))

    # --- User passed a DOORS absolute path (e.g., "/Project/Module") ---
    if isinstance(path_or_doors_id, str):
        doors_path = path_or_doors_id
        target_dir = (
            Path(models_path_or_out_dir)
            if models_path_or_out_dir
            else CURRENT_WORKING_DIR / "generated" / Path(doors_path).name
        )

        # Check if we need to hit DOORS, or if we can use cached files
        data_exists = (target_dir / "module_data.json").exists()
        schema_exists = (target_dir / "schema.json").exists()

        if force_refresh or not (data_exists and schema_exists):
            logger.info("Initiating sync for module: %s", doors_path)
            target_dir.mkdir(parents=True, exist_ok=True)

            # Resolve DOORS executable
            exe_path = doors_exe or Path(os.getenv("DOORS_EXE_PATH", ""))
            if not exe_path.exists():
                raise FileNotFoundError(
                    "DOORS executable not found. Set DOORS_EXE_PATH or pass doors_exe."
                )

            # Call the shared pipeline
            _sync_module(
                profile="all",
                target_dir=target_dir,
                doors_exe=exe_path,
                module_path=doors_path,
            )

        return load_module(target_dir)

    # --- User passed a local directory ---
    elif path_or_doors_id.is_dir():
        module_data_path = path_or_doors_id / "module_data.json"
        try:
            rel_path = path_or_doors_id.resolve().relative_to(
                CURRENT_WORKING_DIR.resolve()
            )
        except ValueError:
            rel_path = path_or_doors_id
        target_models_path = ".".join(rel_path.parts) + ".models"

    # --- User passed a direct file path ---
    else:
        module_data_path = path_or_doors_id
        target_models_path = (
            str(models_path_or_out_dir)
            if models_path_or_out_dir
            else "generated.models"
        )

    # --- Core Execution Logic ---
    try:
        import importlib

        mod = importlib.import_module(target_models_path)
        doors_object = mod.DoorsObject
    except (ImportError, AttributeError) as e:
        raise ImportError(f"Models not found at '{target_models_path}'.") from e

    with module_data_path.open("r", encoding="cp1252") as f:
        raw_json_string = f.read()

    adapter = TypeAdapter(list[doors_object])
    return DoorsList(adapter.validate_json(raw_json_string))


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
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging.",
    )

    return parser.parse_args()


def main() -> None:
    args = _get_args()

    # Configure clean, bracketed logging format
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="[%(asctime)s] %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    target_dir: Path = CURRENT_WORKING_DIR / args.output_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    requires_doors = args.profile in ["schema", "data", "paths", "all"]
    doors_exe_path = None

    if requires_doors:
        if not args.doors_exe:
            logger.error(
                "DOORS executable path missing. Set DOORS_EXE_PATH environment variable or use '--doors-exe'."
            )
            sys.exit(1)

        doors_exe_path = Path(args.doors_exe)
        if not doors_exe_path.exists():
            logger.error("DOORS executable not found at: '%s'", doors_exe_path)
            sys.exit(1)

    try:
        _sync_module(
            profile=args.profile,
            target_dir=target_dir,
            doors_exe=doors_exe_path,
            module_path=args.module_path,
            root_path=args.root_path,
        )
    except Exception as e:
        logger.error("Execution aborted: %s", e, exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
