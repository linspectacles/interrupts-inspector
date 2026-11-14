# Interrupts Inspector

**Expose. Explore. Explain.**

Interrupts Inspector is a read-only view of the running kernel’s hardware interrupt routing and SoftIRQ deferred-work counters, with per-CPU distribution and optional kernel/device context.

Current release: **0.0.7**

Repository: <https://github.com/linspectacles/interrupts-inspector>

<p align="center">
  <a href="https://github.com/brunonlinespace/brunonlinespace/blob/main/linspectacles/interrupts-inspector.png">
    <img
      src="https://raw.githubusercontent.com/brunonlinespace/brunonlinespace/main/linspectacles/interrupts-inspector.png"
      alt="Interrupts Inspector screenshot"
      width="900"
    >
  </a>
</p>

## What Interrupts Inspector is

Interrupts Inspector presents the cumulative interrupt state already reported by the running kernel. It keeps hardware IRQ delivery and SoftIRQ deferred work as separate views and enriches IRQ records only when additional procfs/sysfs context is available.

The applet is point-in-time: counters change only when Refresh is requested. It does not turn cumulative counters into invented rates.

## Highlights

- **Interrupts** view based on `/proc/interrupts`.
- **SoftIRQs** view based on `/proc/softirqs`.
- Per-CPU cumulative counts and total delivery counts.
- Configured and effective IRQ affinity where the kernel exposes it.
- Kernel IRQ actions, chip, hardware IRQ, type, wakeup and spurious context where available.
- Optional PCI MSI/MSI-X device context for numeric IRQs.
- Search and view-specific filters with persistent sorting/column state.
- Metadata Details keeps source and contextual data separate from the main inventory.
- Plain Text, CSV, JSON and Markdown export through Options.
- No background sampling, rate calculation or interrupt-control operations.

## Views

### Interrupts

The inventory includes IRQ, type/source, cumulative total and configured/effective affinity. Numeric IRQs can be enriched from `/proc/irq/<irq>` and `/sys/kernel/irq/<irq>` without making those optional sources prerequisites for the `/proc/interrupts` record itself.

Where a PCI device exposes the IRQ through MSI/MSI-X sysfs state, Metadata Details can add device identifiers, driver/NUMA context and network-interface relationships where present.

### SoftIRQs

Shows SoftIRQ classes, cumulative total, number of CPUs with activity and the CPU list derived from `/proc/softirqs`.

## Data sources

Primary and optional sources include:

- `/proc/interrupts`
- `/proc/softirqs`
- `/proc/irq/<irq>/smp_affinity[_list]`
- `/proc/irq/<irq>/effective_affinity[_list]`
- `/proc/irq/<irq>/node` and `/proc/irq/<irq>/spurious`
- `/sys/kernel/irq/<irq>/*` read-only metadata where present
- `/sys/bus/pci/devices/<address>/msi_irqs/<irq>` and selected PCI device attributes where present

## Interface and export

The View selector switches between Interrupts and SoftIRQs. Refresh updates only the active inventory; Options provides Appearance, Sources, Export and About. Export can include selected views without starting a new acquisition.

## Read-only guarantees

Interrupts Inspector does not modify affinity or IRQ settings, integrate with `irqbalance`, parse the journal or kernel log, load eBPF, use perf/tracing, escalate privileges or perform background sampling.

## Useful keyboard shortcuts

| Command | Shortcut |
| --- | --- |
| Show / hide Metadata Details | `F3` |
| Toggle Horizontal / Vertical details layout | `Ctrl+L` |
| Refresh active inventory / snapshot | `Shift+F5` |
| Options | `Ctrl+/` |

The in-application interface remains authoritative for context-specific actions that do not have a global shortcut.

## Running from source

The current source is directly runnable on Linux. Runtime requirements are deliberately kept separate from distribution packaging:

- Python 3.
- PyQt6 for the graphical interface.
- Linux with procfs; optional sysfs IRQ/PCI context is used only when exposed.

A local virtual environment is a straightforward way to run the applet without installing its Python GUI dependency into the system Python environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install PyQt6
python3 linspectacles_interrupts_inspector/standalone.py
```

If PyQt6 is already provided by the Python environment you intend to use, the virtual-environment step is optional.

The standalone launcher is the canonical direct source entrypoint in this source package.

## LinSpectacles Hub

This applet can run independently, but it can also be installed and used inside **[LinSpectacles Hub](https://github.com/linspectacles/linspectacles-hub)**.

LinSpectacles Hub is the optional workbench for the LinSpectacles applet family. It provides shared applet discovery, navigation and management while each inspector remains independently runnable.

To install a portable or user applet through the Hub, open **Configuration... → Applets** and add the applet ZIP. Once discovered, the applet can be enabled and opened from the Hub navigation.

System-installed applets are discovered by the Hub from its system applet store and remain managed by the system package manager.

## Source layout and LinSpectacles integration

The applet source is contained in:

```text
linspectacles_interrupts_inspector/
├── __init__.py
├── standalone.py
├── LICENSE
├── applet.json
├── README.md
└── interrupts_inspector/
    ├── __init__.py
    ├── applet.py
    ├── _support.py
    ├── interrupts_data.py
    └── icon.png
```

`applet.json` provides the LinSpectacles applet identity and entrypoint metadata, while `create_applet()` in `applet.py` provides the host-loadable widget factory. `standalone.py` launches the same applet as an independent window.

## Configuration

UI preferences are stored through Qt `QSettings` under the `brunonlinespace` organisation and the applet’s application name. The exact persisted presentation fields depend on the applet, but are limited to UI/inspection presentation state such as view/filter choices, columns, sorting, splitter/layout state and Metadata Details where implemented.

The applet does not use configuration persistence as a path to modify the inspected Linux subsystem.

## Scope

Interrupts Inspector owns IRQ and SoftIRQ inspection. Scheduler state, device topology, kernel logging and live performance-rate analysis remain separate LinSpectacles domains.

## License

GNU General Public License v3.0 or later. See [`LICENSE`](LICENSE).

## Links

- LinSpectacles organisation: <https://github.com/linspectacles/>
- LinSpectacles Hub: <https://github.com/linspectacles/linspectacles-hub>
- Repository: <https://github.com/linspectacles/interrupts-inspector>
- Issues: <https://github.com/linspectacles/interrupts-inspector/issues>

<p align="center">
  <a href="https://github.com/linspectacles/interrupts-inspector">
    <img
      src="interrupts_inspector/icon.png"
      alt="Interrupts Inspector"
      width="256"
    >
  </a>
</p>
