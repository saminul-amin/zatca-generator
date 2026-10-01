import base64
import html
import json
import os
import re
import subprocess
import tempfile
import uuid
from urllib.parse import quote
from datetime import datetime, timezone

import requests
import streamlit as st

import invoice_signer

# ═══════════════════════════════════════════════════════════
# PAGE CONFIG
# ═══════════════════════════════════════════════════════════

st.set_page_config(
    page_title="ZATCA E-Invoicing Setup",
    page_icon="🧾",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ═══════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════

ENVIRONMENTS = {
    "sandbox": {
        "label": "Practice (Sandbox)",
        "pill": "Practice mode",
        "caption": "A safe trial run on ZATCA's developer portal. Nothing is real, "
                   "and the sample details below work as they are.",
        "url": "https://gw-fatoora.zatca.gov.sa/e-invoicing/developer-portal",
        "template": "TSTZATCA-Code-Signing",
    },
    "simulation": {
        "label": "Simulation",
        "pill": "Simulation",
        "caption": "A dress rehearsal on ZATCA's test platform, using your real business details.",
        "url": "https://gw-fatoora.zatca.gov.sa/e-invoicing/simulation",
        "template": "PREZATCA-Code-Signing",
    },
    "production": {
        "label": "Live (Production)",
        "pill": "Live",
        "caption": "The real registration. Invoices signed with the result are official.",
        "url": "https://gw-fatoora.zatca.gov.sa/e-invoicing/core",
        "template": "ZATCA-Code-Signing",
    },
}

SANDBOX_OTP = "123345"

INVOICE_TYPES = {
    "1100": "Both: business (B2B) & retail (B2C)",
    "1000": "Business customers only (B2B)",
    "0100": "Retail customers only (B2C)",
}

STEPS = ["Business details", "Verify with OTP", "Test invoices", "Activate", "Download"]
LAST_STEP = len(STEPS)

SAMPLE_VAT = "399999999900003"

# ═══════════════════════════════════════════════════════════
# STYLES
# ═══════════════════════════════════════════════════════════

st.html("""
<style>
:root {
    --brand: #0E7C4A;
    --brand-dark: #0A5E38;
    --brand-soft: #E7F3EC;
    --ink: #13201A;
    --muted: #5E6E66;
    --line: #D9E2DC;
    --card: #FFFFFF;
}

[data-testid="stMainBlockContainer"] {
    max-width: 820px;
    padding-top: 2.25rem;
    padding-bottom: 4rem;
}
header[data-testid="stHeader"] { background: transparent; }

/* ── Header ── */
.app-header { display: flex; align-items: center; gap: 16px; }
.app-logo {
    width: 52px; height: 52px; border-radius: 14px; flex-shrink: 0;
    background: linear-gradient(145deg, #13965C, #0A5E38);
    display: grid; place-items: center;
    box-shadow: 0 6px 16px rgba(14, 124, 74, .25);
}
.app-title {
    font-size: 1.55rem; font-weight: 700; letter-spacing: -.02em;
    color: var(--ink); line-height: 1.2;
}
.app-sub { color: var(--muted); font-size: .95rem; margin-top: 3px; }
.env-pill {
    margin-left: auto; padding: 6px 12px; border-radius: 999px;
    font-size: .75rem; font-weight: 600; white-space: nowrap;
}
.env-sandbox    { background: #FFF4DB; color: #8A5A00; }
.env-simulation { background: #E5EEFF; color: #1D4ED8; }
.env-production { background: var(--brand-soft); color: var(--brand-dark); }

/* ── Progress stepper ── */
.stepper { display: flex; align-items: flex-start; margin: 26px 0 6px; }
.st-item {
    flex: 1; display: flex; flex-direction: column; align-items: center;
    position: relative; text-align: center;
}
.st-item:not(:last-child)::after {
    content: ""; position: absolute; top: 17px; height: 2px;
    left: calc(50% + 24px); right: calc(-50% + 24px);
    background: var(--line);
}
.st-item.done:not(:last-child)::after { background: var(--brand); }
.st-dot {
    width: 36px; height: 36px; border-radius: 50%;
    display: grid; place-items: center; z-index: 1;
    font-weight: 600; font-size: .9rem;
    background: #fff; border: 2px solid var(--line); color: var(--muted);
}
.st-item.done .st-dot { background: var(--brand); border-color: var(--brand); color: #fff; }
.st-item.current .st-dot {
    border-color: var(--brand); color: var(--brand);
    box-shadow: 0 0 0 5px var(--brand-soft);
}
.st-label { margin-top: 8px; font-size: .8rem; font-weight: 500; color: var(--muted); }
.st-item.current .st-label { color: var(--ink); font-weight: 600; }

/* ── Step cards ── */
[class*="st-key-card-"] { background: var(--card); border-radius: 14px !important; }
[class*="st-key-card-current"] {
    border-color: var(--brand) !important;
    box-shadow: 0 10px 28px rgba(19, 32, 26, .07);
}
[class*="st-key-card-locked"] { background: transparent; }
[class*="st-key-card-locked"] .step-title { color: var(--muted); }

.step-head { display: flex; align-items: center; gap: 12px; }
.step-num {
    width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;
    display: grid; place-items: center; font-weight: 600; font-size: .85rem;
    background: #EEF1EF; color: var(--muted);
}
.step-num.current { background: var(--brand); color: #fff; }
.step-num.done { background: var(--brand-soft); color: var(--brand); }
.step-title { font-weight: 650; font-size: 1.06rem; color: var(--ink); line-height: 1.3; }
.step-desc { color: var(--muted); font-size: .88rem; margin-top: 1px; }
.step-tag {
    margin-left: auto; font-size: .72rem; font-weight: 600;
    padding: 4px 10px; border-radius: 999px; white-space: nowrap;
}
.tag-done    { background: var(--brand-soft); color: var(--brand-dark); }
.tag-current { background: #FFF4DB; color: #8A5A00; }
.tag-locked  { background: #EEF1EF; color: #7A8981; }

.section-label {
    font-size: .74rem; font-weight: 700; letter-spacing: .08em;
    text-transform: uppercase; color: var(--muted); margin: 6px 0 -4px;
}

/* ── How-to list ── */
.howto {
    background: #F7FAF8; border: 1px solid var(--line); border-radius: 10px;
    padding: 14px 18px 14px 16px; font-size: .9rem; color: var(--ink);
}
.howto ol { margin: 6px 0 0; padding-left: 20px; }
.howto li { margin: 4px 0; }
.howto a { color: var(--brand); font-weight: 600; }

/* ── Test invoice results ── */
.check-list {
    display: grid; gap: 8px; margin: 2px 0 4px;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
}
.check-row {
    display: flex; gap: 10px; align-items: flex-start;
    padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: #FAFCFB;
}
.check-icon {
    width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0;
    display: grid; place-items: center;
}
.check-icon .ico { width: 14px; height: 14px; }
.check-row.ok .check-icon { background: var(--brand-soft); color: var(--brand); }
.check-row.fail { border-color: #F3C9C9; background: #FFF7F7; }
.check-row.fail .check-icon { background: #FDE3E3; color: #B42318; }
.check-label { font-weight: 600; font-size: .9rem; color: var(--ink); }
.check-note { font-size: .82rem; color: var(--muted); margin-top: 1px; }
.check-row.fail .check-note { color: #B42318; }

/* ── Success panel ── */
.success-panel {
    text-align: center; padding: 22px 18px 8px;
}
.success-icon {
    width: 64px; height: 64px; border-radius: 50%; margin: 0 auto 14px;
    background: var(--brand-soft); color: var(--brand);
    display: grid; place-items: center;
}
.success-title { font-size: 1.35rem; font-weight: 700; color: var(--ink); }
.success-text { color: var(--muted); font-size: .95rem; margin-top: 6px; }

/* ── Footer ── */
.app-footer {
    margin-top: 34px; padding-top: 14px; border-top: 1px solid var(--line);
    text-align: center; color: #8A9891; font-size: .78rem;
}

.env-pill-inline { display: none; }

@media (max-width: 640px) {
    [data-testid="stMainBlockContainer"] { padding-top: 1.25rem; }
    .app-header { align-items: flex-start; gap: 12px; }
    .app-logo { width: 44px; height: 44px; border-radius: 12px; }
    .app-title { font-size: 1.2rem; }
    .app-sub { font-size: .85rem; }
    .env-pill { display: none; }
    .env-pill-inline { display: inline-block; margin: 8px 0 0; padding: 4px 10px; }
    .stepper { margin-top: 20px; }
    .st-label { font-size: .68rem; line-height: 1.25; max-width: 64px; }
    .step-tag { display: none; }
    .step-head { align-items: flex-start; }
}
</style>
""")

ICONS = {
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "receipt": '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/>'
               '<path d="M8 8h8"/><path d="M8 12h8"/><path d="M8 16h5"/>',
}


def _icon_css():
    rules = [
        ".ico { display: inline-block; width: 16px; height: 16px; background-color: currentColor;"
        " -webkit-mask: var(--ico) center / contain no-repeat; mask: var(--ico) center / contain no-repeat; }",
        ".ico-lg { width: 32px; height: 32px; }",
        ".app-logo .ico { width: 26px; height: 26px; background-color: #fff; }",
    ]
    for name, body in ICONS.items():
        svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' "
               "stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'>" + body + "</svg>")
        rules.append(f'.ico-{name} {{ --ico: url("data:image/svg+xml,{quote(svg)}"); }}')
    return "<style>" + "\n".join(rules) + "</style>"


st.html(_icon_css())

# ═══════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════


def default_form():
    return {
        "env": "sandbox",
        "organization": "Maximum Speed Tech Supply LTD",
        "org_unit": "Riyadh Branch",
        "tax_number": SAMPLE_VAT,
        "common_name": "TST-886431145-399999999900003",
        "address": "RRRD2929",
        "business_cat": "Supply activities",
        "invoice_type": "1100",
        "country": "SA",
        "serial_number": f"1-TST|2-TST|3-{uuid.uuid4()}",
    }


PROGRESS_KEYS = {
    "details": None,          # saved business details (step 1)
    "private_key_pem": None,
    "csr_pem": None,
    "csr_base64": None,
    "ccsid": None,            # compliance certificate (step 2)
    "compliance": None,       # test invoice results (step 3)
    "pcsid": None,            # production certificate (step 4)
    "error": None,            # {"step": n, "message": str, "log": str}
    "log": {},                # technical log per step
}

if "form" not in st.session_state:
    st.session_state.form = default_form()
if "otp" not in st.session_state:
    st.session_state.otp = SANDBOX_OTP
for _k, _v in PROGRESS_KEYS.items():
    if _k not in st.session_state:
        st.session_state[_k] = dict(_v) if isinstance(_v, dict) else _v


def clear_progress():
    for k, v in PROGRESS_KEYS.items():
        st.session_state[k] = dict(v) if isinstance(v, dict) else v


def current_step():
    s = st.session_state
    if s.details is None:
        return 1
    if s.ccsid is None:
        return 2
    if not (s.compliance and s.compliance["all_passed"]):
        return 3
    if s.pcsid is None:
        return 4
    return LAST_STEP


# ═══════════════════════════════════════════════════════════
# BACKEND
# ═══════════════════════════════════════════════════════════


def generate_key_and_csr(details):
    """Create an EC private key and CSR with OpenSSL in a private temp folder."""
    template = ENVIRONMENTS[details["env"]]["template"]
    config_content = f"""oid_section = OIDs
[OIDs]
certificateTemplateName = 1.3.6.1.4.1.311.20.2

[req]
default_bits = 2048
prompt = no
default_md = sha256
req_extensions = req_ext
distinguished_name = dn

[dn]
CN = {details['common_name']}
OU = {details['org_unit']}
O  = {details['organization']}
C  = {details['country']}

[req_ext]
certificateTemplateName = ASN1:PRINTABLESTRING:{template}
subjectAltName = dirName:alt_names

[alt_names]
SN = {details['serial_number']}
UID = {details['tax_number']}
title = {details['invoice_type']}
registeredAddress = {details['address']}
businessCategory = {details['business_cat']}
"""
    logs = []
    with tempfile.TemporaryDirectory() as tmp:
        cnf_path = os.path.join(tmp, "zatca_csr.cnf")
        key_path = os.path.join(tmp, "private_key.pem")
        csr_path = os.path.join(tmp, "csr.pem")
        with open(cnf_path, "w") as f:
            f.write(config_content)
        logs.append(f"CSR config written (template: {template})")

        try:
            r1 = subprocess.run(
                ["openssl", "ecparam", "-name", "secp256k1", "-genkey", "-noout", "-out", key_path],
                capture_output=True, text=True,
            )
        except FileNotFoundError:
            return None, "OpenSSL is not installed on this server.", "\n".join(logs)
        if r1.returncode != 0:
            logs.append(f"Key generation failed:\n{r1.stderr}")
            return None, "Could not create your security key.", "\n".join(logs)
        logs.append("EC secp256k1 private key generated")

        r2 = subprocess.run(
            ["openssl", "req", "-new", "-sha256", "-key", key_path, "-config", cnf_path, "-out", csr_path],
            capture_output=True, text=True,
        )
        if r2.returncode != 0:
            logs.append(f"CSR generation failed:\n{r2.stderr}")
            return None, ("Could not create the certificate request. "
                          "Check your business details for unusual characters."), "\n".join(logs)
        logs.append("Certificate Signing Request (CSR) generated")

        with open(key_path) as f:
            private_key_pem = f.read()
        with open(csr_path) as f:
            csr_pem = f.read()

    result = {
        "private_key_pem": private_key_pem,
        "csr_pem": csr_pem,
        "csr_base64": base64.b64encode(csr_pem.encode("utf-8")).decode("utf-8"),
    }
    return result, None, "\n".join(logs)


def _zatca_messages(data):
    msgs = []
    if isinstance(data, dict):
        for k in ("message", "errorMessage", "error", "Message"):
            if isinstance(data.get(k), str):
                msgs.append(data[k])
        for k in ("errors", "validationResults"):
            items = data.get(k)
            if isinstance(items, dict):
                items = items.get("errorMessages") or []
            if isinstance(items, list):
                for e in items:
                    if isinstance(e, str):
                        msgs.append(e)
                    elif isinstance(e, dict):
                        msgs.append(e.get("message") or e.get("code") or json.dumps(e))
    return [m for m in msgs if m]


def explain_failure(step, status, body_text):
    """Turn a ZATCA error response into plain language."""
    try:
        data = json.loads(body_text)
    except ValueError:
        data = None
    msgs = _zatca_messages(data)
    lower = body_text.lower()

    if step == 2 and "otp" in lower:
        return ("ZATCA did not accept the one-time password (OTP). It may be mistyped, "
                "already used, or expired (codes last 1 hour). Get a new code and try again.")
    if step == 4 and "compliance" in lower:
        return ("ZATCA says the test invoices haven't all passed yet. Use Start over to run "
                "the whole process again.")
    if status in (401, 403):
        return "ZATCA refused the request because it couldn't confirm who you are."
    if status >= 500:
        return "ZATCA's servers had a problem on their side. Please wait a few minutes and try again."
    if msgs:
        return "ZATCA did not accept the request: " + "; ".join(msgs[:3])
    return f"ZATCA did not accept the request (error {status})."


def call_zatca(step, url, headers, body):
    logs = [f"POST {url}"]
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=30)
    except requests.RequestException as e:
        logs.append(f"Network error: {e}")
        return None, "Could not reach ZATCA. Check your internet connection and try again.", "\n".join(logs)

    logs.append(f"HTTP {resp.status_code}")
    if resp.status_code in (200, 201):
        try:
            data = resp.json()
        except ValueError:
            logs.append(f"Response: {resp.text[:600]}")
            return None, "ZATCA sent back an unexpected reply. Please try again.", "\n".join(logs)
        result = {
            "binarySecurityToken": data.get("binarySecurityToken"),
            "secret": data.get("secret"),
            "requestID": data.get("requestID"),
        }
        logs.append(f"requestID: {result['requestID']}")
        return result, None, "\n".join(logs)

    logs.append(f"Response: {resp.text[:600]}")
    return None, explain_failure(step, resp.status_code, resp.text), "\n".join(logs)


def request_compliance_csid(env, csr_base64, otp):
    headers = {
        "accept": "application/json",
        "accept-language": "en",
        "Accept-Version": "V2",
        "Content-Type": "application/json",
        "OTP": otp,
    }
    return call_zatca(2, f"{ENVIRONMENTS[env]['url']}/compliance", headers, {"csr": csr_base64})


def request_production_csid(env, ccsid):
    credentials = base64.b64encode(
        f"{ccsid['binarySecurityToken']}:{ccsid['secret']}".encode()
    ).decode()
    headers = {
        "accept": "application/json",
        "accept-language": "en",
        "Accept-Version": "V2",
        "Content-Type": "application/json",
        "Authorization": f"Basic {credentials}",
    }
    body = {"compliance_request_id": str(ccsid["requestID"])}
    return call_zatca(4, f"{ENVIRONMENTS[env]['url']}/production/csids", headers, body)


DOC_LABELS = {
    "STDSI": "Tax invoice (B2B)",
    "STDCN": "Tax credit note (B2B)",
    "STDDN": "Tax debit note (B2B)",
    "SIMSI": "Simplified invoice (B2C)",
    "SIMCN": "Simplified credit note (B2C)",
    "SIMDN": "Simplified debit note (B2C)",
}


def _validation_messages(validation, key):
    return [
        m.get("message") or m.get("code") or json.dumps(m)
        for m in (validation.get(key) or [])
        if isinstance(m, dict)
    ]


def run_compliance_checks(details, ccsid, private_key_pem):
    """Create, sign and submit the sample documents ZATCA requires before activation."""
    logs = []
    try:
        certificate = base64.b64decode(ccsid["binarySecurityToken"]).decode("utf-8")
        invoices = invoice_signer.generate_all_compliance_invoices(
            certificate, private_key_pem,
            seller_name=details["organization"],
            seller_vat=details["tax_number"],
            invoice_type_code=details["invoice_type"],
        )
    except Exception as e:
        logs.append(f"Signing failed: {e!r}")
        return None, "Could not create the test invoices. Please start over and try again.", "\n".join(logs)

    url = f"{ENVIRONMENTS[details['env']]['url']}/compliance/invoices"
    credentials = base64.b64encode(
        f"{ccsid['binarySecurityToken']}:{ccsid['secret']}".encode()
    ).decode()
    headers = {
        "accept": "application/json",
        "accept-language": "en",
        "Accept-Version": "V2",
        "Content-Type": "application/json",
        "Authorization": f"Basic {credentials}",
    }

    results = []
    for inv in invoices:
        row = {"label": DOC_LABELS.get(inv["prefix"], inv["label"]), "ok": False,
               "status": "", "errors": [], "warnings": []}
        logs.append(f"POST {url}  [{inv['prefix']}]")
        try:
            resp = requests.post(
                url, json={k: inv[k] for k in ("invoiceHash", "uuid", "invoice")},
                headers=headers, timeout=30,
            )
        except requests.RequestException as e:
            logs.append(f"  Network error: {e}")
            row["errors"] = ["Could not reach ZATCA."]
            results.append(row)
            continue

        try:
            data = resp.json()
        except ValueError:
            data = {}
        validation = data.get("validationResults") or {}
        row["status"] = data.get("clearanceStatus") or data.get("reportingStatus") or ""
        row["errors"] = _validation_messages(validation, "errorMessages")
        row["warnings"] = _validation_messages(validation, "warningMessages")
        row["ok"] = resp.status_code in (200, 202) and row["status"] in ("CLEARED", "REPORTED")
        if not row["ok"] and not row["errors"]:
            row["errors"] = [explain_failure(3, resp.status_code, resp.text)]

        logs.append(f"  HTTP {resp.status_code} {row['status']} {validation.get('status', '')}")
        logs.extend(f"  error: {m}" for m in row["errors"])
        logs.extend(f"  warning: {m}" for m in row["warnings"])
        results.append(row)

    all_passed = all(r["ok"] for r in results)
    err = None
    if not all_passed:
        failed = sum(not r["ok"] for r in results)
        err = (f"{failed} of {len(results)} test documents were not accepted. "
               "Check the reasons above, then press Try again.")
    return {"results": results, "all_passed": all_passed}, err, "\n".join(logs)


def build_settings_export(details, s):
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    ccsid = s.ccsid or {}
    pcsid = s.pcsid or {}
    return {
        "company_information": {
            "company_name": details["organization"],
            "vat_number": details["tax_number"],
            "commercial_registration_number": "",
            "organization_identifier": details["tax_number"],
            "city_name": "",
            "street_name": "",
            "building_number": "",
            "postal_code": "",
            "country_code": details["country"],
        },
        "solution_information": {
            "solution_name": "",
            "model_name": "",
            "serial_number": details["serial_number"],
            "organizational_unit_name": details["org_unit"],
            "business_category": details["business_cat"],
            "invoice_type": details["invoice_type"],
        },
        "environment": {
            "environment": details["env"],
            "is_production": "t" if details["env"] == "production" else "f",
            "is_active": "t",
        },
        "certificates": {
            "previous_invoice_hash": "MA==",
            "privateKey": base64.b64encode((s.private_key_pem or "").encode("utf-8")).decode("utf-8"),
            "csr": s.csr_base64 or "",
            "ccsid_requestID": str(ccsid.get("requestID", "")),
            "ccsid_binarySecurityToken": ccsid.get("binarySecurityToken", ""),
            "ccsid_secret": ccsid.get("secret", ""),
            "pcsid_binarySecurityToken": pcsid.get("binarySecurityToken", ""),
            "pcsid_secret": pcsid.get("secret", ""),
            "pcsid_requestID": str(pcsid.get("requestID", "")),
            "lastICV": 0,
            "zatcaotp": 0,
        },
        "timestamps": {"created_at": now_str, "updated_at": now_str},
        "export_info": {"exported_at": now_str, "exported_by": "owner"},
    }


def validate_details(d):
    errors = []
    required = {
        "organization": "Company legal name",
        "org_unit": "Branch or department",
        "common_name": "Name for this invoicing system",
        "address": "National short address",
        "business_cat": "Business activity",
    }
    for key, label in required.items():
        if not d[key].strip():
            errors.append(f"**{label}** is required.")
    if not re.fullmatch(r"3\d{13}3", d["tax_number"].strip()):
        errors.append("**VAT number** must be 15 digits, starting and ending with 3 (e.g. 300000000000003).")
    if not re.fullmatch(r"[A-Za-z]{2}", d["country"].strip()):
        errors.append("**Country code** must be 2 letters (e.g. SA).")
    if not re.fullmatch(r"1-[^|]+\|2-[^|]+\|3-[^|]+", d["serial_number"].strip()):
        errors.append("**Serial number** must look like `1-Name|2-Model|3-UniqueID`.")
    for key, value in d.items():
        if any(ch in value for ch in "\n\r$#"):
            errors.append("Details can't contain the characters `$` or `#`.")
            break
    return errors


# ═══════════════════════════════════════════════════════════
# UI HELPERS
# ═══════════════════════════════════════════════════════════

CHECK_ICON = '<span class="ico ico-check"></span>'
LOGO_ICON = '<span class="ico ico-receipt"></span>'
BIG_CHECK_ICON = '<span class="ico ico-check ico-lg"></span>'
X_ICON = '<span class="ico ico-x"></span>'


def esc(value):
    return html.escape(str(value))


def render_header(env):
    e = ENVIRONMENTS[env]
    st.html(f"""
<div class="app-header">
    <div class="app-logo">{LOGO_ICON}</div>
    <div>
        <div class="app-title">ZATCA E-Invoicing Setup</div>
        <div class="app-sub">Register your invoicing system with ZATCA (Fatoora) in a few guided steps.</div>
        <span class="env-pill env-pill-inline env-{env}">{esc(e['pill'])}</span>
    </div>
    <span class="env-pill env-{env}">{esc(e['pill'])}</span>
</div>
""")


def render_stepper(active):
    items = []
    for i, label in enumerate(STEPS, start=1):
        if i < active or active == LAST_STEP:
            cls, dot = "done", CHECK_ICON
        elif i == active:
            cls, dot = "current", str(i)
        else:
            cls, dot = "", str(i)
        items.append(
            f'<div class="st-item {cls}"><div class="st-dot">{dot}</div>'
            f'<div class="st-label">{esc(label)}</div></div>'
        )
    st.html(f'<div class="stepper">{"".join(items)}</div>')


def step_heading(num, title, desc, state):
    tags = {
        "done": ("tag-done", "Done"),
        "current": ("tag-current", "Your next step"),
        "locked": ("tag-locked", "Locked"),
    }
    tag_cls, tag_text = tags[state]
    num_html = CHECK_ICON if state == "done" else str(num)
    st.html(f"""
<div class="step-head">
    <div class="step-num {state}">{num_html}</div>
    <div>
        <div class="step-title">{esc(title)}</div>
        <div class="step-desc">{desc}</div>
    </div>
    <span class="step-tag {tag_cls}">{tag_text}</span>
</div>
""")


def step_state(num, active):
    if num < active:
        return "done"
    return "current" if num == active else "locked"


def render_compliance_results(results):
    rows = []
    for r in results:
        if r["ok"]:
            icon, cls = CHECK_ICON, "ok"
            note = "Accepted by ZATCA"
            if r["warnings"]:
                note += f" with {len(r['warnings'])} warning(s): " + "; ".join(r["warnings"][:2])
        else:
            icon, cls = X_ICON, "fail"
            note = "; ".join(r["errors"][:2]) or "Not accepted"
        rows.append(
            f'<div class="check-row {cls}"><span class="check-icon">{icon}</span><div>'
            f'<div class="check-label">{esc(r["label"])}</div>'
            f'<div class="check-note">{esc(note)}</div></div></div>'
        )
    st.html(f'<div class="check-list">{"".join(rows)}</div>')


def show_error(step):
    err = st.session_state.error
    if err and err["step"] == step:
        st.error(err["message"], icon=":material/error:")
        if err.get("log"):
            with st.expander("Technical details (for your IT support)"):
                st.code(err["log"], language=None)


# ═══════════════════════════════════════════════════════════
# PAGE
# ═══════════════════════════════════════════════════════════

s = st.session_state
form = s.form
active = current_step()
# The header is drawn before the environment radio, so read the radio's latest value directly.
env_for_header = s.details["env"] if s.details else s.get("env_choice", form["env"])

render_header(env_for_header)
render_stepper(active)


# ── STEP 1 · Business details ──────────────────────────────

state1 = step_state(1, active)
with st.container(border=True, key=f"card-{state1}-1"):
    step_heading(
        1, "Tell us about your business",
        "These details go into your certificate, so they must match your ZATCA registration.",
        state1,
    )

    if state1 == "current":
        st.html('<div class="section-label">Where do you want to register?</div>')
        env_keys = list(ENVIRONMENTS)
        form["env"] = st.radio(
            "Where do you want to register?",
            env_keys,
            index=env_keys.index(form["env"]),
            format_func=lambda k: ENVIRONMENTS[k]["label"],
            captions=[ENVIRONMENTS[k]["caption"] for k in env_keys],
            label_visibility="collapsed",
            key="env_choice",
        )

        if form["env"] != "sandbox" and form["tax_number"] == SAMPLE_VAT:
            st.warning(
                "The fields below still contain **sample data**. Replace them with your "
                "real business details before continuing.",
                icon=":material/edit_note:",
            )

        st.html('<div class="section-label">Your business</div>')
        with st.form("details_form", border=False):
            c1, c2 = st.columns(2)
            organization = c1.text_input(
                "Company legal name", value=form["organization"],
                help="Exactly as it appears on your VAT registration.",
            )
            org_unit = c2.text_input(
                "Branch or department", value=form["org_unit"],
                help="The branch that will issue invoices, e.g. Riyadh Branch.",
            )
            c3, c4 = st.columns(2)
            tax_number = c3.text_input(
                "VAT number", value=form["tax_number"], max_chars=15,
                help="Your 15-digit VAT registration number. It starts and ends with 3.",
            )
            type_keys = list(INVOICE_TYPES)
            invoice_type = c4.selectbox(
                "Which invoices will you issue?", type_keys,
                index=type_keys.index(form["invoice_type"]),
                format_func=lambda k: INVOICE_TYPES[k],
                help="Tax invoices are for business customers; simplified invoices are "
                     "for regular shoppers (like a receipt).",
            )
            c5, c6 = st.columns(2)
            address = c5.text_input(
                "National short address", value=form["address"],
                help="Your 8-character Saudi National Address short code, e.g. RRRD2929.",
            )
            business_cat = c6.text_input(
                "Business activity", value=form["business_cat"],
                help="What your business does, e.g. Retail, Restaurant, Supply activities.",
            )
            common_name = st.text_input(
                "Name for this invoicing system", value=form["common_name"],
                help="Any name that identifies this POS or accounting system, e.g. Main-Store-POS.",
            )
            with st.expander("Advanced settings (optional, most people can skip this)"):
                serial_number = st.text_input(
                    "Device serial number", value=form["serial_number"],
                    help="Format: 1-SolutionName|2-ModelOrVersion|3-UniqueID. A unique one is "
                         "generated for you.",
                )
                country = st.text_input("Country code", value=form["country"], max_chars=2)

            submitted = st.form_submit_button(
                "Save and continue", type="primary", width="stretch",
                icon=":material/arrow_forward:", icon_position="right",
            )

        if submitted:
            new_values = {
                "env": form["env"],
                "organization": organization.strip(),
                "org_unit": org_unit.strip(),
                "tax_number": tax_number.strip(),
                "invoice_type": invoice_type,
                "address": address.strip(),
                "business_cat": business_cat.strip(),
                "common_name": common_name.strip(),
                "serial_number": serial_number.strip(),
                "country": country.strip().upper(),
            }
            form.update(new_values)
            problems = validate_details(new_values)
            if problems:
                st.error("Please fix the following:\n\n" + "\n".join(f"- {p}" for p in problems),
                         icon=":material/error:")
            else:
                clear_progress()
                s.details = dict(new_values)
                if new_values["env"] == "sandbox":
                    s.otp = SANDBOX_OTP
                elif s.otp == SANDBOX_OTP:
                    s.otp = ""
                st.rerun()

    elif state1 == "done":
        d = s.details
        left, right = st.columns([5, 1], vertical_alignment="center")
        left.markdown(
            f"**{d['organization']}** · VAT {d['tax_number']}  \n"
            f":gray[{ENVIRONMENTS[d['env']]['label']} · {d['org_unit']}]"
        )
        if active < LAST_STEP:
            if right.button("Edit", type="tertiary", icon=":material/edit:",
                            help="Change your details. You'll need to redo the next steps."):
                clear_progress()
                st.rerun()


# ── STEP 2 · Verify with OTP ──────────────────────────────

state2 = step_state(2, active)
with st.container(border=True, key=f"card-{state2}-2"):
    step_heading(
        2, "Verify with a one-time password",
        "ZATCA uses a short code (OTP) to confirm that you own this VAT number.",
        state2,
    )

    if state2 == "current":
        env = s.details["env"]
        if env == "sandbox":
            st.info(
                f"You're in practice mode, so the test code **{SANDBOX_OTP}** is already filled in. "
                "Just press the button below.",
                icon=":material/lightbulb:",
            )
        else:
            portal = "Simulation portal" if env == "simulation" else "main Fatoora portal"
            st.html(f"""
<div class="howto">
    <b>How to get your code</b>
    <ol>
        <li>Sign in at <a href="https://fatoora.zatca.gov.sa" target="_blank">fatoora.zatca.gov.sa</a>
            with your ZATCA account and open the {portal}.</li>
        <li>Choose <b>Onboard new solution unit / device</b>.</li>
        <li>Enter <b>1</b> as the number of codes and click <b>Generate OTP code</b>.</li>
        <li>Copy the 6-digit code into the box below. It expires after <b>1 hour</b>.</li>
    </ol>
</div>
""")

        s.otp = st.text_input(
            "One-time password (OTP)", value=s.otp, max_chars=6, placeholder="6-digit code",
        ).strip()

        if st.button("Register with ZATCA", type="primary", width="stretch",
                     icon=":material/verified_user:"):
            s.error = None
            if not re.fullmatch(r"\d{6}", s.otp):
                s.error = {"step": 2, "message": "The OTP should be exactly 6 digits.", "log": ""}
            else:
                with st.spinner("Creating your secure key and contacting ZATCA..."):
                    log_parts = []
                    if s.csr_base64 is None:
                        keys, err, log = generate_key_and_csr(s.details)
                        log_parts.append(log)
                        if err:
                            s.error = {"step": 2, "message": err, "log": "\n".join(log_parts)}
                        else:
                            s.private_key_pem = keys["private_key_pem"]
                            s.csr_pem = keys["csr_pem"]
                            s.csr_base64 = keys["csr_base64"]
                    if s.error is None:
                        ccsid, err, log = request_compliance_csid(env, s.csr_base64, s.otp)
                        log_parts.append(log)
                        s.log[2] = "\n".join(log_parts)
                        if err:
                            s.error = {"step": 2, "message": err, "log": s.log[2]}
                        else:
                            s.ccsid = ccsid
            st.rerun()

        show_error(2)

    elif state2 == "done":
        st.markdown(f"Verified. ZATCA issued your compliance certificate "
                    f":gray[(request {s.ccsid.get('requestID', '—')})].")

    else:
        st.caption("Unlocks after you save your business details.")


# ── STEP 3 · Test invoices ─────────────────────────────────

state3 = step_state(3, active)
with st.container(border=True, key=f"card-{state3}-3"):
    step_heading(
        3, "Send test invoices",
        "ZATCA checks that your system can produce correct invoices before activating it.",
        state3,
    )

    if state3 == "current":
        doc_count = len(invoice_signer.document_types_for(s.details["invoice_type"]))
        if not s.compliance:
            st.markdown(
                f"We'll create **{doc_count} sample documents** (invoices, credit notes and debit "
                f"notes) under your company name, sign them, and send them to ZATCA for checking. "
                f"This is automatic and takes about a minute. These are test documents only: "
                f"they don't count as real sales."
            )
        else:
            render_compliance_results(s.compliance["results"])

        label = "Send test invoices" if not s.compliance else "Try again"
        if st.button(label, type="primary", width="stretch", icon=":material/fact_check:"):
            s.error = None
            with st.spinner(f"Creating and sending {doc_count} test documents to ZATCA..."):
                compliance, err, log = run_compliance_checks(
                    s.details, s.ccsid, s.private_key_pem
                )
            s.log[3] = log
            s.compliance = compliance
            if err:
                s.error = {"step": 3, "message": err, "log": log}
            st.rerun()

        show_error(3)

    elif state3 == "done":
        results = s.compliance["results"]
        st.markdown(f"All {len(results)} test documents were accepted by ZATCA.")
        with st.expander("See results"):
            render_compliance_results(results)

    else:
        st.caption("Unlocks after ZATCA verifies your OTP.")


# ── STEP 4 · Activate ──────────────────────────────────────

state4 = step_state(4, active)
with st.container(border=True, key=f"card-{state4}-4"):
    step_heading(
        4, "Activate your certificate",
        "Swap your trial certificate for the one you'll use to sign real invoices.",
        state4,
    )

    if state4 == "current":
        if st.button("Activate my certificate", type="primary", width="stretch",
                     icon=":material/rocket_launch:"):
            s.error = None
            with st.spinner("Activating with ZATCA..."):
                pcsid, err, log = request_production_csid(s.details["env"], s.ccsid)
            s.log[4] = log
            if err:
                s.error = {"step": 4, "message": err, "log": log}
            else:
                s.pcsid = pcsid
            st.rerun()

        show_error(4)

    elif state4 == "done":
        st.markdown(f"Activated. Your production certificate is ready "
                    f":gray[(request {s.pcsid.get('requestID', '—')})].")

    else:
        st.caption("Unlocks after your test invoices pass.")


# ── STEP 5 · Download ──────────────────────────────────────

state5 = "current" if active == LAST_STEP else "locked"
with st.container(border=True, key=f"card-{state5}-5"):
    if active == LAST_STEP:
        d = s.details
        st.html(f"""
<div class="success-panel">
    <div class="success-icon">{BIG_CHECK_ICON}</div>
    <div class="success-title">You're all set!</div>
    <div class="success-text">
        <b>{esc(d['organization'])}</b> is registered with ZATCA
        ({esc(ENVIRONMENTS[d['env']]['label'])}).<br>
        Download your settings file and load it into your invoicing system.
    </div>
</div>
""")
        export_name = f"zatca_settings_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M%S')}.json"
        st.download_button(
            "Download settings file",
            data=json.dumps(build_settings_export(d, s), indent=4, ensure_ascii=False),
            file_name=export_name,
            mime="application/json",
            type="primary",
            width="stretch",
            icon=":material/download:",
            on_click="ignore",
        )
        st.warning(
            "Keep this file private. It contains your secret key: anyone who has it "
            "can sign invoices in your company's name.",
            icon=":material/lock:",
        )
        with st.expander("Individual files (for developers)"):
            files = [
                ("private_key.pem", s.private_key_pem, "text/plain"),
                ("csr.pem", s.csr_pem, "text/plain"),
                ("ccsid.json", json.dumps(s.ccsid, indent=4), "application/json"),
                ("pcsid.json", json.dumps(s.pcsid, indent=4), "application/json"),
            ]
            cols = st.columns(2)
            for i, (name, data, mime) in enumerate(files):
                cols[i % 2].download_button(
                    name, data=data, file_name=name, mime=mime, width="stretch",
                    icon=":material/description:", on_click="ignore", key=f"dl-{name}",
                )
    else:
        step_heading(
            5, "Download your settings",
            "Get the file your invoicing system needs to start signing invoices.",
            "locked",
        )
        st.caption("Unlocks after activation.")


# ── Start over & footer ────────────────────────────────────

if s.details is not None:
    _, mid, _ = st.columns([1, 2, 1])
    with mid.popover("Start over", icon=":material/restart_alt:", type="tertiary", width="stretch"):
        st.markdown("This clears everything on this page, including any certificates you "
                    "haven't downloaded.")
        if st.button("Yes, start over", type="primary", width="stretch"):
            clear_progress()
            st.session_state.form = default_form()
            st.session_state.otp = SANDBOX_OTP
            st.session_state.pop("env_choice", None)
            st.rerun()

st.html("""
<div class="app-footer">
    Connects directly to ZATCA's official Fatoora API. Your details and keys exist only for
    this session and are never saved to disk. Close the tab and they're gone.
</div>
""")
