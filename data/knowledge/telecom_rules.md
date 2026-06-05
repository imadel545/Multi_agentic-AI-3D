# Telecom Rules Seed

- Antenna install height must be less than or equal to tower height.
- Sector count must match the azimuth list length.
- Azimuth values are normalized in degrees and must be in `[0, 360)`.
- Assets must be validated and compatible with the network type.
- RRU assets are required when RRU generation is requested.
- Microwave dish designs do not require RRU assets unless explicitly requested.
- Cables and beams are procedural visual elements controlled by SceneSpec flags.
