"""Read canonical rows back into domain objects (trajectories, formation tops)."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from drillsage.db import models as m
from drillsage.domain.formations import FormationTop, StratLevel, TopSource
from drillsage.domain.trajectory import Trajectory, TrajectoryStation, TvdSource


def trajectory_from_rows(rows: list[m.TrajectoryStation]) -> Trajectory:
    return Trajectory(
        [
            TrajectoryStation(
                md_m=r.md_m,
                incl_deg=r.incl_deg,
                azi_deg=r.azi_deg,
                tvd_m=r.tvd_m,
                north_m=r.north_m,
                east_m=r.east_m,
                dls_deg_per_30m=r.dls_deg_per_30m,
                tvd_mincurv_m=r.tvd_mincurv_m,
                tvd_reported_m=r.tvd_reported_m,
                tvd_source=TvdSource(r.tvd_source),
                reported_rejected=r.reported_tvd_rejected,
                inherited=r.inherited,
            )
            for r in rows
        ]
    )


async def trajectory_rows(session: AsyncSession) -> dict[int, list[m.TrajectoryStation]]:
    rows: dict[int, list[m.TrajectoryStation]] = defaultdict(list)
    result = await session.execute(
        select(m.TrajectoryStation).order_by(
            m.TrajectoryStation.wellbore_id, m.TrajectoryStation.seq
        )
    )
    for station in result.scalars():
        rows[station.wellbore_id].append(station)
    return rows


async def load_trajectories(session: AsyncSession) -> dict[int, Trajectory]:
    """Trajectory per wellbore id (wellbores without stations are absent)."""
    return {
        wid: trajectory_from_rows(rows) for wid, rows in (await trajectory_rows(session)).items()
    }


async def load_formation_tops(session: AsyncSession) -> dict[int, list[FormationTop]]:
    tops: dict[int, list[FormationTop]] = defaultdict(list)
    result = await session.execute(select(m.FormationTop).order_by(m.FormationTop.md_top_m))
    for row in result.scalars():
        tops[row.wellbore_id].append(
            FormationTop(
                name=row.name,
                level=StratLevel(row.level),
                md_top_m=row.md_top_m,
                tvd_top_m=row.tvd_top_m,
                source=TopSource(row.source),
                recognised=True,
                raw_name=row.raw_name,
            )
        )
    return tops
