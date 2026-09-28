"""A small synthetic field (five wellbores, one sidetrack, one loss event) built from raw files."""

import math
from datetime import date
from pathlib import Path

from tests.fixtures.builders import Act, Day, SodirRow, Survey, write_dataset

COS30 = math.cos(math.radians(30))


def _slant_surveys(start: float, stop: float, *, typo_at: float | None = None) -> list[Survey]:
    """Vertical to 500 m, then a straight 30° hole: exact reported TVDs except one typo."""
    out = []
    md = start
    while md <= stop:
        if md <= 500:
            out.append(Survey(md, 0.0, 0.0, md))
        else:
            tvd = 500 + (md - 500) * COS30 if md > 500 else md
            out.append(Survey(md, 30.0, 90.0, 24.8 if md == typo_at else round(tvd, 3)))
        md += 100
    return out


def synthetic_field(data_dir: Path) -> None:
    days = [
        Day(
            "9/9-A-1",
            100,
            date(2020, 1, 1),
            1,
            500,
            surveys=_slant_surveys(100, 500),
            strat=[(300.0, "Utsira Fm")],
        ),
        Day(
            "9/9-A-1",
            100,
            date(2020, 1, 2),
            2,
            1500,
            surveys=[Survey(500, 0, 0, 500), *_slant_surveys(600, 1500, typo_at=1100)],
            activities=[
                Act(20, 1400),
                Act(
                    4,
                    1450,
                    "interruption -- lost circulation",
                    "fail",
                    "circulation loss",
                    "Losses 10 m3/h at 1450 m.",
                ),
            ],
            strat=[(1400.0, "Balder Fm ."), (900.0, "Kai Fm")],
        ),
        Day(
            "9/9-A-1 A",
            101,
            date(2020, 1, 5),
            1,
            1800,
            md_kickoff_m=1000,
            surveys=[
                Survey(1100, 40.0, 90.0, None),
                Survey(1400, 45.0, 90.0, None),
                Survey(1800, 50.0, 90.0, None),
            ],
            strat=[(1450.0, "Balder Fm")],
        ),
        Day(
            "9/9-C-1",
            300,
            date(2019, 6, 1),
            1,
            800,
            surveys=_slant_surveys(100, 800),
            strat=[(320.0, "Utsira Fm")],
        ),
        Day(
            "9/9-D-1",
            400,
            date(2019, 7, 1),
            1,
            800,
            surveys=_slant_surveys(100, 800),
            strat=[(310.0, "Utsira Fm")],
        ),
        Day("9/9-B-1", 200, date(2019, 8, 1), 1, 800, surveys=_slant_surveys(100, 800)),
    ]
    sodir = [
        SodirRow("9/9-A-1", "9/9-A-1", 100, total_depth_md_m=1500, final_tvd_m=500 + 1000 * COS30),
        SodirRow(
            "9/9-A-1 A",
            "9/9-A-1",
            101,
            "sidetrack",
            "9/9-A-1",
            kickoff_md_m=1000,
            total_depth_md_m=1800,
            final_tvd_m=1400,
        ),
        SodirRow("9/9-B-1", "9/9-B-1", 200, lat=58.45, lon=1.90),
        SodirRow("9/9-C-1", "9/9-C-1", 300, lat=58.46, lon=1.91),
        SodirRow("9/9-D-1", "9/9-D-1", 400, lat=58.47, lon=1.92),
    ]
    write_dataset(data_dir, days, sodir)
    # A second copy of A-1's first day with different content: same wellbore and period.
    duplicate = data_dir / "raw" / "volve_ddr_mirror" / "Reports" / "9_9_A_1_dup.xml"
    original = next(
        (data_dir / "raw" / "volve_ddr_mirror" / "Reports").glob("9_9_A_1_2020_01_01.xml")
    )
    duplicate.write_bytes(original.read_bytes().replace(b"Day 1 on", b"Resubmitted day 1 on"))
