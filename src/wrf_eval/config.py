from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


FIXED_SCORE_METRICS = ("pcc", "bias", "mae", "rmse", "normalized_crmse", "rsd")
SUPPORTED_VARIABLES = ("T2", "Tmax", "RH")


@dataclass(frozen=True)
class WrfSection:
    input_root: Path
    schemes: str | list[Any] = "auto"
    scheme_name_pattern: str | None = None
    file_patterns: tuple[str, ...] = ("wrfout_d0*",)
    coord_source: Path | None = None


@dataclass(frozen=True)
class ObservedSection:
    data_dir: Path
    boundary: Path | None = None
    station_policy: str = "all_in_boundary"


@dataclass(frozen=True)
class ValidationSection:
    variable: str = "Tmax"
    start: str | None = "06-01"
    end: str | None = "10-01"


@dataclass(frozen=True)
class OutputSection:
    root: Path = Path("outputs/runs")
    run_id: str | None = None


@dataclass(frozen=True)
class ScoreToolConfig:
    version: int
    project_name: str
    wrf: WrfSection
    observed: ObservedSection
    validation: ValidationSection
    output: OutputSection
    continue_on_error: bool = False

    @property
    def run_id(self) -> str:
        return self.output.run_id or f"wrf_{self.validation.variable.lower()}_station_validation"

    @property
    def score_metrics(self) -> tuple[str, ...]:
        return FIXED_SCORE_METRICS


@dataclass(frozen=True)
class SchemeInput:
    name: str
    path: Path
    file_pattern: str | None = None


def load_score_config(path: Path | str) -> ScoreToolConfig:
    """Load and validate a v1.1 WRF scoring YAML configuration file."""
    config_path = Path(path)
    data = _load_yaml_mapping(config_path)
    if not isinstance(data, dict):
        raise ValueError(f"Configuration root must be a mapping: {config_path}")
    return score_config_from_mapping(data)


def score_config_from_mapping(data: dict[str, Any]) -> ScoreToolConfig:
    _reject_legacy_sections(data)
    version = int(data.get("version", 1))
    if version != 1:
        raise ValueError(f"Unsupported config schema version: {version}")

    project = _mapping(data.get("project", {}), "project")
    wrf_data = _mapping(data.get("wrf", {}), "wrf")
    observed_data = _mapping(data.get("observed", {}), "observed")
    validation_data = _mapping(data.get("validation", {}), "validation")
    output_data = _mapping(data.get("output", {}), "output")
    _reject_legacy_keys(wrf_data, {"input_kind", "variable", "temperature_stat", "rebuild_start", "time_step_days", "drop_initial_frames"}, "wrf")
    _reject_legacy_keys(validation_data, {"date_match"}, "validation")
    _reject_legacy_keys(output_data, {"output_root", "report_root"}, "output")

    variable = _normalize_variable(str(validation_data.get("variable", "Tmax")))

    return ScoreToolConfig(
        version=version,
        project_name=str(project.get("name") or f"wrf_{variable.lower()}_station_validation"),
        wrf=WrfSection(
            input_root=Path(str(wrf_data.get("input_root", "data/wrfout"))),
            schemes=wrf_data.get("schemes", "auto"),
            scheme_name_pattern=_optional_str(wrf_data.get("scheme_name_pattern")),
            file_patterns=_file_patterns(wrf_data),
            coord_source=_optional_path(wrf_data.get("coord_source")),
        ),
        observed=ObservedSection(
            data_dir=Path(str(observed_data.get("data_dir", "data/observed"))),
            boundary=_optional_path(observed_data.get("boundary")),
            station_policy=str(observed_data.get("station_policy", "all_in_boundary")),
        ),
        validation=ValidationSection(
            variable=variable,
            start=_optional_str(validation_data.get("start", "06-01")),
            end=_optional_str(validation_data.get("end", "10-01")),
        ),
        output=OutputSection(
            root=Path(str(output_data.get("root", "outputs/runs"))),
            run_id=_optional_str(output_data.get("run_id")),
        ),
        continue_on_error=bool(data.get("continue_on_error", False)),
    )


def discover_schemes(config: ScoreToolConfig) -> list[SchemeInput]:
    """Discover WRF scheme folders according to the loaded configuration."""
    schemes = config.wrf.schemes
    if schemes == "auto":
        return _discover_auto_schemes(config.wrf.input_root, config.wrf.file_patterns)
    if not isinstance(schemes, list):
        raise ValueError("wrf.schemes must be 'auto' or a list.")

    discovered = []
    for item in schemes:
        if isinstance(item, str):
            path = config.wrf.input_root / item
            pattern = _first_matching_pattern(path, config.wrf.file_patterns)
            discovered.append(SchemeInput(name=item, path=path, file_pattern=pattern))
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("scheme_name") or "")
            if not name:
                raise ValueError("Each explicit scheme mapping must include a name.")
            path = Path(str(item.get("path", config.wrf.input_root / name)))
            pattern = _optional_str(item.get("file_pattern")) or _first_matching_pattern(path, config.wrf.file_patterns)
            discovered.append(SchemeInput(name=name, path=path, file_pattern=pattern))
        else:
            raise ValueError(f"Unsupported scheme entry: {item!r}")

    if not discovered:
        raise FileNotFoundError("No WRF schemes were configured.")
    return discovered


def _discover_auto_schemes(input_root: Path, file_patterns: tuple[str, ...]) -> list[SchemeInput]:
    if not input_root.exists():
        raise FileNotFoundError(f"WRF input root does not exist: {input_root}")
    if not input_root.is_dir():
        raise NotADirectoryError(f"WRF input root must be a directory: {input_root}")

    schemes = []
    for path in sorted(item for item in input_root.iterdir() if item.is_dir()):
        pattern = _first_matching_pattern(path, file_patterns)
        if pattern is not None:
            schemes.append(SchemeInput(name=path.name, path=path, file_pattern=pattern))
    if not schemes:
        patterns = ", ".join(file_patterns)
        raise FileNotFoundError(f"No scheme folders with files matching {patterns} were found under {input_root}.")
    return schemes


def _first_matching_pattern(path: Path, file_patterns: tuple[str, ...]) -> str | None:
    if path.is_file():
        return None
    if not path.exists():
        raise FileNotFoundError(f"WRF scheme path does not exist: {path}")
    for pattern in file_patterns:
        if any(path.glob(pattern)):
            return pattern
    return None


def _normalize_variable(value: str) -> str:
    key = value.strip().lower()
    aliases = {"tmax": "Tmax", "t2": "T2", "rh": "RH", "rhu": "RH", "relative_humidity": "RH"}
    if key not in aliases:
        raise ValueError(f"Unsupported validation.variable: {value!r}. Expected one of: {', '.join(SUPPORTED_VARIABLES)}.")
    return aliases[key]


def _reject_legacy_sections(data: dict[str, Any]) -> None:
    for key in ("time", "metrics"):
        if key in data:
            raise ValueError(f"v1.1 config no longer accepts top-level '{key}'. Time handling and metrics are fixed defaults.")


def _reject_legacy_keys(section: dict[str, Any], keys: set[str], section_name: str) -> None:
    found = sorted(keys.intersection(section))
    if found:
        joined = ", ".join(found)
        raise ValueError(f"v1.1 config no longer accepts {section_name}.{joined}.")


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        return _parse_simple_yaml(text)
    loaded = yaml.safe_load(text)
    return {} if loaded is None else loaded


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the simple YAML subset used by project config files when PyYAML is unavailable."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any] | list[Any]]] = [(-1, root)]
    lines = text.splitlines()

    for line_index, raw_line in enumerate(lines):
        line = _strip_comment(raw_line).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()
        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if content.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError(f"List item without list parent: {raw_line}")
            parent.append(_parse_scalar(content[2:].strip()))
            continue

        if ":" not in content:
            raise ValueError(f"Unsupported YAML line: {raw_line}")
        key, raw_value = content.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if not isinstance(parent, dict):
            raise ValueError(f"Mapping entry under list is not supported: {raw_line}")

        if raw_value:
            parent[key] = _parse_scalar(raw_value)
            continue

        child = _next_container(lines, line_index)
        parent[key] = child
        stack.append((indent, child))

    return root


def _next_container(lines: list[str], current_index: int) -> dict[str, Any] | list[Any]:
    current_line = lines[current_index]
    current_indent = len(current_line) - len(current_line.lstrip(" "))
    for raw_next in lines[current_index + 1 :]:
        next_line = _strip_comment(raw_next).rstrip()
        if not next_line.strip():
            continue
        next_indent = len(next_line) - len(next_line.lstrip(" "))
        if next_indent <= current_indent:
            return {}
        return [] if next_line.strip().startswith("- ") else {}
    return {}


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    for idx, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:idx]
    return line


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        inside = value[1:-1].strip()
        if not inside:
            return []
        return [_parse_scalar(item.strip()) for item in inside.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    lower = value.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    if lower in {"null", "none", "~"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} section must be a mapping.")
    return value


def _file_patterns(wrf_data: dict[str, Any]) -> tuple[str, ...]:
    if "file_patterns" in wrf_data:
        patterns = _string_tuple(wrf_data["file_patterns"], default=())
    elif "file_pattern" in wrf_data:
        patterns = _string_tuple(wrf_data["file_pattern"], default=())
    else:
        patterns = WrfSection.file_patterns
    if not patterns:
        raise ValueError("At least one WRF file pattern is required.")
    return patterns


def _string_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    raise ValueError(f"Expected a string or list of strings, got {value!r}.")


def _optional_path(value: Any) -> Path | None:
    if value is None or value == "":
        return None
    return Path(str(value))


def _optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)
