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
    """A joining stage: two or more children combined via one interface.

    Lifecycle:
    - After Calculate is clicked, the subassembly is a DRAFT. Its results
      are computed but not locked. You can add features to source parts and
      click Recalculate to update results.
    - A subassembly becomes permanently FROZEN only when it is selected as
      a child while building a higher-level subassembly. Once frozen, it
      can never be recalculated.
    """

    name: str
    children: List[Union[Part, "Subassembly"]]
    datum_child_id: str
    datum_tolerance: float
    interface_tolerance: float
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    is_locked: bool = False
    frozen_results: Dict[str, FrozenFeatureResult] = field(default_factory=dict)

    def _child_features(self, child: Union[Part, "Subassembly"]) -> List[Tuple[str, str, str, float]]:
        """Return (feature_id, feature_name, source_part_name, current_tolerance)
        for every feature in child. For a raw Part, reads live off the Part object.
        For a Subassembly, reads from its most recent frozen_results."""
        if isinstance(child, Part):
            return [(f.id, f.name, f.source_part_name, f.own_tolerance) for f in child.features]
        elif isinstance(child, Subassembly):
            return [
                (fid, r.feature_name, r.source_part_name, r.effective_tolerance)
                for fid, r in child.frozen_results.items()
            ]
        return []

    def calculate_and_freeze(self, method: ToleranceCombinationMethod = rss_combine) -> None:
        """(Re)calculate this subassembly's feature results from children's current state.

        Can be called repeatedly while the subassembly is a DRAFT.
        Raises ValueError if already locked, fewer than two children, or
        datum child not found.
        """
        if self.is_locked:
            raise ValueError(f"'{self.name}' is locked and cannot be recalculated.")
        if len(self.children) < 2:
            raise ValueError("A subassembly needs at least two children.")

        child_ids = [c.id for c in self.children]
        if self.datum_child_id not in child_ids:
            raise ValueError("The selected datum child is not one of this subassembly's children.")

        total_features = sum(len(list(self._child_features(c))) for c in self.children)
        if total_features == 0:
            raise ValueError(
                "No features found on any child. "
                "Add features to the source parts before calculating."
            )

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

    def lock(self) -> None:
        """Permanently lock this subassembly. Called when it is consumed as
        a child of a higher-level subassembly."""
        self.is_locked = True

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

DARK_NAVY       = "#1B2A4A"
DARK_NAVY_HOVER = "#243B66"
WHITE_ROW       = "#FFFFFF"
LIGHT_ROW       = "#F0F4F8"
BORDER_BLUE     = "#8CA3C4"
MUTED_TEXT      = "#5B6B82"
SAMEBODY_BG     = "#E1F5E9"
SAMEBODY_TEXT   = "#1E6B3A"
FROZEN_BG       = "#E3E8EF"
FROZEN_TEXT     = "#33415C"
DRAFT_BG        = "#FFF4E0"
DRAFT_TEXT      = "#8A5A00"
FONT_STACK      = "'Segoe UI', Arial, sans-serif"
DECIMALS        = 2


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
            background-color: {FROZEN_BG};
            color: {FROZEN_TEXT};
            padding: 2px 9px;
            border-radius: 4px;
            font-size: 0.72rem;
            font-weight: 700;
            font-family: {FONT_STACK};
            letter-spacing: 0.03em;
            vertical-align: middle;
        }}
        .draft-badge {{
            display: inline-block;
            background-color: {DRAFT_BG};
            color: {DRAFT_TEXT};
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
            border: 1px solid {BORDER_BLUE};
            margin-bottom: 0.75rem;
        }}
        .results-table th {{
            background-color: {DARK_NAVY};
            color: #FFFFFF;
            font-weight: 700;
            text-align: center;
            padding: 9px 10px;
            border: 1px solid {BORDER_BLUE};
        }}
        .results-table td {{
            padding: 8px 10px;
            border: 1px solid {BORDER_BLUE};
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
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def styled_section_header(text: str) -> None:
    st.markdown(
        f"<div class='section-header'>{html.escape(text)}</div>",
        unsafe_allow_html=True,
    )


def styled_panel_title_with_badge(text: str, is_locked: bool) -> None:
    badge = (
        "<span class='frozen-badge'>FROZEN</span>"
        if is_locked
        else "<span class='draft-badge'>DRAFT</span>"
    )
    st.markdown(
        f"<span class='panel-title'>{html.escape(text)}</span>{badge}",
        unsafe_allow_html=True,
    )


def build_subassembly_table_html(sub: Subassembly) -> str:
    if not sub.frozen_results:
        return "<p style='color:#8A5A00; font-family: Arial, sans-serif; font-size:0.9rem;'>No results yet. Add features to source parts and click Recalculate.</p>"

    header = (
        "<tr>"
        "<th style='text-align:center;'>S. No.</th>"
        "<th style='text-align:center;'>Functional Feature Name</th>"
        "<th style='text-align:center;'>Component</th>"
        "<th style='text-align:center;'>Datum Reference</th>"
        "<th style='text-align:center;'>Effective RSS Tolerance (mm)</th>"
        "</tr>"
    )
    rows = []
    for idx, result in enumerate(sub.frozen_results.values(), start=1):
        bg = WHITE_ROW if idx % 2 == 1 else LIGHT_ROW
        val = f"{result.effective_tolerance:.{DECIMALS}f}"
        tol_cell = (
            f"{val}<br><span class='samebody-badge'>(same body)</span>"
            if result.same_body
            else val
        )
        rows.append(
            f"<tr style='background-color:{bg}; color:#1A1A1A;'>"
            f"<td style='text-align:left;'>{idx}</td>"
            f"<td style='text-align:left;'>{html.escape(result.feature_name)}</td>"
            f"<td style='text-align:left;'>{html.escape(result.source_part_name)}</td>"
            f"<td style='text-align:center;'>{html.escape(sub.datum_child_label)}</td>"
            f"<td style='text-align:center;'>{tol_cell}</td>"
            "</tr>"
        )
    return (
        f"<table class='results-table'><thead>{header}</thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def build_export_df(sub: Subassembly) -> pd.DataFrame:
    rows = []
    for idx, r in enumerate(sub.frozen_results.values(), start=1):
        rows.append({
            "S. No.": idx,
            "Functional Feature Name": r.feature_name,
            "Component": r.source_part_name,
            "Datum Reference": sub.datum_child_label,
            "Effective RSS Tolerance (mm)": f"{r.effective_tolerance:.{DECIMALS}f}",
            "Notes": "(same body)" if r.same_body else "",
        })
    return pd.DataFrame(rows)


# ============================================================
# 3. SESSION STATE HELPERS
# The core fix: always explicitly write back mutated objects into
# session_state by index. Streamlit does not reliably detect in-place
# mutations on objects stored in session_state lists, so we must
# reassign the slot directly to guarantee the change persists across
# st.rerun().
# ============================================================

def _save_part(part: Part) -> None:
    """Write a mutated Part back into session_state.parts by index."""
    for i, p in enumerate(st.session_state.parts):
        if p.id == part.id:
            st.session_state.parts[i] = part
            return


def _save_subassembly(sub: Subassembly) -> None:
    """Write a mutated Subassembly back into session_state.subassemblies by index."""
    for i, s in enumerate(st.session_state.subassemblies):
        if s.id == sub.id:
            st.session_state.subassemblies[i] = sub
            return


def _find_part(part_id: str) -> Part:
    return next(p for p in st.session_state.parts if p.id == part_id)


def _find_sub(sub_id: str) -> Subassembly:
    return next(s for s in st.session_state.subassemblies if s.id == sub_id)


def get_all_units() -> List[Union[Part, Subassembly]]:
    return st.session_state.parts + st.session_state.subassemblies


def get_available_units() -> List[Union[Part, Subassembly]]:
    return [u for u in get_all_units() if u.id in st.session_state.available_unit_ids]


def is_consumed(unit_id: str) -> bool:
    return unit_id not in st.session_state.available_unit_ids


# ============================================================
# 4. STREAMLIT UI
# ============================================================

st.set_page_config(page_title="Assembly Tolerance Propagation Tool", layout="wide")
inject_global_css()


def init_session_state() -> None:
    defaults: dict = {
        "parts": [],
        "subassemblies": [],
        "available_unit_ids": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()

st.title("Assembly Tolerance Propagation Tool")

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:

    # --- 1. Parts ---
    styled_section_header("1. Parts")
    with st.form("add_part_form", clear_on_submit=True):
        new_part_name = st.text_input("Part name")
        if st.form_submit_button("Add Part"):
            name = new_part_name.strip()
            if not name:
                st.error("Part name cannot be empty.")
            else:
                p = Part(name=name)
                st.session_state.parts.append(p)
                st.session_state.available_unit_ids.append(p.id)
                st.success(f"Added part '{name}'.")

    # --- 2. Features ---
    styled_section_header("2. Features")
    if not st.session_state.parts:
        st.info("Add a part before adding features.")
    else:
        part_options = {p.id: p.name for p in st.session_state.parts}
        with st.form("add_feature_form", clear_on_submit=True):
            target_part_id = st.selectbox(
                "Add a feature to which part?",
                options=list(part_options.keys()),
                format_func=lambda pid: part_options[pid],
            )
            feature_name   = st.text_input("Feature name")
            feature_tol    = st.number_input(
                "Feature tolerance (mm)", min_value=0.0, value=0.0,
                step=0.01, format=f"%.{DECIMALS}f",
            )
            if st.form_submit_button("Add Feature"):
                name = feature_name.strip()
                if not name:
                    st.error("Feature name cannot be empty.")
                elif feature_tol <= 0:
                    st.error("Feature tolerance must be greater than zero.")
                else:
                    # Get the part, mutate it, then write it back explicitly.
                    target_part = _find_part(target_part_id)
                    target_part.add_feature(name, round(feature_tol, DECIMALS))
                    _save_part(target_part)   # <-- explicit write-back
                    st.success(f"Added feature '{name}' to '{target_part.name}'.")

    for part in st.session_state.parts:
        label = part.name + ("  (used in subassembly)" if is_consumed(part.id) else "")
        with st.expander(label):
            if part.features:
                for f in part.features:
                    st.write(f"- {f.name}: {f.own_tolerance:.{DECIMALS}f} mm")
            else:
                st.caption("No features yet.")
            if not is_consumed(part.id):
                if st.button("Remove Part", key=f"rm_part_{part.id}"):
                    st.session_state.parts = [
                        p for p in st.session_state.parts if p.id != part.id
                    ]
                    st.session_state.available_unit_ids = [
                        uid for uid in st.session_state.available_unit_ids if uid != part.id
                    ]
                    st.rerun()

    st.divider()

    # --- 3. Build a Subassembly ---
    styled_section_header("3. Build a Subassembly")
    available_units = get_available_units()
    if len(available_units) < 2:
        st.info("You need at least two available parts or subassemblies to build a new subassembly.")
    else:
        unit_options = {u.id: u.name for u in available_units}
        selected_ids = st.multiselect(
            "Select which parts/subassemblies to join",
            options=list(unit_options.keys()),
            format_func=lambda uid: unit_options[uid],
            key="sub_children_select",
        )

        if len(selected_ids) < 2:
            st.caption("Select at least two to continue.")
        else:
            selected_units = [u for u in available_units if u.id in selected_ids]
            datum_opts     = {u.id: u.name for u in selected_units}
            datum_child_id = st.selectbox(
                "Which child carries the reference datum?",
                options=list(datum_opts.keys()),
                format_func=lambda uid: datum_opts[uid],
                key="sub_datum_select",
            )
            datum_unit = next(u for u in selected_units if u.id == datum_child_id)

            if isinstance(datum_unit, Subassembly):
                st.number_input(
                    "Datum tolerance (mm) — inherited",
                    value=float(datum_unit.datum_tolerance),
                    disabled=True, format=f"%.{DECIMALS}f",
                    key="sub_datum_tol_display",
                )
                datum_tol_value = datum_unit.datum_tolerance
            else:
                datum_tol_value = st.number_input(
                    "Datum tolerance (mm)", min_value=0.0, value=0.0,
                    step=0.01, format=f"%.{DECIMALS}f", key="sub_datum_tol_input",
                )

            iface_tol_value = st.number_input(
                "Interface tolerance (mm)", min_value=0.0, value=0.0,
                step=0.01, format=f"%.{DECIMALS}f", key="sub_iface_tol_input",
            )
            default_name   = f"Subassembly {len(st.session_state.subassemblies) + 1}"
            sub_name       = st.text_input("Name this subassembly", value=default_name, key="sub_name_input")
            st.caption(
                "Results start as DRAFT — add more features and Recalculate anytime. "
                "Becomes permanently FROZEN when used in the next stage."
            )

            if st.button("Calculate", type="primary"):
                name = sub_name.strip()
                if not name:
                    st.error("Subassembly name cannot be empty.")
                elif iface_tol_value <= 0:
                    st.error("Interface tolerance must be greater than zero.")
                elif datum_tol_value <= 0:
                    st.error("Datum tolerance must be greater than zero.")
                else:
                    new_sub = Subassembly(
                        name=name,
                        children=selected_units,
                        datum_child_id=datum_child_id,
                        datum_tolerance=round(datum_tol_value, DECIMALS),
                        interface_tolerance=round(iface_tol_value, DECIMALS),
                    )
                    try:
                        new_sub.calculate_and_freeze()
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        # Lock any Subassembly children — Parts are never locked.
                        for child in selected_units:
                            if isinstance(child, Subassembly):
                                child.lock()
                                _save_subassembly(child)   # <-- explicit write-back

                        # Remove consumed IDs, add new subassembly.
                        st.session_state.available_unit_ids = [
                            uid for uid in st.session_state.available_unit_ids
                            if uid not in selected_ids
                        ]
                        st.session_state.available_unit_ids.append(new_sub.id)
                        st.session_state.subassemblies.append(new_sub)
                        st.success(f"'{name}' calculated.")
                        st.rerun()


# ── Main panel ───────────────────────────────────────────────────────────────
if st.session_state.subassemblies:
    for sub in st.session_state.subassemblies:
        styled_panel_title_with_badge(sub.name, sub.is_locked)
        st.markdown(
            f"<div class='stage-meta'>"
            f"Joined: {html.escape(', '.join(sub.child_names))} &nbsp;|&nbsp; "
            f"Datum: {html.escape(sub.datum_child_label)} ({sub.datum_tolerance:.{DECIMALS}f} mm) &nbsp;|&nbsp; "
            f"Interface: {sub.interface_tolerance:.{DECIMALS}f} mm"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown(build_subassembly_table_html(sub), unsafe_allow_html=True)

        btn_col, export_col = st.columns([1, 2])

        with btn_col:
            if not sub.is_locked:
                if st.button("Recalculate", key=f"recalc_{sub.id}"):
                    try:
                        sub.calculate_and_freeze()
                        _save_subassembly(sub)   # <-- explicit write-back: THE CORE FIX
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.success(f"'{sub.name}' recalculated.")
                        st.rerun()

        with export_col:
            export_df  = build_export_df(sub)
            csv_bytes  = export_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                f"Export '{sub.name}' to CSV",
                data=csv_bytes,
                file_name=f"{sub.name.replace(' ', '_')}_results.csv",
                mime="text/csv",
                key=f"export_{sub.id}",
            )

        if not sub.is_locked:
            st.caption(
                "DRAFT — add features to source parts and click Recalculate to update. "
                "Becomes FROZEN when selected as a child in the next stage."
            )
        st.divider()
else:
    st.info("Add parts and features in the sidebar, then build a subassembly to see results here.")
