"""Objective function, fuel model, compliance costs, pooling, and the
per-scenario GA solver (Task 2R component 3).

Consumes `nexfleet.fleet` (component 2) and `nexfleet.compliance.scope_gating`
plus `nexfleet.regulatory` (Task 2 / Phase 0) — this package composes them
into a searchable objective, it does not redefine any of their concerns.
"""
