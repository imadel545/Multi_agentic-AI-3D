from core.services.library_search import LibraryMetadataSearch


def _entry(path, digest=None):
    return {
        "file_id": path,
        "relative_path": path,
        "content_sha256": digest or path,
        "claimed_dimension": "3d",
        "extension": "dwg",
        "duplicate_of": None,
    }


def test_bilingual_terms_do_not_match_substrings_and_keep_quarantine_evidence():
    index = LibraryMetadataSearch(
        [
            _entry("Radio/StreetMacro_6701.dwg"),
            _entry("Nature/Arbre.dwg"),
            _entry("Batiment/Escalier/Colimasson.dwg"),
        ]
    )
    results = index.rank("tree", claimed_dimension=None, extension=None)
    assert [row[1]["relative_path"] for row in results] == ["Nature/Arbre.dwg"]
    assert results[0][2]["geometry_verified"] is False
    stairs = index.rank("spiral staircase", claimed_dimension=None, extension=None)
    assert stairs[0][2]["query_coverage"] == 1


def test_reference_units_and_content_dedup_are_explicit():
    index = LibraryMetadataSearch(
        [
            _entry("Axians/Pylone/35m/Nedea.dwg"),
            _entry("Axians/Pylone/36m/Nedea.dwg", "same"),
            _entry("Axians/Pylone/36m/Nedea_copy.dwg", "same"),
        ]
    )
    results = index.rank("Axians tower 36 m", claimed_dimension="3d", extension="dwg")
    assert results[0][1]["relative_path"] == "Axians/Pylone/36m/Nedea.dwg"
    assert results[0][2]["matched_terms"]["36m"] == ["36m"]
    assert len(results) == 2
    assert index.rank("Axians", claimed_dimension="2d", extension=None) == []


def test_unknown_query_and_os_junk_are_not_candidates():
    index = LibraryMetadataSearch([_entry("Volx/.DS_Store"), _entry("Volx/Support.dwg")])
    assert index.rank("unicorn", claimed_dimension=None, extension=None) == []
    assert len(index.rank("Volx", claimed_dimension=None, extension=None)) == 1
