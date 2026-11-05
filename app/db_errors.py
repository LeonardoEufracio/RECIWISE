"""Inspect driver diagnostics without parsing messages or exposing SQL/DSNs."""
def diagnostics(exc):
    original = getattr(exc, "orig", exc)
    state = getattr(original, "sqlstate", None)
    constraint = getattr(getattr(original, "diag", None), "constraint_name", None)
    return state, constraint


SHIFT_EXCLUSIONS = {"shifts_vehicle_no_overlap", "shifts_driver_no_overlap"}
