"""Pure DTO checks. No database, network, D3 model or credentials."""
import uuid
import pytest
from pydantic import ValidationError
from app.grouping_contracts import D3Suggestion, GroupingDecisionCreate

def suggestion(**overrides):
    return {"reporte_nuevo_id": str(uuid.uuid4()), "evento_candidato_id": str(uuid.uuid4()),
        "similitud_texto": .8, "distancia_metros": 12, "diferencia_horas": 2,
        "sugerencia": "requiere_revision", "motivos": ["Comparación pendiente de validación"],
        "version_configuracion": "propuesta-v1", **overrides}

def command(**overrides):
    return {"operation_id": str(uuid.uuid4()), "report_id": str(uuid.uuid4()),
        "decision": "agrupar", "candidate_event_id": str(uuid.uuid4()),
        "expected_event_id": None, "expected_decision_id": None, **overrides}

@pytest.mark.parametrize("field,value", [
    ("similitud_texto", float("nan")), ("similitud_texto", float("inf")),
    ("similitud_texto", 1.01), ("similitud_texto", -1.01),
    ("distancia_metros", -1), ("diferencia_horas", -1),
    ("sugerencia", "confirmar_automaticamente"), ("reporte_nuevo_id", "invalid"),
    ("evento_candidato_id", "invalid"), ("motivos", []), ("motivos", ["  "]),
    ("version_configuracion", "  "),
])
def test_invalid_provisional_suggestion(field, value):
    with pytest.raises(ValidationError):
        D3Suggestion.model_validate(suggestion(**{field:value}))

@pytest.mark.parametrize("value", [-1, 0, 1, None])
def test_cosine_is_not_a_calibrated_probability(value):
    assert D3Suggestion.model_validate(suggestion(similitud_texto=value)).similitud_texto == value

def test_suggestion_does_not_choose_a_municipal_decision():
    sample = suggestion(sugerencia="requiere_revision")
    value = command(report_id=sample["reporte_nuevo_id"], candidate_event_id=sample["evento_candidato_id"], suggestion=sample)
    parsed = GroupingDecisionCreate.model_validate(value)
    assert parsed.decision == "agrupar" and parsed.config_version == "propuesta-v1"
    assert parsed.suggestion.sugerencia == "requiere_revision"

@pytest.mark.parametrize("field", ["expected_event_id", "expected_decision_id", "operation_id", "report_id", "decision"])
def test_required_command_fields_are_never_implicitly_unconditional(field):
    data = command(); data.pop(field)
    with pytest.raises(ValidationError):
        GroupingDecisionCreate.model_validate(data)

@pytest.mark.parametrize("extra", [
    {"factors":{"nested":[{"x":float("nan")}]}}, {"factors":{"x":"v"*32769}},
    {"decided_by":str(uuid.uuid4())}, {"decided_at":"2026-01-01T00:00:00Z"},
    {"latitude":91}, {"priority_score":10}, {"candidate_event_id":None},
    {"decision":"separar"}, {"suggestion":suggestion()},
])
def test_invalid_or_forged_command(extra):
    with pytest.raises(ValidationError):
        GroupingDecisionCreate.model_validate(command(**extra))
