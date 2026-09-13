# M1-A verification — core and data contracts

- Date: 2026-09-12
- Status: PASS
- Interpreter: `C:\isaacsim\kit\python\python.exe`, Python 3.12.13
- New dependencies installed: none

Command:

```powershell
C:\isaacsim\python.bat -m unittest discover -s packages\twinpulse_core\tests -v
```

Result: 10 tests passed. Coverage includes valid fixed fixture, JSON round-trip, negative dimensions, NaN position, duplicate IDs, broken robot reference, unallowlisted asset/operation, configurable object limit, and missing dynamic mass.

The first round-trip assertion compared JSON lists with dataclass tuples and failed. The assertion was corrected to compare canonical JSON on both sides; the actual dataclass round-trip already matched. The final command passed.

