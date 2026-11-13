# Synthetic D2021 Demonstration File

This sample is fully fabricated for portfolio testing. It contains no client, customer, MPAN, invoice, tariff, address, or payment data.

## Files

- `synthetic_d2021_demo.uff`: upload directly to the Streamlit File Upload page.
- `synthetic_d2021_demo.uff.example`: Git-safe copy. Rename to `.uff` for local testing.

## Contents

- 1 ZHV header
- 1 SDT distributor record
- 1 CDT supplier record
- 12 CLO site sections
- 12 MPC records
- 12 BCD invoice records
- 72 CCD charge records
- 1 ZPT trailer

Invoice 12 includes an intentionally extreme reactive-power quantity. The BCD total still equals the sum of CCD amounts, allowing the platform to demonstrate the difference between arithmetic reconciliation and statistical anomaly detection.

All organizations, identifiers, addresses, invoice numbers, MPAN-like values, and charge values are synthetic.
