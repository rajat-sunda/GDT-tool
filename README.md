# Assembly Tolerance Propagation Tool

## 1. What this tool does

This tool calculates the effective (assembly-level) positional tolerance of a
feature — a hole, a slot, any toleranced GD&T feature — after it has passed
through however many part-to-part joints separate it from your reference
datum. In a Body-in-White assembly, a feature's tolerance on its own part
drawing is never the whole story: every interface it stacks through on the
way back to the datum adds its own variation. This tool builds a graph of
your assembly (components as nodes, interfaces as edges), walks the shortest
path from the datum to each feature, and combines every tolerance on that
path using **Root Sum Square (RSS)**. Change the datum, add a component,
remove an interface — the tool recalculates every feature's effective
tolerance and the path it traveled, automatically.

## 2. How to install and run

**Requirements:** Python 3.9 or above.

1. Open a terminal and navigate to the project folder (the one containing
   `app.py` and `requirements.txt`).
2. Install the dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Launch the app:
   ```
   streamlit run app.py
   ```
4. Streamlit will start a local server and print a URL in the terminal —
   normally:
   ```
   http://localhost:8501
   ```
   Open that address in your browser. If it doesn't open automatically,
   copy-paste the URL yourself.

## 3. How to use the tool — step by step

1. **Add your components.** In the sidebar, under "1. Components," type a
   part name (e.g. "Part A") and click **Add Component**. Repeat for every
   component in the assembly. Each one appears in a list below the form,
   with a Remove button if you need to delete it.

2. **Add the interfaces between components.** Under "2. Interfaces," pick
   the two components that are joined, and enter the **interface
   tolerance** — this is the positional variation that the joint itself
   contributes (weld nugget location tolerance, locator pin clearance,
   fixture repeatability, etc. — whatever variation that specific joint
   physically introduces between the two parts). Click **Add Interface**.
   You need at least two components before this section becomes active.

3. **Add your features.** Under "3. Features," give the feature a name
   (e.g. "Hole 1"), choose which component it lives on, and enter its own
   positional tolerance from the part's drawing. Click **Add Feature**.

4. **Select the reference datum.** Under "4. Reference Datum," pick which
   component is the assembly's datum reference, and enter that datum's own
   tolerance (its locating/fixturing tolerance at the assembly level).

5. **Click Calculate.** The button is disabled until a datum is selected
   with a positive tolerance. Once you click it, the main panel appears
   with two views:
   - **Assembly Connectivity** (left): a tree showing the datum and every
     component reachable from it, with the interface tolerance crossed to
     reach each one.
   - **Results Table** (right): every feature you entered, its component,
     the current datum reference, and its calculated effective RSS
     tolerance. Features on the same component as the datum are marked
     "(same body)" since no stack-up applies to them. Features with no
     connection to the datum (a disconnected part of the assembly) show
     "No path found" instead of crashing the tool.

6. **Change the datum and recalculate.** Pick a different datum component
   in Section 4, adjust its tolerance if needed, and click **Calculate**
   again. Nothing about the assembly graph changes — only the paths and
   results are recomputed from the new starting point. This is a normal
   part of BIW analysis: you'll often want to see how the same assembly
   looks from a different reference.

7. **Export to CSV.** Once you've calculated results, the **Export Results
   to CSV** button becomes active. It downloads a spreadsheet-friendly file
   with the same feature-by-feature results, plus a Notes column flagging
   "(same body)" or "No path found" in plain text.

## 4. How the calculation works

The core formula is Root Sum Square:

```
T_effective = sqrt(T1² + T2² + T3² + ...)
```

For a feature that is **not** on the same component as the datum, the terms
being combined are:

- the **datum tolerance**,
- the tolerance of **every interface** crossed along the shortest path from
  the datum's component to the feature's component, in order,
- and the **feature's own tolerance**.

**Business rule:** if the feature is on the *same* component as the current
datum, none of that applies — its effective tolerance is simply its own
tolerance, full stop. No datum tolerance is added, no interfaces are
crossed, no RSS is performed, because there's no physical joint between the
datum and the feature to introduce variation.

**Why RSS instead of adding tolerances directly (worst case)?** Worst-case
addition assumes every contributor hits its maximum deviation at the same
time, in the same direction — which is statistically very unlikely in a
real production run. RSS treats each contributor as an independent random
variable and combines them the way independent variances actually combine,
giving a realistic (rather than overly conservative) picture of expected
stack-up.

All tolerance values entered and displayed in this tool are rounded to
**2 decimal places**.

## 5. Worked examples

You can enter each of these from scratch to confirm the tool is behaving
correctly.

### Example 1 — Two components, one interface

- Components: `Part A`, `Part B`
- Interface: Part A ↔ Part B, tolerance = **0.10**
- Datum: Part A, datum tolerance = **0.10**
- Features:
  - Hole 1 on Part A, tolerance = **0.05**
  - Hole 2 on Part B, tolerance = **0.05**

**Expected results:**
- Hole 1 → **0.05**. It's on the same component as the datum, so the
  business rule applies: its own tolerance only, no stack-up.
- Hole 2 → **0.15**. It's on a different component, one interface away:
  `sqrt(0.10² + 0.10² + 0.05²) = sqrt(0.0225) = 0.15`.

### Example 2 — Three components in a chain

- Components: `Part A`, `Part B`, `Part C`
- Interfaces: A ↔ B = **0.10**, B ↔ C = **0.08**
- Datum: Part A, datum tolerance = **0.10**
- Features: one hole on each part, each with tolerance **0.05**

**Expected results:**
- Hole on Part A → **0.05**. Same component as the datum — own tolerance
  only.
- Hole on Part B → **0.15**. One interface from the datum:
  `sqrt(0.10² + 0.10² + 0.05²) = 0.15`.
- Hole on Part C → **0.17**. Two interfaces from the datum, through B:
  `sqrt(0.10² + 0.10² + 0.08² + 0.05²) = sqrt(0.0289) = 0.17`.

### Example 3 — Changing the datum

Using the same assembly as Example 2, change the datum to **Part C**, with
datum tolerance = **0.08**, and click Calculate again.

**Expected results:**
- Hole on Part C → **0.05**. It's now on the datum's own component, so the
  business rule applies again — own tolerance only.
- Hole on Part A → **0.16**. The path now runs the other direction, C → B →
  A: `sqrt(0.08² + 0.08² + 0.10² + 0.05²) = sqrt(0.0253) ≈ 0.1591`, which
  the tool displays rounded to **0.16**.

The point of this example: the graph itself never changes — only the
starting point does. The tool recalculates every path and every tolerance
automatically the moment you pick a new datum and click Calculate.

## 6. Input rules and validation

The tool enforces these rules and will show an error message instead of
silently accepting bad data:

- **Tolerance values must be greater than zero.** Zero or negative
  tolerances are physically meaningless for this analysis and are rejected
  for interfaces, features, and the datum alike.
- **A component cannot be connected to itself.** An interface needs two
  distinct components on either end.
- **Duplicate interfaces are not allowed.** If an interface already exists
  between two components (in either direction), adding another between the
  same pair is rejected.
- **You need at least one component before adding a feature**, and **at
  least two components before adding an interface** — a feature or joint
  can't exist without something to attach it to.
- **Calculation cannot proceed without a datum selected** with a positive
  tolerance. The Calculate button stays disabled until both conditions are
  met.
