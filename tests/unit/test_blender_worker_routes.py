import pytest

from apps.blender_worker.generate_scene import (
    _assembly_route_object_identity,
    _resolved_support_anchor_contract,
)


def test_rf_connection_is_not_classified_as_an_optional_sector_cable() -> None:
    name, role = _assembly_route_object_identity(
        "rf",
        "antenna-to-radio-rf",
        "S1",
    )

    assert name == "rf_connection_antenna-to-radio-rf_S1"
    assert role == "rf_connection"
    assert not name.startswith("cable_")
    assert role != "cable"


def test_radio_adapter_uses_declared_fixed_support_anchor_identity() -> None:
    contract = _resolved_support_anchor_contract(
        {
            "connection_id": "radio-to-mount",
            "operation_id": "assembly:radio-to-mount",
            "target_role_id": "antenna_mount",
            "target_anchor": {
                "anchor_id": "radio_rail",
                "placement_policy": "resolved_from_operation",
                "resolved_support_anchor_id": "radio_adapter_base",
            },
        },
        {
            "antenna_rail": {
                "anchor_id": "antenna_rail",
                "position_m": [0.4, 0.0, 0.0],
            },
            "radio_adapter_base": {
                "anchor_id": "radio_adapter_base",
                "position_m": [0.2, -0.16, -0.8],
            },
        },
        endpoint="target",
    )

    assert contract == {
        "connection_id": "radio-to-mount",
        "operation_id": "assembly:radio-to-mount",
        "endpoint": "target",
        "role_id": "antenna_mount",
        "resolved_anchor_id": "radio_rail",
        "support_anchor_id": "radio_adapter_base",
        "support_position_m": (0.2, -0.16, -0.8),
    }


def test_resolved_support_contract_rejects_undeclared_support_anchor() -> None:
    with pytest.raises(RuntimeError, match="ASSEMBLY_RESOLVED_SUPPORT_ANCHOR_INVALID"):
        _resolved_support_anchor_contract(
            {
                "connection_id": "radio-to-mount",
                "operation_id": "assembly:radio-to-mount",
                "target_role_id": "antenna_mount",
                "target_anchor": {
                    "anchor_id": "radio_rail",
                    "placement_policy": "resolved_from_operation",
                    "resolved_support_anchor_id": "missing_base",
                },
            },
            {},
            endpoint="target",
        )
