import hashlib
import re
import runpy
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st


# ---------------------------------------------------------
# Page configuration
# ---------------------------------------------------------
st.set_page_config(
    page_title="D2021 Invoice Validation Platform",
    page_icon="📄",
    layout="wide",
)

selected_page = st.sidebar.radio(
    "D2021 Workflow",
    [
        "1. File Upload",
        "2. Parse & Structure",
        "3. Data Validation",
        "4. Invoice Reconciliation",
        "5. Anomaly Detection",
        "6. Risk Scoring",
        "7. RAG Rule Retrieval",
        "8. Grounded AI Explanation",
        "9. Human Review",
        "10. Final Dashboard & Report",
        "11. Model Evaluation",
    ],
)

if selected_page == "2. Parse & Structure":
    runpy.run_path(
        "page_code/2_Parse_and_Structure.py",
        run_name="__main__",
    )
    st.stop()

elif selected_page == "3. Data Validation":
    runpy.run_path(
        "page_code/3_Data_Validation.py",
        run_name="__main__",
    )
    st.stop()

elif selected_page == "4. Invoice Reconciliation":
    runpy.run_path(
        "page_code/4_Invoice_Reconciliation.py",
        run_name="__main__",
    )
    st.stop()

elif selected_page == "5. Anomaly Detection":
    runpy.run_path(
        "page_code/5_Anomaly_Detection.py",
        run_name="__main__",
    )
    st.stop()

elif selected_page == "6. Risk Scoring":
    runpy.run_path(
        "page_code/6_Risk_Scoring_AI_Explanation.py",
        run_name="__main__",
    )
    st.stop()
elif selected_page == "7. RAG Rule Retrieval":
    runpy.run_path(
        "page_code/7_RAG_Rule_Retrieval.py",
        run_name="__main__",
    )
    st.stop()

elif selected_page == "8. Grounded AI Explanation":
    runpy.run_path(
        "page_code/8_Grounded_AI_Explanation.py",
        run_name="__main__",
    )
    st.stop()

elif selected_page == "9. Human Review":
    runpy.run_path(
        "page_code/9_Human_Review.py",
        run_name="__main__",
    )
    st.stop()

elif selected_page == "10. Final Dashboard & Report":
    runpy.run_path(
        "page_code/10_Final_Dashboard_Report.py",
        run_name="__main__",
    )
    st.stop()

elif selected_page == "11. Model Evaluation":
    runpy.run_path(
        "page_code/11_Model_Evaluation.py",
        run_name="__main__",
    )
    st.stop()



# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------
MAX_FILE_SIZE_MB = 10

KNOWN_RECORD_TYPES = [
    "ZHV",
    "SDT",
    "CDT",
    "CLO",
    "MPC",
    "MDT",
    "BCD",
    "CCD",
    "ZPT",
]

MANDATORY_RECORD_TYPES = [
    "ZHV",
    "SDT",
    "CDT",
    "CLO",
    "MPC",
    "BCD",
    "CCD",
    "ZPT",
]

FILE_NAME_PATTERN = re.compile(
    r"^H\d{8}\.uff$",
    re.IGNORECASE,
)


# ---------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------
if "processed_hashes" not in st.session_state:
    st.session_state.processed_hashes = set()

if "latest_result" not in st.session_state:
    st.session_state.latest_result = None


# ---------------------------------------------------------
# Helper functions
# ---------------------------------------------------------
def calculate_sha256(file_bytes: bytes) -> str:
    """Calculate a SHA-256 checksum for duplicate-file detection."""
    return hashlib.sha256(file_bytes).hexdigest()


def decode_file(file_bytes: bytes) -> tuple[str | None, str | None]:
    """
    Attempt to decode the uploaded file.

    UTF-8 is attempted first. Windows-1252 is used as a fallback,
    because legacy business files may use Windows encoding.
    """
    encodings = ["utf-8-sig", "utf-8", "windows-1252"]

    for encoding in encodings:
        try:
            return file_bytes.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    return None, None


def get_non_empty_lines(file_text: str) -> list[str]:
    """Return trimmed, non-empty lines."""
    return [
        line.strip()
        for line in file_text.splitlines()
        if line.strip()
    ]


def get_record_type(line: str) -> str:
    """Return the first pipe-delimited value as the record type."""
    if "|" not in line:
        return "INVALID"

    return line.split("|", 1)[0].strip().upper()


def count_record_types(lines: list[str]) -> dict[str, int]:
    """Count known and unknown D2021 record types."""
    counts = {record_type: 0 for record_type in KNOWN_RECORD_TYPES}
    counts["UNKNOWN"] = 0
    counts["INVALID"] = 0

    for line in lines:
        record_type = get_record_type(line)

        if record_type in counts:
            counts[record_type] += 1
        elif record_type == "INVALID":
            counts["INVALID"] += 1
        else:
            counts["UNKNOWN"] += 1

    return counts


def mask_sensitive_value(value: str) -> str:
    """
    Mask long numeric values such as MPANs in the preview.

    Example:
    2336500061019 becomes *********1019
    """
    value = value.strip()

    if value.isdigit() and len(value) >= 10:
        return "*" * (len(value) - 4) + value[-4:]

    return value


def mask_line_for_preview(line: str) -> str:
    """Mask likely sensitive values before showing file preview."""
    fields = line.split("|")
    masked_fields = [mask_sensitive_value(field) for field in fields]
    return "|".join(masked_fields)


def validate_file(
    file_name: str,
    file_size_bytes: int,
    lines: list[str],
    checksum: str,
) -> list[dict]:
    """Run basic upload-page validations."""
    validation_results = []

    def add_result(check_name: str, passed: bool, message: str):
        validation_results.append(
            {
                "check": check_name,
                "passed": passed,
                "message": message,
            }
        )

    extension_valid = Path(file_name).suffix.lower() == ".uff"

    add_result(
        "File extension",
        extension_valid,
        (
            "Valid .uff file extension."
            if extension_valid
            else "Only .uff files are supported."
        ),
    )

    name_valid = bool(FILE_NAME_PATTERN.fullmatch(file_name))

    add_result(
        "File name",
        name_valid,
        (
            "File name matches the expected H########.uff pattern."
            if name_valid
            else "Expected file-name format: H followed by 8 digits and .uff."
        ),
    )

    file_not_empty = file_size_bytes > 0 and len(lines) > 0

    add_result(
        "File content",
        file_not_empty,
        (
            "File contains readable records."
            if file_not_empty
            else "The uploaded file is empty."
        ),
    )

    size_valid = file_size_bytes <= MAX_FILE_SIZE_MB * 1024 * 1024

    add_result(
        "File size",
        size_valid,
        (
            f"File is within the {MAX_FILE_SIZE_MB} MB limit."
            if size_valid
            else f"File exceeds the {MAX_FILE_SIZE_MB} MB limit."
        ),
    )

    pipe_format_valid = bool(lines) and all("|" in line for line in lines)

    add_result(
        "Delimiter format",
        pipe_format_valid,
        (
            "Pipe-delimited format detected."
            if pipe_format_valid
            else "One or more records are not pipe-delimited."
        ),
    )

    header_valid = bool(lines) and get_record_type(lines[0]) == "ZHV"

    add_result(
        "ZHV header",
        header_valid,
        (
            "The first record is a ZHV header."
            if header_valid
            else "The first non-empty record must be ZHV."
        ),
    )

    trailer_valid = bool(lines) and get_record_type(lines[-1]) == "ZPT"

    add_result(
        "ZPT trailer",
        trailer_valid,
        (
            "The final record is a ZPT trailer."
            if trailer_valid
            else "The final non-empty record must be ZPT."
        ),
    )

    record_counts = count_record_types(lines)

    for record_type in MANDATORY_RECORD_TYPES:
        record_present = record_counts.get(record_type, 0) > 0

        add_result(
            f"{record_type} record",
            record_present,
            (
                f"{record_counts.get(record_type, 0)} "
                f"{record_type} record(s) found."
                if record_present
                else f"Mandatory {record_type} record is missing."
            ),
        )

    one_header = record_counts.get("ZHV", 0) == 1

    add_result(
        "Single ZHV header",
        one_header,
        (
            "Exactly one ZHV record found."
            if one_header
            else (
                "The file must have exactly one ZHV record. "
                f"Found: {record_counts.get('ZHV', 0)}."
            )
        ),
    )

    one_trailer = record_counts.get("ZPT", 0) == 1

    add_result(
        "Single ZPT trailer",
        one_trailer,
        (
            "Exactly one ZPT record found."
            if one_trailer
            else (
                "The file must have exactly one ZPT record. "
                f"Found: {record_counts.get('ZPT', 0)}."
            )
        ),
    )

    known_records_only = (
        record_counts.get("UNKNOWN", 0) == 0
        and record_counts.get("INVALID", 0) == 0
    )

    add_result(
        "Recognized records",
        known_records_only,
        (
            "All records use recognized D2021 record types."
            if known_records_only
            else (
                f"Unknown records: {record_counts.get('UNKNOWN', 0)}; "
                f"invalid records: {record_counts.get('INVALID', 0)}."
            )
        ),
    )

    duplicate = checksum in st.session_state.processed_hashes

    add_result(
        "Duplicate file",
        not duplicate,
        (
            "This file has not been processed in the current session."
            if not duplicate
            else "The same file content was already processed."
        ),
    )

    return validation_results


def create_processing_id(checksum: str) -> str:
    """Generate a display-only processing ID."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"D2021-{timestamp}-{checksum[:6].upper()}"


def create_record_summary(record_counts: dict[str, int]) -> pd.DataFrame:
    """Build a DataFrame for displaying record counts."""
    labels = {
        "ZHV": "File Header",
        "SDT": "Distributor Details",
        "CDT": "Supplier Details",
        "CLO": "Site / Location",
        "MPC": "MPAN Details",
        "MDT": "Meter Details",
        "BCD": "Invoice Details",
        "CCD": "Charge Details",
        "ZPT": "File Trailer",
        "UNKNOWN": "Unknown Records",
        "INVALID": "Invalid Records",
    }

    rows = []

    for record_type, count in record_counts.items():
        rows.append(
            {
                "Record Type": record_type,
                "Description": labels.get(record_type, "Unknown"),
                "Count": count,
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------
# Page header
# ---------------------------------------------------------
st.title("D2021 Invoice Validation Platform")
st.subheader("Step 1: File Upload")

st.write(
    "Upload a D2021 `.uff` invoice file for initial file-level "
    "validation and record analysis."
)

st.info(
    "This page performs basic file checks only. Detailed invoice, "
    "MPAN, charge and reconciliation checks will be handled in the "
    "Data Validation page."
)


# ---------------------------------------------------------
# Upload control
# ---------------------------------------------------------
uploaded_file = st.file_uploader(
    "Drag and drop a D2021 file or browse from your computer",
    type=["uff"],
    accept_multiple_files=False,
    help=f"Accepted format: .uff | Maximum size: {MAX_FILE_SIZE_MB} MB",
)


if uploaded_file is None:
    st.markdown("---")

    st.markdown(
        """
        ### Upload requirements

        - File extension must be `.uff`
        - File name should follow `H########.uff`
        - File must be pipe-delimited
        - First record must be `ZHV`
        - Final record must be `ZPT`
        - File must contain `CLO`, `MPC`, `BCD`, and `CCD` records
        """
    )

    st.stop()


# ---------------------------------------------------------
# Read uploaded file
# ---------------------------------------------------------
file_bytes = uploaded_file.getvalue()
file_size_bytes = len(file_bytes)
file_size_kb = file_size_bytes / 1024
checksum = calculate_sha256(file_bytes)

file_text, detected_encoding = decode_file(file_bytes)

if file_text is None:
    st.error(
        "The file could not be decoded as UTF-8 or Windows-1252 text."
    )
    st.stop()

lines = get_non_empty_lines(file_text)
record_counts = count_record_types(lines)

validation_results = validate_file(
    file_name=uploaded_file.name,
    file_size_bytes=file_size_bytes,
    lines=lines,
    checksum=checksum,
)


# ---------------------------------------------------------
# Selected file details
# ---------------------------------------------------------
st.markdown("---")
st.subheader("Selected File")

column1, column2, column3, column4 = st.columns(4)

column1.metric("File Name", uploaded_file.name)
column2.metric("File Size", f"{file_size_kb:,.2f} KB")
column3.metric("Total Records", f"{len(lines):,}")
column4.metric("Detected Encoding", detected_encoding.upper())

with st.expander("Technical file details"):
    st.write(f"**SHA-256 checksum:** `{checksum}`")
    st.write(f"**MIME type:** `{uploaded_file.type or 'Not provided'}`")
    st.write(f"**Extension:** `{Path(uploaded_file.name).suffix.lower()}`")


# ---------------------------------------------------------
# Validation results
# ---------------------------------------------------------
st.markdown("---")
st.subheader("Initial File Checks")

passed_checks = sum(
    1 for result in validation_results if result["passed"]
)

failed_checks = len(validation_results) - passed_checks

summary_col1, summary_col2, summary_col3 = st.columns(3)

summary_col1.metric(
    "Total Checks",
    len(validation_results),
)

summary_col2.metric(
    "Passed",
    passed_checks,
)

summary_col3.metric(
    "Failed",
    failed_checks,
)

for result in validation_results:
    if result["passed"]:
        st.success(
            f"✓ {result['check']}: {result['message']}"
        )
    else:
        st.error(
            f"✗ {result['check']}: {result['message']}"
        )


# ---------------------------------------------------------
# Record summary
# ---------------------------------------------------------
st.markdown("---")
st.subheader("D2021 Record Summary")

record_summary_df = create_record_summary(record_counts)

st.dataframe(
    record_summary_df,
    use_container_width=True,
    hide_index=True,
)


# ---------------------------------------------------------
# File preview
# ---------------------------------------------------------
st.markdown("---")
st.subheader("Masked File Preview")

preview_size = st.slider(
    "Number of records to preview",
    min_value=5,
    max_value=min(30, len(lines)) if lines else 5,
    value=min(10, len(lines)) if lines else 5,
)

if lines:
    masked_preview = [
        {
            "Line": index,
            "Record Type": get_record_type(line),
            "Content": mask_line_for_preview(line),
        }
        for index, line in enumerate(lines[:preview_size], start=1)
    ]

    preview_df = pd.DataFrame(masked_preview)

    st.dataframe(
        preview_df,
        use_container_width=True,
        hide_index=True,
    )


# ---------------------------------------------------------
# Upload and process button
# ---------------------------------------------------------
st.markdown("---")

all_checks_passed = failed_checks == 0

if not all_checks_passed:
    st.warning(
        "The file cannot proceed because one or more initial checks failed."
    )

process_button = st.button(
    "Upload and Process",
    type="primary",
    use_container_width=True,
    disabled=not all_checks_passed,
)


if process_button:
    processing_id = create_processing_id(checksum)

    st.session_state.processed_hashes.add(checksum)

    st.session_state.latest_result = {
    "processing_id": processing_id,
    "file_name": uploaded_file.name,
    "checksum": checksum,
    "record_counts": record_counts,
    "total_records": len(lines),
    "encoding": detected_encoding,
    "status": "READY_FOR_PARSING",
    "file_text": file_text,
    "lines": lines,
    }

    st.success("D2021 file uploaded successfully.")

    st.markdown("### Processing Registration")

    result_col1, result_col2 = st.columns(2)

    with result_col1:
        st.write(f"**Processing ID:** `{processing_id}`")
        st.write(f"**File name:** `{uploaded_file.name}`")
        st.write("**Status:** `READY_FOR_PARSING`")

    with result_col2:
        st.write(f"**Total records:** `{len(lines):,}`")
        st.write(
            f"**Invoice records:** `{record_counts.get('BCD', 0):,}`"
        )
        st.write(
            f"**Charge records:** `{record_counts.get('CCD', 0):,}`"
        )

    st.info(
        "The file is ready for the next stage: "
        "D2021 Parsing and Structuring."
    )