"""WITSML 1.4 `drillReport` (daily drilling report, DDR) parser.

Every element observed in the Volve DDRs is mapped (see the parser-fidelity report in
`eval/reports/parser_fidelity.md`). Quantities are converted to canonical units using each
element's `uom` attribute; `-999.99` null sentinels become None. Elements the model does not
know are counted, never silently dropped, so format drift shows up in the fidelity report.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict

from drillsage.core.units import Kind
from drillsage.domain.names import canonical_wellbore_name
from drillsage.ingest.xml_safe import local_name, parse_xml
from drillsage.ingest.xmlmap import ParseReport, Xml, XmlValueError, parse_model

WITSML_NS = "http://www.witsml.org/schemas/1series"
NPD_NUMBER = "NPD number"
NPD_CODE = "NPD code"

L = Kind.LENGTH


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DocumentInfo(_Model):
    document_name: Annotated[str | None, Xml("documentName")] = None
    owner: Annotated[str | None, Xml("owner")] = None


class Alias(_Model):
    name: Annotated[str | None, Xml("name")] = None
    naming_system: Annotated[str | None, Xml("namingSystem")] = None


class WellboreInfo(_Model):
    pre_spud_at: Annotated[datetime | None, Xml("dTimPreSpud")] = None
    spud_at: Annotated[datetime | None, Xml("dTimSpud")] = None
    drill_complete_on: Annotated[date | None, Xml("dateDrillComplete")] = None
    days_ahead: Annotated[float | None, Xml("daysAhead")] = None
    days_behind: Annotated[float | None, Xml("daysBehind")] = None
    operator: Annotated[str | None, Xml("operator")] = None
    drill_contractor: Annotated[str | None, Xml("drillContractor")] = None
    rig_aliases: Annotated[list[Alias], Xml("rigAlias")] = []


class StatusInfo(_Model):
    report_no: Annotated[int | None, Xml("reportNo")] = None
    at: Annotated[datetime | None, Xml("dTim")] = None
    md_m: Annotated[float | None, Xml("md", L)] = None
    tvd_m: Annotated[float | None, Xml("tvd", L)] = None
    md_planned_m: Annotated[float | None, Xml("mdPlanned", L)] = None
    dist_drill_m: Annotated[float | None, Xml("distDrill", L)] = None
    hole_diameter_m: Annotated[float | None, Xml("diaHole", L)] = None
    hole_diameter_start_at: Annotated[datetime | None, Xml("dTimDiaHoleStart")] = None
    md_hole_diameter_start_m: Annotated[float | None, Xml("mdDiaHoleStart", L)] = None
    pilot_diameter_m: Annotated[float | None, Xml("diaPilot", L)] = None
    md_kickoff_m: Annotated[float | None, Xml("mdKickoff", L)] = None
    md_plug_top_m: Annotated[float | None, Xml("mdPlugTop", L)] = None
    strength_form_gcc: Annotated[float | None, Xml("strengthForm", Kind.DENSITY)] = None
    md_strength_form_m: Annotated[float | None, Xml("mdStrengthForm", L)] = None
    tvd_strength_form_m: Annotated[float | None, Xml("tvdStrengthForm", L)] = None
    pres_test_type: Annotated[str | None, Xml("presTestType")] = None
    md_csg_last_m: Annotated[float | None, Xml("mdCsgLast", L)] = None
    tvd_csg_last_m: Annotated[float | None, Xml("tvdCsgLast", L)] = None
    elev_kelly_m: Annotated[float | None, Xml("elevKelly", L)] = None
    wellhead_elevation_m: Annotated[float | None, Xml("wellheadElevation", L)] = None
    water_depth_m: Annotated[float | None, Xml("waterDepth", L)] = None
    summary_24h: Annotated[str | None, Xml("sum24Hr")] = None
    forecast_24h: Annotated[str | None, Xml("forecast24Hr")] = None
    rop_current_mph: Annotated[float | None, Xml("ropCurrent", Kind.ROP)] = None
    tight_well: Annotated[bool | None, Xml("tightWell")] = None
    hpht: Annotated[bool | None, Xml("hpht")] = None
    fixed_rig: Annotated[bool | None, Xml("fixedRig")] = None
    avg_pres_bh_kpa: Annotated[float | None, Xml("avgPresBH", Kind.PRESSURE)] = None
    avg_temp_bh_degc: Annotated[float | None, Xml("avgTempBH", Kind.TEMPERATURE)] = None


class Activity(_Model):
    start_at: Annotated[datetime | None, Xml("dTimStart")] = None
    end_at: Annotated[datetime | None, Xml("dTimEnd")] = None
    md_m: Annotated[float | None, Xml("md", L)] = None
    phase: Annotated[str | None, Xml("phase")] = None
    proprietary_code: Annotated[str | None, Xml("proprietaryCode")] = None
    state: Annotated[str | None, Xml("state")] = None
    state_detail: Annotated[str | None, Xml("stateDetailActivity")] = None
    comments: Annotated[str | None, Xml("comments")] = None

    @property
    def duration_h(self) -> float | None:
        if self.start_at is None or self.end_at is None:
            return None
        return (self.end_at - self.start_at).total_seconds() / 3600.0


class Fluid(_Model):
    fluid_type: Annotated[str | None, Xml("type")] = None
    location_sample: Annotated[str | None, Xml("locationSample")] = None
    at: Annotated[datetime | None, Xml("dTim")] = None
    md_m: Annotated[float | None, Xml("md", L)] = None
    pres_bop_rating_kpa: Annotated[float | None, Xml("presBopRating", Kind.PRESSURE)] = None
    mud_class: Annotated[str | None, Xml("mudClass")] = None
    density_gcc: Annotated[float | None, Xml("density", Kind.DENSITY)] = None
    vis_funnel_s: Annotated[float | None, Xml("visFunnel", Kind.FUNNEL_VISCOSITY)] = None
    pv_mpas: Annotated[float | None, Xml("pv", Kind.VISCOSITY)] = None
    yp_pa: Annotated[float | None, Xml("yp", Kind.YIELD_STRESS)] = None
    temp_hthp_degc: Annotated[float | None, Xml("tempHthp", Kind.TEMPERATURE)] = None
    filtrate_ltlp_m3: Annotated[float | None, Xml("filtrateLtlp", Kind.VOLUME)] = None
    filter_cake_ltlp_m: Annotated[float | None, Xml("filterCakeLtlp", L)] = None


class PorePressure(_Model):
    reading_kind: Annotated[str | None, Xml("readingKind")] = None
    emw_gcc: Annotated[float | None, Xml("equivalentMudWeight", Kind.DENSITY)] = None
    at: Annotated[datetime | None, Xml("dTim")] = None
    md_m: Annotated[float | None, Xml("md", L)] = None


class SurveyStation(_Model):
    at: Annotated[datetime | None, Xml("dTim")] = None
    md_m: Annotated[float | None, Xml("md", L)] = None
    tvd_m: Annotated[float | None, Xml("tvd", L)] = None
    incl_deg: Annotated[float | None, Xml("incl", Kind.ANGLE)] = None
    azi_deg: Annotated[float | None, Xml("azi", Kind.ANGLE)] = None


class LithShow(_Model):
    at: Annotated[datetime | None, Xml("dTim")] = None
    md_top_m: Annotated[float | None, Xml("mdTop", L)] = None
    md_bottom_m: Annotated[float | None, Xml("mdBottom", L)] = None
    tvd_top_m: Annotated[float | None, Xml("tvdTop", L)] = None
    tvd_bottom_m: Annotated[float | None, Xml("tvdBottom", L)] = None
    show: Annotated[str | None, Xml("show")] = None
    lithology: Annotated[str | None, Xml("lithology")] = None


class StratTop(_Model):
    at: Annotated[datetime | None, Xml("dTim")] = None
    md_top_m: Annotated[float | None, Xml("mdTop", L)] = None
    tvd_top_m: Annotated[float | None, Xml("tvdTop", L)] = None
    description: Annotated[str | None, Xml("description")] = None


class GasReading(_Model):
    at: Annotated[datetime | None, Xml("dTim")] = None
    reading_type: Annotated[str | None, Xml("readingType")] = None
    md_top_m: Annotated[float | None, Xml("mdTop", L)] = None
    tvd_top_m: Annotated[float | None, Xml("tvdTop", L)] = None
    gas_high_pct: Annotated[float | None, Xml("gasHigh", Kind.FRACTION)] = None
    methane_ppm: Annotated[float | None, Xml("meth", Kind.CONCENTRATION)] = None
    ethane_ppm: Annotated[float | None, Xml("eth", Kind.CONCENTRATION)] = None
    propane_ppm: Annotated[float | None, Xml("prop", Kind.CONCENTRATION)] = None
    ibutane_ppm: Annotated[float | None, Xml("ibut", Kind.CONCENTRATION)] = None
    nbutane_ppm: Annotated[float | None, Xml("nbut", Kind.CONCENTRATION)] = None
    ipentane_ppm: Annotated[float | None, Xml("ipent", Kind.CONCENTRATION)] = None


class BitRun(_Model):
    op_time_h: Annotated[float | None, Xml("eTimOpBit", Kind.DURATION)] = None
    md_hole_start_m: Annotated[float | None, Xml("mdHoleStart", L)] = None
    md_hole_stop_m: Annotated[float | None, Xml("mdHoleStop", L)] = None
    rop_avg_mph: Annotated[float | None, Xml("ropAv", Kind.ROP)] = None
    hole_made_m: Annotated[float | None, Xml("mdTotHoleMade", L)] = None
    hrs_drilled_h: Annotated[float | None, Xml("hrsDrilled", Kind.DURATION)] = None
    tot_hrs_drilled_h: Annotated[float | None, Xml("totHrsDrilled", Kind.DURATION)] = None
    tot_rop_mph: Annotated[float | None, Xml("totRop", Kind.ROP)] = None


class Nozzle(_Model):
    count: Annotated[int | None, Xml("numNozzle")] = None
    diameter_m: Annotated[float | None, Xml("diaNozzle", L)] = None


class BitRecord(_Model):
    bit_number: Annotated[str | None, Xml("numBit")] = None
    diameter_m: Annotated[float | None, Xml("diaBit", L)] = None
    manufacturer: Annotated[str | None, Xml("manufacturer")] = None
    code_mfg: Annotated[str | None, Xml("codeMfg")] = None
    code_iadc: Annotated[str | None, Xml("codeIADC")] = None
    cond_inner: Annotated[str | None, Xml("condFinalInner")] = None
    cond_outer: Annotated[str | None, Xml("condFinalOuter")] = None
    cond_dull: Annotated[str | None, Xml("condFinalDull")] = None
    cond_location: Annotated[str | None, Xml("condFinalLocation")] = None
    cond_bearing: Annotated[str | None, Xml("condFinalBearing")] = None
    cond_gauge: Annotated[str | None, Xml("condFinalGauge")] = None
    cond_other: Annotated[str | None, Xml("condFinalOther")] = None
    cond_reason: Annotated[str | None, Xml("condFinalReason")] = None
    comment: Annotated[str | None, Xml("comment")] = None
    run: Annotated[BitRun | None, Xml("bitRun")] = None
    nozzles: Annotated[list[Nozzle], Xml("nozzle")] = []


class CasingRun(_Model):
    casing_type: Annotated[str | None, Xml("casingType")] = None
    start_at: Annotated[datetime | None, Xml("dTimStart")] = None
    end_at: Annotated[datetime | None, Xml("dTimEnd")] = None
    description: Annotated[str | None, Xml("description")] = None


class CasingString(_Model):
    string_type: Annotated[str | None, Xml("type")] = None
    """`c` casing, `l` liner, `t` tubing."""
    inner_diameter_m: Annotated[float | None, Xml("id", L)] = None
    outer_diameter_m: Annotated[float | None, Xml("od", L)] = None
    weight_kgpm: Annotated[float | None, Xml("weight", Kind.LINEAR_MASS)] = None
    grade: Annotated[str | None, Xml("grade")] = None
    connection: Annotated[str | None, Xml("connection")] = None
    length_m: Annotated[float | None, Xml("length", L)] = None
    md_top_m: Annotated[float | None, Xml("mdTop", L)] = None
    md_bottom_m: Annotated[float | None, Xml("mdBottom", L)] = None
    run: Annotated[CasingRun | None, Xml("casing_liner_tubing_run")] = None


class CoreInfo(_Model):
    at: Annotated[datetime | None, Xml("dTim")] = None
    core_number: Annotated[str | None, Xml("coreNumber")] = None
    md_top_m: Annotated[float | None, Xml("mdTop", L)] = None
    md_bottom_m: Annotated[float | None, Xml("mdBottom", L)] = None
    len_recovered_m: Annotated[float | None, Xml("lenRecovered", L)] = None
    recovery_pct: Annotated[float | None, Xml("recoverPc", Kind.FRACTION)] = None
    len_barrel_m: Annotated[float | None, Xml("lenBarrel", L)] = None
    inner_barrel_type: Annotated[str | None, Xml("innerBarrelType")] = None
    description: Annotated[str | None, Xml("coreDescription")] = None


class LogInfo(_Model):
    run_number: Annotated[str | None, Xml("runNumber")] = None
    service_company: Annotated[str | None, Xml("serviceCompany")] = None
    md_top_m: Annotated[float | None, Xml("mdTop", L)] = None
    md_bottom_m: Annotated[float | None, Xml("mdBottom", L)] = None
    tool: Annotated[str | None, Xml("tool")] = None
    temp_bhst_degc: Annotated[float | None, Xml("tempBHST", Kind.TEMPERATURE)] = None
    static_time_h: Annotated[float | None, Xml("eTimStatic", Kind.DURATION)] = None
    md_temp_tool_m: Annotated[float | None, Xml("mdTempTool", L)] = None


class PerfInfo(_Model):
    open_at: Annotated[datetime | None, Xml("dTimOpen")] = None
    close_at: Annotated[datetime | None, Xml("dTimClose")] = None
    md_top_m: Annotated[float | None, Xml("mdTop", L)] = None
    md_bottom_m: Annotated[float | None, Xml("mdBottom", L)] = None


class WellTestInfo(_Model):
    at: Annotated[datetime | None, Xml("dTim")] = None
    test_type: Annotated[str | None, Xml("testType")] = None
    test_number: Annotated[str | None, Xml("testNumber")] = None
    md_top_m: Annotated[float | None, Xml("mdTop", L)] = None
    md_bottom_m: Annotated[float | None, Xml("mdBottom", L)] = None
    choke_orifice_m: Annotated[float | None, Xml("chokeOrificeSize", L)] = None
    density_oil_gcc: Annotated[float | None, Xml("densityOil", Kind.DENSITY)] = None
    density_water_gcc: Annotated[float | None, Xml("densityWater", Kind.DENSITY)] = None
    density_gas_gcc: Annotated[float | None, Xml("densityGas", Kind.DENSITY)] = None
    flow_rate_oil_m3pd: Annotated[float | None, Xml("flowRateOil", Kind.VOLUME_RATE)] = None
    flow_rate_water_m3pd: Annotated[float | None, Xml("flowRateWater", Kind.VOLUME_RATE)] = None
    flow_rate_gas_m3pd: Annotated[float | None, Xml("flowRateGas", Kind.VOLUME_RATE)] = None
    pres_shut_in_kpa: Annotated[float | None, Xml("presShutIn", Kind.PRESSURE)] = None
    pres_flowing_kpa: Annotated[float | None, Xml("presFlowing", Kind.PRESSURE)] = None
    pres_bottom_kpa: Annotated[float | None, Xml("presBottom", Kind.PRESSURE)] = None
    gas_oil_ratio_m3pm3: Annotated[float | None, Xml("gasOilRatio", Kind.VOLUME_RATIO)] = None
    water_oil_ratio_m3pm3: Annotated[float | None, Xml("waterOilRatio", Kind.VOLUME_RATIO)] = None
    chloride_ppm: Annotated[float | None, Xml("chloride", Kind.CONCENTRATION)] = None
    co2_ppm: Annotated[float | None, Xml("carbonDioxide", Kind.CONCENTRATION)] = None
    h2s_ppm: Annotated[float | None, Xml("hydrogenSulfide", Kind.CONCENTRATION)] = None
    vol_oil_total_m3: Annotated[float | None, Xml("volOilTotal", Kind.VOLUME)] = None
    vol_gas_total_m3: Annotated[float | None, Xml("volGasTotal", Kind.VOLUME)] = None
    vol_water_total_m3: Annotated[float | None, Xml("volWaterTotal", Kind.VOLUME)] = None
    vol_oil_stored_m3: Annotated[float | None, Xml("volOilStored", Kind.VOLUME)] = None


class EquipmentFailure(_Model):
    at: Annotated[datetime | None, Xml("dTim")] = None
    md_m: Annotated[float | None, Xml("md", L)] = None
    equip_class: Annotated[str | None, Xml("equipClass")] = None
    missed_production_h: Annotated[float | None, Xml("eTimMissProduction", Kind.DURATION)] = None
    repaired_at: Annotated[datetime | None, Xml("dTimRepair")] = None
    description: Annotated[str | None, Xml("description")] = None


class DrillReport(_Model):
    name_well: Annotated[str | None, Xml("nameWell")] = None
    name_wellbore: Annotated[str | None, Xml("nameWellbore")] = None
    name: Annotated[str | None, Xml("name")] = None
    start_at: Annotated[datetime | None, Xml("dTimStart")] = None
    end_at: Annotated[datetime | None, Xml("dTimEnd")] = None
    version_kind: Annotated[str | None, Xml("versionKind")] = None
    created_at: Annotated[datetime | None, Xml("createDate")] = None
    well_aliases: Annotated[list[Alias], Xml("wellAlias")] = []
    wellbore_aliases: Annotated[list[Alias], Xml("wellboreAlias")] = []
    wellbore_info: Annotated[WellboreInfo | None, Xml("wellboreInfo")] = None
    status: Annotated[StatusInfo | None, Xml("statusInfo")] = None
    bit_records: Annotated[list[BitRecord], Xml("bitRecord")] = []
    casing_strings: Annotated[list[CasingString], Xml("casing_liner_tubing")] = []
    fluids: Annotated[list[Fluid], Xml("fluid")] = []
    pore_pressures: Annotated[list[PorePressure], Xml("porePressure")] = []
    survey_stations: Annotated[list[SurveyStation], Xml("surveyStation")] = []
    activities: Annotated[list[Activity], Xml("activity")] = []
    log_info: Annotated[list[LogInfo], Xml("logInfo")] = []
    core_info: Annotated[list[CoreInfo], Xml("coreInfo")] = []
    well_tests: Annotated[list[WellTestInfo], Xml("wellTestInfo")] = []
    perforations: Annotated[list[PerfInfo], Xml("perfInfo")] = []
    strat_tops: Annotated[list[StratTop], Xml("stratInfo")] = []
    lith_shows: Annotated[list[LithShow], Xml("lithShowInfo")] = []
    gas_readings: Annotated[list[GasReading], Xml("gasReadingInfo")] = []
    equipment_failures: Annotated[list[EquipmentFailure], Xml("equipFailureInfo")] = []

    def alias(self, naming_system: str) -> str | None:
        for alias in self.wellbore_aliases:
            if alias.naming_system == naming_system:
                return alias.name
        return None

    @property
    def wellbore_name(self) -> str:
        """Canonical wellbore name (`15/9-F-1 C`), preferring the regulator code alias."""
        raw = self.alias(NPD_CODE) or self.name_wellbore
        if raw is None:
            raise XmlValueError("drillReport has no wellbore name")
        return canonical_wellbore_name(raw)

    @property
    def npdid_wellbore(self) -> int | None:
        value = self.alias(NPD_NUMBER)
        return int(value) if value is not None and value.isdigit() else None


class DrillReportsDocument(_Model):
    document_info: Annotated[DocumentInfo | None, Xml("documentInfo")] = None
    reports: Annotated[list[DrillReport], Xml("drillReport")] = []


@dataclass(frozen=True, slots=True)
class ParsedDdr:
    document: DrillReportsDocument
    report: ParseReport
    witsml_version: str | None


def parse_ddr(data: bytes) -> ParsedDdr:
    """Parse a WITSML `drillReports` document (one or more daily reports)."""
    root = parse_xml(data)
    if local_name(root) != "drillReports":
        raise XmlValueError(f"expected a drillReports document, got <{local_name(root)}>")
    namespace = root.nsmap.get(root.prefix)
    if namespace != WITSML_NS:
        raise XmlValueError(f"unexpected namespace {namespace!r}; expected WITSML 1.x")
    report = ParseReport.empty()
    document = parse_model(root, DrillReportsDocument, "/drillReports", report)
    if not document.reports:
        raise XmlValueError("drillReports document contains no drillReport")
    return ParsedDdr(document=document, report=report, witsml_version=root.get("version"))


def looks_like_ddr(head: bytes) -> bool:
    """Content sniffing for the ingest router (never trust the file extension)."""
    return b"drillReports" in head and WITSML_NS.encode() in head
