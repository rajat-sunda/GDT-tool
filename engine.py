"""
app.py

Assembly Tolerance Propagation Tool
------------------------------------
A simple Streamlit app for GD&T tolerance stack-up analysis.

Parts get joined into a single subassembly. Every feature (hole, slot,
etc.) on every part has a positional tolerance. This tool calculates
each feature's effective assembly-level tolerance using Root Sum
Square (RSS):

    Feature is on the same part as the datum
        -> effective tolerance = its own tolerance (no RSS)

    Feature is on any other part
        -> effective tolerance = sqrt(datum_tolerance**2
                                       + interface_tolerance**2
                                       + feature_tolerance**2)

No graphs, no paths, no multi-stage hierarchy - just one flat set of
parts, one datum, one interface tolerance, calculated in one pass.
"""

import math
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

import streamlit as st


# =============================================================================
# Data model
# =============================================================================

@dataclass
class Part:
    """A physical part in the assembly.

    Attributes:
        name: Human-readable part name.
        id: Unique identifier, auto-generated with uuid4.
    """
    name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class Feature:
    """A toleranced feature (hole, slot, etc.) defined on a Part.

    Attributes:
        name: Human-readable feature name.
        part_id: Id of the Part this feature belongs to.
        tolerance: The feature's own positional tolerance, in mm.
        id: Unique identifier, auto-generated with uuid4.
    """
    name: str
    part_id: str
    tolerance: float
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


def calculate_effective_tolerance(
    feature: Feature,
    datum_part_id: str,
    datum_tolerance: float,
    interface_tolerance: float,
) -> float:
    """Calculate one feature's effective assembly-level tolerance.

    Business rule:
        If the feature is on the same part as the datum, its effective
        tolerance is simply its own tolerance - no RSS is applied.
        Otherwise, effective tolerance is the RSS of the datum
        tolerance, the interface tolerance, and the feature's own
        tolerance.

    Args:
        feature: The Feature to calculate for.
        datum_part_id: Id of whichever Part carries the datum.
        datum_tolerance: The datum's own tolerance, in mm.
        interface_tolerance: The joining interface tolerance, in mm.

    Returns:
        The effective tolerance, in mm.
    """
    if feature.part_id == datum_part_id:
        return feature.tolerance
    return math.sqrt(datum_tolerance ** 2 + interface_tolerance ** 2 + feature.tolerance ** 2)


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
    """Inject the one-time global <style> block for the results table,
    sidebar section headers, and the Calculate button."""
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
    """Render a sidebar section header in dark navy bold."""
    st.markdown(f"<div class='section-header'>{text}</div>", unsafe_allow_html=True)


def build_results_table_html(rows: List[dict]) -> str:
    """Build the styled results table as HTML.

    Args:
        rows: List of dicts, each with keys: feature_name, part_name,
            datum_reference, effective_tolerance, same_body.

    Returns:
        A complete <table> as an HTML string, ready for
        st.markdown(..., unsafe_allow_html=True).
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
# Streamlit UI
# =============================================================================

st.set_page_config(page_title="Assembly Tolerance Propagation Tool", layout="wide")
inject_global_css()


def init_session_state() -> None:
    """Initialize all required session_state keys exactly once. Starts empty."""
    defaults = {
        "parts": [],      # list[Part]
        "features": [],   # list[Feature]
        "results": None,  # list[dict] or None
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
                st.session_state.results = None
                st.success(f"Added part '{name}'.")

    for part in st.session_state.parts:
        col1, col2 = st.columns([4, 1])
        col1.write(part.name)
        if col2.button("Remove", key=f"remove_part_{part.id}"):
            removed_id = part.id
            st.session_state.parts = [p for p in st.session_state.parts if p.id != removed_id]
            st.session_state.features = [f for f in st.session_state.features if f.part_id != removed_id]
            st.session_state.results = None
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
                    st.session_state.results = None
                    st.success(f"Added feature '{name}'.")

    # Features grouped under their part
    for part in st.session_state.parts:
        part_features = [f for f in st.session_state.features if f.part_id == part.id]
        if part_features:
            st.caption(part.name)
            for feat in part_features:
                st.write(f"- {feat.name}: {feat.tolerance:.{DECIMALS}f} mm")

    st.divider()

    # --- Section 3: Assembly Setup ---
    styled_section_header("3. Assembly Setup")
    if not st.session_state.parts:
        st.info("Add at least one part to set up the assembly.")
        datum_part_id: Optional[str] = None
        datum_tolerance = 0.0
        interface_tolerance = 0.0
    else:
        part_options = {p.id: p.name for p in st.session_state.parts}
        datum_part_id = st.selectbox(
            "Which part carries the datum?",
            options=list(part_options.keys()),
            format_func=lambda pid: part_options[pid],
        )
        datum_tolerance = st.number_input(
            "Datum tolerance (mm)", min_value=0.0, value=0.0,
            step=0.01, format=f"%.{DECIMALS}f",
        )
        interface_tolerance = st.number_input(
            "Interface tolerance (mm)", min_value=0.0, value=0.0,
            step=0.01, format=f"%.{DECIMALS}f",
        )

    calculate_clicked = st.button("Calculate", type="primary")

    if calculate_clicked:
        if not st.session_state.parts:
            st.error("Add at least one part before calculating.")
        elif not st.session_state.features:
            st.error("Add at least one feature before calculating.")
        elif datum_part_id is None:
            st.error("Select which part carries the datum before calculating.")
        elif datum_tolerance <= 0:
            st.error("Datum tolerance must be a positive number greater than zero.")
        elif interface_tolerance <= 0:
            st.error("Interface tolerance must be a positive number greater than zero.")
        else:
            part_lookup = {p.id: p.name for p in st.session_state.parts}
            datum_part_name = part_lookup[datum_part_id]

            rows = []
            for part in st.session_state.parts:
                part_features = [f for f in st.session_state.features if f.part_id == part.id]
                if not part_features:
                    # Skip parts with no features silently.
                    continue
                for feat in part_features:
                    effective = calculate_effective_tolerance(
                        feat, datum_part_id, datum_tolerance, interface_tolerance
                    )
                    rows.append(
                        {
                            "feature_name": feat.name,
                            "part_name": part_lookup[feat.part_id],
                            "datum_reference": datum_part_name,
                            "effective_tolerance": effective,
                            "same_body": feat.part_id == datum_part_id,
                        }
                    )

            st.session_state.results = rows


# -- Main panel -------------------------------------------------------------

if st.session_state.results is not None:
    if len(st.session_state.results) == 0:
        st.info("No features to display.")
    else:
        st.markdown(build_results_table_html(st.session_state.results), unsafe_allow_html=True)
else:
    st.info("Add parts and features in the sidebar, set up the assembly, then click Calculate.")
