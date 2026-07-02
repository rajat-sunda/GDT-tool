# Assembly Tolerance Propagation Tool

## 1. What this tool does

When you build something out of multiple parts, a car body, a bracket
assembly, anything with holes or slots that need to line up, the tolerance
on any one part's drawing isn't the whole story. Once parts get joined
together, the joints themselves add variation, and that variation stacks up.
This tool calculates that stack-up.

You tell it what parts you have, what toleranced features (holes, slots,
etc.) live on each part, which part is your reference datum, and how loose
the joints are. It then works out the **effective tolerance** of every
feature at the assembly level, not just what the drawing says, but what you
can actually expect once everything is bolted, welded, or riveted together.

It also supports building up in stages: calculate a first subassembly, then
add another part on top of it and calculate again, and again, exactly the
way a real production line adds one station after another. Each stage's
results stay visible on screen, stacked one below the other, so you can see
the whole build history at a glance.

The math behind it is called **Root Sum Square (RSS)** 

## 2. How to install and run

**Requirements:** Python 3.9 or above.

1. Open a terminal and navigate to the folder containing `app.py` and
   `requirements.txt`.
2. Install the one dependency:
   ```
   pip install -r requirements.txt
   ```
3. Launch the app:
   ```
   streamlit run app.py
   ```
4. Streamlit will print a URL in the terminal, normally:
   ```
   http://localhost:8501
   ```
   Open that in your browser. If it doesn't open automatically, copy-paste
   the URL yourself.

The tool starts completely empty — nothing is pre-loaded. Everything you
enter lives only in that browser session; closing the tab clears it.

## 3. How to use the tool — step by step

### Building your first subassembly

1. **Add Parts.** In the sidebar, under "1. Parts," type a part name (e.g.
   "Part A") and click **Add Part**. Repeat for every part you're starting
   with. Each one appears in a list with a Remove button if you need to
   delete it.

2. **Add Features.** Under "2. Features," pick a part from the dropdown,
   give the feature a name (e.g. "Hole 1"), and enter its own positional
   tolerance from the part's drawing. There's no restriction on which part
   you can add a feature to — add as many as you need, whenever you need to.

3. **Set up the assembly.** Under "3. Assembly Setup":
   - Choose **which part carries the datum** — this is your reference point,
     the part everything else is measured relative to.
   - Enter the **datum tolerance** — how precisely that part itself locates
     in the assembly fixture.
   - Enter the **interface tolerance** — the variation introduced by the
     joint itself (weld location, locator pin clearance, fixture
     repeatability, whatever applies physically).
   - Click **Calculate.**

4. **Read the results.** A table titled "Subassembly - Level 1" appears in
   the main panel, with every feature's effective tolerance. Features on the
   datum part are marked **(same body)** — no stack-up applies to them,
   since they're not affected by a joint they're the reference for.

### Adding another level

Once Level 1 exists, a new sidebar section appears:

5. **Add more parts and features** if you haven't already (same as steps 1
   and 2 — this works at any point, not just at the start).

6. **Build the next level.** Under "4. Add Next Assembly Level":
   - **Select which new component(s)** are joining this level, from a
     multiselect showing parts not already folded into the subassembly.
   - **Choose which side carries the datum this time.** You can either keep
     the datum on the subassembly you've already built (its existing
     features simply carry forward unchanged — its datum tolerance
     auto-fills, since it's inherited from before), or shift the datum onto
     one of the new parts you're adding (in which case the *existing*
     subassembly's features are the ones that get recalculated against the
     new datum and interface).
   - Enter the **interface tolerance** for this joining operation.
   - Click **Calculate Next Level.**

7. A new table, "Subassembly - Level 2," appears below the first one. Repeat
   step 6 as many times as you need — every click adds one more table,
   nothing is ever overwritten.

There's no save or export button by design — every result stays visible on
screen as you build, exactly as it's calculated.

## 4. How the calculation works

The formula is Root Sum Square:

```
T_effective = sqrt(T1² + T2² + ...)
```

At every level, there are exactly two rules:

- **A feature on the datum side** gets its own current tolerance, unchanged.
  No calculation happens to it. This is because a feature isn't affected by
  a joint it's the reference point for.
- **A feature on the other side** gets:
  ```
  T_effective = sqrt(datum_tolerance² + interface_tolerance² + own_tolerance²)
  ```
  where `own_tolerance` is that feature's *current* value — its original
  drawing tolerance the first time it's included, or its most recently
  calculated effective tolerance if it was carried forward from an earlier
  level.

That second point is what makes multi-level builds work: once a feature has
gone through one level's calculation, its *result* becomes the input to the
next level, not the raw numbers that produced it. This mirrors how a real
assembly line works — station 20 doesn't reopen and recheck every individual
part that went into the subassembly from station 10; it just works with
whatever came out of station 10.

**Why RSS instead of just adding tolerances directly (worst case)?** Adding
tolerances directly (worst-case addition) assumes every contributor hits its
maximum deviation at the same time, in the same direction — which is
statistically very unlikely in a real production run. RSS treats each
contributor as an independent source of variation and combines them the way
independent variation actually combines, giving a realistic rather than
overly pessimistic picture.

All values entered and displayed in this tool are rounded to **2 decimal
places**.

## 5. Worked example (verify the tool with this)

You can enter this from scratch to confirm everything is working correctly.

### Level 1

- Parts: `Part A`, `Part B`
- Features: "Hole 1" on Part A, tolerance **0.05**; "Hole 2" on Part B,
  tolerance **0.05**
- Assembly setup: datum part = **Part A**, datum tolerance = **0.10**,
  interface tolerance = **0.10**
- Click Calculate.

**Expected results:**
- Hole 1 → **0.05**. Part A carries the datum, so it's marked "(same body)"
  — its own tolerance only, no RSS.
- Hole 2 → **0.15**. Part B is the other side:
  `sqrt(0.10² + 0.10² + 0.05²) = sqrt(0.0225) = 0.15`.

### Level 2 — datum stays on the subassembly

- Add a new part, `Part C`, with a feature "Hole 3," tolerance **0.05**.
- In Section 4, select Part C as the new component, keep the datum on
  "Subassembly (through Level 1)" (its datum tolerance auto-fills to
  **0.10**), and set interface tolerance = **0.10**.
- Click Calculate Next Level.

**Expected results:**
- Hole 1 → **0.05**, unchanged from Level 1. Marked "(same body)" — the
  subassembly carries the datum this level, so everything already in it
  passes through untouched.
- Hole 2 → **0.15**, also unchanged, for the same reason.
- Hole 3 → **0.15**: `sqrt(0.10² + 0.10² + 0.05²) = sqrt(0.0225) = 0.15`.

### Level 2, alternative — datum shifts to the new part instead

Starting over from the same Level 1 result, suppose instead you set Part C
as the datum-carrying side this time, with a freshly entered datum tolerance
of **0.50** and interface tolerance **0.10**:

**Expected results:**
- Hole 3 → **0.05**, unchanged. Part C now carries the datum, so its own
  feature passes through untouched, marked "(same body)".
- Hole 1 → **0.51**: `sqrt(0.50² + 0.10² + 0.05²) = sqrt(0.2625) ≈ 0.5123`.
- Hole 2 → **0.53**: `sqrt(0.50² + 0.10² + 0.15²) = sqrt(0.2825) ≈ 0.5315`.

This shows the key idea: whether a feature "passes through unchanged" or
"gets recalculated" depends entirely on which side carries the datum at
*that* level — not on whether it's an old feature or a new one.

## 6. Input rules and validation

- **Tolerance values must be greater than zero.** This applies to feature
  tolerances, datum tolerances, and interface tolerances alike — zero or
  negative values are rejected with an error message.
- **A part or feature name cannot be empty.**
- **Features can be added to any part at any time**, whether or not that
  part has already been used in a calculated level.
- **Level 1 can only be calculated once.** Once it exists, Section 3 is
  replaced by a message pointing you to Section 4 for further levels — this
  keeps the build history consistent and avoids accidentally recalculating
  from scratch.
- **A part can only be added to the subassembly once.** Once it's been
  included in some level's calculation, it no longer appears as an option
  for a future level — it's already part of the running subassembly.
- **You need at least one new component selected** in Section 4 before
  Calculate Next Level becomes meaningful.
