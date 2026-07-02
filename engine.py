"""
app.py

Assembly Tolerance Propagation Tool
------------------------------------
A simple Streamlit app for GD&T tolerance stack-up analysis, now
supporting multiple assembly levels (subassemblies built on top of
subassemblies).

Core rule (unchanged):
    Feature is on the datum side  -> effective tolerance = its current
                                      tolerance, no RSS ("same body")
    Feature is on the other side  -> effective tolerance =
                                      sqrt(datum_tolerance**2
                                           + interface_tolerance**2
                                           + current_tolerance**2)

How multi-level works:
    Level 1: pick a datum part from your raw parts, set datum tolerance
    and interface tolerance, click Calculate. This produces the first
    results table.

    Level 2+: add one or more NEW parts, then choose whether the datum
    for this level stays on "the subassembly built so far" (its
    existing features simply pass through unchanged) or shifts to one
    of the new parts you just added (in which case the subassembly's
    existing features get RSS-combined with the new datum + interface,
    using their most recently calculated value as the input). Click
    Calculate Next Level. A new table is appended below the previous
    one - nothing is overwritten or removed.

No export, no save button - everything lives in st.session_state and
stays visible in the interface as you go.
"""

import math
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import streamlit as st


# =============================================================================
# Data model
# =============================================================================

@dataclass
class Part:
    """A physical part in the assembly."""
    name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class Feature:
    """A toleranced feature (hole, slot, etc.) defined on a Part."""
    name: str
    part_id: str
    tolerance: float
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


def combine(current_tolerance: float, is_datum_side: bool, datum_tolerance: float, interface_tolerance: float) -> float:
    """Apply the same-body / RSS rule to a single feature's current tolerance.

    Args:
        current_tolerance: The feature's tolerance going into this
            level's calculation - its own drawing tolerance if this is
            the first time it's being included, or its most recently
            calculated effective tolerance if it was carried forward
            from an earlier level.
        is_datum_side: True if this feature's part (or the "built so
            far" subassembly it belongs to) carries the datum at this
            level.
        datum_tolerance: This level's datum tolerance, in mm.
        interface_tolerance: This level's interface tolerance, in mm.

    Returns:
        The effective tolerance for this level, in mm.
    """
    if is_datum_side:
        return current_tolerance
    return math.sqrt(datum_tolerance ** 2 + interface_tolerance ** 2 + current_tolerance ** 2)


# =============================================================================
# Styling
# =============================================================================

DARK_NAVY = "#1B2A4A"
DARK_NAVY_HOVER = "#243B66"
WHITE_ROW = "#FFFFFF"
LIGHT_ROW = "#F0F4F8"
BORDER_BLUE_GREY = "#8CA3C4"

SAMEBODY_BG = "#E1F5E9"
SAMEBODY_TEXT = "#1E6B3A"

FONT_STACK = "'Segoe UI', Arial, sans-serif"
DECIMALS = 2


def inject_global_css() -> None:
    """Inject the one-time global <style> block."""
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
        .stage-title {{
            color: {DARK_NAVY};
            font-weight: 700;
            font-family: {FONT_STACK};
            font-size: 1.2rem;
            margin-top: 1.2rem;
            margin-bottom: 0.4rem;
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
        .results-table {{
            width: 100%;
            border-collapse: collapse;
            font-family: {FONT_STACK};
            font-size: 0.9rem;
            border: 1px solid {BORDER_BLUE_GREY};
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
    st.markdown(f"<div class='section-header'>{text}</div>", unsafe_allow_html=True)


def styled_stage_title(text: str) -> None:
    st.markdown(f"<div class='stage-title'>{text}</div>", unsafe_allow_html=True)


def build_results_table_html(rows: List[dict]) -> str:
    """Build the styled results table as HTML for one stage's rows.

    Args:
        rows: List of dicts with keys: feature_name, part_name,
            datum_reference, effective_tolerance, same_body.
    """
    header_html = (
        "<tr>"
        "<th>S. No.</th>"
        "<th>Feature Name</th>"
        "<th>Part</th>"
        "<th>Datum Reference</th>"
        "<th>Effective Tolerance (mm)</th>"
        "</tr>"
    )

    row_fragments = []
    for idx, row in enumerate(rows, start=1):
        row_bg = WHITE_ROW if idx % 2 == 1 else LIGHT_ROW
        effective_val = round(row["effective_tolerance"], DECIMALS)

        if row["same_body"]:
            tolerance_cell = (
                f"{effective_val:.{DECIMALS}f}<br>"
                "<span class='samebody-badge'>(same body)</span>"
            )
        else:
            tolerance_cell = f"{effective_val:.{DECIMALS}f}"

        row_fragments.append(
            f"<tr style='background-color:{row_bg}; color:#1A1A1A;'>"
            f"<td style='text-align:left;'>{idx}</td>"
            f"<td style='text-align:left;'>{row['feature_name']}</td>"
            f"<td style='text-align:left;'>{row['part_name']}</td>"
            f"<td style='text-align:center;'>{row['datum_reference']}</td>"
            f"<td style='text-align:center;'>{tolerance_cell}</td>"
            "</tr>"
        )

    return (
        "<table class='results-table'>"
        f"<thead>{header_html}</thead>"
        f"<tbody>{''.join(row_fragments)}</tbody>"
        "</table>"
    )


# =============================================================================
# Calculation
# =============================================================================

def run_level_calculation(
    datum_is_subassembly: bool,
    datum_part_id: Optional[str],
    datum_tolerance: float,
    interface_tolerance: float,
    new_part_ids: List[str],
    datum_label: str,
) -> List[dict]:
    """Run one assembly level's calculation and update running state.

    Every feature already folded into the subassembly (from earlier
    levels) carries forward its most recent effective tolerance as the
    input to this level. Every feature on a brand-new part uses its own
    original drawing tolerance as the input. Whichever side carries the
    datum this level passes through unchanged; everything else gets
    RSS-combined with this level's datum and interface tolerances.

    Args:
        datum_is_subassembly: True if the datum stays on the
            already-built subassembly this level (only possible from
            level 2 onward).
        datum_part_id: Id of the new part carrying the datum this
            level, or None if datum_is_subassembly is True.
        datum_tolerance: This level's datum tolerance, in mm.
        interface_tolerance: This level's interface tolerance, in mm.
        new_part_ids: Ids of the parts being folded in at this level
            (for level 1, this is every part that currently has
            features).
        datum_label: Human-readable label for the "Datum Reference"
            column (a part name, or "Subassembly (Level N)").

    Returns:
        The list of row dicts for this level's results table.
    """
    part_lookup = {p.id: p.name for p in st.session_state.parts}
    rows: List[dict] = []
    updated_tolerances: Dict[str, float] = {}

    # Features already part of the subassembly from earlier levels.
    for part in st.session_state.parts:
        if part.id not in st.session_state.included_part_ids:
            continue
        part_features = [f for f in st.session_state.features if f.part_id == part.id]
        for feat in part_features:
            current_val = st.session_state.current_tolerances[feat.id]
            is_datum_side = datum_is_subassembly
            effective = combine(current_val, is_datum_side, datum_tolerance, interface_tolerance)
            rows.append(
                {
                    "feature_name": feat.name,
                    "part_name": part_lookup[part.id],
                    "datum_reference": datum_label,
                    "effective_tolerance": effective,
                    "same_body": is_datum_side,
                }
            )
            updated_tolerances[feat.id] = effective

    # Features on parts newly added at this level.
    for pid in new_part_ids:
        part_features = [f for f in st.session_state.features if f.part_id == pid]
        for feat in part_features:
            current_val = feat.tolerance
            is_datum_side = (not datum_is_subassembly) and (pid == datum_part_id)
            effective = combine(current_val, is_datum_side, datum_tolerance, interface_tolerance)
            rows.append(
                {
                    "feature_name": feat.name,
                    "part_name": part_lookup[pid],
                    "datum_reference": datum_label,
                    "effective_tolerance": effective,
                    "same_body": is_datum_side,
                }
            )
            updated_tolerances[feat.id] = effective

    st.session_state.current_tolerances.update(updated_tolerances)
    st.session_state.included_part_ids.update(new_part_ids)
    st.session_state.last_datum_tolerance = datum_tolerance

    return rows


# =============================================================================
# Streamlit UI
# =============================================================================

st.set_page_config(page_title="Assembly Tolerance Propagation Tool", layout="wide")
inject_global_css()


def init_session_state() -> None:
    """Initialize all required session_state keys exactly once. Starts empty."""
    defaults = {
        "parts": [],                  # list[Part]
        "features": [],                # list[Feature]
        "stages": [],                  # list[{"title": str, "rows": list[dict]}]
        "current_tolerances": {},      # feature_id -> latest effective tolerance
        "included_part_ids": set(),    # part ids already folded into the subassembly
        "last_datum_tolerance": 0.0,   # datum tolerance used at the most recent level
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()

st.title("Assembly Tolerance Propagation Tool")

with st.sidebar:

    # --- Section 1: Parts ---
    styled_section_header("1. Parts")
    with st.form("add_part_form", clear_on_submit=True):
        new_part_name = st.text_input("Part name")
        add_part_submitted = st.form_submit_button("Add Part")
        if add_part_submitted:
            name = new_part_name.strip()
            if not name:
                st.error("Part name cannot be empty.")
            else:
                st.session_state.parts.append(Part(name=name))
                st.success(f"Added part '{name}'.")

    for part in st.session_state.parts:
        col1, col2 = st.columns([4, 1])
        col1.write(part.name)
        if col2.button("Remove", key=f"remove_part_{part.id}"):
            removed_id = part.id
            st.session_state.parts = [p for p in st.session_state.parts if p.id != removed_id]
            st.session_state.features = [f for f in st.session_state.features if f.part_id != removed_id]
            st.session_state.included_part_ids.discard(removed_id)
            st.rerun()

    st.divider()

    # --- Section 2: Features ---
    styled_section_header("2. Features")
    if not st.session_state.parts:
        st.info("Add a part before adding features.")
    else:
        part_options = {p.id: p.name for p in st.session_state.parts}
        with st.form("add_feature_form", clear_on_submit=True):
            feature_part_id = st.selectbox(
                "Which part does this feature belong to?",
                options=list(part_options.keys()),
                format_func=lambda pid: part_options[pid],
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
                    st.session_state.features.append(
                        Feature(name=name, part_id=feature_part_id, tolerance=round(feature_tolerance, DECIMALS))
                    )
                    st.success(f"Added feature '{name}'.")

    for part in st.session_state.parts:
        part_features = [f for f in st.session_state.features if f.part_id == part.id]
        if part_features:
            st.caption(part.name)
            for feat in part_features:
                st.write(f"- {feat.name}: {feat.tolerance:.{DECIMALS}f} mm")

    st.divider()

    # --- Section 3: Assembly Setup (Level 1 only) ---
    styled_section_header("3. Assembly Setup")

    if st.session_state.stages:
        st.caption("Level 1 is already calculated. Use Section 4 below to add more components.")
    else:
        parts_with_features = [
            p for p in st.session_state.parts
            if any(f.part_id == p.id for f in st.session_state.features)
        ]
        if not parts_with_features:
            st.info("Add at least one part with a feature to set up the assembly.")
        else:
            part_options = {p.id: p.name for p in parts_with_features}
            datum_part_id = st.selectbox(
                "Which part carries the datum?",
                options=list(part_options.keys()),
                format_func=lambda pid: part_options[pid],
                key="level1_datum_part",
            )
            datum_tolerance = st.number_input(
                "Datum tolerance (mm)", min_value=0.0, value=0.0,
                step=0.01, format=f"%.{DECIMALS}f", key="level1_datum_tol",
            )
            interface_tolerance = st.number_input(
                "Interface tolerance (mm)", min_value=0.0, value=0.0,
                step=0.01, format=f"%.{DECIMALS}f", key="level1_interface_tol",
            )

            if st.button("Calculate", type="primary"):
                if datum_tolerance <= 0:
                    st.error("Datum tolerance must be a positive number greater than zero.")
                elif interface_tolerance <= 0:
                    st.error("Interface tolerance must be a positive number greater than zero.")
                else:
                    part_lookup = {p.id: p.name for p in st.session_state.parts}
                    new_part_ids = [p.id for p in parts_with_features]
                    rows = run_level_calculation(
                        datum_is_subassembly=False,
                        datum_part_id=datum_part_id,
                        datum_tolerance=round(datum_tolerance, DECIMALS),
                        interface_tolerance=round(interface_tolerance, DECIMALS),
                        new_part_ids=new_part_ids,
                        datum_label=part_lookup[datum_part_id],
                    )
                    st.session_state.stages.append({"title": "Subassembly - Level 1", "rows": rows})
                    st.rerun()

    st.divider()

    # --- Section 4: Add Next Assembly Level ---
    if st.session_state.stages:
        styled_section_header("4. Add Next Assembly Level")

        available_new_parts = [
            p for p in st.session_state.parts
            if p.id not in st.session_state.included_part_ids
            and any(f.part_id == p.id for f in st.session_state.features)
        ]

        if not available_new_parts:
            st.info("Add a new part (with at least one feature) above to build the next level.")
        else:
            new_part_options = {p.id: p.name for p in available_new_parts}
            selected_new_part_ids = st.multiselect(
                "Which new component(s) are joining this level?",
                options=list(new_part_options.keys()),
                format_func=lambda pid: new_part_options[pid],
                key="level_new_parts",
            )

            if not selected_new_part_ids:
                st.caption("Select at least one new component to continue.")
            else:
                next_level_number = len(st.session_state.stages) + 1
                subassembly_option = f"Subassembly (through Level {next_level_number - 1})"
                datum_side_options = [subassembly_option] + [
                    new_part_options[pid] for pid in selected_new_part_ids
                ]
                datum_side_choice = st.selectbox(
                    "Which side carries the datum for this level?",
                    options=datum_side_options,
                    key="level_datum_side",
                )

                datum_is_subassembly = (datum_side_choice == subassembly_option)

                if datum_is_subassembly:
                    st.number_input(
                        "Datum tolerance (mm) \u2014 inherited from the subassembly",
                        value=float(st.session_state.last_datum_tolerance),
                        disabled=True, format=f"%.{DECIMALS}f", key="level_datum_tol_display",
                    )
                    next_datum_tolerance = st.session_state.last_datum_tolerance
                    next_datum_part_id = None
                    next_datum_label = subassembly_option
                else:
                    next_datum_tolerance = st.number_input(
                        "Datum tolerance (mm)", min_value=0.0, value=0.0,
                        step=0.01, format=f"%.{DECIMALS}f", key="level_datum_tol_input",
                    )
                    chosen_name = datum_side_choice
                    next_datum_part_id = next(
                        pid for pid in selected_new_part_ids if new_part_options[pid] == chosen_name
                    )
                    next_datum_label = chosen_name

                next_interface_tolerance = st.number_input(
                    "Interface tolerance (mm)", min_value=0.0, value=0.0,
                    step=0.01, format=f"%.{DECIMALS}f", key="level_interface_tol",
                )

                if st.button("Calculate Next Level", type="primary"):
                    if (not datum_is_subassembly) and next_datum_tolerance <= 0:
                        st.error("Datum tolerance must be a positive number greater than zero.")
                    elif next_interface_tolerance <= 0:
                        st.error("Interface tolerance must be a positive number greater than zero.")
                    else:
                        rows = run_level_calculation(
                            datum_is_subassembly=datum_is_subassembly,
                            datum_part_id=next_datum_part_id,
                            datum_tolerance=round(next_datum_tolerance, DECIMALS),
                            interface_tolerance=round(next_interface_tolerance, DECIMALS),
                            new_part_ids=selected_new_part_ids,
                            datum_label=next_datum_label,
                        )
                        st.session_state.stages.append(
                            {"title": f"Subassembly - Level {next_level_number}", "rows": rows}
                        )
                        st.rerun()


# -- Main panel: every level's table, stacked, oldest first ----------------

if not st.session_state.stages:
    st.info("Add parts and features in the sidebar, set up the assembly, then click Calculate.")
else:
    for stage in st.session_state.stages:
        styled_stage_title(stage["title"])
        if len(stage["rows"]) == 0:
            st.info("No features to display for this level.")
        else:
            st.markdown(build_results_table_html(stage["rows"]), unsafe_allow_html=True)
