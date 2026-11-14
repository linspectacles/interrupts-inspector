#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# LinSpectacles - Linux Inspection Suite
# Copyright (C) 2026 brunonlinespace
# GPL-3.0-or-later

APPLET_ID = "linspectacles-interrupts-inspector"
APPLET_NAME = "Interrupts Inspector"
APPLET_VERSION = "0.0.7"
APPLET_AUTHOR = "brunonlinespace"
APPLET_EDITOR = "brunonlinespace"
APPLET_PUBLISHER = "brunonlinespace"
APPLET_ORGANIZATION_ID = "linspectacles"
APPLET_ORGANIZATION_URL = "https://github.com/linspectacles/"
APPLET_REPOSITORY = "https://github.com/linspectacles/interrupts-inspector"

from pathlib import Path
from datetime import datetime
import json

from PyQt6.QtCore import QSettings, Qt, QUrl
from PyQt6.QtGui import QColor, QKeySequence, QPixmap, QShortcut, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ._support import BaseInspectorTab, export_records_dialog, metadata_font_qss
from .interrupts_data import collect_interrupts, collect_softirqs


_VIEW_ORDER = ("interrupts", "softirqs")
_VIEW_SPECS = {
    "interrupts": {
        "label": "Interrupts",
        "counter": "Total Interrupt Records",
        "columns": [
            ("irq", "IRQ", 85, "right"),
            ("type", "Type", 185, "left"),
            ("source", "Source", 260, "left"),
            ("total", "Total", 120, "right"),
            ("configured_affinity", "Configured Affinity", 160, "left"),
            ("effective_affinity", "Effective Affinity", 160, "left"),
        ],
        "numeric": {"total"},
    },
    "softirqs": {
        "label": "SoftIRQs",
        "counter": "Total SoftIRQ Classes",
        "columns": [
            ("class", "Class", 150, "left"),
            ("total", "Total", 150, "right"),
            ("active_cpu_count", "Active CPUs", 110, "right"),
            ("active_cpus", "CPU List", 260, "left"),
        ],
        "numeric": {"total", "active_cpu_count"},
    },
}


def _detail_canvas(owner):
    widget = QTextEdit()
    widget.setReadOnly(True)
    widget.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
    font = getattr(owner, "_metadata_font", None)
    font_rule = metadata_font_qss(font) if font is not None else ""
    if font is not None:
        widget.setFont(font)
        widget.document().setDefaultFont(font)
        widget.setCurrentFont(font)
    widget.setStyleSheet(
        "QTextEdit { "
        f"{font_rule} "
        "background-color: #151719; color: #dcdcdc; border: 1px solid #333333; "
        "}"
    )
    return widget


def _formats():
    key = QTextCharFormat()
    key.setForeground(QColor("#9cdcfe"))
    key.setFontWeight(600)
    value = QTextCharFormat()
    value.setForeground(QColor("#dcdcdc"))
    return key, value


def _append_heading(widget, text):
    key, value = _formats()
    cursor = widget.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    if cursor.position() > 0:
        cursor.insertText("\n", value)
    cursor.insertText(str(text) + "\n", key)
    widget.setTextCursor(cursor)


def _append_property(widget, key_text, value_text):
    key, value = _formats()
    cursor = widget.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(f"{key_text}: ", key)
    cursor.insertText(str(value_text if value_text not in (None, "") else "Not reported") + "\n", value)
    widget.setTextCursor(cursor)


def _populate_sources(widget):
    widget.clear()
    groups = [
        (
            "Primary Interrupt Inventory",
            [
                "/proc/interrupts",
                "Cumulative interrupt vectors and per-CPU counts reported by the running kernel.",
            ],
        ),
        (
            "Primary SoftIRQ Inventory",
            [
                "/proc/softirqs",
                "Cumulative deferred interrupt-work classes and per-CPU counts.",
            ],
        ),
        (
            "IRQ Affinity",
            [
                "/proc/irq/<irq>/smp_affinity[_list]",
                "/proc/irq/<irq>/effective_affinity[_list]",
                "Configured and effective CPU routing for numeric IRQs where exposed.",
            ],
        ),
        (
            "Optional IRQ Context",
            [
                "/sys/kernel/irq/<irq>/actions",
                "/sys/kernel/irq/<irq>/chip_name",
                "/sys/kernel/irq/<irq>/hwirq",
                "/sys/kernel/irq/<irq>/name",
                "/sys/kernel/irq/<irq>/type",
                "/sys/kernel/irq/<irq>/wakeup",
                "/sys/kernel/irq/<irq>/per_cpu_count",
                "/proc/irq/<irq>/node",
                "/proc/irq/<irq>/spurious",
                "These sources enrich a record only when present; their absence never invalidates /proc/interrupts.",
            ],
        ),
        (
            "Optional Device Context",
            [
                "/sys/bus/pci/devices/<address>/msi_irqs/<irq>",
                "/sys/bus/pci/devices/<address>/{vendor,device,class,numa_node,driver}",
                "/sys/bus/pci/devices/<address>/net/*",
                "MSI/MSI-X IRQs may be associated with a PCI function, driver and network-interface name without invoking lspci.",
            ],
        ),
        (
            "Boundaries",
            [
                "All counters are cumulative snapshots; Interrupts Inspector does not calculate rates in 0.0.7.",
                "No irqbalance, lspci, perf, tracefs, eBPF, dmesg or journal source is used.",
                "The applet never writes IRQ affinity or any other kernel setting.",
            ],
        ),
    ]
    for heading, lines in groups:
        _append_heading(widget, heading)
        for line in lines:
            _append_property(widget, "Source" if line.startswith("/") else "Note", line)
    cursor = widget.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    widget.setTextCursor(cursor)
    widget.verticalScrollBar().setValue(0)


class InterruptsOptionsDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("Options — Interrupts Inspector")
        self.resize(940, 690)

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        configuration = QWidget()
        layout = QVBoxLayout(configuration)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        inventory_heading = QLabel("Inventory")
        inventory_font = inventory_heading.font(); inventory_font.setBold(True); inventory_heading.setFont(inventory_font)
        layout.addWidget(inventory_heading)
        inventory_note = QLabel("Choose which interrupt inventory is displayed. Ctrl+I switches between Interrupts and SoftIRQs.")
        inventory_note.setWordWrap(True); layout.addWidget(inventory_note)
        inventory_row = QHBoxLayout()
        self.interrupts_inventory = QRadioButton("Interrupts")
        self.softirqs_inventory = QRadioButton("SoftIRQs")
        if owner._current_view == "softirqs":
            self.softirqs_inventory.setChecked(True)
        else:
            self.interrupts_inventory.setChecked(True)
        self.interrupts_inventory.toggled.connect(lambda checked: checked and owner.select_inventory("interrupts"))
        self.softirqs_inventory.toggled.connect(lambda checked: checked and owner.select_inventory("softirqs"))
        inventory_row.addWidget(self.interrupts_inventory)
        inventory_row.addWidget(self.softirqs_inventory)
        inventory_row.addStretch(1)
        inventory_row.addWidget(QLabel("Ctrl+I"))
        layout.addLayout(inventory_row)

        heading = QLabel("Record details")
        font = heading.font(); font.setBold(True); heading.setFont(font)
        layout.addWidget(heading)
        note = QLabel("Choose how the interrupt inventory and Metadata Details are arranged.")
        note.setWordWrap(True); layout.addWidget(note)
        row = QHBoxLayout(); row.addWidget(QLabel("Record details layout:"))
        self.orientation = QComboBox(); self.orientation.addItems(["Horizontal", "Vertical"])
        self.orientation.setCurrentText(owner.details_orientation.title())
        self.orientation.currentTextChanged.connect(lambda text: owner.set_details_orientation(str(text).lower(), persist=True))
        row.addWidget(self.orientation); row.addStretch(1); layout.addLayout(row)
        self.show_metadata = QCheckBox("Show Metadata Details panel (F3)")
        self.show_metadata.setChecked(owner.metadata_panel_visible)
        self.show_metadata.toggled.connect(lambda checked: owner.set_metadata_panel_visible(bool(checked), persist=True))
        layout.addWidget(self.show_metadata)
        shortcuts = QLabel(
            "Shortcuts: Ctrl+I switches inventory; F3 hides/restores Metadata Details; "
            "Shift+F5 refreshes the active inventory; Ctrl+L toggles Horizontal/Vertical; Ctrl+/ opens Options."
        )
        shortcuts.setWordWrap(True); layout.addWidget(shortcuts); layout.addStretch(1)
        tabs.addTab(configuration, "Configuration")

        sources = QWidget(); sources_layout = QVBoxLayout(sources)
        sources_layout.setContentsMargins(12, 12, 12, 12); sources_layout.setSpacing(10)
        sources_heading = QLabel("Data Sources")
        sources_font = sources_heading.font(); sources_font.setBold(True); sources_font.setPointSize(max(11, sources_font.pointSize())); sources_heading.setFont(sources_font)
        sources_layout.addWidget(sources_heading)
        sources_note = QLabel("Direct Linux interfaces used by this read-only interrupt inspector. Context sources are optional enrichment.")
        sources_note.setWordWrap(True); sources_layout.addWidget(sources_note)
        self.sources_text = _detail_canvas(owner); _populate_sources(self.sources_text)
        sources_layout.addWidget(self.sources_text, 1)
        tabs.addTab(sources, "Sources")

        export = QWidget(); export_layout = QVBoxLayout(export)
        export_layout.setContentsMargins(12, 12, 12, 12); export_layout.setSpacing(10)
        export_heading = QLabel("Export")
        export_font = export_heading.font(); export_font.setBold(True); export_heading.setFont(export_font)
        export_layout.addWidget(export_heading)
        export_note = QLabel("Export uses data already collected in this session; unopened views are not scanned in the background.")
        export_note.setWordWrap(True); export_layout.addWidget(export_note)
        self.export_checks = {}
        for key in _VIEW_ORDER:
            checkbox = QCheckBox(_VIEW_SPECS[key]["label"]); checkbox.setChecked(True)
            self.export_checks[key] = checkbox; export_layout.addWidget(checkbox)
        self.export_metadata = QCheckBox("Metadata Details"); export_layout.addWidget(self.export_metadata)
        export_layout.addStretch(1)
        export_row = QHBoxLayout(); export_row.addStretch(1)
        export_button = QPushButton("Export Selected Views...")
        export_button.clicked.connect(self._export); export_row.addWidget(export_button); export_layout.addLayout(export_row)
        tabs.addTab(export, "Export")

        # About — follows the Kernel Modules applet authority, with LinSpectacles identity.
        about = QWidget()
        about_layout = QVBoxLayout(about)
        about_layout.setContentsMargins(24, 20, 24, 18)
        about_layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(112, 112)
        icon_path = Path(__file__).resolve().parent / "icon.png"
        if icon_path.is_file():
            pix = QPixmap(str(icon_path))
            if not pix.isNull():
                icon_label.setPixmap(
                    pix.scaled(
                        112,
                        112,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        about_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        name = QLabel("<h2 style='margin:0'>Interrupts Inspector</h2>")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(name)

        version = QLabel(f"Version {APPLET_VERSION}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(version)

        slogan = QLabel("<b>Expose. Explore. Explain.</b>")
        slogan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(slogan)

        desc = QLabel(
            "A read-only LinSpectacles applet for inspecting hardware interrupt delivery, "
            "IRQ affinity and deferred SoftIRQ work across CPUs."
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(desc)

        details = QLabel(
            "<b>Build:</b> Standalone LinSpectacles applet<br>"
            "<b>Organisation ID:</b> "
            f"<a href='{APPLET_ORGANIZATION_URL}'>{APPLET_ORGANIZATION_ID}</a><br>"
            f"<b>Applet ID:</b> {APPLET_ID}"
        )
        details.setWordWrap(True)
        details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
            | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        details.setOpenExternalLinks(True)
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(details)

        copyright_label = QLabel(
            "Copyright © 2026 "
            "<a href='https://github.com/brunonlinespace'>brunonlinespace</a>"
        )
        copyright_label.setOpenExternalLinks(True)
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(copyright_label)

        license_label = QLabel("Licensed under GNU GPLv3 or later.")
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(license_label)

        readme_url = QUrl.fromLocalFile(
            str(Path(__file__).resolve().parent.parent / "README.md")
        ).toString()
        license_url = QUrl.fromLocalFile(
            str(Path(__file__).resolve().parent.parent / "LICENSE")
        ).toString()
        links = QLabel(
            f"<a href='{readme_url}'>README</a> "
            "&nbsp;·&nbsp; "
            f"<a href='{license_url}'>License</a> "
            "&nbsp;·&nbsp; "
            f"<a href='{APPLET_REPOSITORY}'>Repository</a>"
        )
        links.setOpenExternalLinks(True)
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(links)
        about_layout.addStretch(1)
        tabs.addTab(about, "About")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject); root.addWidget(buttons)

    def _export(self):
        selected = [key for key, checkbox in self.export_checks.items() if checkbox.isChecked()]
        self.owner.export_selected_views(selected, include_metadata=self.export_metadata.isChecked(), parent=self)


class InterruptsInspectorTab(BaseInspectorTab):
    NUMERIC_COLUMNS = {"total"}
    BYTE_COLUMNS = set()

    def __init__(self, parent=None):
        spec = _VIEW_SPECS["interrupts"]
        super().__init__(spec["counter"], spec["columns"], ["All", "Active", "Zero-count"], parent)
        self.export_title = APPLET_NAME
        self._settings = QSettings("brunonlinespace", "Interrupts Inspector")
        self._datasets = {key: [] for key in _VIEW_ORDER}
        self._snapshots = {key: None for key in _VIEW_ORDER}
        self._loaded_views = set()
        self._current_view = "interrupts"
        self._status_filters = {key: "All" for key in _VIEW_ORDER}
        self._column_widths = {key: None for key in _VIEW_ORDER}
        self._sort_state = {key: {"column": "", "descending": False} for key in _VIEW_ORDER}
        self._restoring_view_state = False
        self._host_column_callback = None
        self._host_hidden_all = set()

        self.refresh_btn.setText("Refresh")
        self.export_btn.setText("Options...")
        try:
            self.export_btn.clicked.disconnect()
        except TypeError:
            pass
        self.export_btn.clicked.connect(self.show_options)
        self.export_btn.setEnabled(True)

        self.details_orientation = "horizontal"
        self.metadata_panel_visible = True
        self._load_ui_state()
        self._install_shortcuts()
        self.category_dropdown.currentTextChanged.connect(self._status_filter_changed)
        self.table.horizontalHeader().sectionResized.connect(self._column_resized)

        self._configure_view(self._current_view, refresh=False)
        self.load_modules()

    def apply_host_settings(self, settings=None, column_visibility_callback=None):
        settings = settings or {}
        super().apply_host_settings({"metadata_font": settings.get("metadata_font", ""), "hidden_columns": []}, None)
        self._host_column_callback = column_visibility_callback if callable(column_visibility_callback) else None
        self._host_hidden_all = {str(item) for item in settings.get("hidden_columns", [])}
        self.column_visibility.set_changed_callback(self._column_visibility_changed)
        self._apply_view_hidden_columns()

    def _view_prefix(self, view=None):
        return str(view or self._current_view)

    def _visibility_columns(self):
        prefix = self._view_prefix()
        return [(f"{prefix}:{cid}", label, width, align) for cid, label, width, align in self.columns]

    def _apply_view_hidden_columns(self):
        if not hasattr(self, "column_visibility"):
            return
        self.column_visibility.columns = self._visibility_columns()
        prefix = self._view_prefix() + ":"
        current = [item for item in self._host_hidden_all if item.startswith(prefix)]
        self.column_visibility.apply_hidden(current)

    def _column_visibility_changed(self, hidden_current):
        prefix = self._view_prefix() + ":"
        self._host_hidden_all = {item for item in self._host_hidden_all if not item.startswith(prefix)}
        self._host_hidden_all.update(str(item) for item in hidden_current)
        if callable(self._host_column_callback):
            self._host_column_callback(sorted(self._host_hidden_all))

    def _install_shortcuts(self):
        self._metadata_shortcut = QShortcut(QKeySequence("F3"), self)
        self._metadata_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._metadata_shortcut.activated.connect(self.toggle_metadata_panel)
        self._layout_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        self._layout_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._layout_shortcut.activated.connect(self.toggle_details_orientation)
        self._inventory_shortcut = QShortcut(QKeySequence("Ctrl+I"), self)
        self._inventory_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._inventory_shortcut.activated.connect(self.toggle_inventory)
        self._refresh_shortcut = QShortcut(QKeySequence("Shift+F5"), self)
        self._refresh_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._refresh_shortcut.activated.connect(self.load_modules)
        self._options_shortcut = QShortcut(QKeySequence("Ctrl+/"), self)
        self._options_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._options_shortcut.activated.connect(self.show_options)

    def _load_ui_state(self):
        orientation = str(self._settings.value("details_orientation", "horizontal") or "horizontal").lower()
        self.set_details_orientation(orientation if orientation in {"horizontal", "vertical"} else "horizontal", persist=False)
        visible = self._settings.value("metadata_panel_visible", True)
        if isinstance(visible, str):
            visible = visible.strip().lower() not in {"0", "false", "no", "off"}
        self.set_metadata_panel_visible(bool(visible), persist=False)

        active_view = str(self._settings.value("active_view", "interrupts") or "interrupts").lower()
        self._current_view = active_view if active_view in _VIEW_SPECS else "interrupts"

        for key in _VIEW_ORDER:
            status = str(self._settings.value(f"views/{key}/status_filter", "All") or "All")
            self._status_filters[key] = status if status in {"All", "Active", "Zero-count"} else "All"

            raw_widths = self._settings.value(f"views/{key}/column_widths", "")
            widths = None
            if raw_widths not in (None, ""):
                try:
                    candidate = json.loads(str(raw_widths))
                    if isinstance(candidate, list) and len(candidate) == len(_VIEW_SPECS[key]["columns"]):
                        parsed = [max(24, int(value)) for value in candidate]
                        widths = parsed
                except (TypeError, ValueError, json.JSONDecodeError):
                    widths = None
            self._column_widths[key] = widths

            column = str(self._settings.value(f"views/{key}/sort_column", "") or "")
            valid_columns = {item[0] for item in _VIEW_SPECS[key]["columns"]}
            if column not in valid_columns:
                column = ""
            descending = self._settings.value(f"views/{key}/sort_descending", False)
            if isinstance(descending, str):
                descending = descending.strip().lower() in {"1", "true", "yes", "on"}
            self._sort_state[key] = {"column": column, "descending": bool(descending)}

    def _persist_view_state(self, key=None):
        key = str(key or self._current_view)
        if key not in _VIEW_SPECS:
            return
        self._settings.setValue("active_view", self._current_view)
        self._settings.setValue(f"views/{key}/status_filter", self._status_filters.get(key, "All"))
        widths = self._column_widths.get(key)
        if widths:
            self._settings.setValue(f"views/{key}/column_widths", json.dumps(widths))
        state = self._sort_state.get(key, {})
        self._settings.setValue(f"views/{key}/sort_column", state.get("column", ""))
        self._settings.setValue(f"views/{key}/sort_descending", bool(state.get("descending", False)))
        self._settings.sync()

    def _capture_column_widths(self, key=None):
        key = str(key or self._current_view)
        if key not in _VIEW_SPECS or self.table.columnCount() != len(_VIEW_SPECS[key]["columns"]):
            return
        self._column_widths[key] = [self.table.columnWidth(index) for index in range(self.table.columnCount())]

    def _column_resized(self, logical_index, old_size, new_size):
        if self._restoring_view_state or logical_index < 0:
            return
        self._capture_column_widths(self._current_view)
        self._persist_view_state(self._current_view)

    def _status_filter_changed(self, text):
        text = str(text or "All")
        if text not in {"All", "Active", "Zero-count"}:
            text = "All"
        self._status_filters[self._current_view] = text
        if not self._restoring_view_state:
            self._persist_view_state(self._current_view)

    def _apply_persisted_sort(self, view, records):
        state = self._sort_state.get(view, {})
        column = state.get("column", "")
        if not column:
            return list(records)
        valid_columns = {item[0] for item in _VIEW_SPECS[view]["columns"]}
        if column not in valid_columns:
            return list(records)
        numeric = column in _VIEW_SPECS[view]["numeric"]
        def key_func(record):
            value = record.get(column, "")
            if numeric:
                try:
                    return int(value or 0)
                except (TypeError, ValueError):
                    return 0
            return str(value).lower()
        try:
            return sorted(records, key=key_func, reverse=bool(state.get("descending", False)))
        except Exception:
            return list(records)

    def _update_sort_indicator(self, view):
        header = self.table.horizontalHeader()
        state = self._sort_state.get(view, {})
        column = state.get("column", "")
        ids = [item[0] for item in _VIEW_SPECS[view]["columns"]]
        if column in ids:
            header.setSortIndicatorShown(True)
            order = Qt.SortOrder.DescendingOrder if state.get("descending", False) else Qt.SortOrder.AscendingOrder
            header.setSortIndicator(ids.index(column), order)
        else:
            header.setSortIndicatorShown(False)

    def sort_by_section(self, section):
        if not (0 <= section < len(self.columns)):
            return
        column = self.columns[section][0]
        state = self._sort_state[self._current_view]
        if state.get("column") == column:
            descending = not bool(state.get("descending", False))
        else:
            descending = False
        self._sort_state[self._current_view] = {"column": column, "descending": descending}
        sorted_records = self._apply_persisted_sort(self._current_view, self._datasets.get(self._current_view, []))
        self._datasets[self._current_view] = sorted_records
        self.modules_data = list(sorted_records)
        self._update_sort_indicator(self._current_view)
        self._persist_view_state(self._current_view)
        self.filter_modules()

    def set_metadata_panel_visible(self, visible, *, persist=True):
        self.metadata_panel_visible = bool(visible)
        panel = self.splitter.widget(1)
        if panel is not None:
            panel.setVisible(self.metadata_panel_visible)
        if persist:
            self._settings.setValue("metadata_panel_visible", self.metadata_panel_visible)
            self._settings.sync()

    def toggle_metadata_panel(self):
        self.set_metadata_panel_visible(not self.metadata_panel_visible, persist=True)

    def set_details_orientation(self, orientation, *, persist=True):
        orientation = str(orientation or "horizontal").lower()
        if orientation not in {"horizontal", "vertical"}:
            orientation = "horizontal"
        self.details_orientation = orientation
        panel = self.splitter.widget(1)
        panel_layout = panel.layout() if panel is not None else None
        if orientation == "vertical":
            self.splitter.setOrientation(Qt.Orientation.Vertical)
            if panel_layout is not None: panel_layout.setContentsMargins(0, 8, 0, 0)
            self.splitter.setSizes([430, 330])
        else:
            self.splitter.setOrientation(Qt.Orientation.Horizontal)
            if panel_layout is not None: panel_layout.setContentsMargins(8, 0, 0, 0)
            self.splitter.setSizes([480, 700])
        if persist:
            self._settings.setValue("details_orientation", orientation); self._settings.sync()

    def toggle_details_orientation(self):
        self.set_details_orientation("vertical" if self.details_orientation == "horizontal" else "horizontal", persist=True)

    def select_inventory(self, key):
        if key not in _VIEW_SPECS or key == self._current_view:
            return
        previous = self._current_view
        self._capture_column_widths(previous)
        self._persist_view_state(previous)
        self._configure_view(key, refresh=False)
        self._settings.setValue("active_view", key)
        self._settings.sync()
        if key not in self._loaded_views:
            self.load_modules()
        else:
            self.modules_data = list(self._datasets[key])
            self.filter_modules()
            self.set_status(f"Showing collected {_VIEW_SPECS[key]['label']} data.")

    def toggle_inventory(self):
        self.select_inventory("softirqs" if self._current_view == "interrupts" else "interrupts")

    def _configure_view(self, key, *, refresh=False):
        if key not in _VIEW_SPECS:
            key = "interrupts"
        self._current_view = key
        spec = _VIEW_SPECS[key]
        self.total_label_text = spec["counter"]
        self.columns = list(spec["columns"])
        self.NUMERIC_COLUMNS = set(spec["numeric"])
        self.stats_label.setText(f"{self.total_label_text}: {len(self._datasets.get(key, []))}")
        self._restoring_view_state = True
        try:
            self.table.setSortingEnabled(False); self.table.clearContents(); self.table.setRowCount(0)
            self.table.setColumnCount(len(self.columns)); self.table.setHorizontalHeaderLabels([col[1] for col in self.columns])
            widths = self._column_widths.get(key)
            for index, (_cid, _label, width, _align) in enumerate(self.columns):
                self.table.setColumnWidth(index, widths[index] if widths and index < len(widths) else width)
            self._apply_view_hidden_columns()
            self.category_label.setText("Status:")
            self.category_dropdown.blockSignals(True)
            self.category_dropdown.clear(); self.category_dropdown.addItems(["All", "Active", "Zero-count"])
            saved_status = self._status_filters.get(key, "All")
            self.category_dropdown.setCurrentText(saved_status if saved_status in {"All", "Active", "Zero-count"} else "All")
            self.category_dropdown.blockSignals(False)
            self._update_sort_indicator(key)
        finally:
            self._restoring_view_state = False
        self.search_entry.setPlaceholderText(f"Search {spec['label'].lower()}...")
        self.clear_info()
        if refresh: self.load_modules()

    def load_modules(self):
        key = self._current_view
        try:
            snapshot = collect_interrupts() if key == "interrupts" else collect_softirqs()
        except Exception as exc:
            self.set_status(f"Failed to read {_VIEW_SPECS[key]['label']}: {exc}")
            return
        snapshot = dict(snapshot)
        snapshot["acquired_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        self._snapshots[key] = snapshot
        if not snapshot.get("available", False):
            self._datasets[key] = []
            self._loaded_views.add(key)
            self.modules_data = []
            self.stats_label.setText(f"{self.total_label_text}: 0")
            self.filter_modules()
            self.set_status(f"{_VIEW_SPECS[key]['label']} unavailable: {snapshot.get('error') or 'source unavailable'}")
            return
        records = self._apply_persisted_sort(key, list(snapshot.get("records", [])))
        self._datasets[key] = records; self._loaded_views.add(key); self.modules_data = list(records)
        self._update_sort_indicator(key)
        self.stats_label.setText(f"{self.total_label_text}: {len(records)}")
        self.filter_modules()
        malformed = int(snapshot.get("malformed_lines", 0) or 0)
        suffix = f" · {malformed} malformed line(s) skipped" if malformed else ""
        self.set_status(f"Refreshed {_VIEW_SPECS[key]['label']}: {len(records)} record(s){suffix}.")

    def filter_modules(self, *_):
        query = self.search_entry.text().strip().lower()
        selected = self.category_dropdown.currentText()
        matches = []
        for record in self.modules_data:
            status = "Active" if int(record.get("total", 0) or 0) > 0 else "Zero-count"
            if selected != "All" and status != selected:
                continue
            if query and not any(query in str(value).lower() for key, value in record.items() if not str(key).startswith("_") and key not in {"cpu_counts", "pci_context"}):
                continue
            matches.append(record)

        blocked = self.table.blockSignals(True)
        try:
            self.clear_info(); self.table.clearSelection(); self.table.setSortingEnabled(False); self.table.setRowCount(len(matches))
            from PyQt6.QtWidgets import QTableWidgetItem
            for row, record in enumerate(matches):
                for col_index, (cid, _label, _width, alignment) in enumerate(self.columns):
                    item = QTableWidgetItem(str(record.get(cid, "")))
                    if col_index == 0: item.setData(Qt.ItemDataRole.UserRole, record)
                    if alignment == "right": item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    else: item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    self.table.setItem(row, col_index, item)
        finally:
            self.table.blockSignals(blocked)

        self.clear_info()
        if matches:
            blocked = self.table.blockSignals(True)
            try:
                self.table.setCurrentCell(0, 0); self.table.selectRow(0)
            finally:
                self.table.blockSignals(blocked)
            self._render_record_details(matches[0], self._current_view)
        else:
            self.table.setCurrentCell(-1, -1)
        cursor = self.info_text.textCursor(); cursor.movePosition(QTextCursor.MoveOperation.Start); self.info_text.setTextCursor(cursor); self.info_text.verticalScrollBar().setValue(0)
        if query or selected != "All": self.filter_status_lbl.setText(f"(Showing {len(matches)} of {len(self.modules_data)} items)")
        else: self.filter_status_lbl.clear()

    def on_module_select(self):
        record = self.current_record()
        if record:
            self._render_record_details(record, self._current_view)
            cursor = self.info_text.textCursor(); cursor.movePosition(QTextCursor.MoveOperation.Start); self.info_text.setTextCursor(cursor); self.info_text.verticalScrollBar().setValue(0)

    def _render_record_details(self, record, view):
        self.clear_info()
        if view == "interrupts": self._render_interrupt_details(record)
        else: self._render_softirq_details(record)

    def _acquired_at(self, view):
        snapshot = self._snapshots.get(view) or {}
        return snapshot.get("acquired_at") or "Not reported"

    def _render_interrupt_details(self, record):
        self.append_info("--- Interrupt ---\n")
        for label, key in (("IRQ", "irq"), ("Kind", "kind"), ("Type", "type"), ("Source / Action", "source"), ("Total Count", "total"), ("Raw Descriptor", "raw_descriptor")):
            self.append_key_value(label, record.get(key, "Not reported"))

        self.append_info("\n--- Affinity ---\n")
        for label, key in (("Configured CPUs", "configured_affinity"), ("Effective CPUs", "effective_affinity"), ("Configured Mask", "configured_affinity_mask"), ("Effective Mask", "effective_affinity_mask"), ("IRQ NUMA Node", "irq_node")):
            self.append_key_value(label, record.get(key) or "Not reported")

        self.append_info("\n--- CPU Distribution ---\n")
        self.append_key_value("Scope", record.get("distribution_scope", "Per CPU"))
        counts = record.get("cpu_counts", {}) or {}
        if counts:
            for cpu in sorted(counts): self.append_key_value(f"CPU {cpu}", counts[cpu])
            self.append_key_value("Active CPUs", record.get("active_cpus", "None"))
        else:
            self.append_info("This kernel reports this interrupt summary as a global counter rather than a per-CPU vector.\n")

        native = any(record.get(key) for key in ("chip_name", "hwirq", "irq_name", "irq_type", "wakeup", "sys_per_cpu_count", "spurious_count", "unhandled_count"))
        if native:
            self.append_info("\n--- IRQ Context ---\n")
            for label, key in (("Chip", "chip_name"), ("Hardware IRQ", "hwirq"), ("Kernel Name", "irq_name"), ("Kernel Type", "irq_type"), ("Wakeup", "wakeup"), ("Kernel Per-CPU Count", "sys_per_cpu_count"), ("Spurious Count", "spurious_count"), ("Unhandled Count", "unhandled_count"), ("Last Unhandled", "last_unhandled")):
                value = record.get(key)
                if value not in (None, ""): self.append_key_value(label, value)

        pci = record.get("pci_context", []) or []
        if pci:
            self.append_info("\n--- Optional Device Context ---\n")
            for index, item in enumerate(pci, 1):
                prefix = f"Device {index}" if len(pci) > 1 else "Device"
                for label, key in (("PCI Address", "pci_address"), ("Vendor ID", "pci_vendor"), ("Device ID", "pci_device"), ("Class", "pci_class"), ("Driver", "driver"), ("NUMA Node", "pci_numa_node"), ("Network Interfaces", "network_interfaces")):
                    self.append_key_value(f"{prefix} {label}", item.get(key, "Not reported"))

        self.append_info("\n--- Source ---\n")
        self.append_key_value("Primary", "/proc/interrupts")
        irq = record.get("irq_number")
        if isinstance(irq, int):
            self.append_key_value("Affinity", f"/proc/irq/{irq}/...")
            self.append_key_value("Optional IRQ Context", f"/sys/kernel/irq/{irq}/...")
        if pci:
            self.append_key_value("Optional Device Context", "/sys/bus/pci/devices/*/msi_irqs/*")
        self.append_key_value("Acquired", self._acquired_at("interrupts"))
        self.append_info("Interpretation note: counts are cumulative kernel counters. A large count is not by itself a problem or a current rate.\n")

    def _render_softirq_details(self, record):
        self.append_info("--- SoftIRQ ---\n")
        self.append_key_value("Class", record.get("class", "Not reported"))
        self.append_key_value("Total Count", record.get("total", 0))
        self.append_key_value("Active CPUs", record.get("active_cpus", "None"))
        self.append_info("\n--- CPU Distribution ---\n")
        counts = record.get("cpu_counts", {}) or {}
        for cpu in sorted(counts): self.append_key_value(f"CPU {cpu}", counts[cpu])
        self.append_info("\n--- Source ---\n")
        self.append_key_value("Primary", "/proc/softirqs")
        self.append_key_value("Acquired", self._acquired_at("softirqs"))
        self.append_info("Interpretation note: counts are cumulative deferred-work counters. Interrupts Inspector does not convert them into rates in this release.\n")

    def show_options(self):
        InterruptsOptionsDialog(self).exec()

    def metadata_details_for_export(self, view, record):
        original = self.info_text
        temporary = QTextEdit(); self.info_text = temporary
        try:
            self._render_record_details(record, view)
            return temporary.toPlainText()
        finally:
            self.info_text = original

    def export_selected_views(self, selected, *, include_metadata=False, parent=None):
        selected = list(selected or [])
        if not selected:
            QMessageBox.information(parent or self, "Export", "Select at least one Interrupts Inspector view to export.")
            return
        flat = []
        for key in _VIEW_ORDER:
            if key not in selected: continue
            spec = _VIEW_SPECS[key]
            records = self._datasets[key] if key in self._loaded_views else []
            if not records:
                flat.append({"view": spec["label"], "record": "", "field": "Status", "value": "No collected data."})
                continue
            for index, record in enumerate(records, 1):
                for cid, label, _width, _align in spec["columns"]:
                    flat.append({"view": spec["label"], "record": str(index), "field": label, "value": record.get(cid, "")})
                if include_metadata:
                    flat.append({"view": spec["label"], "record": str(index), "field": "Metadata Details", "value": self.metadata_details_for_export(key, record)})
        path = export_records_dialog(parent or self, APPLET_NAME, flat, columns=[("view", "View"), ("record", "Record"), ("field", "Field"), ("value", "Value")])
        if path is not None: self.set_status(f"Exported selected Interrupts Inspector views to {path}")


def create_applet(parent=None):
    return InterruptsInspectorTab(parent=parent)


def run_standalone():
    import sys
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication, QMainWindow
    from ._support import STANDALONE_STYLESHEET

    app = QApplication(sys.argv); app.setApplicationName(APPLET_NAME); app.setOrganizationName(APPLET_AUTHOR); app.setStyleSheet(STANDALONE_STYLESHEET)
    icon_path = Path(__file__).resolve().parent / "icon.png"
    if icon_path.is_file(): app.setWindowIcon(QIcon(str(icon_path)))
    window = QMainWindow(); window.setWindowTitle(f"{APPLET_NAME} {APPLET_VERSION} — LinSpectacles Applet")
    if icon_path.is_file(): window.setWindowIcon(QIcon(str(icon_path)))
    window.setCentralWidget(create_applet()); window.resize(1260, 760); window.show()
    return app.exec()
