# Version 1 matching behavior

Version 1 keeps the original **urgency-first greedy matching** idea and its
default weights. It fixes participant identity, accounting and eligibility.
It does not use a global optimizer or language model.

## What is preserved

For each canonical subject `s`, count the tutors who can teach it, `supply(s)`.
Compute this once from the initial tutor pool, before making any assignments.
The count is people, even when a tutor has capacity greater than one.

For a tutee, the urgency score is:

```text
subject_sum = 100 * (10/supply(primary) + 3/supply(secondary) + 1/supply(tertiary))
gender_bonus = 1000 if a gender preference is specified, otherwise 0
urgency = round(subject_sum + gender_bonus)
```

The gender bonus is added to the subject sum before rounding. An absent subject
or a subject with zero tutor supply contributes zero rather than dividing by
zero. Rounding uses Python's `round`, including ties to the nearest even integer.
The formula is written explicitly in code as a sum plus the optional bonus.

Process tutees by descending urgency. For each one, choose the highest-scoring
eligible tutor with remaining capacity. The pair score is:

| Compatibility | Points |
| --- | ---: |
| Primary subject | 1,000,000 |
| Secondary subject | 100 |
| Tertiary subject | 1 |

Subject membership is an exact comparison of normalized internal subject IDs.
For example, `functions11` can represent several approved labels for the same
questionnaire choice. Substring coincidences do not create matches.

## Hard constraints and ties

The default profile requires the tutor to teach the primary subject and honor
an explicit gender preference. A missing primary subject is an input error.
Tutor capacity defaults to one. Capacity cannot be exceeded.

Equal urgency is broken by ascending tutee ID; equal pair scores are broken by
ascending tutor ID. Display names are never identity keys. Distinct IDs with the
same name remain distinct people. Equal inputs with unchanged IDs give the same
results, including after row reordering. If no ID is supplied, the loader derives
a private identity from role, normalized name and email when present. Editing
those fields changes that identity; collisions require review. Assign persistent
opaque IDs for repeatable production runs. A digest of personal information is
not an anonymization guarantee.

Structured availability and grade checks are supported, but disabled in the
default profile because the prepared historical schema does not provide verified
structured fields for them. If enabled, missing or incompatible values reject
the pair. Do not infer schedule or grade compatibility from a successful default
run. The quality summary counts unevaluated values separately. A subject label
containing a grade is not a validated student-grade constraint.

The configuration can select `subject_policy: any` to allow any requested
subject. `legacy_flag` subject and gender modes are explicit comparison options
that can permit flagged incompatible matches. They are not the default and do
not reconstruct Version 0 exactly: identity, tie-breaking, parsing and accounting
fixes still apply. Keep strict defaults for ordinary matching.

## Every participant is accounted for

The program never truncates the tutee input to the number of tutors. Each valid
tutee appears exactly once in either matches or the unmatched list. An unmatched
record states:

- `no_eligible_tutor`: no tutor satisfies the configured hard constraints.
- `capacity_exhausted`: a suitable tutor exists but has no remaining capacity,
  or the tutor pool is empty.

Rejection counts give more detail, such as primary subject or gender
incompatibility. They describe the candidate pool at that step, not a proof that
no other overall allocation could match that person. Tutor usage and remaining
capacity are also recorded. Independent checks reconcile participant totals and
capacity, and recalculate compatibility from the canonical records.

Each selected pair includes urgency, pair score, subject score components,
compatibility checks, and any flags. The run summary reports matched/unmatched
counts, capacity use, subject satisfaction and the scope of evaluated constraints.
Review unmatched participants alongside the matches.

## Limits retained deliberately

The algorithm makes a locally best choice and does not revisit it. It does not
maximize the total number of matches or total score globally. For example, with
tutees A and B, a flexible tutor who teaches English and French, and an
English-only tutor, assigning A (English) to the flexible tutor can leave B
(French) unmatched. Static urgency often helps but does not guarantee avoiding
such cases once preferences, genders and capacities interact.

The gender bonus can move a participant ahead of someone with greater subject
scarcity. A subject with no tutors gives no urgency points. These are inherited
policy choices, not claims about fairness. Counts reflect subject supply, not
gender-specific eligible supply. Scarcity is not recalculated after assignments.
IDs deterministically settle ties but do not provide a lottery or fairness rule.

With `N` tutees, `M` tutors and bounded small subject/availability sets, the main
loop is `O(N*M)` plus sorting. Temporary candidate storage is `O(M)` and stored
results are `O(N+M)`. This is suitable for a small Saturday program; measure real
larger inputs before changing the implementation.

## Results may differ from Version 0

The strict eligibility checks may leave someone unmatched where Version 0 made
a zero-score or incompatible match. Previously truncated tutees now participate.
Duplicate names no longer remove unrelated tutors, approved questionnaire labels
map consistently, and ties are explicit. These are intentional fixes, so Version
1 is not a byte-for-byte reproduction of historical match results. Version 0
preserves the original script and inputs for reference.

## Future work

Keep global optimization and NLP as later, separately tested changes. A future
comparison could evaluate maximum-weight bipartite matching or min-cost flow
under exactly the same eligibility rules and agreed priorities. Establish
whether the first objective is maximum participation, urgency, total preference
satisfaction, or another fairness policy before selecting a solver. Tutor
programs and tutee career goals could become an optional reviewed score only
after defining consent, privacy handling and an understandable evaluation method.
No questionnaire free text is used in Version 1 matching.
