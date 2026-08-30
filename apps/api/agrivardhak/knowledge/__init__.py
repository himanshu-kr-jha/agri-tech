"""The Data Observer: raw external payloads to retrievable, gated knowledge (ADR-0018).

``ingestion/`` lands a fetched payload as an ``ExternalRecord``. This package turns that raw
JSON into passages an orchestrator can retrieve and cite:

    classify  →  segment  →  embed  →  index  →  retrieve

Nothing here is an intelligence module. Modules are pure and may not touch the database
(CLAUDE.md §6), so retrieval is called by ``orchestrator/gather.py`` and the results are
handed to a module as ordinary data.
"""
