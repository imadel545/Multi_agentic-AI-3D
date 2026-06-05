# Scene Templates Seed

## 5G lattice tower 30m with 3 sectors

- tower_type: lattice_tower
- tower_height_m: 30
- network_type: 5G
- sector_count: 3
- antenna_install_height_m: 24
- azimuths_deg: 0, 120, 240
- include_rru: true
- include_cables: true
- include_beams: true
- include_labels: true

This template should produce one tower, three sector antennas, one RRU per antenna,
procedural cables, sector beams, azimuth arrows, and technical labels.
