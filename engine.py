"""
engine.py

Calculation engine for the Assembly Tolerance Propagation Tool.

This module contains all data models and business logic for GD&T
(Geometric Dimensioning & Tolerancing) tolerance stack-up analysis in
automotive Body-in-White (BIW) assemblies. It has zero UI dependencies
and can be imported, instantiated, and tested completely independently
of any front end (e.g. Streamlit).

Tolerance propagation method (default): Root Sum Square (RSS).

    T_effective = sqrt(sum(T_i ** 2 for T_i in tolerance_stack))

Business Rule (must hold exactly):
    If a feature belongs to the SAME component as the reference datum,
    its effective tolerance equals its own feature tolerance ONLY. The
    datum tolerance is excluded and no interfaces are traversed / no
    stack-up occurs.

    If the feature is on a DIFFERENT component than the datum, the
    effective tolerance is the RSS (or other configured combination)
    of: the datum tolerance, every interface tolerance crossed along
    the shortest (hop-count) path from the datum component to the
    feature's component, and the feature's own tolerance.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import networkx as nx


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Component:
    """A physical sheet-metal part/body in the BIW assembly.

    Attributes:
        name: Human-readable component name (e.g. "Part1", "A-Pillar").
        id: Unique identifier, auto-generated with uuid4. This is never
            supplied by the caller/user directly.
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
            Positivity is enforced by the caller (e.g. the UI layer),
            not by this dataclass.
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
    The engine always treats an Interface as a bidirectional connection
    when building the assembly graph, and all lookups check both
    orderings of the two ids.

    Attributes:
        component_1_id: Id of one of the two connected components.
        component_2_id: Id of the other connected component.
        tolerance: The interface (joint) tolerance, in mm.
    """

    component_1_id: str
    component_2_id: str
    tolerance: float


# ---------------------------------------------------------------------------
# Tolerance combination strategies (extensibility point)
# ---------------------------------------------------------------------------
#
# A combination method takes the ordered list of tolerance values collected
# along a stack-up path and returns a single effective tolerance. Swapping
# the `method` argument passed to Assembly.calculate_effective_tolerance /
# Assembly.calculate_all is all that's needed to support alternative
# propagation methods (Worst Case, Monte Carlo, etc.) later, WITHOUT
# modifying the UI or the Assembly class structure.

ToleranceCombinationMethod = Callable[[List[float]], float]


def rss_combine(tolerance_stack: List[float]) -> float:
    """Root Sum Square combination: sqrt(sum(t ** 2 for t in stack)).

    This is the default and currently the only method wired into the UI.
    """
    return math.sqrt(sum(t ** 2 for t in tolerance_stack))


def worst_case_combine(tolerance_stack: List[float]) -> float:
    """Worst Case (linear addition) combination: sum(stack).

    Provided as a ready-made example of an alternative propagation
    method that can be swapped in later without touching the Assembly
    class or the UI. Not used by default.
    """
    return sum(tolerance_stack)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


@dataclass
class Assembly:
    """The full BIW assembly: components, features, interfaces, and datum.

    Attributes:
        components: All Component objects in the assembly.
        features: All Feature objects in the assembly.
        interfaces: All Interface objects (undirected joints) in the
            assembly.
        reference_datum_component_id: Id of the Component chosen as the
            assembly's reference datum, or None if not yet set.
        reference_datum_tolerance: Tolerance value of the reference
            datum, in mm, or None if not yet set.
    """

    components: List[Component] = field(default_factory=list)
    features: List[Feature] = field(default_factory=list)
    interfaces: List[Interface] = field(default_factory=list)
    reference_datum_component_id: Optional[str] = None
    reference_datum_tolerance: Optional[float] = None

    # -- Graph construction ---------------------------------------------

    def build_graph(self) -> nx.Graph:
        """Build an undirected graph representing the assembly.

        Nodes are component ids. Each Interface becomes a single
        undirected edge between its two component ids, carrying the
        interface's tolerance value under the 'tolerance' edge
        attribute. Components with no interfaces are still added as
        isolated nodes so every component exists in the graph.

        Cyclic connectivity (e.g. A-B, B-C, A-C) is fully supported
        since this is a plain networkx.Graph, not a tree.

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

    # -- Path finding -----------------------------------------------------

    def find_path(self, from_component_id: str, to_component_id: str) -> List[str]:
        """Find the shortest path (by hop count) between two components.

        Uses nx.shortest_path with no weight argument, so the path
        returned has the fewest interfaces (hops) — it is NOT weighted
        by tolerance magnitude. This is the intended behaviour: the
        number of physical part-to-part joints on the path determines
        the RSS stack, not the size of any tolerance value.

        Args:
            from_component_id: Id of the starting component (typically
                the reference datum component).
            to_component_id: Id of the destination component (typically
                a feature's component).

        Returns:
            A list of component ids representing the shortest path,
            inclusive of both endpoints. If from_component_id equals
            to_component_id, returns a single-element list.

        Raises:
            networkx.NetworkXNoPath: If no path exists between the two
                components (disconnected graph).
            networkx.NodeNotFound: If either component id is not a node
                in the graph.
        """
        graph = self.build_graph()
        return nx.shortest_path(graph, source=from_component_id, target=to_component_id)

    # -- Lookups ------------------------------------------------------------

    def get_interface_tolerance(self, component_a_id: str, component_b_id: str) -> float:
        """Look up the tolerance of the interface between two adjacent components.

        Interfaces are undirected, so both orderings of the two
        component ids are checked.

        Args:
            component_a_id: Id of one component in the interface.
            component_b_id: Id of the other component in the interface.

        Returns:
            The tolerance (mm) of the matching interface.

        Raises:
            ValueError: If no interface exists between the two given
                components.
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
        """Return the Component with the given id, or None if not found.

        Args:
            component_id: The id to look up.

        Returns:
            The matching Component, or None if no component has that id.
        """
        for component in self.components:
            if component.id == component_id:
                return component
        return None

    # -- Stack collection & calculation --------------------------------------

    def collect_tolerance_stack(self, feature: Feature) -> List[float]:
        """Collect the ordered list of tolerance values for a feature's stack-up.

        Business Rule:
            If the feature is on the same component as the reference
            datum, the stack is simply [feature.tolerance] — the datum
            tolerance is excluded and no interfaces are traversed.

            Otherwise, the stack is:
                [datum_tolerance, interface_1, interface_2, ..., feature.tolerance]
            where interface_1 .. interface_n are the tolerances of each
            interface crossed along the shortest path from the datum
            component to the feature's component, in path order.

        Args:
            feature: The Feature to build a tolerance stack for.

        Returns:
            An ordered list of tolerance values (floats), ready to be
            passed to a ToleranceCombinationMethod.

        Raises:
            ValueError: If no reference datum has been set on this
                Assembly.
            networkx.NetworkXNoPath: If there is no path between the
                datum component and the feature's component.
            networkx.NodeNotFound: If either component id is missing
                from the graph.
        """
        if self.reference_datum_component_id is None or self.reference_datum_tolerance is None:
            raise ValueError("Reference datum has not been set on this Assembly.")

        # Business rule: feature on the datum's own component -> no stack-up.
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
        """Calculate a single feature's effective tolerance at the assembly level.

        Args:
            feature: The Feature to calculate the effective tolerance for.
            method: The combination method applied to the tolerance
                stack. Defaults to Root Sum Square (rss_combine). Pass a
                different callable (e.g. worst_case_combine) to use an
                alternative propagation method without changing the
                Assembly class or the UI.

        Returns:
            The effective tolerance, in mm.

        Raises:
            ValueError: If no reference datum has been set.
            networkx.NetworkXNoPath: If no path exists between the datum
                component and the feature's component.
            networkx.NodeNotFound: If either component id is missing
                from the graph.
        """
        stack = self.collect_tolerance_stack(feature)
        return method(stack)

    def calculate_all(
        self,
        method: ToleranceCombinationMethod = rss_combine,
    ) -> Dict[str, Dict]:
        """Calculate effective tolerances for every feature in the assembly.

        For each feature, attempts to compute the effective tolerance,
        the human-readable path of component names traversed, and the
        raw tolerance stack that was combined. If no path exists
        between the datum component and the feature's component
        (disconnected graph), that feature's entry records the failure
        instead of raising, so one disconnected feature does not
        prevent results for the rest of the assembly.

        Args:
            method: The combination method to apply to each feature's
                tolerance stack. Defaults to Root Sum Square.

        Returns:
            A dict keyed by feature_id. Each value is a dict with:
                - 'effective_tolerance': float, or None if no path was
                  found.
                - 'path': list of human-readable component names along
                  the traversal (datum -> ... -> feature's component),
                  or an empty list if no path was found.
                - 'tolerance_stack': list of float values that were
                  combined, or an empty list if no path was found.
                - 'error': None, or a short message such as
                  "No path found" when the feature could not be
                  connected to the datum.

        Raises:
            ValueError: If no reference datum has been set on this
                Assembly. (Calculation is only meaningful once a datum
                exists; the UI is expected to prevent calling this
                before a datum is selected.)
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
