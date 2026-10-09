"""Pure normalization and metadata. No Home Assistant dependency."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Metric:
    key: str
    name: str
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = "measurement"
    scale: float = 1


def flatten(value: dict, prefix: str = "") -> dict:
    """Flatten nested API objects consistently with dotted paths."""
    result = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            result.update(flatten(item, path))
        elif isinstance(item, list):
            for index, element in enumerate(item):
                if not isinstance(element, (dict, list)):
                    result[f"{path}.{index}"] = element
        else:
            result[path] = item
    return result


def numeric(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def normalize(raw: dict, kind: str) -> dict:
    data = flatten(raw)
    # Do not blindly turn arbitrary fields into entities: explicit semantics.
    aliases = {"memory.used": "mem", "memory.total": "maxmem", "memory.free": "memory_free",
               "swap.used": "swap_used", "swap.total": "swap_total", "swap.free": "swap_free",
               "rootfs.used": "disk", "rootfs.total": "maxdisk", "rootfs.avail": "disk_free",
               "cpuinfo.cpus": "cpu_count", "cpuinfo.sockets": "cpu_sockets",
               "cpuinfo.cores": "cpu_cores_per_socket", "cpuinfo.mhz": "cpu_mhz",
               "cpuinfo.model": "cpu_model", "loadavg.0": "load_1m",
               "loadavg.1": "load_5m", "loadavg.2": "load_15m"}
    if kind in {"qemu", "lxc"}:
        aliases["cpus"] = "cpu_count"
        aliases["swap"] = "swap_used"
    if kind == "storage":
        aliases.update(used="disk", total="maxdisk", avail="disk_free")
        data["status"] = "active" if raw.get("active") else "inactive"
    for source, target in aliases.items():
        if source in data:
            data[target] = data[source]
    for used, total, free, percent in (("mem", "maxmem", "memory_free", "memory_percent"),
                                      ("disk", "maxdisk", "disk_free", "disk_percent"),
                                      ("swap_used", "swap_total", "swap_free", "swap_percent")):
        u, t = numeric(data.get(used)), numeric(data.get(total))
        if u is not None and t is not None and t > 0:
            data[percent] = u / t * 100
            data.setdefault(free, max(0, t - u))
    # Stopped guests may omit uptime/usage. Do not fabricate missing metrics.
    return data


METRICS = (
    Metric("status", "Status", state_class=None),
    Metric("cpu", "CPU utilization", "%", scale=100),
    Metric("iowait", "IO wait", "%", scale=100),
    Metric("mem", "Memory used", "B", "data_size"),
    Metric("maxmem", "Memory capacity", "B", "data_size"),
    Metric("memory_free", "Memory free", "B", "data_size"),
    Metric("memory_percent", "Memory utilization", "%"),
    Metric("swap_used", "Swap used", "B", "data_size"),
    Metric("swap_total", "Swap capacity", "B", "data_size"),
    Metric("swap_free", "Swap free", "B", "data_size"),
    Metric("swap_percent", "Swap utilization", "%"),
    Metric("disk", "Disk used", "B", "data_size"),
    Metric("maxdisk", "Disk capacity", "B", "data_size"),
    Metric("disk_free", "Disk free", "B", "data_size"),
    Metric("disk_percent", "Disk utilization", "%"),
    Metric("uptime", "Uptime", "s", "duration"),
    Metric("netin", "Network received", "B", "data_size", "total_increasing"),
    Metric("netout", "Network sent", "B", "data_size", "total_increasing"),
    Metric("diskread", "Disk read", "B", "data_size", "total_increasing"),
    Metric("diskwrite", "Disk written", "B", "data_size", "total_increasing"),
    Metric("network_in_rate", "Network receive rate", "B/s", "data_rate"),
    Metric("network_out_rate", "Network transmit rate", "B/s", "data_rate"),
    Metric("cpu_count", "Logical processors"),
    Metric("cpu_sockets", "CPU sockets"),
    Metric("cpu_cores_per_socket", "CPU cores per socket"),
    Metric("cpu_mhz", "CPU frequency", "MHz", "frequency"),
    Metric("cpu_model", "CPU model", state_class=None),
    Metric("load_1m", "Load average 1 minute"),
    Metric("load_5m", "Load average 5 minutes"),
    Metric("load_15m", "Load average 15 minutes"),
    Metric("balloon", "Balloon memory", "B", "data_size"),
    Metric("ballooninfo.actual", "Balloon actual memory", "B", "data_size"),
    Metric("ballooninfo.free_mem", "Balloon free memory", "B", "data_size"),
    Metric("ballooninfo.total_mem", "Balloon total memory", "B", "data_size"),
    Metric("pid", "Host process ID", state_class=None),
)


def sensor_value(record: dict, metric: Metric):
    value = record.get(metric.key)
    if metric.state_class is None:
        return value if isinstance(value, (str, int, float)) else None
    number = numeric(value)
    return None if number is None else number * metric.scale


def new_sensor_keys(data: dict, seen: set) -> list:
    """Incremental discovery shared by HA and standalone tests."""
    added = []
    for group in ("nodes", "guests", "storage"):
        for resource, record in data.get(group, {}).items():
            for metric in METRICS:
                key = (group, resource, metric.key)
                if key not in seen and sensor_value(record, metric) is not None:
                    seen.add(key)
                    added.append((group, resource, metric))
    return added
