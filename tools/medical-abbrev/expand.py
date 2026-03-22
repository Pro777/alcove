"""Alcove medical abbreviation expander — clinical search quality plugin (#434).

Expands clinical abbreviations so that ``"patient has SOB and HTN"`` matches
documents containing ``"shortness of breath"`` and ``"hypertension"``.

This is the search-quality component of clinical alcove deployments: a
doctor types ``"last UTI"`` and alcove expands the query to include ``"urinary
tract infection"`` before running the vector search — locally, no cloud call.

Intended usage
--------------
1. **Query expansion** — wrap the user's search query before embedding::

       from tools.medical_abbrev.expand import expand_query
       expanded = expand_query("SOB + chest pain + hx MI")
       # → "shortness of breath + chest pain + history myocardial infarction"

2. **Ingest pre-processing** — expand abbreviations in documents at ingest
   time to improve recall for full-term queries.

3. **Standalone CLI** for testing::

       python tools/medical-abbrev/expand.py expand --text "Pt c/o SOB, HTN, DM2"
       python tools/medical-abbrev/expand.py list-abbrevs
       python tools/medical-abbrev/expand.py expand --text "..." --context clinical

Abbreviation coverage
---------------------
Covers ~150 common clinical abbreviations across:

- **Symptoms / findings** — SOB, CP, HA, N/V, ...
- **Diagnoses** — HTN, DM, MI, CHF, COPD, ...
- **Chart / note shorthand** — HPI, PMH, ROS, SOAP sections, c/o, hx, ...
- **Anatomical / specialties** — CV, GI, GU, MSK, Neuro, ...
- **Labs / vitals** — HR, BP, RR, SpO2, BMI, ...
- **Medications / Rx** — PO, IV, PRN, BID, TID, QD, ...
- **Social history** — Pt, F/U, d/c, h/o, ...

Design notes
------------
- Expansion is **token-based** (word boundary matching) — ``"MI"`` expands
  within ``"Pt hx MI"`` but not within ``"AMINO"``.
- Abbreviations are matched **case-insensitively** by default; the original
  case is preserved when ``preserve_case=True``.
- ``expand_query()`` additionally deduplicates the expansion to avoid
  embedding noise (``"SOB"`` → ``"shortness of breath"`` not
  ``"SOB shortness of breath shortness of breath"``).
- The ``ABBREVS`` dict is the single source of truth — extend it freely.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo root on sys.path
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Abbreviation dictionary
# ---------------------------------------------------------------------------

# Keys are uppercase canonical forms.  Values are the full expansion.
ABBREVS: dict[str, str] = {
    # --- Symptoms / findings ---
    "SOB": "shortness of breath",
    "SOBOE": "shortness of breath on exertion",
    "CP": "chest pain",
    "HA": "headache",
    "N/V": "nausea and vomiting",
    "N/V/D": "nausea vomiting and diarrhea",
    "DOE": "dyspnea on exertion",
    "PND": "paroxysmal nocturnal dyspnea",
    "LOC": "loss of consciousness",
    "ALOC": "altered level of consciousness",
    "AMS": "altered mental status",
    "BRBPR": "bright red blood per rectum",
    "GERD": "gastroesophageal reflux disease",
    "LBP": "low back pain",
    "LE": "lower extremity",
    "UE": "upper extremity",
    "BLE": "bilateral lower extremities",
    "BUE": "bilateral upper extremities",
    "RUE": "right upper extremity",
    "LUE": "left upper extremity",
    "RLE": "right lower extremity",
    "LLE": "left lower extremity",
    "RUQ": "right upper quadrant",
    "LUQ": "left upper quadrant",
    "RLQ": "right lower quadrant",
    "LLQ": "left lower quadrant",
    "NSVT": "non-sustained ventricular tachycardia",
    "SVT": "supraventricular tachycardia",
    "VT": "ventricular tachycardia",
    "VF": "ventricular fibrillation",
    "AF": "atrial fibrillation",
    "AFIB": "atrial fibrillation",
    "AFLUTTER": "atrial flutter",
    "DVT": "deep vein thrombosis",
    "PE": "pulmonary embolism",
    "TIA": "transient ischemic attack",
    "CVA": "cerebrovascular accident stroke",
    "UTI": "urinary tract infection",
    "URI": "upper respiratory infection",
    "URTI": "upper respiratory tract infection",
    "LRTI": "lower respiratory tract infection",

    # --- Diagnoses / conditions ---
    "HTN": "hypertension",
    "DM": "diabetes mellitus",
    "DM1": "type 1 diabetes mellitus",
    "DM2": "type 2 diabetes mellitus",
    "T2DM": "type 2 diabetes mellitus",
    "T1DM": "type 1 diabetes mellitus",
    "MI": "myocardial infarction",
    "NSTEMI": "non-ST-elevation myocardial infarction",
    "STEMI": "ST-elevation myocardial infarction",
    "CHF": "congestive heart failure",
    "HF": "heart failure",
    "COPD": "chronic obstructive pulmonary disease",
    "CKD": "chronic kidney disease",
    "AKI": "acute kidney injury",
    "ESRD": "end stage renal disease",
    "CAD": "coronary artery disease",
    "PVD": "peripheral vascular disease",
    "PAD": "peripheral artery disease",
    "RA": "rheumatoid arthritis",
    "OA": "osteoarthritis",
    "OSA": "obstructive sleep apnea",
    "PTSD": "post-traumatic stress disorder",
    "MDD": "major depressive disorder",
    "GAD": "generalized anxiety disorder",
    "OCD": "obsessive compulsive disorder",
    "ADHD": "attention deficit hyperactivity disorder",
    "ADD": "attention deficit disorder",
    "ASD": "autism spectrum disorder",
    "MS": "multiple sclerosis",
    "ALS": "amyotrophic lateral sclerosis",
    "PD": "Parkinson disease",
    "AD": "Alzheimer disease",
    "SLE": "systemic lupus erythematosus",
    "IBD": "inflammatory bowel disease",
    "UC": "ulcerative colitis",
    "NAFLD": "non-alcoholic fatty liver disease",
    "NASH": "non-alcoholic steatohepatitis",
    "HCC": "hepatocellular carcinoma",
    "CRC": "colorectal cancer",
    "NHL": "non-Hodgkin lymphoma",
    "HL": "Hodgkin lymphoma",
    "CLL": "chronic lymphocytic leukemia",
    "AML": "acute myeloid leukemia",
    "ALL": "acute lymphoblastic leukemia",

    # --- SOAP / chart shorthand ---
    "HPI": "history of present illness",
    "PMH": "past medical history",
    "PMHX": "past medical history",
    "PSH": "past surgical history",
    "PSHX": "past surgical history",
    "FH": "family history",
    "FHX": "family history",
    "SH": "social history",
    "SHX": "social history",
    "ROS": "review of systems",
    "HX": "history",
    "H/O": "history of",
    "C/O": "complains of",
    "S/P": "status post",
    "W/U": "workup",
    "F/U": "follow up",
    "PT": "patient",
    "YO": "year old",
    "YOM": "year old male",
    "YOF": "year old female",
    "M": "male",
    "F": "female",
    "A&O": "alert and oriented",
    "AOX3": "alert and oriented times three",
    "AOX4": "alert and oriented times four",
    "NAD": "no acute distress",
    "WNL": "within normal limits",
    "NKA": "no known allergies",
    "NKDA": "no known drug allergies",
    "DNR": "do not resuscitate",
    "DNI": "do not intubate",
    "FULL CODE": "full resuscitation",
    "D/C": "discharge or discontinue",
    "R/O": "rule out",
    "A/W": "associated with",
    "B/L": "bilateral",
    "BL": "bilateral",

    # --- Labs / vitals ---
    "HR": "heart rate",
    "BP": "blood pressure",
    "RR": "respiratory rate",
    "SPO2": "oxygen saturation",
    "O2SAT": "oxygen saturation",
    "BMI": "body mass index",
    "WBC": "white blood cell count",
    "RBC": "red blood cell count",
    "HGB": "hemoglobin",
    "HCT": "hematocrit",
    "PLT": "platelet count",
    "BMP": "basic metabolic panel",
    "CMP": "comprehensive metabolic panel",
    "LFT": "liver function tests",
    "TSH": "thyroid stimulating hormone",
    "HBA1C": "hemoglobin A1c",
    "A1C": "hemoglobin A1c",
    "BNP": "B-type natriuretic peptide",
    "TROPONIN": "troponin",
    "INR": "international normalized ratio",
    "PTT": "partial thromboplastin time",
    "ESR": "erythrocyte sedimentation rate",
    "CRP": "C-reactive protein",
    "UA": "urinalysis",
    "UCX": "urine culture",
    "BCX": "blood culture",
    "EKG": "electrocardiogram",
    "ECG": "electrocardiogram",
    "CXR": "chest x-ray",
    "CT": "computed tomography",
    "MRI": "magnetic resonance imaging",
    "US": "ultrasound",
    "ECHO": "echocardiogram",
    "EEG": "electroencephalogram",
    "EMG": "electromyogram",

    # --- Medications / Rx ---
    "PO": "by mouth oral",
    "IV": "intravenous",
    "IM": "intramuscular",
    "SQ": "subcutaneous",
    "SL": "sublingual",
    "PR": "per rectum",
    "PRN": "as needed",
    "BID": "twice daily",
    "TID": "three times daily",
    "QID": "four times daily",
    "QD": "once daily",
    "QHS": "every night at bedtime",
    "QAM": "every morning",
    "Q4H": "every 4 hours",
    "Q6H": "every 6 hours",
    "Q8H": "every 8 hours",
    "Q12H": "every 12 hours",
    "NPO": "nothing by mouth",
    "ASA": "aspirin",
    "APAP": "acetaminophen",
    "NSAID": "non-steroidal anti-inflammatory drug",
    "ACE": "ACE inhibitor",
    "ACEI": "ACE inhibitor",
    "ARB": "angiotensin receptor blocker",
    "BB": "beta blocker",
    "CCB": "calcium channel blocker",
    "SSRI": "selective serotonin reuptake inhibitor",
    "SNRI": "serotonin norepinephrine reuptake inhibitor",
    "PPI": "proton pump inhibitor",
    "H2": "H2 blocker",
    "LABA": "long-acting beta agonist",
    "SABA": "short-acting beta agonist",
    "ICS": "inhaled corticosteroid",
    "GLP1": "GLP-1 agonist",
    "SGLT2": "SGLT-2 inhibitor",

    # --- Procedures / interventions ---
    "CABG": "coronary artery bypass graft",
    "PCI": "percutaneous coronary intervention",
    "PTCA": "percutaneous transluminal coronary angioplasty",
    "TAVR": "transcatheter aortic valve replacement",
    "AVR": "aortic valve replacement",
    "MVR": "mitral valve replacement",
    "ICD": "implantable cardioverter defibrillator",
    "PPM": "permanent pacemaker",
    "ERCP": "endoscopic retrograde cholangiopancreatography",
    "EGD": "esophagogastroduodenoscopy",
    "TURP": "transurethral resection of the prostate",
    "THR": "total hip replacement",
    "TKR": "total knee replacement",
    "LP": "lumbar puncture",
    "BX": "biopsy",
    "I&D": "incision and drainage",
}

# ---------------------------------------------------------------------------
# Core expansion functions
# ---------------------------------------------------------------------------


def _build_pattern(abbrevs: dict[str, str]) -> re.Pattern:
    """Build a compiled regex for word-boundary abbreviation matching."""
    # Escape each abbreviation for regex, sort longest-first to avoid
    # short matches shadowing longer ones (e.g. "DM" vs "DM2").
    sorted_keys = sorted(abbrevs.keys(), key=len, reverse=True)
    escaped = [re.escape(k) for k in sorted_keys]
    return re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)


def expand_text(
    text: str,
    *,
    abbrevs: dict[str, str] | None = None,
    preserve_case: bool = False,
) -> str:
    """Replace clinical abbreviations in *text* with their expansions.

    Parameters
    ----------
    text:
        Input text (clinical note, query string, etc.).
    abbrevs:
        Override abbreviation dict.  Defaults to the built-in ``ABBREVS``.
    preserve_case:
        If ``True``, return the expansion with the same case style as the
        matched abbreviation token.  If ``False`` (default), the expansion
        is returned in lowercase.
    """
    d = abbrevs if abbrevs is not None else ABBREVS
    pattern = _build_pattern(d)

    def replace(m: re.Match) -> str:
        token = m.group(1)
        expansion = d.get(token.upper(), token)
        if preserve_case and token.isupper():
            return expansion.upper()
        return expansion

    return pattern.sub(replace, text)


def expand_query(
    query: str,
    *,
    abbrevs: dict[str, str] | None = None,
    include_original: bool = True,
) -> str:
    """Expand a search query, appending long-form terms alongside abbreviations.

    Unlike ``expand_text``, this does **not** replace the original token —
    it appends the expansion so both the abbreviation and full term are in
    the query string (maximising recall for both abbreviation and full-text
    indexed documents).

    Parameters
    ----------
    query:
        User search query.
    abbrevs:
        Override abbreviation dict.
    include_original:
        If ``True`` (default), keep the original abbreviation alongside the
        expansion.  If ``False``, replace the abbreviation.

    Returns
    -------
    str
        Expanded query string with duplicates removed.
    """
    d = abbrevs if abbrevs is not None else ABBREVS
    pattern = _build_pattern(d)

    seen: set[str] = set()
    parts: list[str] = []
    last_end = 0

    for m in pattern.finditer(query):
        # Emit any non-matching text between the last match and this one
        gap = query[last_end:m.start()]
        if gap:
            for word in gap.split():
                if word.lower() not in seen:
                    parts.append(word)
                    seen.add(word.lower())
        last_end = m.end()

        token = m.group(1)
        upper = token.upper()
        expansion = d.get(upper, token)
        if include_original and upper not in seen:
            parts.append(token)
            seen.add(upper)
        for term in expansion.split():
            if term.lower() not in seen:
                parts.append(term)
                seen.add(term.lower())

    # Emit any remaining non-matching text after the last match
    tail = query[last_end:]
    if tail:
        for word in tail.split():
            if word.lower() not in seen:
                parts.append(word)
                seen.add(word.lower())

    return " ".join(parts)


def list_abbrevs(
    *,
    abbrevs: dict[str, str] | None = None,
    prefix: str = "",
) -> list[dict[str, str]]:
    """Return a sorted list of ``{abbrev, expansion}`` dicts.

    Parameters
    ----------
    abbrevs:
        Override dict.
    prefix:
        If provided, filter to abbreviations starting with this prefix
        (case-insensitive).
    """
    d = abbrevs if abbrevs is not None else ABBREVS
    results = [
        {"abbrev": k, "expansion": v}
        for k, v in sorted(d.items())
        if k.upper().startswith(prefix.upper())
    ]
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_expand(args: argparse.Namespace) -> int:
    result = expand_text(args.text)
    print(result)
    return 0


def _cmd_expand_query(args: argparse.Namespace) -> int:
    result = expand_query(args.text, include_original=not args.replace)
    print(result)
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    abbrevs = list_abbrevs(prefix=args.prefix or "")
    for entry in abbrevs:
        print(f"{entry['abbrev']:20s}  {entry['expansion']}")
    print(f"\n{len(abbrevs)} abbreviation(s).", file=sys.stderr)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Alcove clinical abbreviation expander.")
    sub = p.add_subparsers(dest="command", required=True)

    exp_p = sub.add_parser("expand", help="Expand abbreviations in text (replace mode).")
    exp_p.add_argument("--text", required=True, help="Text to expand.")

    qry_p = sub.add_parser("expand-query", help="Expand abbreviations in a search query (append mode).")
    qry_p.add_argument("--text", required=True, help="Query to expand.")
    qry_p.add_argument(
        "--replace",
        action="store_true",
        help="Replace abbreviation instead of appending expansion.",
    )

    lst_p = sub.add_parser("list-abbrevs", help="List known abbreviations.")
    lst_p.add_argument("--prefix", default="", help="Filter by prefix.")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "expand":
        return _cmd_expand(args)
    if args.command == "expand-query":
        return _cmd_expand_query(args)
    if args.command == "list-abbrevs":
        return _cmd_list(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
