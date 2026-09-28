"""Deterministic hazard lexicon: operator activity codes and free-text phrases.

Tuned on real Volve comments, where routine operations reuse hazard words: "kick drill",
"kick-off", "packer", "overpull tested", "leak tested", "flow checked - static", "no losses".
Each text rule has an optional sentence-level exclusion, and every match is checked for a
preceding negation ("no", "without", ...) before it counts.

Rule ids are stable: they are stored as evidence and quoted in evaluation reports.
"""

import re
from dataclasses import dataclass
from typing import Final

from drillsage.domain.hazards import HazardType

H = HazardType
_I = re.IGNORECASE


@dataclass(frozen=True, slots=True)
class CodeRule:
    id: str
    hazard: HazardType
    proprietary_code: str | None = None
    state_detail: str | None = None
    subtype: str | None = None


@dataclass(frozen=True, slots=True)
class TextRule:
    id: str
    hazard: HazardType
    pattern: re.Pattern[str]
    exclude: re.Pattern[str] | None = None
    """Skip the match when its sentence matches this (routine uses of the same words)."""
    require: re.Pattern[str] | None = None
    """Keep the match only when its sentence also matches this (context the word needs)."""
    subtype: str | None = None


def _re(*alternatives: str) -> re.Pattern[str]:
    """Case-insensitive pattern matching any of `alternatives` (one per line for review)."""
    return re.compile("|".join(alternatives), _I)


CODE_RULES: Final[tuple[CodeRule, ...]] = (
    CodeRule("code.lost_circulation", H.LOST_CIRCULATION, "interruption -- lost circulation"),
    CodeRule("detail.circulation_loss", H.LOST_CIRCULATION, state_detail="circulation loss"),
    CodeRule("detail.mud_loss", H.LOST_CIRCULATION, state_detail="mud loss"),
    CodeRule("code.well_control", H.WELL_CONTROL, "interruption -- well control"),
    CodeRule("detail.stuck_equipment", H.STUCK_PIPE, state_detail="stuck equipment"),
    CodeRule("code.fish", H.FISHING_JUNK, "interruption -- fish"),
    CodeRule(
        "code.waiting_on_weather",
        H.WAITING,
        "interruption -- waiting on weather",
        subtype="weather",
    ),
    CodeRule("code.wait", H.WAITING, "interruption -- wait"),
    CodeRule("code.repair", H.EQUIPMENT_FAILURE, "interruption -- repair"),
    CodeRule("detail.equipment_failure", H.EQUIPMENT_FAILURE, state_detail="equipment failure"),
)
"""Operator codes are episode-level weak labels (a whole fishing job is coded `fish`, including
its toolbox talks); they seed events but never provide depth or text evidence on their own."""

_PIPE_WORDS = (
    r"(?:string|pipe|dp|drill ?pipe|drill ?string|bha|assembly|tool|jt|joint|sub|connection)"
)

TEXT_RULES: Final[tuple[TextRule, ...]] = (
    # ---------------------------------------------------------------- lost circulation
    TextRule(
        "lc.losses",
        H.LOST_CIRCULATION,
        _re(
            r"\blosses\b",
            r"\blos(?:s|t|ing)\b[^.;\n]{0,25}?\b(?:mud|m3|bbls?|returns|to (?:the )?formation"
            r"|circulation)\b",
        ),
        exclude=_re(
            r"\bloss of (?:signal|communication|power|prime|pressure)\b",
            r"\bpressure loss",
            r"\bleak\w*\b",
            r"\bslip joint\b",
            r"\bspill\w*\b",
            r"\bsurface (?:system|equipment|lines?)\b",
        ),
    ),
    TextRule("lc.lost_circulation", H.LOST_CIRCULATION, _re(r"\blost circ\w*")),
    TextRule(
        "lc.no_returns",
        H.LOST_CIRCULATION,
        _re(r"\b(?:no|partial|reduced|lost) returns\b"),
        exclude=_re(
            r"\bseals?\b",
            r"\bball seat\b",
            r"\bplug\w*\b",
            r"\bcement unit\b",
            r"\bpressure test",
            r"\bannulus\b",
            r"\bwellhead\b",
            r"\bWH\b",
            r"\bbled back\b",
        ),
        subtype="returns",
    ),
    # ---------------------------------------------------------------- well control
    TextRule(
        "wc.kick",
        H.WELL_CONTROL,
        _re(
            r"\bkick\b(?![\s-]*(?:drill|off|assembly|sub|out|tolerance|valve|stand|plates?|joint))"
        ),
        exclude=_re(r"\bkick[\s-]*(?:drill|off)\b|\bkicked off\b"),
    ),
    TextRule("wc.influx", H.WELL_CONTROL, _re(r"\binflux\b"), exclude=_re(r"\binflux test")),
    TextRule(
        "wc.shut_in",
        H.WELL_CONTROL,
        _re(
            r"\bSICP\b",
            r"\bSIDPP\b",
            r"\bshut[\s-]?in (?:the )?well\b",
            r"\bS/I well\b",
        ),
        exclude=_re(r"\b(?:test|drill|procedure|plan)\w*\b"),
    ),
    TextRule(
        "wc.gain",
        H.WELL_CONTROL,
        _re(
            r"\b(?:pit )?gain(?:ed|ing)?\b[^.;\n]{0,20}?\b\d+(?:[.,]\d+)?\s?(?:m3|bbls?|l)\b",
            r"\bslight gain\b",
            r"\bgain in (?:the )?(?:pit|trip tank)",
        ),
    ),
    TextRule(
        "wc.flowing",
        H.WELL_CONTROL,
        _re(
            r"\bwell (?:was )?flowing\b",
            r"\bflow ?check\w*[^.;\n]{0,25}?\b(?:positive|flowing|gain)\b",
        ),
        exclude=_re(r"\bnegative\b|\bstatic\b"),
    ),
    TextRule(
        "wc.gas",
        H.WELL_CONTROL,
        _re(r"\bgas[\s-]?cut\b|\bhigh gas\b|\bgas peak\b|\bgas influx\b"),
        subtype="gas",
    ),
    # ---------------------------------------------------------------- stuck pipe
    TextRule(
        "sp.stuck",
        H.STUCK_PIPE,
        _re(r"\b(?:differentially )?stuck\b"),
        exclude=_re(
            r"\bstuck pipe (?:drill|procedure|contingenc)",
            r"\bpotential\b",
            r"\brisk\b",
            r"\bfocus\w*\b",
            r"\btong\b",
            r"\bprotectors?\b",
            r"\bsetting tool\b",
            r"\bvalve\b",
            r"\bslips\b",
            r"\bfingerboard\b",
            r"\bderrick\b",
        ),
        require=_re(
            rf"\b{_PIPE_WORDS}\b",
            r"\b(?:casing|liner|bit|differential\w*|wire ?line|logging tool|hole)\b",
            r"\bstuck pipe\b",
        ),
    ),
    TextRule(
        "sp.jarring",
        H.STUCK_PIPE,
        _re(
            r"\bjarr(?:ed|ing)\b",
            r"\bjar(?:red)? (?:up|down)\b",
            r"\bfired (?:the )?jars?\b",
        ),
    ),
    TextRule(
        "sp.worked_free",
        H.STUCK_PIPE,
        _re(
            rf"\bwork(?:ed|ing) (?:the )?{_PIPE_WORDS}[^.;\n]{{0,20}}?\bfree\b",
            r"\b(?:got|came|pulled) free\b",
        ),
    ),
    TextRule(
        "sp.back_off",
        H.STUCK_PIPE,
        _re(
            r"\bstring ?shot\b",
            r"\bback(?:ed)?[\s-]?off (?:the )?(?:string|pipe|dp)",
            r"\bsever(?:ance|ing|ed)? (?:charge|the)\b",
        ),
    ),
    # ---------------------------------------------------------------- tight hole
    TextRule(
        "th.tight",
        H.TIGHT_HOLE,
        _re(
            r"\btight (?:hole|spots?|section|area)\b",
            r"\bhole (?:was |became )?tight\b",
            r"\btight (?:at|from|between)\b",
        ),
    ),
    TextRule(
        "th.overpull",
        H.TIGHT_HOLE,
        _re(r"\boverpull\b"),
        exclude=_re(
            r"\btest\w*\b",
            r"\bapplied\b",
            r"\bmaintain\w*\b",
            r"\badjustable\b",
            r"\bhanger\b",
            r"\blanding\b",
            r"\blatch\w*\b",
            r"\bconfirm\w*\b",
            r"\bverif\w*\b",
            r"\bpacker\b",
            r"\bshear\w*\b",
            r"\bset(?:ting)? (?:sequence|tool)\b",
            r"\blogging tool\b",
            r"\bseals?\b",
            r"\bPBR\b",
            r"\btie[\s-]?back\b",
            r"\briser\b",
            r"\bmultibowl\b",
            r"\bslips\b",
            r"\bj[\s-]?slot\b",
            r"\bplug\b",
            r"\bensure\b",
            r"\bengag\w*\b",
        ),
        require=_re(
            r"\bPOOH\b",
            r"\bpull\w*\b",
            r"\btight\b",
            r"\bhole\b",
            r"\bBHA\b",
            r"\bworked\b",
            r"\breciprocat\w*",
            r"\d{2,5}(?:[.,]\d+)?\s?m\b",
        ),
    ),
    TextRule(
        "th.drag",
        H.TIGHT_HOLE,
        _re(
            r"\b(?:high|excessive|abnormal)\s(?:drag|torque)\b",
            r"\bdrag increase\b",
            r"\b\d+\s?(?:t|mt|tons?|tonn)\s(?:of )?drag\b",
        ),
    ),
    TextRule(
        "th.took_weight",
        H.TIGHT_HOLE,
        _re(
            r"\btook (?:\d+(?:[.,]\d+)?(?:\s?-\s?\d+)?\s?(?:t|mt|tons?|tonn|klbs?)\s)?(?:weight"
            r"|wt)\b",
            r"\btag(?:ged)? (?:an )?obstruction\b",
        ),
        exclude=_re(
            r"\b(?:casing|csg|liner|screen|packer|plug|cement|toc|fish|hanger|retainer|PBR|seal"
            r"|stinger|mill|tie[\s-]?back)\b"
        ),
    ),
    TextRule(
        "th.restriction",
        H.TIGHT_HOLE,
        _re(r"\brestrictions?\b|\bobstructions?\b"),
        exclude=_re(
            r"\bgyro\b",
            r"\bpulling speed\b",
            r"\bsurface (?:line|equipment)",
            r"\bwellhead\b",
            r"\bno (?:\w+\s){0,2}(?:restrictions?|obstructions?)",
        ),
    ),
    TextRule(
        "th.backream",
        H.TIGHT_HOLE,
        _re(
            r"\bback[\s-]?ream(?:ed|ing)?\b",
            r"\bream(?:ed|ing)? (?:the )?(?:tight|through tight|through (?:the )?restriction)",
        ),
    ),
    # ---------------------------------------------------------------- wellbore instability
    TextRule(
        "wi.packoff",
        H.WELLBORE_INSTABILITY,
        _re(
            r"\bpack(?:ed|ing)?[\s-]?off\b(?![\s-]*(?:running|bushing|tool|element|seal|assembly"
            r"|nut))"
        ),
        exclude=_re(r"\brunning tool\b|\bbushing\b|\bwellhead\b"),
        subtype="pack-off",
    ),
    TextRule(
        "wi.cavings",
        H.WELLBORE_INSTABILITY,
        _re(r"\bcavings?\b|\bsplintery\b|\bsloughing\b"),
        subtype="cavings",
    ),
    TextRule(
        "wi.washout",
        H.WELLBORE_INSTABILITY,
        _re(
            r"\bhole (?:was )?wash(?:ed)?[\s-]?out\b",
            r"\bwash[\s-]?outs? in (?:the )?(?:open )?hole\b",
            r"\bwashed[\s-]out hole\b",
            r"\bover[\s-]?gauge\b",
            r"\benlarged hole\b",
        ),
        subtype="washout",
    ),
    TextRule(
        "wi.fill",
        H.WELLBORE_INSTABILITY,
        _re(
            r"\b\d+(?:[.,]\d+)?\s?m (?:of )?fill\b",
            r"\bfill on bottom\b",
            r"\bhole (?:collapse|instability)\b",
        ),
        subtype="fill",
    ),
    # ---------------------------------------------------------------- shallow gas / H2S
    TextRule(
        "sg.shallow_gas",
        H.SHALLOW_GAS_H2S,
        _re(r"\bshallow gas\b"),
        exclude=_re(
            r"\bpilot hole\b",
            r"\bprocedure",
            r"\bcontingenc",
            r"\bmeeting\b",
            r"\bdrill\b",
        ),
    ),
    TextRule(
        "sg.h2s",
        H.SHALLOW_GAS_H2S,
        _re(r"\bH2S\b"),
        exclude=_re(
            r"\bmeeting\b",
            r"\bprocedure",
            r"\bcontingenc",
            r"\bdrill\b",
            r"\bsensor\w*\b",
            r"\bscav[ae]ng\w*",
            r"\beventual\b",
            r"\bno (?:\w+[\s/])?(?:gas|H2S)\b",
        ),
    ),
    # ---------------------------------------------------------------- cementing
    TextRule(
        "cm.problem",
        H.CEMENTING,
        _re(
            r"\b(?:no|lost|partial) cement returns\b",
            r"\bcement (?:was )?(?:not|never) (?:set|hard)",
            r"\bgreen cement\b",
            r"\b(?:failed to|did not|unable to) bump\b",
            r"\bremedial (?:cement|squeeze)",
            r"\bsqueeze cement\w*\b",
            r"\bcement squeeze\b",
            r"\bwet shoe\b",
            r"\bchannel(?:l)?ing\b",
            r"\b(?:FIT|LOT)\b[^.;\n]{0,20}?\bfail\w*",
        ),
    ),
    # ---------------------------------------------------------------- casing running
    TextRule(
        "cr.problem",
        H.CASING_RUNNING,
        _re(
            r"\b(?:casing|csg|liner)\b[^.;\n]{0,60}?\b(?:stuck|took weight|set down|held up"
            r"|hung up|unable to (?:pass|run|get|work)|could not (?:pass|get|run|work)"
            r"|not able to (?:pass|get))\b"
        ),
        exclude=_re(r"\btong\b|\btransport frame\b|\bcoupling\b"),
    ),
    # ---------------------------------------------------------------- directional
    TextRule(
        "dd.problem",
        H.DIRECTIONAL,
        _re(
            r"\b(?:unable|could not|not able) to (?:build|turn|drop|steer|orient)\b",
            r"\bhigh dog[\s-]?leg\b",
            r"\banti[\s-]?collision\b(?! system)",
            r"\bcollision risk\b",
            r"\boff target\b",
            r"\blost tool ?face\b",
        ),
    ),
    # ---------------------------------------------------------------- equipment failure
    TextRule(
        "ef.failure",
        H.EQUIPMENT_FAILURE,
        _re(
            r"\b(?:fail(?:ed|ure|ing)|malfunction\w*|broke down|breakdown|not working"
            r"|out of order)\b"
        ),
        exclude=_re(
            r"\b(?:test|pressure test|leak test|inflow test|FIT|LOT)\w*\b[^.;\n]{0,15}\bfail",
            r"\bfailed to bump\b",
            r"\bno fail",
        ),
    ),
    TextRule(
        "ef.washout_in_string",
        H.EQUIPMENT_FAILURE,
        _re(
            rf"\bwash[\s-]?out\b[^.;\n]{{0,30}}?\b{_PIPE_WORDS}\b",
            rf"\b{_PIPE_WORDS}\b[^.;\n]{{0,30}}?\bwash[\s-]?out\b",
        ),
        subtype="string washout",
    ),
    # ---------------------------------------------------------------- fishing / junk
    TextRule(
        "fj.fishing",
        H.FISHING_JUNK,
        _re(r"\bfish(?:ing)?\b(?![\s-]*neck)"),
        exclude=_re(r"\bfishing neck\b|\brisk assess"),
    ),
    TextRule(
        "fj.junk",
        H.FISHING_JUNK,
        _re(
            r"\bjunk (?:mill|in (?:the )?hole)\b",
            r"\bleft in (?:the )?hole\b",
            r"\btwist(?:ed)?[\s-]?off\b",
            r"\b(?:bha|string|pipe|dp|wire(?:line)?) (?:had |was )?parted\b",
        ),
    ),
    # ---------------------------------------------------------------- waiting
    TextRule(
        "wt.weather",
        H.WAITING,
        _re(
            r"\bwait(?:ed|ing)? on (?:the )?weather\b",
            r"\bWOW\b",
            r"\bdue to (?:bad |high )?(?:weather|wind|waves|heave)\b",
        ),
        subtype="weather",
    ),
)

NEGATION: Final = re.compile(
    r"\b(?:no|not|nil|without|zero|negative|non|never)\b(?:[\s/-]+[\w.,]+){0,3}[\s/-]*$", _I
)
"""A negation cue within three words before a match (`NO LOSSES`, `no mud losses`)."""


@dataclass(frozen=True, slots=True)
class MitigationRule:
    id: str
    action: str
    pattern: re.Pattern[str]
    hazards: frozenset[HazardType]


_ALL_GEO = frozenset(
    {H.LOST_CIRCULATION, H.WELL_CONTROL, H.STUCK_PIPE, H.TIGHT_HOLE, H.WELLBORE_INSTABILITY}
)

MITIGATION_RULES: Final[tuple[MitigationRule, ...]] = (
    MitigationRule(
        "mt.lcm",
        "Pumped LCM pill",
        _re(
            r"\b(?:pumped|spotted|set|placed|bled in)\b[^.;\n]{0,40}?\b(?:LCM"
            r"|lost circulation material|fibre|calcium carbonate|CaCO3)\b"
        ),
        frozenset({H.LOST_CIRCULATION}),
    ),
    MitigationRule(
        "mt.reduce_rate",
        "Reduced circulation rate",
        _re(
            r"\breduc\w+ (?:the )?(?:circulat\w+ |pump |flow )?rate\b",
            r"\breduced (?:flow|pump rate)",
        ),
        frozenset({H.LOST_CIRCULATION, H.WELLBORE_INSTABILITY}),
    ),
    MitigationRule(
        "mt.reduce_mw",
        "Reduced mud weight",
        _re(
            r"\breduc\w+ (?:the )?mud (?:weight|density)\b",
            r"\bcut back mud weight\b",
        ),
        frozenset({H.LOST_CIRCULATION}),
    ),
    MitigationRule(
        "mt.increase_mw",
        "Increased mud weight",
        _re(
            r"\b(?:increas\w+|rais\w+|weight\w* up)\b[^.;\n]{0,20}?\b(?:mud (?:weight|density)"
            r"|MW)\b",
            r"\bweighted up\b",
        ),
        frozenset({H.WELL_CONTROL, H.WELLBORE_INSTABILITY, H.TIGHT_HOLE}),
    ),
    MitigationRule(
        "mt.cement_plug",
        "Set cement plug",
        _re(r"\b(?:set|pumped|spotted)\b[^.;\n]{0,25}?\bcement plug\b"),
        frozenset({H.LOST_CIRCULATION}),
    ),
    MitigationRule(
        "mt.shut_in",
        "Shut in well",
        _re(r"\bshut[\s-]?in\b|\bclosed (?:the )?(?:BOP|annular|pipe ram)"),
        frozenset({H.WELL_CONTROL}),
    ),
    MitigationRule(
        "mt.circulate_choke",
        "Circulated out through choke",
        _re(
            r"\bcirculat\w+[^.;\n]{0,40}?\bchoke\b",
            r"\bdriller'?s method\b",
            r"\bbullhead\w*",
        ),
        frozenset({H.WELL_CONTROL}),
    ),
    MitigationRule("mt.jar", "Jarred", _re(r"\bjarr(?:ed|ing)\b"), frozenset({H.STUCK_PIPE})),
    MitigationRule(
        "mt.work_pipe",
        "Worked pipe",
        _re(rf"\bwork(?:ed|ing) (?:the )?{_PIPE_WORDS}\b"),
        frozenset({H.STUCK_PIPE, H.TIGHT_HOLE}),
    ),
    MitigationRule(
        "mt.spot_pill",
        "Spotted freeing pill",
        _re(
            r"\bspot(?:ted)?\b[^.;\n]{0,30}?\b(?:pipe[\s-]?lax|acid|oil|freeing|diesel) (?:pill"
            r"|spot)?"
        ),
        frozenset({H.STUCK_PIPE}),
    ),
    MitigationRule(
        "mt.back_off",
        "Backed off string",
        _re(r"\bback(?:ed)?[\s-]?off\b|\bstring ?shot\b|\bsever\w*"),
        frozenset({H.STUCK_PIPE}),
    ),
    MitigationRule(
        "mt.ream",
        "Reamed / back-reamed",
        _re(r"\b(?:back[\s-]?)?ream(?:ed|ing)\b"),
        frozenset({H.TIGHT_HOLE, H.WELLBORE_INSTABILITY}),
    ),
    MitigationRule(
        "mt.wiper",
        "Wiper trip",
        _re(r"\bwiper trip\b|\bshort trip\b"),
        frozenset({H.TIGHT_HOLE, H.WELLBORE_INSTABILITY}),
    ),
    MitigationRule(
        "mt.circulate_clean",
        "Circulated hole clean",
        _re(
            r"\bcirculat\w+ (?:the )?hole clean\b",
            r"\bcirculat\w+ (?:\d+ x )?(?:bottoms? up|until (?:shakers|hole) clean)",
        ),
        _ALL_GEO,
    ),
    MitigationRule(
        "mt.hivis",
        "Pumped hi-vis sweep",
        _re(r"\bhi(?:gh)?[\s-]?vis\w*\b(?: pill| sweep)?"),
        frozenset({H.WELLBORE_INSTABILITY, H.TIGHT_HOLE}),
    ),
    MitigationRule(
        "mt.fishing_tool",
        "Ran fishing tool",
        _re(
            r"\bovershot (?:assembly|bha)\b",
            r"\bjunk mill\b",
            r"\bfishing (?:bha|assembly|tool|jars?)\b",
            r"\bengaged (?:the )?fish\b",
        ),
        frozenset({H.FISHING_JUNK}),
    ),
    MitigationRule(
        "mt.sidetrack",
        "Sidetracked",
        _re(r"\bsidetrack\w*\b"),
        frozenset({H.STUCK_PIPE, H.FISHING_JUNK, H.LOST_CIRCULATION, H.WELLBORE_INSTABILITY}),
    ),
)

OUTCOME_SUCCESS: Final = _re(
    r"\blosses (?:cured|stopped|healed|reduced)\b",
    r"\bregained (?:full )?(?:returns|circulation)\b",
    r"\bfull returns\b",
    r"\b(?:got|came|pulled|worked|was) (?:string |pipe )?free\b",
    r"\bwell (?:static|dead|stable)\b",
    r"\b(?:fish )?(?:recovered|retrieved|caught)\b",
    r"\bpassed (?:ok|freely|without)\b",
)
OUTCOME_FAILURE: Final = _re(
    r"\bno success\b",
    r"\bunsuccessful\w*\b",
    r"\bwithout success\b",
    r"\bnegative\b",
    r"\bno progress\b",
    r"\bstill (?:stuck|losing)\b",
    r"\bnot recovered\b",
)
