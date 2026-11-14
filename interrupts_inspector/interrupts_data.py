#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# LinSpectacles - Linux Inspection Suite
# Copyright (C) 2026 brunonlinespace
# GPL-3.0-or-later

"""Read-only collectors for Interrupts Inspector.

Primary authoritative sources:
  /proc/interrupts
  /proc/softirqs
  /proc/irq/<irq>/*

Optional context sources:
  /sys/kernel/irq/<irq>/*
  /sys/bus/pci/devices/*/msi_irqs/* and selected device attributes

No commands are executed and no kernel state is modified.
"""

from pathlib import Path
import re


def _read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except (FileNotFoundError, PermissionError, OSError):
        return ""


def _read_link_name(path):
    try:
        return Path(path).resolve(strict=True).name
    except (FileNotFoundError, PermissionError, OSError):
        return ""


def _parse_int(value, default=None):
    try:
        return int(str(value).strip(), 10)
    except (TypeError, ValueError):
        return default


def _parse_spurious(path):
    result = {}
    text = _read_text(path)
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        key = parts[0].rstrip(":")
        value = parts[1] if len(parts) > 1 else ""
        if key in {"count", "unhandled", "last_unhandled"}:
            result[key] = value
    return result


def _pci_context_map():
    """Map MSI/MSI-X IRQ numbers to conservative PCI context.

    This is optional enrichment only. Failure or absence never invalidates the
    /proc/interrupts inventory.
    """
    mapping = {}
    root = Path("/sys/bus/pci/devices")
    try:
        devices = sorted(p for p in root.iterdir() if p.is_dir() or p.is_symlink())
    except (FileNotFoundError, PermissionError, OSError):
        return mapping

    for dev in devices:
        irq_dir = dev / "msi_irqs"
        try:
            irq_entries = list(irq_dir.iterdir())
        except (FileNotFoundError, PermissionError, OSError):
            continue
        irqs = []
        for item in irq_entries:
            irq = _parse_int(item.name)
            if irq is not None:
                irqs.append(irq)
        if not irqs:
            continue

        net_names = []
        try:
            net_names = sorted(p.name for p in (dev / "net").iterdir())
        except (FileNotFoundError, PermissionError, OSError):
            pass

        context = {
            "pci_address": dev.name,
            "pci_vendor": _read_text(dev / "vendor") or "Not reported",
            "pci_device": _read_text(dev / "device") or "Not reported",
            "pci_class": _read_text(dev / "class") or "Not reported",
            "driver": _read_link_name(dev / "driver") or "Unbound",
            "pci_numa_node": _read_text(dev / "numa_node") or "Not reported",
            "network_interfaces": ", ".join(net_names) if net_names else "Not reported",
        }
        for irq in irqs:
            mapping.setdefault(irq, []).append(dict(context))
    return mapping


def _irq_context(irq, pci_map):
    proc_dir = Path("/proc/irq") / str(irq)
    sys_dir = Path("/sys/kernel/irq") / str(irq)

    actions = _read_text(sys_dir / "actions")
    chip_name = _read_text(sys_dir / "chip_name")
    hwirq = _read_text(sys_dir / "hwirq")
    irq_name = _read_text(sys_dir / "name")
    irq_type = _read_text(sys_dir / "type")
    wakeup = _read_text(sys_dir / "wakeup")
    per_cpu_count = _read_text(sys_dir / "per_cpu_count")

    configured_mask = _read_text(proc_dir / "smp_affinity")
    configured_list = _read_text(proc_dir / "smp_affinity_list")
    effective_mask = _read_text(proc_dir / "effective_affinity")
    effective_list = _read_text(proc_dir / "effective_affinity_list")
    irq_node = _read_text(proc_dir / "node")
    spurious = _parse_spurious(proc_dir / "spurious")

    return {
        "actions": actions,
        "chip_name": chip_name,
        "hwirq": hwirq,
        "irq_name": irq_name,
        "irq_type": irq_type,
        "wakeup": wakeup,
        "sys_per_cpu_count": per_cpu_count,
        "configured_affinity_mask": configured_mask,
        "configured_affinity": configured_list,
        "effective_affinity_mask": effective_mask,
        "effective_affinity": effective_list,
        "irq_node": irq_node,
        "spurious_count": spurious.get("count", ""),
        "unhandled_count": spurious.get("unhandled", ""),
        "last_unhandled": spurious.get("last_unhandled", ""),
        "pci_context": list(pci_map.get(irq, [])),
    }


def _descriptor_for_numeric(remainder, context):
    action = str(context.get("actions", "") or "").strip()
    source = action or ""
    descriptor = str(remainder or "").strip()

    # /proc/interrupts generally reports controller/type followed by an action.
    # If sysfs supplies the action, remove only an exact suffix; otherwise retain
    # the complete descriptor and use a conservative last-field fallback.
    type_text = ""
    if source and descriptor.endswith(source):
        type_text = descriptor[: -len(source)].strip()
    elif descriptor:
        parts = descriptor.split()
        if len(parts) >= 2:
            source = parts[-1]
            type_text = " ".join(parts[:-1])
        else:
            source = descriptor

    chip = str(context.get("chip_name", "") or "").strip()
    irq_name = str(context.get("irq_name", "") or "").strip()
    irq_type = str(context.get("irq_type", "") or "").strip()
    native_type = " / ".join(x for x in (chip, irq_name or irq_type) if x)
    if native_type:
        type_text = native_type
    if not type_text:
        type_text = "Kernel IRQ"
    if not source:
        source = "Not reported"
    return type_text, source


def collect_interrupts(proc_path="/proc/interrupts"):
    path = Path(proc_path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return {"available": False, "error": "Source is not present.", "cpus": [], "records": []}
    except PermissionError:
        return {"available": False, "error": "Permission denied reading the source.", "cpus": [], "records": []}
    except OSError as exc:
        return {"available": False, "error": str(exc), "cpus": [], "records": []}

    lines = text.splitlines()
    if not lines:
        return {"available": True, "error": "", "cpus": [], "records": []}

    header_index = None
    cpus = []
    for index, line in enumerate(lines):
        matches = re.findall(r"\bCPU(\d+)\b", line)
        if matches:
            cpus = [int(value) for value in matches]
            header_index = index
            break
    if header_index is None:
        return {"available": False, "error": "CPU header was not found in /proc/interrupts.", "cpus": [], "records": []}

    pci_map = _pci_context_map()
    records = []
    malformed = 0
    for line in lines[header_index + 1:]:
        if not line.strip() or ":" not in line:
            continue
        label_part, payload = line.split(":", 1)
        label = label_part.strip()
        tokens = payload.split()
        numeric_irq = _parse_int(label)

        # Numeric IRQ rows are per-CPU vectors and should contain one count per
        # header CPU. Some kernel summary rows (notably ERR/MIS on x86) expose
        # one global counter instead; retain those rather than treating them as
        # malformed interrupt records.
        counts = []
        consumed = 0
        if numeric_irq is not None:
            if len(tokens) < len(cpus):
                malformed += 1
                continue
            try:
                counts = [int(token, 10) for token in tokens[:len(cpus)]]
            except ValueError:
                malformed += 1
                continue
            consumed = len(cpus)
            cpu_counts = {cpu: counts[i] for i, cpu in enumerate(cpus)}
            distribution_scope = "Per CPU"
        else:
            for token in tokens:
                try:
                    counts.append(int(token, 10))
                    consumed += 1
                except ValueError:
                    break
            if not counts:
                malformed += 1
                continue
            if len(counts) == len(cpus):
                cpu_counts = {cpu: counts[i] for i, cpu in enumerate(cpus)}
                distribution_scope = "Per CPU"
            else:
                cpu_counts = {}
                distribution_scope = "Global"

        remainder = " ".join(tokens[consumed:]).strip()
        total = sum(counts)
        active_cpu_list = [cpu for cpu, count in cpu_counts.items() if count > 0]

        if numeric_irq is not None:
            context = _irq_context(numeric_irq, pci_map)
            type_text, source = _descriptor_for_numeric(remainder, context)
            configured_affinity = context.get("configured_affinity") or "Not reported"
            effective_affinity = context.get("effective_affinity") or "Not reported"
            record = {
                "irq": str(numeric_irq),
                "irq_number": numeric_irq,
                "kind": "IRQ",
                "type": type_text,
                "source": source,
                "total": total,
                "configured_affinity": configured_affinity,
                "effective_affinity": effective_affinity,
                "raw_descriptor": remainder or "Not reported",
                "cpu_counts": cpu_counts,
                "active_cpus": ", ".join(str(cpu) for cpu in active_cpu_list) if active_cpu_list else "None",
                "active_cpu_count": len(active_cpu_list),
                "distribution_scope": distribution_scope,
                **context,
            }
        else:
            # Kernel summary vectors such as NMI, LOC, ERR, MIS, etc. are part
            # of /proc/interrupts but do not represent configurable numeric IRQs.
            record = {
                "irq": label,
                "irq_number": None,
                "kind": "Kernel vector",
                "type": "Kernel vector",
                "source": remainder or "Not reported",
                "total": total,
                "configured_affinity": "Not applicable",
                "effective_affinity": "Not applicable",
                "raw_descriptor": remainder or "Not reported",
                "cpu_counts": cpu_counts,
                "active_cpus": ", ".join(str(cpu) for cpu in active_cpu_list) if active_cpu_list else "None",
                "active_cpu_count": len(active_cpu_list),
                "distribution_scope": distribution_scope,
                "actions": "",
                "chip_name": "",
                "hwirq": "",
                "irq_name": "",
                "irq_type": "",
                "wakeup": "",
                "sys_per_cpu_count": "",
                "configured_affinity_mask": "",
                "effective_affinity_mask": "",
                "irq_node": "",
                "spurious_count": "",
                "unhandled_count": "",
                "last_unhandled": "",
                "pci_context": [],
            }
        record["_filter_values"] = ["Active" if total > 0 else "Zero-count"]
        records.append(record)

    def sort_key(record):
        number = record.get("irq_number")
        return (0, number) if isinstance(number, int) else (1, str(record.get("irq", "")).lower())
    records.sort(key=sort_key)
    return {
        "available": True,
        "error": "",
        "cpus": cpus,
        "records": records,
        "malformed_lines": malformed,
    }


def collect_softirqs(proc_path="/proc/softirqs"):
    path = Path(proc_path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return {"available": False, "error": "Source is not present.", "cpus": [], "records": []}
    except PermissionError:
        return {"available": False, "error": "Permission denied reading the source.", "cpus": [], "records": []}
    except OSError as exc:
        return {"available": False, "error": str(exc), "cpus": [], "records": []}

    lines = text.splitlines()
    if not lines:
        return {"available": True, "error": "", "cpus": [], "records": []}

    header_index = None
    cpus = []
    for index, line in enumerate(lines):
        matches = re.findall(r"\bCPU(\d+)\b", line)
        if matches:
            cpus = [int(value) for value in matches]
            header_index = index
            break
    if header_index is None:
        return {"available": False, "error": "CPU header was not found in /proc/softirqs.", "cpus": [], "records": []}

    records = []
    malformed = 0
    for line in lines[header_index + 1:]:
        if not line.strip() or ":" not in line:
            continue
        class_part, payload = line.split(":", 1)
        irq_class = class_part.strip()
        tokens = payload.split()
        if len(tokens) < len(cpus):
            malformed += 1
            continue
        counts = []
        try:
            counts = [int(token, 10) for token in tokens[:len(cpus)]]
        except ValueError:
            malformed += 1
            continue
        cpu_counts = {cpu: counts[i] for i, cpu in enumerate(cpus)}
        total = sum(counts)
        active = [cpu for cpu, value in cpu_counts.items() if value > 0]
        records.append({
            "class": irq_class,
            "total": total,
            "active_cpus": ", ".join(str(cpu) for cpu in active) if active else "None",
            "active_cpu_count": len(active),
            "cpu_counts": cpu_counts,
            "_filter_values": ["Active" if total > 0 else "Zero-count"],
        })

    return {
        "available": True,
        "error": "",
        "cpus": cpus,
        "records": records,
        "malformed_lines": malformed,
    }
