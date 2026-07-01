from __future__ import annotations

import html
import math
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple, Union

import pandas as pd
import streamlit as st


# ============================================================
# 1. ENGINE
# ============================================================


@dataclass
class Feature:
    name: str
    own_tolerance: float
    source_part_name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class Part:
    name: str
    features: List[Feature] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def add_feature(self, name: str, tolerance: float) -> Feature:
        feat = Feature(name=name, own_tolerance=tolerance, source_part_name=self.name)
        self.features.append(feat)
        return feat


@dataclass
class FrozenFeatureResult:
    feature_id: str
    feature_name: str
    source_part_name: str
    effective_tolerance: float
    same_body: bool


ToleranceCombinationMethod = Callable[[List[float]], float]


def rss_combine(tolerance_stack: List[float]) -> float:
    return math.sqrt(sum(t ** 2 for t in tolerance_stack))


def worst_case_combine(tolerance_stack: List[float]) -> float:
    return sum(tolerance_stack)


@dataclass
class Subassembly:
    name: str
    children: List[Union[Part, "Subassembly"]]
    datum_child_id: str
    datum_tolerance: float
    interface_tolerance: float
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    is_frozen: bool = False
    frozen_results: Dict[str, FrozenFeatureResult] = field(default_factory=dict)

    def _child_features(self, child: Union[Part, "Subassembly"]) -> List[Tuple[str, str, str, float]]:
        if isinstance(child, Part):
            return [(f.id, f.name, f.source_part_name, f.own_tolerance) for f in child.features]
        elif isinstance(child, Subassembly):
            return [
                (fid, r.feature_name, r.source_part_name, r.effective_tolerance)
                for fid, r in child.frozen_results.items()
            ]
        return []

    def calculate_and_freeze(self, method: ToleranceCombinationMethod = rss_combine) -> None:
        if len(self.children) < 2:
            raise ValueError("A subassembly needs at least two children to join.")

        child_ids = [c.id for c in self.children]
        if self.datum_child_id not in child_ids:
            raise ValueError("The selected datum child is not one of this subassembly's children.")

        results: Dict[str, FrozenFeatureResult] = {}
        for child in self.children:
            same_body = (child.id == self.datum_child_id)
            for fid, fname, source, current_tol in self._child_features(child):
                if same_body:
                    effective = current_tol
                else:
                    effective = method([self.datum_tolerance, self.interface_tolerance, current_tol])
                results[fid] = FrozenFeatureResult(
                    feature_id=fid,
                    feature_name=fname,
                    source_part_name=source,
                    effective_tolerance=effective,
                    same_body=same_body,
                )

        self.frozen_results = results
        self.is_frozen = True

    @property
    def datum_child_label(self) -> str:
        for c in self.children:
            if c.id == self.datum_child_id:
                return c.name
        return "-"

    @property
    def child_names(self) -> List[str]:
        return [c.name for c in self.children]


# ============================================================
# 2. STYLING / HTML HELPERS
# ============================================================

DARK_NAVY = "#1B2A4A"
DARK_NAVY_HOVER = "#243B66"
WHITE_ROW = "#FFFFFF"
LIGHT_ROW = "#F0F4F8"
BORDER_BLUE_GREY = "#8CA3C4"
MUTED_TEXT = "#5B6B82"

SAMEBODY_BG = "#E1F5E9"
SAMEBODY_TEXT = "#1E6B3A"

FROZEN_BADGE_BG = "#E3E8EF"
FROZEN_BADGE_TEXT = "#33415C"

FONT_STACK = "'Segoe UI', Arial, sans-serif"
DECIMALS = 2


def inject_global_css() -> None:
    st.markdown(
        f"""
        <style>
        .section-header {{
            color: {DARK_NAVY};
            font-weight: 700;
            font-family: {FONT_STACK};
            font-size: 1.05rem;
            margin-top: 0.6rem;
            margin-bottom: 0.3rem;
        }}
        .panel-title {{
            color: {DARK_NAVY};
            font-weight: 700;
            font-family: {FONT_STACK};
            font-size: 1.25rem;
            margin-bottom: 0.3rem;
            display: inline-block;
            margin-right: 8px;
        }}
        .samebody-badge {{
            display: inline-block;
            background-color: {SAMEBODY_BG};
            color: {SAMEBODY_TEXT};
            padding: 1px 6px;
            border-radius: 4px;
            font-size: 0.68rem;
            font-family: {FONT_STACK};
            margin-top: 3px;
        }}
        .frozen-badge {{
            display: inline-block;
            background-color: {FROZEN_BADGE_BG};
            color: {FROZEN_BADGE_TEXT};
            padding: 2px 9px;
            border-radius: 4px;
            font-size: 0.72rem;
            font-weight: 700;
            font-family: {FONT_STACK};
            letter-spacing: 0.03em;
            vertical-align: middle;
        }}
        .stage-meta {{
            font-family: {FONT_STACK};
            font-size: 0.85rem;
            color: {MUTED_TEXT};
            margin-bottom: 0.5rem;
        }}
        .results-table {{
            width: 100%;
            border-collapse: collapse;
            font-family: {FONT_STACK};
            font-size: 0.9rem;
            border: 1px solid {BORDER_BLUE_GREY};
            margin-bottom: 0.75rem;
        }}
        .results-table th {{
            background-color: {DARK_NAVY};
            color: #FFFFFF;
            font-weight: 700;
            text-align: center;
            padding: 9px 10px;
            border: 1px solid {BORDER_BLUE_GREY};
        }}
        .results-table td {{
            padding: 8px 10px;
            border: 1px solid {BORDER_BLUE_GREY};
            vertical-align: middle;
        }}
        button[kind="primary"],
        button[data-testid="stBaseButton-primary"] {{
            background-color: {DARK_NAVY} !important;
            color: #FFFFFF !important;
            border: 1px solid {DARK_NAVY} !important;
        }}
        button[kind="primary"]:hover,
        button[data-testid="stBaseButton-primary"]:hover {{
            background-color: {DARK_NAVY_HOVER} !important;
            color: #FFFFFF !important;
            border: 1px solid {DARK_NAVY_HOVER} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def styled_section_header(text: str) -> None:
    st.markdown(f"<div class='section-header'>{html.escape(text)}</div>", unsafe_allow_html=True)


def styled_panel_title_with_badge(text: str) -> None:
    st.markdown(
        f"<span class='panel-title'>{html.escape(text)}</span>"
        f"<span class='frozen-badge'>FROZEN</span>",
        unsafe_allow_html=True,
    )


def build_subassembly_table_html(sub: Subassembly) -> str:
    header_html = (
        "<tr>"
        "<th style='text-align:center;'>S. No.</th>"
        "<th style='text-align:center;'>Functional Feature Name</th>"
        "<th style='text-align:center;'>Component</th>"
        "<th style='text-align:center;'>Datum Reference</th>"
        "<th style='text-align:center;'>Effective RSS Tolerance (mm)</th>"
        "</tr>"
    )

    row_fragments: List[str] = []
    for idx, result in enumerate(sub.frozen_results.values(), start=1):
        row_bg = WHITE_ROW if idx % 2 == 1 else LIGHT_ROW
        effective_str = f"{result.effective_tolerance:.{DECIMALS}f}"

        if result.same_body:
            tolerance_cell = f"{effective_str}<br><span class='samebody-badge'>(same body)</span>"
        else:
            tolerance_cell = effective_str

        row_fragments.append(
            f"<tr style='background-color:{row_bg}; color:#1A1A1A;'>"
            f"<td style='text-align:left;'>{idx}</td>"
            f"<td style='text-align:left;'>{html.escape(result.feature_name)}</td>"
            f"<td style='text-align:left;'>{html.escape(result.source_part_name)}</td>"
            f"<td style='text-align:center;'>{html.escape(sub.datum_child_label)}</td>"
            f"<td style='text-align:center;'>{tolerance_cell}</td>"
            "</tr>"
        )

    return (
        "<table class='results-table'>"
        f"<thead>{header_html}</thead>"
        f"<tbody>{''.join(row_fragments)}</tbody>"
        "</table>"
    )


def build_subassembly_export_dataframe(sub: Subassembly) -> pd.DataFrame:
    rows = []
    for idx, result in enumerate(sub.frozen_results.values(), start=1):
        rows.append(
            {
                "S. No.": idx,
                "Functional Feature Name": result.feature_name,
                "Component": result.source_part_name,
                "Datum Reference": sub.datum_child_label,
                # Formatted as a fixed 2-decimal string (not a raw float) so the
                # CSV matches the on-screen table exactly - a bare float here
                # would print "0.1" instead of "0.10" and silently lose precision.
                "Effective RSS Tolerance (mm)": f"{result.effective_tolerance:.{DECIMALS}f}",
                "Notes": "(same body)" if result.same_body else "",
            }
        )
    return pd.DataFrame(rows)


# ============================================================
# 3. STREAMLIT UI
# ============================================================

st.set_page_config(page_title="Assembly Tolerance Propagation Tool", layout="wide")
inject_global_css()


def init_session_state() -> None:
    defaults = {
        "parts": [],
        "subassemblies": [],
        "available_unit_ids": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()


def get_all_units() -> List[Union[Part, Subassembly]]:
    return st.session_state.parts + st.session_state.subassemblies


def get_available_units() -> List[Union[Part, Subassembly]]:
    return [u for u in get_all_units() if u.id in st.session_state.available_unit_ids]


def is_consumed(unit_id: str) -> bool:
    return unit_id not in st.session_state.available_unit_ids


st.title("Assembly Tolerance Propagation Tool")

with st.sidebar:

    styled_section_header("1. Parts")
    with st.form("add_part_form", clear_on_submit=True):
        new_part_name = st.text_input("Part name")
        add_part_submitted = st.form_submit_button("Add Part")
        if add_part_submitted:
            name = new_part_name.strip()
            if not name:
                st.error("Part name cannot be empty.")
            else:
                new_part = Part(name=name)
                st.session_state.parts.append(new_part)
                st.session_state.available_unit_ids.append(new_part.id)
                st.success(f"Added part '{name}'.")

    styled_section_header("2. Features")
    unconsumed_parts = [p for p in st.session_state.parts if not is_consumed(p.id)]
    if not unconsumed_parts:
        st.info("Add a part (that hasn't been used in a subassembly yet) before adding features.")
    else:
        part_options = {p.id: p.name for p in unconsumed_parts}
        with st.form("add_feature_form", clear_on_submit=True):
            target_part_id = st.selectbox(
                "Add a feature to which part?",
                options=list(part_options.keys()), format_func=lambda pid: part_options[pid],
            )
            feature_name = st.text_input("Feature name")
            feature_tolerance = st.number_input(
                "Feature tolerance (mm)", min_value=0.0, value=0.0,
                step=0.01, format=f"%.{DECIMALS}f",
            )
            add_feature_submitted = st.form_submit_button("Add Feature")
            if add_feature_submitted:
                name = feature_name.strip()
                if not name:
                    st.error("Feature name cannot be empty.")
                elif feature_tolerance <= 0:
                    st.error("Feature tolerance must be a positive number greater than zero.")
                else:
                    target_part = next(p for p in st.session_state.parts if p.id == target_part_id)
                    target_part.add_feature(name, round(feature_tolerance, DECIMALS))
                    st.success(f"Added feature '{name}' to '{target_part.name}'.")

    for part in st.session_state.parts:
        consumed = is_consumed(part.id)
        label = part.name + ("  (used - locked)" if consumed else "")
        with st.expander(label):
            if part.features:
                for feat in part.features:
                    st.write(f"- {feat.name}: {feat.own_tolerance:.{DECIMALS}f} mm")
            else:
                st.caption("No features yet.")
            if not consumed:
                if st.button("Remove Part", key=f"remove_part_{part.id}"):
                    st.session_state.parts = [p for p in st.session_state.parts if p.id != part.id]
                    st.session_state.available_unit_ids = [
                        uid for uid in st.session_state.available_unit_ids if uid != part.id
                    ]
                    st.rerun()

    st.divider()

    styled_section_header("3. Build a Subassembly")

    available_units = get_available_units()
    if len(available_units) < 2:
        st.info("You need at least two available parts (or frozen subassemblies) to build a new subassembly.")
    else:
        unit_options = {u.id: u.name for u in available_units}
        selected_ids = st.multiselect(
            "Select which parts/subassemblies to join",
            options=list(unit_options.keys()),
            format_func=lambda uid: unit_options[uid],
            key="subassembly_children_select",
        )

        if len(selected_ids) < 2:
            st.caption("Select at least two to continue.")
        else:
            selected_units = [u for u in available_units if u.id in selected_ids]
            datum_options = {u.id: u.name for u in selected_units}
            datum_child_id = st.selectbox(
                "Which child carries the reference datum?",
                options=list(datum_options.keys()),
                format_func=lambda uid: datum_options[uid],
                key="subassembly_datum_select",
            )
            datum_unit = next(u for u in selected_units if u.id == datum_child_id)

            if isinstance(datum_unit, Subassembly):
                st.number_input(
                    "Datum tolerance (mm) \u2014 inherited from the frozen subassembly",
                    value=float(datum_unit.datum_tolerance), disabled=True,
                    format=f"%.{DECIMALS}f", key="subassembly_datum_tol_display",
                )
                datum_tolerance_value = datum_unit.datum_tolerance
            else:
                datum_tolerance_value = st.number_input(
                    "Datum tolerance (mm)", min_value=0.0, value=0.0,
                    step=0.01, format=f"%.{DECIMALS}f", key="subassembly_datum_tol_input",
                )

            interface_tolerance_value = st.number_input(
                "Interface tolerance (mm) \u2014 this station's joining operation",
                min_value=0.0, value=0.0, step=0.01,
                format=f"%.{DECIMALS}f", key="subassembly_interface_tol_input",
            )

            default_sub_name = f"Subassembly {len(st.session_state.subassemblies) + 1}"
            subassembly_name = st.text_input(
                "Name this subassembly", value=default_sub_name, key="subassembly_name_input",
            )

            if st.button("Calculate and Freeze", type="primary"):
                name = subassembly_name.strip()
                if not name:
                    st.error("Subassembly name cannot be empty.")
                elif interface_tolerance_value <= 0:
                    st.error("Interface tolerance must be a positive number greater than zero.")
                elif datum_tolerance_value is None or datum_tolerance_value <= 0:
                    st.error("Datum tolerance must be a positive number greater than zero.")
                else:
                    new_sub = Subassembly(
                        name=name,
                        children=selected_units,
                        datum_child_id=datum_child_id,
                        datum_tolerance=round(datum_tolerance_value, DECIMALS),
                        interface_tolerance=round(interface_tolerance_value, DECIMALS),
                    )
                    try:
                        new_sub.calculate_and_freeze()
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.available_unit_ids = [
                            uid for uid in st.session_state.available_unit_ids if uid not in selected_ids
                        ]
                        st.session_state.available_unit_ids.append(new_sub.id)
                        st.session_state.subassemblies.append(new_sub)
                        st.success(f"'{name}' calculated and frozen.")
                        st.rerun()


if st.session_state.subassemblies:
    for sub in st.session_state.subassemblies:
        styled_panel_title_with_badge(sub.name)
        st.markdown(
            f"<div class='stage-meta'>Joined: {html.escape(', '.join(sub.child_names))} "
            f"&nbsp;|&nbsp; Datum: {html.escape(sub.datum_child_label)} "
            f"({sub.datum_tolerance:.{DECIMALS}f} mm) "
            f"&nbsp;|&nbsp; Interface: {sub.interface_tolerance:.{DECIMALS}f} mm</div>",
            unsafe_allow_html=True,
        )
        st.markdown(build_subassembly_table_html(sub), unsafe_allow_html=True)

        export_df = build_subassembly_export_dataframe(sub)
        csv_bytes = export_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            f"Export '{sub.name}' Results to CSV",
            data=csv_bytes,
            file_name=f"{sub.name.replace(' ', '_')}_results.csv",
            mime="text/csv",
            key=f"export_{sub.id}",
        )
        st.divider()
else:
    st.info(
        "Add parts and features in the sidebar, then build and freeze a subassembly "
        "to see its results here."
    )
