from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WrfSection:
    input_root: Path
    schemes: str | list[Any] = "auto"
    scheme_name_pattern: str | None = None
    input_kind: str = "hourly_t2"
    variable: str = "T2"
    file_patterns: tuple[str, ...] = ("T2_output*.nc", "T2_out*.nc")
    coord_source: Path | None = None
    rebuild_start: str | None = None
    time_step_days: int = 1
    drop_initial_frames: int = 0


@dataclass(frozen=True)
class ObservedSection:
    data_dir: Path
    boundary: Path | None = None
    station_policy: str = "all_in_boundary"


@dataclass(frozen=True)
class TimeSection:
    time_offset_hours: int = 8
    local_day_boundary_hour: int | None = 20
    drop_incomplete_start_day: bool = True
    drop_incomplete_end_day: bool = True


@dataclass(frozen=True)
class ValidationSection:
    start: str | None = "06-01"
    end: str | None = "10-01"
    date_match: str = "exact"


@dataclass(frozen=True)
class MetricsSection:
    selected: tuple[str, ...] = ("pcc", "bias", "mae", "rmse", "normalized_crmse", "rsd")
    weights: dict[str, float] | None = None


@dataclass(frozen=True)
class OutputSection:
    output_root: Path = Path("outputs/runs")
    report_root: Path = Path("reports/runs")
    run_id: str | None = None
    formats: tuple[str, ...] = ("csv", "markdown")


@dataclass(frozen=True)
class ScoreToolConfig:
    version: int
    project_name: str
    wrf: WrfSection
    observed: ObservedSection
    time: TimeSection
    validation: ValidationSection
    metrics: MetricsSection
    output: OutputSection
    continue_on_error: bool = False

    @property
    def run_id(self) -> str:
        return self.output.run_id or self.project_name


@dataclass(frozen=True)
class SchemeInput:
    name: str
    path: Path
    file_pattern: str | None = None


def load_score_config(path: Path | str) -> ScoreToolConfig:
    """Load and validate a WRF scoring YAML configuration file."""
    config_path = Path(path)
    data = _load_yaml_mapping(config_path)
    if not isinstance(data, dict):
        raise ValueError(f"Configuration root must be a mapping: {config_path}")
    return score_config_from_mapping(data)


def score_config_from_mapping(data: dict[str, Any]) -> ScoreToolConfig:
    version = int(data.get("version", 1))
    if version != 1:
        raise ValueError(f"Unsupported config version: {version}")

    project = _mapping(data.get("project", {}), "project")
    wrf_data = _mapping(data.get("wrf", {}), "wrf")
    observed_data = _mapping(data.get("observed", {}), "observed")
    time_data = _mapping(data.get("time", {}), "time")
    validation_data = _mapping(data.get("validation", {}), "validation")
    metrics_data = _mapping(data.get("metrics", {}), "metrics")
    output_data = _mapping(data.get("output", {}), "output")

    file_patterns = _file_patterns(wrf_data)
    selected_metrics = _string_tuple(metrics_data.get("selected"), default=MetricsSection.selected)

    return ScoreToolConfig(
        version=version,
        project_name=str(project.get("name") or "wrf_score_run"),
        wrf=WrfSection(
            input_root=Path(str(wrf_data.get("input_root", "data/wrfout"))),
            schemes=wrf_data.get("schemes", "auto"),
            scheme_name_pattern=_optional_str(wrf_data.get("scheme_name_pattern")),
            input_kind=str(wrf_data.get("input_kind", "hourly_t2")),
            variable=str(wrf_data.get("variable", "T2")),
            file_patterns=file_patterns,
            coord_source=_optional_path(wrf_data.get("coord_source")),
            rebuild_start=_optional_str(wrf_data.get("rebuild_start")),
            time_step_days=int(wrf_data.get("time_step_days", 1)),
            drop_initial_frames=int(wrf_data.get("drop_initial_frames", 0)),
        ),
        observed=ObservedSection(
            data_dir=Path(str(observed_data.get("data_dir", "data/observed"))),
            boundary=_optional_path(observed_data.get("boundary")),
            station_policy=str(observed_data.get("station_policy", "all_in_boundary")),
        ),
        time=TimeSection(
            time_offset_hours=int(time_data.get("time_offset_hours", 8)),
            local_day_boundary_hour=_optional_int(time_data.get("local_day_boundary_hour", 20)),
            drop_incomplete_start_day=bool(time_data.get("drop_incomplete_start_day", True)),
            drop_incomplete_end_day=bool(time_data.get("drop_incomplete_end_day", True)),
        ),
        validation=ValidationSection(
            start=_optional_str(validation_data.get("start", "06-01")),
            end=_optional_str(validation_data.get("end", "10-01")),
            date_match=str(validation_data.get("date_match", "exact")),
        ),
        metrics=MetricsSection(
            selected=selected_metrics,
            weights=_optional_weights(metrics_data.get("weights")),
        ),
        output=OutputSection(
            output_root=Path(str(output_data.get("output_root", "outputs/runs"))),
            report_root=Path(str(output_data.get("report_root", "reports/runs"))),
            run_id=_optional_str(output_data.get("run_id")),
            formats=_string_tuple(output_data.get("formats"), default=OutputSection.formats),
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


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_weights(value: Any) -> dict[str, float] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("metrics.weights must be a mapping.")
    return {str(key): float(weight) for key, weight in value.items()}
