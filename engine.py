"""
app.py

Assembly Tolerance Propagation Tool
------------------------------------
A single-file Streamlit application for GD&T (Geometric Dimensioning &
Tolerancing) tolerance stack-up analysis in automotive Body-in-White
(BIW) assemblies.

This file is organized into two clearly separated sections:

    1. CALCULATION ENGINE  - pure Python + networkx, no Streamlit calls.
                              (Component, Feature, Interface, Assembly)
    2. STREAMLIT UI         - everything that touches st.*, session
                              state, input validation, and rendering.

They are combined into one file purely for simplicity of deployment
(single "main module" for Streamlit Cloud). The engine section still
has zero UI dependencies internally and could be lifted into its own
engine.py later with no changes.

Tolerance propagation method: Root Sum Square (RSS).
    T_effective = sqrt(sum(T_i ** 2 for T_i in tolerance_stack))

Business Rule:
    If a feature belongs to the same component as the reference datum,
    its effective tolerance equals its own feature tolerance only (the
    datum tolerance is excluded, no stack-up occurs). Otherwise, the
    effective tolerance is the RSS of the datum tolerance, every
    interface tolerance crossed along the shortest path from the datum
    component to the feature's component, and the feature's own
    tolerance.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import networkx as nx
import pandas as pd
import streamlit as st


# =============================================================================
# 1. CALCULATION ENGINE (no Streamlit / UI dependencies)
# =============================================================================


@dataclass
class Component:
    """A physical sheet-metal part/body in the BIW assembly.

    Attributes:
        name: Human-readable component name (e.g. "Part1", "A-Pillar").
        id: Unique identifier, auto-generated with uuid4. Never supplied
            by the caller/user directly.
    """

    name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class Feature:
    """A toleranced feature (hole, slot, etc.) located on a Component.

    Attributes:
        name: Human-readable feature name (e.g. "Hole A").
        component_id: The id of the Component this feature belongs to.
        tolerance: The feature's own positional tolerance, in mm.
        id: Unique identifier, auto-generated with uuid4.
    """

    name: str
    component_id: str
    tolerance: float
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class Interface:
    """An undirected part-to-part joint between two components.

    Interfaces are undirected: component_1_id and component_2_id are
    merely labels for "one side" and "the other side" of the joint.
    The engine always treats an Interface as bidirectional, and all
    lookups check both orderings of the two ids.

    Attributes:
        component_1_id: Id of one of the two connected components.
        component_2_id: Id of the other connected component.
        tolerance: The interface (joint) tolerance, in mm.
    """

    component_1_id: str
    component_2_id: str
    tolerance: float


# -- Tolerance combination strategies (extensibility point) -----------------
#
# A combination method takes the ordered tolerance stack and returns a
# single effective tolerance. Swapping the `method` argument on
# Assembly.calculate_effective_tolerance / calculate_all is all that's
# needed to support alternative propagation methods (Worst Case, Monte
# Carlo, etc.) later, without touching the UI or the Assembly class.

ToleranceCombinationMethod = Callable[[List[float]], float]


def rss_combine(tolerance_stack: List[float]) -> float:
    """Root Sum Square combination: sqrt(sum(t ** 2 for t in stack))."""
    return math.sqrt(sum(t ** 2 for t in tolerance_stack))


def worst_case_combine(tolerance_stack: List[float]) -> float:
    """Worst Case (linear addition) combination: sum(stack).

    Example of an alternative propagation method that can be swapped in
    later without modifying the Assembly class or the UI. Not used by
    default.
    """
    return sum(tolerance_stack)


@dataclass
class Assembly:
    """The full BIW assembly: components, features, interfaces, and datum.

    Attributes:
        components: All Component objects in the assembly.
        features: All Feature objects in the assembly.
        interfaces: All Interface objects (undirected joints).
        reference_datum_component_id: Id of the datum Component, or None.
        reference_datum_tolerance: Datum tolerance in mm, or None.
    """

    components: List[Component] = field(default_factory=list)
    features: List[Feature] = field(default_factory=list)
    interfaces: List[Interface] = field(default_factory=list)
    reference_datum_component_id: Optional[str] = None
    reference_datum_tolerance: Optional[float] = None

    def build_graph(self) -> nx.Graph:
        """Build an undirected graph of the assembly.

        Nodes are component ids. Each Interface becomes an undirected
        edge carrying its tolerance under the 'tolerance' edge
        attribute. Cyclic connectivity is fully supported since this is
        a plain networkx.Graph, not a tree.

        Returns:
            An nx.Graph representing the assembly's connectivity.
        """
        graph = nx.Graph()
        for component in self.components:
            graph.add_node(component.id)
        for interface in self.interfaces:
            graph.add_edge(
                interface.component_1_id,
                interface.component_2_id,
                tolerance=interface.tolerance,
            )
        return graph

    def find_path(self, from_component_id: str, to_component_id: str) -> List[str]:
        """Find the shortest path (by hop count) between two components.

        Uses nx.shortest_path with no weight argument, so the path
        returned has the fewest interfaces (hops), not the smallest
        cumulative tolerance.

        Raises:
            networkx.NetworkXNoPath: If no path exists (disconnected).
            networkx.NodeNotFound: If either id is not in the graph.
        """
        graph = self.build_graph()
        return nx.shortest_path(graph, source=from_component_id, target=to_component_id)

    def get_interface_tolerance(self, component_a_id: str, component_b_id: str) -> float:
        """Look up the tolerance of the interface between two adjacent components.

        Checks both orderings since interfaces are undirected.

        Raises:
            ValueError: If no interface exists between the two components.
        """
        for interface in self.interfaces:
            same_order = (
                interface.component_1_id == component_a_id
                and interface.component_2_id == component_b_id
            )
            reverse_order = (
                interface.component_1_id == component_b_id
                and interface.component_2_id == component_a_id
            )
            if same_order or reverse_order:
                return interface.tolerance
        raise ValueError(
            f"No interface found between components '{component_a_id}' and '{component_b_id}'."
        )

    def get_component_by_id(self, component_id: str) -> Optional[Component]:
        """Return the Component with the given id, or None if not found."""
        for component in self.components:
            if component.id == component_id:
                return component
        return None

    def collect_tolerance_stack(self, feature: Feature) -> List[float]:
        """Collect the ordered tolerance values for a feature's stack-up.

        Business Rule: if the feature is on the same component as the
        datum, returns [feature.tolerance] only. Otherwise returns
        [datum_tolerance, interface_1, ..., interface_n, feature.tolerance]
        along the shortest path from datum to feature's component.

        Raises:
            ValueError: If no reference datum has been set.
            networkx.NetworkXNoPath / NodeNotFound: If unreachable.
        """
        if self.reference_datum_component_id is None or self.reference_datum_tolerance is None:
            raise ValueError("Reference datum has not been set on this Assembly.")

        if feature.component_id == self.reference_datum_component_id:
            return [feature.tolerance]

        path = self.find_path(self.reference_datum_component_id, feature.component_id)
        stack: List[float] = [self.reference_datum_tolerance]
        for i in range(len(path) - 1):
            stack.append(self.get_interface_tolerance(path[i], path[i + 1]))
        stack.append(feature.tolerance)
        return stack

    def calculate_effective_tolerance(
        self,
        feature: Feature,
        method: ToleranceCombinationMethod = rss_combine,
    ) -> float:
        """Calculate a single feature's effective tolerance.

        Args:
            feature: The Feature to calculate for.
            method: Combination method (defaults to RSS). Swap this to
                use an alternative propagation method later.
        """
        stack = self.collect_tolerance_stack(feature)
        return method(stack)

    def calculate_all(
        self,
        method: ToleranceCombinationMethod = rss_combine,
    ) -> Dict[str, Dict]:
        """Calculate effective tolerances for every feature in the assembly.

        Disconnected features (no path from datum) do not raise; their
        entry records the failure instead so the rest of the assembly
        still gets results.

        Returns:
            Dict keyed by feature_id -> {
                'effective_tolerance': float or None,
                'path': list of component names, or [],
                'tolerance_stack': list of floats, or [],
                'error': None or a short message like "No path found",
            }

        Raises:
            ValueError: If no reference datum has been set.
        """
        if self.reference_datum_component_id is None or self.reference_datum_tolerance is None:
            raise ValueError("Reference datum has not been set on this Assembly.")

        results: Dict[str, Dict] = {}
        for feature in self.features:
            try:
                stack = self.collect_tolerance_stack(feature)
                effective = method(stack)

                if feature.component_id == self.reference_datum_component_id:
                    path_ids = [feature.component_id]
                else:
                    path_ids = self.find_path(
                        self.reference_datum_component_id, feature.component_id
                    )

                path_names = [
                    (self.get_component_by_id(cid).name if self.get_component_by_id(cid) else cid)
                    for cid in path_ids
                ]

                results[feature.id] = {
                    "effective_tolerance": effective,
                    "path": path_names,
                    "tolerance_stack": stack,
                    "error": None,
                }
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                results[feature.id] = {
                    "effective_tolerance": None,
                    "path": [],
                    "tolerance_stack": [],
                    "error": "No path found",
                }
        return results


# =============================================================================
# 2. STREAMLIT UI
# =============================================================================

st.set_page_config(page_title="Assembly Tolerance Propagation Tool", layout="wide")


# -- Session state -------------------------------------------------------

def init_session_state() -> None:
    """Initialize all required session_state keys exactly once.

    The tool starts completely empty; no sample data is pre-loaded.
    """
    defaults = {
        "components": [],       # list[Component]
        "interfaces": [],       # list[Interface]
        "features": [],         # list[Feature]
        "results": None,        # dict returned by calculate_all(), or None
        "datum_component_id": None,   # str or None
        "datum_tolerance": None,      # float or None
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()


def get_current_assembly() -> Assembly:
    """Build an Assembly snapshot from the current session_state."""
    return Assembly(
        components=st.session_state.components,
        features=st.session_state.features,
        interfaces=st.session_state.interfaces,
        reference_datum_component_id=st.session_state.datum_component_id,
        reference_datum_tolerance=st.session_state.datum_tolerance,
    )


def interface_exists(component_1_id: str, component_2_id: str) -> bool:
    """Check whether an interface already exists between two components (either order)."""
    for iface in st.session_state.interfaces:
        if {iface.component_1_id, iface.component_2_id} == {component_1_id, component_2_id}:
            return True
    return False


def remove_component(component_id: str) -> None:
    """Remove a component and cascade-delete any interfaces/features that reference it.

    If the removed component was the reference datum, the datum
    selection is cleared. Any existing results are invalidated since
    the underlying data changed.
    """
    st.session_state.components = [
        c for c in st.session_state.components if c.id != component_id
    ]
    st.session_state.interfaces = [
        i for i in st.session_state.interfaces
        if component_id not in (i.component_1_id, i.component_2_id)
    ]
    st.session_state.features = [
        f for f in st.session_state.features if f.component_id != component_id
    ]
    if st.session_state.datum_component_id == component_id:
        st.session_state.datum_component_id = None
        st.session_state.datum_tolerance = None
    st.session_state.results = None


def remove_interface(index: int) -> None:
    """Remove an interface by its position in the list and invalidate results."""
    st.session_state.interfaces.pop(index)
    st.session_state.results = None


def remove_feature(feature_id: str) -> None:
    """Remove a feature by id and invalidate results."""
    st.session_state.features = [
        f for f in st.session_state.features if f.id != feature_id
    ]
    st.session_state.results = None


def render_bfs_tree(assembly: Assembly) -> str:
    """Render the BFS spanning tree rooted at the current datum as formatted text.

    Example output:
        [Datum] Part A  (datum tolerance: 0.1000 mm)
            connects to Part B  (interface: 0.1200 mm)
            connects to Part C  (interface: 0.0800 mm)

    Components unreachable from the datum simply do not appear (their
    features will show "No path found" in the results table instead).
    """
    graph = assembly.build_graph()
    datum_id = assembly.reference_datum_component_id

    if datum_id is None or datum_id not in graph:
        return "No reference datum selected."

    bfs_tree = nx.bfs_tree(graph, source=datum_id)
    lines: List[str] = []

    def comp_name(cid: str) -> str:
        comp = assembly.get_component_by_id(cid)
        return comp.name if comp else cid

    def walk(node: str, parent: Optional[str], depth: int) -> None:
        name = comp_name(node)
        if parent is None:
            datum_tol = assembly.reference_datum_tolerance or 0.0
            lines.append(f"[Datum] {name}  (datum tolerance: {datum_tol:.4f} mm)")
        else:
            tol = graph[parent][node]["tolerance"]
            indent = "    " * (depth - 1)
            lines.append(f"{indent}connects to {name}  (interface: {tol:.4f} mm)")
        for child in sorted(bfs_tree.successors(node), key=comp_name):
            walk(child, node, depth + 1)

    walk(datum_id, None, 0)
    return "\n".join(lines)


def build_results_dataframe(assembly: Assembly, results: Dict[str, Dict]) -> pd.DataFrame:
    """Build the results table shown in the UI (and used for CSV export).

    Columns: Feature | Component | Own Tolerance (mm) |
             Effective RSS Tolerance (mm) | Path | Tolerance Stack

    All tolerance values are rounded to 4 decimal places. Features with
    no path to the datum show "No path found" instead of a value.
    """
    rows = []
    for feature in assembly.features:
        comp = assembly.get_component_by_id(feature.component_id)
        comp_name = comp.name if comp else feature.component_id
        entry = results.get(feature.id, {})

        if entry.get("error"):
            effective_display = "No path found"
            path_display = "No path found"
            stack_display = "No path found"
        else:
            effective_display = f"{round(entry['effective_tolerance'], 4):.4f}"
            path_display = " \u2192 ".join(entry["path"])
            stack_display = str([round(v, 4) for v in entry["tolerance_stack"]])

        rows.append(
            {
                "Feature": feature.name,
                "Component": comp_name,
                "Own Tolerance (mm)": round(feature.tolerance, 4),
                "Effective RSS Tolerance (mm)": effective_display,
                "Path": path_display,
                "Tolerance Stack": stack_display,
            }
        )
    return pd.DataFrame(rows)


# -- Sidebar: all inputs --------------------------------------------------

st.title("Assembly Tolerance Propagation Tool")

with st.sidebar:

    # --- Section 1: Components ---
    st.header("1. Components")
    with st.form("add_component_form", clear_on_submit=True):
        new_component_name = st.text_input("Component name")
        add_component_submitted = st.form_submit_button("Add Component")
        if add_component_submitted:
            name = new_component_name.strip()
            if not name:
                st.error("Component name cannot be empty.")
            else:
                st.session_state.components.append(Component(name=name))
                st.session_state.results = None
                st.success(f"Added component '{name}'.")

    for comp in st.session_state.components:
        col1, col2 = st.columns([4, 1])
        col1.write(comp.name)
        if col2.button("Remove", key=f"remove_component_{comp.id}"):
            remove_component(comp.id)
            st.rerun()

    st.divider()

    # --- Section 2: Interfaces ---
    st.header("2. Interfaces")
    if len(st.session_state.components) < 2:
        st.info("Add at least two components before creating an interface.")
    else:
        comp_options = {c.id: c.name for c in st.session_state.components}
        comp_ids = list(comp_options.keys())

        with st.form("add_interface_form", clear_on_submit=True):
            comp_1_id = st.selectbox(
                "Select Component 1", options=comp_ids,
                format_func=lambda cid: comp_options[cid], key="iface_comp1",
            )
            comp_2_id = st.selectbox(
                "Select Component 2", options=comp_ids,
                format_func=lambda cid: comp_options[cid], key="iface_comp2",
            )
            interface_tolerance = st.number_input(
                "Interface Tolerance (mm)", min_value=0.0, value=0.0,
                step=0.01, format="%.4f",
            )
            add_interface_submitted = st.form_submit_button("Add Interface")
            if add_interface_submitted:
                if comp_1_id == comp_2_id:
                    st.error("An interface cannot connect a component to itself.")
                elif interface_tolerance <= 0:
                    st.error("Interface tolerance must be a positive number greater than zero.")
                elif interface_exists(comp_1_id, comp_2_id):
                    st.error("An interface between these two components already exists.")
                else:
                    st.session_state.interfaces.append(
                        Interface(
                            component_1_id=comp_1_id,
                            component_2_id=comp_2_id,
                            tolerance=interface_tolerance,
                        )
                    )
                    st.session_state.results = None
                    st.success("Interface added.")

    for idx, iface in enumerate(st.session_state.interfaces):
        comp_options_all = {c.id: c.name for c in st.session_state.components}
        name_1 = comp_options_all.get(iface.component_1_id, "?")
        name_2 = comp_options_all.get(iface.component_2_id, "?")
        col1, col2 = st.columns([4, 1])
        col1.write(f"{name_1} \u2014 {name_2}: {round(iface.tolerance, 4)} mm")
        if col2.button("Remove", key=f"remove_interface_{idx}"):
            remove_interface(idx)
            st.rerun()

    st.divider()

    # --- Section 3: Features ---
    st.header("3. Features")
    if len(st.session_state.components) == 0:
        st.info("Add at least one component before adding features.")
    else:
        comp_options = {c.id: c.name for c in st.session_state.components}
        comp_ids = list(comp_options.keys())

        with st.form("add_feature_form", clear_on_submit=True):
            feature_name = st.text_input("Feature name")
            feature_component_id = st.selectbox(
                "Select which component this feature belongs to",
                options=comp_ids, format_func=lambda cid: comp_options[cid],
            )
            feature_tolerance = st.number_input(
                "Feature tolerance (mm)", min_value=0.0, value=0.0,
                step=0.01, format="%.4f",
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
                        Feature(
                            name=name,
                            component_id=feature_component_id,
                            tolerance=feature_tolerance,
                        )
                    )
                    st.session_state.results = None
                    st.success(f"Added feature '{name}'.")

    for feat in st.session_state.features:
        comp_options_all = {c.id: c.name for c in st.session_state.components}
        comp_name = comp_options_all.get(feat.component_id, "?")
        col1, col2 = st.columns([4, 1])
        col1.write(f"{feat.name} ({comp_name}): {round(feat.tolerance, 4)} mm")
        if col2.button("Remove", key=f"remove_feature_{feat.id}"):
            remove_feature(feat.id)
            st.rerun()

    st.divider()

    # --- Section 4: Reference Datum ---
    st.header("4. Reference Datum")
    if len(st.session_state.components) == 0:
        st.info("Add at least one component to select a reference datum.")
    else:
        comp_options = {c.id: c.name for c in st.session_state.components}
        comp_ids = list(comp_options.keys())

        default_index = 0
        if st.session_state.datum_component_id in comp_ids:
            default_index = comp_ids.index(st.session_state.datum_component_id)

        selected_datum_id = st.selectbox(
            "Select datum component", options=comp_ids,
            format_func=lambda cid: comp_options[cid],
            index=default_index, key="datum_select",
        )
        selected_datum_tolerance = st.number_input(
            "Datum tolerance (mm)", min_value=0.0,
            value=float(st.session_state.datum_tolerance or 0.0),
            step=0.01, format="%.4f", key="datum_tol_input",
        )
        st.session_state.datum_component_id = selected_datum_id
        st.session_state.datum_tolerance = selected_datum_tolerance

    st.divider()

    # --- Section 5: Action ---
    st.header("5. Action")

    datum_missing = st.session_state.datum_component_id is None
    datum_invalid = (
        st.session_state.datum_tolerance is None
        or st.session_state.datum_tolerance <= 0
    )
    calculate_disabled = datum_missing or datum_invalid

    if datum_missing:
        st.warning("Select a reference datum component before calculating.")
    elif datum_invalid:
        st.warning("Enter a positive datum tolerance before calculating.")

    if st.button("Calculate", disabled=calculate_disabled):
        assembly = get_current_assembly()
        try:
            st.session_state.results = assembly.calculate_all()
        except ValueError as exc:
            st.session_state.results = None
            st.error(str(exc))

    if st.session_state.results is not None:
        export_assembly = get_current_assembly()
        export_df = build_results_dataframe(export_assembly, st.session_state.results)
        csv_data = export_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Export Results to CSV",
            data=csv_data,
            file_name="tolerance_results.csv",
            mime="text/csv",
        )
    else:
        st.download_button("Export Results to CSV", data="", disabled=True)


# -- Main panel -------------------------------------------------------------

if st.session_state.results is not None:
    assembly = get_current_assembly()

    left_col, right_col = st.columns(2)

    with left_col:
        st.subheader("Assembly Connectivity")
        st.text(render_bfs_tree(assembly))

    with right_col:
        st.subheader("Results Table")
        results_df = build_results_dataframe(assembly, st.session_state.results)
        st.dataframe(results_df, use_container_width=True, hide_index=True)
else:
    st.info("Add components, interfaces, and features in the sidebar, select a reference datum, then click Calculate.")
