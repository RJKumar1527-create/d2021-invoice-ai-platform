import pandas as pd
import streamlit as st



def split_fields(line):
    """Split one D2021 record into fields."""
    return [value.strip() for value in line.split("|")]


def safe_value(fields, index, default=""):
    """Return a field safely without causing an index error."""
    if index < len(fields):
        return fields[index]
    return default


def parse_d2021(lines):
    """
    Parse D2021 records into a structured hierarchy.

    Hierarchy:
    File -> Site -> MPANs -> Invoice -> Charges
    """

    parsed_data = {
        "header": None,
        "distributor": None,
        "customer": None,
        "trailer": None,
        "sites": [],
        "invoices": [],
        "errors": [],
    }

    current_site = None
    current_mpans = []
    current_invoice = None

    for line_number, line in enumerate(lines, start=1):
        fields = split_fields(line)
        record_type = safe_value(fields, 0).upper()

        try:
            if record_type == "ZHV":
                parsed_data["header"] = {
                    "line_number": line_number,
                    "file_sequence": safe_value(fields, 1),
                    "flow_version": safe_value(fields, 2),
                    "run_type": safe_value(fields, 3),
                    "sender": safe_value(fields, 4),
                    "receiver": safe_value(fields, 6),
                    "created_datetime": safe_value(fields, 7),
                    "operator": safe_value(fields, 12),
                }

            elif record_type == "SDT":
                parsed_data["distributor"] = {
                    "line_number": line_number,
                    "company_name": safe_value(fields, 1),
                    "department": safe_value(fields, 2),
                    "phone": safe_value(fields, 3),
                    "alternate_phone": safe_value(fields, 4),
                    "address_line_1": safe_value(fields, 5),
                    "address_line_2": safe_value(fields, 6),
                    "city": safe_value(fields, 7),
                    "postcode": safe_value(fields, 15),
                    "email": (
                        safe_value(fields, 18)
                        + "@"
                        + safe_value(fields, 19)
                        if safe_value(fields, 18)
                        and safe_value(fields, 19)
                        else ""
                    ),
                }

            elif record_type == "CDT":
                parsed_data["customer"] = {
                    "line_number": line_number,
                    "company_name": safe_value(fields, 1),
                    "trading_name": safe_value(fields, 2),
                    "previous_name": safe_value(fields, 3),
                    "address_line_1": safe_value(fields, 4),
                    "address_line_2": safe_value(fields, 5),
                    "city": safe_value(fields, 6),
                    "county": safe_value(fields, 7),
                    "postcode": safe_value(fields, 12),
                }

            elif record_type == "CLO":
                current_site = {
                    "site_number": len(parsed_data["sites"]) + 1,
                    "line_number": line_number,
                    "site_name": safe_value(fields, 1),
                    "site_reference": safe_value(fields, 2),
                    "customer_name": safe_value(fields, 4),
                    "address_line_1": safe_value(fields, 7),
                    "address_line_2": safe_value(fields, 8),
                    "city": safe_value(fields, 10),
                    "county": safe_value(fields, 11),
                    "postcode": safe_value(fields, 12),
                    "mpans": [],
                    "invoice_numbers": [],
                }

                parsed_data["sites"].append(current_site)
                current_mpans = []
                current_invoice = None

            elif record_type == "MPC":
                if current_site is None:
                    raise ValueError("MPC record found before a CLO record.")

                mpan = {
                    "line_number": line_number,
                    "full_mpan": safe_value(fields, 1),
                    "core_mpan": safe_value(fields, 2),
                    "profile_class": safe_value(fields, 3),
                    "metering_type": safe_value(fields, 6),
                }

                current_site["mpans"].append(mpan)
                current_mpans.append(mpan)

            elif record_type == "BCD":
                if current_site is None:
                    raise ValueError("BCD record found before a CLO record.")

                current_invoice = {
                    "line_number": line_number,
                    "site_name": current_site["site_name"],
                    "site_reference": current_site["site_reference"],
                    "mpans": [
                        mpan["core_mpan"]
                        for mpan in current_mpans
                        if mpan["core_mpan"]
                    ],
                    "invoice_date": safe_value(fields, 1),
                    "received_date": safe_value(fields, 2),
                    "due_date": safe_value(fields, 3),
                    "invoice_number": safe_value(fields, 4),
                    "invoice_type": safe_value(fields, 5),
                    "tariff_description": safe_value(fields, 6),
                    "reference_date": safe_value(fields, 7),
                    "reference_invoice": safe_value(fields, 8),
                    "original_net": safe_value(fields, 9),
                    "original_vat": safe_value(fields, 10),
                    "original_gross": safe_value(fields, 11),
                    "period_start": safe_value(fields, 12),
                    "period_end": safe_value(fields, 13),
                    "final_net": safe_value(fields, 32),
                    "vat_indicator": safe_value(fields, 33),
                    "final_vat": safe_value(fields, 34),
                    "final_gross": safe_value(fields, 35),
                    "charges": [],
                }

                parsed_data["invoices"].append(current_invoice)

                current_site["invoice_numbers"].append(
                    current_invoice["invoice_number"]
                )

            elif record_type == "CCD":
                if current_invoice is None:
                    raise ValueError("CCD record found before a BCD record.")

                charge = {
                    "line_number": line_number,
                    "invoice_number": current_invoice["invoice_number"],
                    "charge_type": safe_value(fields, 1),
                    "description": safe_value(fields, 2),
                    "number_of_days": safe_value(fields, 3),
                    "unit_code": safe_value(fields, 4),
                    "quantity": safe_value(fields, 5),
                    "rate": safe_value(fields, 6),
                    "amount": safe_value(fields, 7),
                    "comment_1": safe_value(fields, 8),
                    "comment_2": safe_value(fields, 9),
                }

                current_invoice["charges"].append(charge)

            elif record_type == "ZPT":
                parsed_data["trailer"] = {
                    "line_number": line_number,
                    "file_sequence": safe_value(fields, 1),
                    "record_count": safe_value(fields, 2),
                    "file_count": safe_value(fields, 4),
                    "created_datetime": safe_value(fields, 5),
                }

            else:
                parsed_data["errors"].append(
                    {
                        "line_number": line_number,
                        "record_type": record_type,
                        "error": "Unknown record type",
                    }
                )

        except Exception as error:
            parsed_data["errors"].append(
                {
                    "line_number": line_number,
                    "record_type": record_type,
                    "error": str(error),
                }
            )

    return parsed_data


def mask_mpan(mpan):
    """Mask MPAN except for the final four characters."""
    if not mpan:
        return ""

    if len(mpan) <= 4:
        return mpan

    return "*" * (len(mpan) - 4) + mpan[-4:]


st.title("D2021 Invoice Validation Platform")
st.subheader("Step 2: Parse & Structure")

result = st.session_state.get("latest_result")

if not result:
    st.warning("No processed D2021 file is available.")
    st.info(
        "Go to 1. File Upload, select a .uff file, "
        "and click Upload and Process."
    )
    st.stop()

if not result.get("lines"):
    st.warning("The uploaded file content is unavailable.")
    st.info(
        "Return to 1. File Upload and process the file again."
    )
    st.stop()

lines = result["lines"]
parsed_data = parse_d2021(lines)

site_count = len(parsed_data["sites"])

mpan_count = sum(
    len(site["mpans"])
    for site in parsed_data["sites"]
)

invoice_count = len(parsed_data["invoices"])

charge_count = sum(
    len(invoice["charges"])
    for invoice in parsed_data["invoices"]
)

error_count = len(parsed_data["errors"])

st.info(
    f"File: {result['file_name']} | "
    f"Processing ID: {result['processing_id']}"
)

metric1, metric2, metric3, metric4, metric5 = st.columns(5)

metric1.metric("CLO Sections", site_count)
metric2.metric("MPAN Records", mpan_count)
metric3.metric("Invoices", invoice_count)
metric4.metric("Charges", charge_count)
metric5.metric("Parsing Errors", error_count)

if error_count == 0:
    st.success("D2021 file parsed and structured successfully.")
else:
    st.warning(
        f"Parsing completed with {error_count} error(s)."
    )


st.markdown("---")
st.subheader("File Information")

file_information = []

if parsed_data["header"]:
    header = parsed_data["header"]

    file_information.append(
        {
            "Section": "Header",
            "Name": "File sequence",
            "Value": header["file_sequence"],
        }
    )

    file_information.append(
        {
            "Section": "Header",
            "Name": "Flow version",
            "Value": header["flow_version"],
        }
    )

    file_information.append(
        {
            "Section": "Header",
            "Name": "Sender",
            "Value": header["sender"],
        }
    )

    file_information.append(
        {
            "Section": "Header",
            "Name": "Receiver",
            "Value": header["receiver"],
        }
    )

    file_information.append(
        {
            "Section": "Header",
            "Name": "Created date and time",
            "Value": header["created_datetime"],
        }
    )

if parsed_data["trailer"]:
    trailer = parsed_data["trailer"]

    file_information.append(
        {
            "Section": "Trailer",
            "Name": "Declared record count",
            "Value": trailer["record_count"],
        }
    )

    file_information.append(
        {
            "Section": "Trailer",
            "Name": "File count",
            "Value": trailer["file_count"],
        }
    )

if file_information:
    st.dataframe(
        pd.DataFrame(file_information),
        use_container_width=True,
        hide_index=True,
    )


st.markdown("---")
st.subheader("Distributor and Customer")

company_column1, company_column2 = st.columns(2)

with company_column1:
    st.markdown("#### Distributor")

    if parsed_data["distributor"]:
        distributor = parsed_data["distributor"]

        st.write(
            "**Company:**",
            distributor["company_name"],
        )
        st.write(
            "**Department:**",
            distributor["department"],
        )
        st.write(
            "**Phone:**",
            distributor["phone"],
        )
        st.write(
            "**Postcode:**",
            distributor["postcode"],
        )
        st.write(
            "**Email:**",
            distributor["email"],
        )

with company_column2:
    st.markdown("#### Customer")

    if parsed_data["customer"]:
        customer = parsed_data["customer"]

        st.write(
            "**Company:**",
            customer["company_name"],
        )
        st.write(
            "**Trading name:**",
            customer["trading_name"],
        )
        st.write(
            "**Address:**",
            customer["address_line_1"],
        )
        st.write(
            "**City:**",
            customer["city"],
        )
        st.write(
            "**Postcode:**",
            customer["postcode"],
        )


st.markdown("---")
st.subheader("Sites and MPANs")

site_rows = []

for site in parsed_data["sites"]:
    masked_mpans = [
        mask_mpan(mpan["core_mpan"])
        for mpan in site["mpans"]
        if mpan["core_mpan"]
    ]

    site_rows.append(
        {
            "Site": site["site_name"],
            "Site Reference": site["site_reference"],
            "Customer": site["customer_name"],
            "Postcode": site["postcode"],
            "MPAN Count": len(site["mpans"]),
            "MPANs": ", ".join(masked_mpans),
            "Invoice Count": len(site["invoice_numbers"]),
        }
    )

if site_rows:
    st.dataframe(
        pd.DataFrame(site_rows),
        use_container_width=True,
        hide_index=True,
    )


st.markdown("---")
st.subheader("Invoice Summary")

invoice_rows = []

for invoice in parsed_data["invoices"]:
    invoice_rows.append(
        {
            "Invoice Number": invoice["invoice_number"],
            "Type": invoice["invoice_type"],
            "Site": invoice["site_name"],
            "MPAN Count": len(invoice["mpans"]),
            "Period Start": invoice["period_start"],
            "Period End": invoice["period_end"],
            "Original Net": invoice["original_net"],
            "Original VAT": invoice["original_vat"],
            "Original Gross": invoice["original_gross"],
            "Final Net": invoice["final_net"],
            "Final VAT": invoice["final_vat"],
            "Final Gross": invoice["final_gross"],
            "Charge Count": len(invoice["charges"]),
        }
    )

if invoice_rows:
    st.dataframe(
        pd.DataFrame(invoice_rows),
        use_container_width=True,
        hide_index=True,
    )


st.markdown("---")
st.subheader("Charge Details")

selected_invoice = st.selectbox(
    "Select an invoice",
    options=[
        invoice["invoice_number"]
        for invoice in parsed_data["invoices"]
    ],
)

selected_invoice_data = next(
    (
        invoice
        for invoice in parsed_data["invoices"]
        if invoice["invoice_number"] == selected_invoice
    ),
    None,
)

if selected_invoice_data:
    charge_rows = selected_invoice_data["charges"]

    if charge_rows:
        st.dataframe(
            pd.DataFrame(charge_rows),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No charge records were found for this invoice.")


st.markdown("---")
st.subheader("Parsing Errors")

if parsed_data["errors"]:
    st.dataframe(
        pd.DataFrame(parsed_data["errors"]),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.success("No structural parsing errors were identified.")


st.session_state.parsed_d2021 = parsed_data
st.session_state.latest_result["status"] = "PARSED"

st.markdown("---")

st.success(
    "Structured D2021 data has been saved for the next step: "
    "Data Validation."
)