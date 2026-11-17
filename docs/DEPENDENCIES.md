# Dependencias entre issues

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

Una flecha A → B significa que B requiere A completado. El checker rechaza ciclos, referencias desconocidas e inversiones de fase.

```mermaid
flowchart TD
  MOA_000["MOA-000"]
  MOA_001["MOA-001"]
  MOA_002["MOA-002"]
  MOA_003["MOA-003"]
  MOA_004["MOA-004"]
  MOA_005["MOA-005"]
  MOA_006["MOA-006"]
  MOA_007["MOA-007"]
  MOA_008["MOA-008"]
  MOA_009["MOA-009"]
  MOA_010["MOA-010"]
  MOA_011["MOA-011"]
  MOA_012["MOA-012"]
  MOA_013["MOA-013"]
  MOA_014["MOA-014"]
  MOA_015["MOA-015"]
  MOA_016["MOA-016"]
  MOA_017["MOA-017"]
  MOA_018["MOA-018"]
  MOA_019["MOA-019"]
  MOA_020["MOA-020"]
  MOA_021["MOA-021"]
  MOA_022["MOA-022"]
  MOA_023["MOA-023"]
  MOA_024["MOA-024"]
  MOA_025["MOA-025"]
  MOA_026["MOA-026"]
  MOA_027["MOA-027"]
  MOA_028["MOA-028"]
  MOA_029["MOA-029"]
  MOA_030["MOA-030"]
  MOA_031["MOA-031"]
  MOA_032["MOA-032"]
  MOA_033["MOA-033"]
  MOA_034["MOA-034"]
  MOA_035["MOA-035"]
  MOA_000 --> MOA_001
  MOA_001 --> MOA_002
  MOA_001 --> MOA_003
  MOA_002 --> MOA_003
  MOA_001 --> MOA_004
  MOA_003 --> MOA_004
  MOA_001 --> MOA_005
  MOA_002 --> MOA_005
  MOA_004 --> MOA_006
  MOA_005 --> MOA_006
  MOA_006 --> MOA_007
  MOA_010 --> MOA_007
  MOA_028 --> MOA_007
  MOA_006 --> MOA_008
  MOA_002 --> MOA_009
  MOA_004 --> MOA_009
  MOA_005 --> MOA_009
  MOA_006 --> MOA_009
  MOA_008 --> MOA_009
  MOA_002 --> MOA_010
  MOA_003 --> MOA_010
  MOA_006 --> MOA_010
  MOA_009 --> MOA_010
  MOA_010 --> MOA_011
  MOA_010 --> MOA_012
  MOA_011 --> MOA_012
  MOA_009 --> MOA_013
  MOA_010 --> MOA_013
  MOA_013 --> MOA_014
  MOA_005 --> MOA_014
  MOA_005 --> MOA_015
  MOA_013 --> MOA_015
  MOA_005 --> MOA_016
  MOA_013 --> MOA_016
  MOA_014 --> MOA_017
  MOA_015 --> MOA_017
  MOA_016 --> MOA_017
  MOA_002 --> MOA_018
  MOA_010 --> MOA_018
  MOA_012 --> MOA_018
  MOA_013 --> MOA_018
  MOA_018 --> MOA_019
  MOA_018 --> MOA_020
  MOA_019 --> MOA_020
  MOA_011 --> MOA_020
  MOA_020 --> MOA_021
  MOA_018 --> MOA_022
  MOA_019 --> MOA_022
  MOA_010 --> MOA_022
  MOA_022 --> MOA_023
  MOA_011 --> MOA_023
  MOA_022 --> MOA_024
  MOA_005 --> MOA_024
  MOA_011 --> MOA_024
  MOA_022 --> MOA_025
  MOA_011 --> MOA_025
  MOA_014 --> MOA_026
  MOA_015 --> MOA_026
  MOA_022 --> MOA_026
  MOA_017 --> MOA_027
  MOA_022 --> MOA_027
  MOA_026 --> MOA_027
  MOA_028 --> MOA_027
  MOA_004 --> MOA_028
  MOA_010 --> MOA_029
  MOA_011 --> MOA_029
  MOA_028 --> MOA_029
  MOA_003 --> MOA_030
  MOA_020 --> MOA_030
  MOA_021 --> MOA_030
  MOA_022 --> MOA_030
  MOA_010 --> MOA_031
  MOA_022 --> MOA_031
  MOA_027 --> MOA_031
  MOA_018 --> MOA_032
  MOA_031 --> MOA_032
  MOA_012 --> MOA_033
  MOA_018 --> MOA_033
  MOA_020 --> MOA_033
  MOA_026 --> MOA_033
  MOA_008 --> MOA_034
  MOA_016 --> MOA_034
  MOA_020 --> MOA_034
  MOA_023 --> MOA_034
  MOA_007 --> MOA_035
  MOA_021 --> MOA_035
  MOA_023 --> MOA_035
  MOA_024 --> MOA_035
  MOA_025 --> MOA_035
  MOA_027 --> MOA_035
  MOA_029 --> MOA_035
  MOA_030 --> MOA_035
  MOA_032 --> MOA_035
  MOA_033 --> MOA_035
  MOA_034 --> MOA_035
```

## Orden topológico válido

MOA-000 → MOA-001 → MOA-002 → MOA-003 → MOA-004 → MOA-005 → MOA-006 → MOA-008 → MOA-009 → MOA-010 → MOA-028 → MOA-007 → MOA-011 → MOA-012 → MOA-013 → MOA-014 → MOA-015 → MOA-016 → MOA-017 → MOA-018 → MOA-019 → MOA-020 → MOA-021 → MOA-022 → MOA-023 → MOA-024 → MOA-025 → MOA-026 → MOA-027 → MOA-029 → MOA-030 → MOA-031 → MOA-032 → MOA-033 → MOA-034 → MOA-035

El orden no obliga a ejecutar secuencialmente issues independientes. El siguiente issue listo se obtiene de dependencias completadas, no del número menor.
