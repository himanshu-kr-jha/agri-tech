"""Named lookups — the answers that are not decisions.

A ``LOOKUP`` turn returns ``list[Claim]`` and persists nothing but the turn itself. That is
the distinction worth protecting: a ``DECISION`` freezes an ``EvidenceSnapshot`` and writes
``Recommendation`` rows, and doing that for "which farmers need attention" would devalue the
snapshot for the decisions that actually need one (INV-2).

Two modules, deliberately sharing no query code:

* :mod:`agrivardhak.orchestrator.lookups.fpo` — organization scope
* :mod:`agrivardhak.orchestrator.lookups.farmer` — one farmer's own world

The duplication is the point. INV-5 must not depend on a ``ContextScope`` argument being
passed correctly at every call site; it should be impossible to reach an organization query
from a farmer turn because the function is not imported there. This follows the pattern the
``/farmer/today`` endpoint already set.
"""

from __future__ import annotations
