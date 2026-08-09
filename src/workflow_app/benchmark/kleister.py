"""Kleister-Charity benchmark builder (ticket #13, plan section 42).

Adapts the public Kleister-Charity dev split
(github.com/applicaai/kleister-charity) into WorkCrew benchmark
inputs: one folder per document holding the dataset's best OCR text
layer, a labels file recording expected value / evidence folder /
blank-or-unresolved status per field, the workbook template and schema
config, and the rule files the two derived columns depend on. The
build is deterministic — fixed seed, sorted inputs, no timestamps —
so rebuilding from the same split is byte-identical.
"""

import datetime
import io
import json
import lzma
import random
import zipfile
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

SHEET = "Charity Reports"
SEED = 20260809
TEXT_CAP = 40_000
SAMPLE_FULL = 28
SAMPLE_PARTIAL = 8
CONFLICTS = 3
BAND_SMALL_BELOW = Decimal(250000)
BAND_MEDIUM_BELOW = Decimal(1000000)
# in.tsv column layout: filename, keys, text_djvu, text_tesseract,
# text_textract, text_best. The benchmark uses the combined best layer.
TEXT_BEST_COLUMN = 5
# Reproducible-build convention: openpyxl stamps both the zip entries
# and docProps with the wall clock; pinning them keeps rebuilds
# byte-identical.
XLSX_TIMESTAMP = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)

DATASET_KEYS = {
    "charity_name": "Charity Name",
    "charity_number": "Registration Number",
    "report_date": "Report Date",
    "address__street_line": "Street Line",
    "address__post_town": "Post Town",
    "address__postcode": "Postcode",
    "income_annually_in_british_pounds": "Annual Income GBP",
    "spending_annually_in_british_pounds": "Annual Spending GBP",
}

CONFLICT_FIELD = "Annual Income GBP"
CONFLICT_FILE = "register_extract.txt"

WORKBOOK_SCHEMA_CONFIG = {
    "sheets": [
        {
            "name": SHEET,
            "target": True,
            "notes_field": "Notes",
            "title_field": "Charity Name",
            "overview_fields": ["Registration Number", "Income Size Band"],
            "fields": {
                "Charity ID*": {
                    "required": True,
                    "type": "id",
                    "column": "A",
                    "pattern": r"^CHA-\d{6,7}$",
                    "value_kind": "constructed",
                    "writable": True,
                    "gloss_zh": "机构编号（按规则构造）",
                },
                "Charity Name": {
                    "type": "string",
                    "column": "B",
                    "writable": True,
                    "gloss_zh": "慈善机构名称",
                },
                "Registration Number": {
                    "type": "id",
                    "column": "C",
                    "pattern": r"^\d{6,7}$",
                    "writable": True,
                    "gloss_zh": "注册号",
                },
                "Report Date": {
                    "type": "date",
                    "column": "D",
                    "writable": True,
                    "gloss_zh": "报告期截止日期",
                },
                "Street Line": {
                    "type": "string",
                    "column": "E",
                    "writable": True,
                    "gloss_zh": "街道地址",
                },
                "Post Town": {
                    "type": "string",
                    "column": "F",
                    "writable": True,
                    "gloss_zh": "邮镇",
                },
                "Postcode": {
                    "type": "string",
                    "column": "G",
                    "writable": True,
                    "gloss_zh": "邮政编码",
                },
                "Annual Income GBP": {
                    "type": "number",
                    "column": "H",
                    "writable": True,
                    "gloss_zh": "年度收入（英镑）",
                },
                "Annual Spending GBP": {
                    "type": "number",
                    "column": "I",
                    "writable": True,
                    "gloss_zh": "年度支出（英镑）",
                },
                "Income Size Band": {
                    "type": "controlled_vocabulary",
                    "column": "J",
                    "values": ["Small", "Medium", "Large"],
                    "value_kind": "mapped",
                    "writable": True,
                    "gloss_zh": "收入规模档（按规则映射）",
                },
                "Notes": {
                    "type": "string",
                    "column": "K",
                    "writable": True,
                    "gloss_zh": "备注",
                },
            },
        }
    ]
}


def unescape_text(raw):
    # The dataset's TSV writer replaced newlines with \n and tabs with
    # \t and escaped nothing else (raw OCR backslashes like \D remain),
    # so plain replacement is the exact inverse.
    return raw.replace("\\n", "\n").replace("\\t", "\t")


def parse_split(split_dir):
    split_dir = Path(split_dir)
    plain = split_dir / "in.tsv"
    if plain.is_file():
        in_text = plain.read_text(encoding="utf-8")
    else:
        in_text = lzma.decompress((split_dir / "in.tsv.xz").read_bytes()).decode(
            "utf-8"
        )
    in_rows = in_text.rstrip("\n").split("\n")
    expected_rows = (
        (split_dir / "expected.tsv")
        .read_text(encoding="utf-8")
        .rstrip("\n")
        .split("\n")
    )
    if len(in_rows) != len(expected_rows):
        raise ValueError(
            f"split rows mismatch: {len(in_rows)} inputs"
            f" vs {len(expected_rows)} expected lines"
        )

    docs = []
    for line, expected in zip(in_rows, expected_rows):
        columns = line.split("\t")
        labels = dict(pair.split("=", 1) for pair in expected.split(" ") if pair)
        docs.append(
            {
                "stem": Path(columns[0]).stem,
                "text": unescape_text(columns[TEXT_BEST_COLUMN]),
                "labels": labels,
            }
        )
    return sorted(docs, key=lambda doc: doc["stem"])


def income_band(income):
    value = Decimal(income)
    if value < BAND_SMALL_BELOW:
        return "Small"
    if value < BAND_MEDIUM_BELOW:
        return "Medium"
    return "Large"


def derive_fields(labels):
    fields = {
        field: labels.get(dataset_key) for dataset_key, field in DATASET_KEYS.items()
    }
    number = fields["Registration Number"]
    fields["Charity ID*"] = None if number is None else f"CHA-{number}"
    income = fields["Annual Income GBP"]
    fields["Income Size Band"] = None if income is None else income_band(income)
    return fields


def sample_documents(docs, sample_full, sample_partial, text_cap, seed):
    eligible = [doc for doc in docs if len(doc["text"]) <= text_cap]
    full = [doc for doc in eligible if len(doc["labels"]) == len(DATASET_KEYS)]
    partial = [doc for doc in eligible if len(doc["labels"]) < len(DATASET_KEYS)]
    if len(full) < sample_full or len(partial) < sample_partial:
        raise ValueError(
            f"cannot sample {sample_full} full + {sample_partial} partial"
            f" documents: {len(full)} full and {len(partial)} partial"
            f" eligible under the {text_cap}-char text cap"
        )
    rng = random.Random(seed)
    chosen = rng.sample(full, sample_full) + rng.sample(partial, sample_partial)
    return sorted(chosen, key=lambda doc: doc["stem"])


def conflicting_income(income):
    # Deterministic and always different from the report's value.
    return str((Decimal(income) * 2 + 137).quantize(Decimal("0.01")))


def _conflict_extract(number, value):
    return (
        "UK CHARITY COMMISSION - REGISTER EXTRACT (AUTOMATED COPY)\n"
        f"Charity number: {number or 'not recorded'}\n"
        f"Latest reported annual income (GBP): {value}\n"
    )


SCOPING_ANSWERS = """\
# Scoping answers (pre-provided)

- One workbook row per source folder: assign folders to rows in
  ascending alphabetical folder-name order, starting at row 2.
- Fill only what the folder's documents support; leave a cell blank
  when the value cannot be determined from the sources.
- Every document inside a folder is an equally authoritative source
  for that folder's row.
"""

EXTRACTION_CONVENTIONS = """\
# Extraction conventions - Charity Reports

One workbook row per charity annual-report folder. All values come
from the folder's documents, never from outside knowledge.

- Charity Name: the full registered charity name exactly as the
  charity register states it, including any leading article ("The
  ...") and spelled-out conjunctions - not a shortened display form.
- Registration Number: the charity registration number, digits only.
- Report Date: the financial period end date, ISO format YYYY-MM-DD.
- Street Line / Post Town / Postcode: the charity's registered
  address, written as printed (UK convention: street line and post
  town appear in uppercase). Street Line is the street line only -
  house number and street name; building, house, or barracks names
  that precede the street belong to no field and are dropped.
- Annual Income GBP / Annual Spending GBP: total annual income and
  spending in British pounds as plain numbers - no currency symbols,
  no thousands separators.
- Every document in a folder is equally authoritative. If documents in
  the same folder state conflicting values for a field, do not pick
  one - the value cannot be determined from the sources.
"""

CHARITY_ID_RULE = """\
# Constructed field: Charity ID

Charity ID = "CHA-" followed by the Registration Number, e.g.
registration number 1022119 gives CHA-1022119.

Leave the Charity ID blank when the registration number cannot be
determined from the sources.
"""

INCOME_BANDS_RULE = """\
# Mapped field: Income Size Band

Map the Annual Income GBP value onto a size band:

- Small: income below 250,000
- Medium: income of at least 250,000 and below 1,000,000
- Large: income of at least 1,000,000

Leave the band blank when the annual income cannot be determined from
the sources.
"""

README = """\
# Kleister-Charity benchmark inputs

Benchmark inputs for the WorkCrew engine (ticket #13, plan section
42), adapted from the public Kleister-Charity dataset
(https://github.com/applicaai/kleister-charity, dev-0 split).

## Layout

- `source/<doc>/report.txt` - the dataset's best OCR text layer
  (`text_best`) for one charity annual report; one folder per
  document, one workbook row per folder.
- `source/<doc>/register_extract.txt` - synthetic conflicting income
  copy injected into a few folders to exercise the
  conflict -> UNRESOLVED -> human-fallback path with known truth.
- `labels.json` - expected value, evidence folder, and
  expected / blank / unresolved status per field per row.
- `workbook_schema.json`, `template.xlsx`, `rules/`,
  `scoping_answers.md` - the run inputs.

The original PDFs (12 GB, git-annex) are deliberately not used: the
dataset's official challenge input is the OCR text, and the engine's
agents read text sources.

## License note

The Kleister-Charity repository declares no explicit license; the
underlying documents are public filings from the UK Charity
Commission register. These inputs are used for internal evaluation
only - do not redistribute the document texts.

## Rebuilding

`workflow build-benchmark --split-dir <dev-0 dir> --output <this dir>`
regenerates everything above deterministically (fixed seed, sorted
inputs). The dev-0 split (`in.tsv.xz`, `expected.tsv`) is downloaded
from the dataset repository.
"""


def _write_rules(rules_dir):
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "extraction_conventions.md").write_text(EXTRACTION_CONVENTIONS)
    (rules_dir / "charity_id.md").write_text(CHARITY_ID_RULE)
    (rules_dir / "income_bands.md").write_text(INCOME_BANDS_RULE)


def _save_reproducible_xlsx(workbook, path):
    # An .xlsx is a zip: openpyxl stamps docProps and every zip entry
    # with the wall clock, so a naive save is never byte-identical
    # across rebuilds. Pin both to XLSX_TIMESTAMP.
    workbook.properties.created = XLSX_TIMESTAMP
    workbook.properties.modified = XLSX_TIMESTAMP
    buffer = io.BytesIO()
    workbook.save(buffer)
    stamped = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as source,
        zipfile.ZipFile(stamped, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        for item in source.infolist():
            info = zipfile.ZipInfo(
                item.filename, date_time=XLSX_TIMESTAMP.timetuple()[:6]
            )
            info.external_attr = item.external_attr
            target.writestr(info, source.read(item.filename))
    Path(path).write_bytes(stamped.getvalue())


def _row_labels(row, doc, columns, conflict_value):
    fields = {}
    derived = derive_fields(doc["labels"])
    for field, column in columns.items():
        value = derived[field]
        status = "expected" if value is not None else "blank"
        if conflict_value is not None and field in (
            CONFLICT_FIELD,
            "Income Size Band",
        ):
            # A genuinely conflicting second source makes the value
            # undeterminable — and the band derives from it.
            value, status = None, "unresolved"
        fields[field] = {
            "cell": f"{column}{row}",
            "expected_value": value,
            "status": status,
        }
    return {
        "row": row,
        "folder": doc["stem"],
        "document": f"{doc['stem']}/report.txt",
        "conflict": None
        if conflict_value is None
        else {
            "field": CONFLICT_FIELD,
            "file": CONFLICT_FILE,
            "value": conflict_value,
        },
        "fields": fields,
    }


def build_benchmark(
    split_dir,
    output_dir,
    sample_full=SAMPLE_FULL,
    sample_partial=SAMPLE_PARTIAL,
    text_cap=TEXT_CAP,
    conflicts=CONFLICTS,
    seed=SEED,
):
    output_dir = Path(output_dir)
    docs = parse_split(split_dir)
    sampled = sample_documents(docs, sample_full, sample_partial, text_cap, seed)

    candidates = [
        doc
        for doc in sampled
        if doc["labels"].get("income_annually_in_british_pounds") is not None
    ]
    if conflicts > len(candidates):
        raise ValueError(
            f"cannot inject {conflicts} conflicts: only {len(candidates)}"
            " sampled documents carry an income value"
        )
    conflicted = {
        doc["stem"] for doc in random.Random(seed + 1).sample(candidates, conflicts)
    }

    sheet_config = WORKBOOK_SCHEMA_CONFIG["sheets"][0]
    columns = {field: spec["column"] for field, spec in sheet_config["fields"].items()}
    # The Notes column is the note_append channel, not extracted data —
    # it carries no labels.
    labeled_columns = {
        field: column
        for field, column in columns.items()
        if field != sheet_config["notes_field"]
    }

    source_root = output_dir / "source"
    rows = []
    for index, doc in enumerate(sampled):
        folder = source_root / doc["stem"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "report.txt").write_text(doc["text"], encoding="utf-8")
        conflict_value = None
        if doc["stem"] in conflicted:
            conflict_value = conflicting_income(
                doc["labels"]["income_annually_in_british_pounds"]
            )
            (folder / CONFLICT_FILE).write_text(
                _conflict_extract(doc["labels"].get("charity_number"), conflict_value),
                encoding="utf-8",
            )
        rows.append(_row_labels(2 + index, doc, labeled_columns, conflict_value))

    labels = {
        "benchmark": "kleister-charity",
        "sheet": SHEET,
        "seed": seed,
        "rows": rows,
    }
    (output_dir / "labels.json").write_text(json.dumps(labels, indent=2) + "\n")
    (output_dir / "workbook_schema.json").write_text(
        json.dumps(WORKBOOK_SCHEMA_CONFIG, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET
    for offset, field in enumerate(columns, start=1):
        sheet.cell(row=1, column=offset, value=field)
    _save_reproducible_xlsx(workbook, output_dir / "template.xlsx")

    _write_rules(output_dir / "rules")
    (output_dir / "scoping_answers.md").write_text(SCOPING_ANSWERS)
    (output_dir / "README.md").write_text(README)

    return {
        "documents": len(sampled),
        "conflicts": len(conflicted),
        "output": str(output_dir),
    }
