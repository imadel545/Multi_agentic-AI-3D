from core.services.blender_runtime import (
    has_qualified_blender_runtime,
    output_reports_qualified_blender,
)


def test_only_the_governed_blender_runtime_is_certifiable() -> None:
    assert has_qualified_blender_runtime(
        {
            "version": "4.5.12 LTS",
            "version_tuple": [4, 5, 12],
            "background": True,
            "factory_startup": True,
        }
    )
    assert not has_qualified_blender_runtime(
        {
            "version": "5.1.2",
            "version_tuple": [5, 1, 2],
            "background": True,
            "factory_startup": True,
        }
    )
    assert output_reports_qualified_blender("Blender 4.5.12 LTS (hash verified)\nready")
    assert output_reports_qualified_blender(
        "TELECOM_STUDIO_BLENDER_READY\nBlender 4.5.12 LTS (hash verified)\n"
    )
    assert not output_reports_qualified_blender("Blender 5.1.2\nready")
