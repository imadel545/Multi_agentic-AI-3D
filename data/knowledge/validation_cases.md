# Validation Cases Seed

## Antenna above tower height

Input with `antenna_install_height_m > tower_height_m` must fail before SceneSpec export.

## Sector count mismatch

Input with `sector_count = 3` and only two azimuths must fail Pydantic or Rule Engine validation.

## Asset compatibility mismatch

An asset whose `compatible_networks` does not contain the requested network must be rejected.
