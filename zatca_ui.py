import uuid
import json
import base64
import hashlib
import requests
import subprocess
import streamlit as st
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════════
# PAGE CONFIG
# ═══════════════════════════════════════════════════════════

st.set_page_config(
    page_title="ZATCA E-Invoicing Integration",
    page_icon="🇸🇦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════
# ENVIRONMENT URL MAPPING
# ═══════════════════════════════════════════════════════════

ENV_OPTIONS = {
    "🧪 Sandbox (Developer Portal)": "https://gw-fatoora.zatca.gov.sa/e-invoicing/developer-portal",
    "🔬 Simulation": "https://gw-fatoora.zatca.gov.sa/e-invoicing/simulation",
    "🏭 Production": "https://gw-fatoora.zatca.gov.sa/e-invoicing/core",
}

ENV_BADGE_STYLES = {
    "🧪 Sandbox (Developer Portal)": {
        "label": "SANDBOX",
        "bg": "linear-gradient(135deg, #c8a96e, #a07840)",
        "color": "#0f1117",
    },
    "🔬 Simulation": {
        "label": "SIMULATION",
        "bg": "linear-gradient(135deg, #4a8fe7, #2d6bc4)",
        "color": "#ffffff",
    },
    "🏭 Production": {
        "label": "PRODUCTION",
        "bg": "linear-gradient(135deg, #34c975, #1f8a50)",
        "color": "#0f1117",
    },
}

# ═══════════════════════════════════════════════════════════
# CUSTOM CSS
# ═══════════════════════════════════════════════════════════

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    /* --- Base & Background --- */
    .stApp {
        background-color: #0f1117;
        color: #e8eaf0;
        font-family: 'Inter', sans-serif;
    }

    /* --- Sidebar --- */
    [data-testid="stSidebar"] {
        background: linear-gradient(160deg, #1a1f2e 0%, #12161f 100%);
        border-right: 1px solid #2a2f3e;
    }
    [data-testid="stSidebar"] .stMarkdown h1,
    [data-testid="stSidebar"] .stMarkdown h2,
    [data-testid="stSidebar"] .stMarkdown h3 {
        color: #c8a96e;
    }

    /* --- Main header --- */
    .main-header {
        background: linear-gradient(135deg, #1e2540 0%, #162032 50%, #1a2535 100%);
        border: 1px solid #2e3a50;
        border-radius: 14px;
        padding: 28px 36px;
        margin-bottom: 28px;
        display: flex;
        align-items: center;
        gap: 18px;
    }
    .main-header h1 {
        font-size: 2rem;
        font-weight: 700;
        color: #e8eaf0;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .main-header p {
        color: #8a94aa;
        margin: 4px 0 0;
        font-size: 0.95rem;
    }
    .zatca-badge {
        padding: 5px 14px;
        border-radius: 20px;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 1.2px;
        white-space: nowrap;
        display: inline-block;
    }

    /* --- Step Cards --- */
    .step-card {
        background: #161b27;
        border: 1px solid #252b3b;
        border-radius: 12px;
        padding: 24px 28px;
        margin-bottom: 20px;
        transition: border-color 0.3s, box-shadow 0.3s;
    }
    .step-card:hover {
        border-color: #3a4255;
    }
    .step-card-active {
        border-color: #c8a96e !important;
        background: linear-gradient(135deg, #1e1f16 0%, #161b27 100%) !important;
        box-shadow: 0 0 20px rgba(200, 169, 110, 0.06);
    }
    .step-card-done {
        border-color: #2a5c3f !important;
        background: linear-gradient(135deg, #162a1e 0%, #161b27 100%) !important;
    }
    .step-card-error {
        border-color: #5c2a2a !important;
        background: linear-gradient(135deg, #2a1616 0%, #161b27 100%) !important;
    }

    /* --- Step header --- */
    .step-header {
        display: flex;
        align-items: center;
        gap: 14px;
        margin-bottom: 16px;
    }
    .step-number {
        width: 38px;
        height: 38px;
        border-radius: 50%;
        background: #2a3045;
        border: 2px solid #3d4560;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 1rem;
        color: #8a94aa;
        flex-shrink: 0;
    }
    .step-number-active {
        background: #2e2818;
        border-color: #c8a96e;
        color: #e8c96e;
        animation: pulseGold 2.5s ease-in-out infinite;
    }
    @keyframes pulseGold {
        0%, 100% { box-shadow: 0 0 0 0 rgba(200, 169, 110, 0.25); }
        50% { box-shadow: 0 0 12px 3px rgba(200, 169, 110, 0.15); }
    }
    .step-number-done {
        background: #1a4030;
        border-color: #2e7a55;
        color: #4ec98a;
    }
    .step-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #c8cfe0;
    }
    .step-subtitle {
        font-size: 0.82rem;
        color: #5a6478;
        margin-top: 2px;
    }

    /* --- Status badges --- */
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    .badge-pending  { background: #2a2f3e; color: #6a748a; }
    .badge-running  { background: #2e2818; color: #e8c96e; }
    .badge-success  { background: #1a3a28; color: #4ec98a; }
    .badge-error    { background: #3a1a1a; color: #e06060; }

    /* --- Result boxes --- */
    .result-box {
        background: #0d1018;
        border: 1px solid #222736;
        border-radius: 8px;
        padding: 16px 18px;
        font-family: 'Courier New', monospace;
        font-size: 0.82rem;
        color: #7aff9a;
        white-space: pre-wrap;
        word-break: break-all;
        max-height: 260px;
        overflow-y: auto;
        margin-top: 12px;
    }
    .result-box-error {
        color: #ff7a7a;
        border-color: #3a2020;
    }

    /* --- Info grid --- */
    .info-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        gap: 12px;
        margin-top: 14px;
    }
    .info-item {
        background: #0d1018;
        border: 1px solid #1e2330;
        border-radius: 8px;
        padding: 12px 14px;
    }
    .info-label {
        font-size: 0.72rem;
        color: #5a6478;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 4px;
    }
    .info-value {
        font-size: 0.88rem;
        color: #c8cfe0;
        font-weight: 500;
        word-break: break-all;
    }

    /* --- Divider --- */
    .section-divider {
        border: none;
        border-top: 1px solid #1e2330;
        margin: 20px 0;
    }

    /* ============================================ */
    /* PRIMARY ACTION BUTTONS — High-Contrast Gold  */
    /* ============================================ */
    .stButton > button {
        background: linear-gradient(135deg, #d4b36a 0%, #c8a96e 40%, #b8944a 100%) !important;
        color: #1a1400 !important;
        border: 1px solid #c8a96e !important;
        border-radius: 10px !important;
        padding: 12px 28px !important;
        font-weight: 700 !important;
        font-size: 0.92rem !important;
        letter-spacing: 0.3px !important;
        transition: all 0.25s ease !important;
        cursor: pointer !important;
        box-shadow: 0 2px 8px rgba(200, 169, 110, 0.18) !important;
        text-shadow: 0 1px 0 rgba(255,255,255,0.15) !important;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #e0c278 0%, #d4b36a 40%, #c8a96e 100%) !important;
        border-color: #e0c278 !important;
        box-shadow: 0 4px 16px rgba(200, 169, 110, 0.3) !important;
        transform: translateY(-2px) !important;
        color: #0f0a00 !important;
    }
    .stButton > button:active {
        transform: translateY(0) !important;
        box-shadow: 0 1px 4px rgba(200, 169, 110, 0.15) !important;
    }
    .stButton > button:focus {
        outline: 2px solid #e0c278 !important;
        outline-offset: 2px !important;
    }

    /* ============================================ */
    /* DOWNLOAD BUTTONS — Teal / Emerald accent     */
    /* ============================================ */
    .stDownloadButton > button {
        background: linear-gradient(135deg, #1a4a3a 0%, #1e5c48 50%, #1a4a3a 100%) !important;
        color: #5aeaa0 !important;
        border: 1px solid #2e7a55 !important;
        border-radius: 10px !important;
        padding: 10px 22px !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        transition: all 0.25s ease !important;
        cursor: pointer !important;
        box-shadow: 0 2px 6px rgba(46, 122, 85, 0.12) !important;
    }
    .stDownloadButton > button:hover {
        background: linear-gradient(135deg, #1e5c48 0%, #24725a 50%, #1e5c48 100%) !important;
        border-color: #3ea875 !important;
        box-shadow: 0 4px 14px rgba(46, 122, 85, 0.25) !important;
        transform: translateY(-1px) !important;
        color: #7affc0 !important;
    }
    .stDownloadButton > button:active {
        transform: translateY(0) !important;
    }
    .stDownloadButton > button:focus {
        outline: 2px solid #3ea875 !important;
        outline-offset: 2px !important;
    }

    /* ============================================ */
    /* RESET BUTTON — Red outline in sidebar        */
    /* ============================================ */
    [data-testid="stSidebar"] .stButton > button[kind="secondary"],
    [data-testid="stSidebar"] .reset-btn-container .stButton > button {
        background: transparent !important;
        color: #e06060 !important;
        border: 1.5px solid #5c2a2a !important;
        font-weight: 600 !important;
        box-shadow: none !important;
        text-shadow: none !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover,
    [data-testid="stSidebar"] .reset-btn-container .stButton > button:hover {
        background: rgba(224, 96, 96, 0.08) !important;
        border-color: #e06060 !important;
        box-shadow: 0 0 12px rgba(224, 96, 96, 0.1) !important;
        color: #ff7a7a !important;
        transform: translateY(-1px) !important;
    }

    /* --- Input fields --- */
    div[data-testid="stTextInput"] input,
    div[data-testid="stTextArea"] textarea,
    div[data-testid="stSelectbox"] > div > div {
        background: #0d1018 !important;
        border: 1px solid #252b3b !important;
        color: #e8eaf0 !important;
        border-radius: 8px !important;
    }
    div[data-testid="stTextInput"] input:focus,
    div[data-testid="stTextArea"] textarea:focus {
        border-color: #c8a96e !important;
        box-shadow: 0 0 0 1px rgba(200, 169, 110, 0.2) !important;
    }
    label[data-testid="stWidgetLabel"] p {
        color: #8a94aa !important;
        font-size: 0.85rem !important;
    }
    .stAlert {
        border-radius: 8px !important;
    }
    .stExpander {
        border: 1px solid #252b3b !important;
        border-radius: 8px !important;
        background: #161b27 !important;
    }
    div[data-testid="stExpander"] summary {
        color: #8a94aa !important;
    }
    div[data-testid="stExpander"] summary:hover {
        color: #c8a96e !important;
    }

    /* Progress pipeline */
    .pipeline {
        display: flex;
        align-items: center;
        gap: 0;
        margin: 20px 0 28px;
    }
    .pipe-step {
        flex: 1;
        text-align: center;
        padding: 10px 6px;
        background: #161b27;
        border: 1px solid #252b3b;
        font-size: 0.78rem;
        color: #5a6478;
        font-weight: 600;
        position: relative;
        transition: all 0.3s ease;
    }
    .pipe-step:first-child { border-radius: 8px 0 0 8px; }
    .pipe-step:last-child  { border-radius: 0 8px 8px 0; }
    .pipe-step-active {
        background: #2e2818;
        border-color: #c8a96e;
        color: #e8c96e;
    }
    .pipe-step-done {
        background: #1a3a28;
        border-color: #2e7a55;
        color: #4ec98a;
    }

    /* --- Env URL display --- */
    .env-url-display {
        background: #0d1018;
        border: 1px solid #1e2330;
        border-radius: 6px;
        padding: 8px 12px;
        font-family: 'Courier New', monospace;
        font-size: 0.72rem;
        color: #5a8a6a;
        word-break: break-all;
        margin-top: 6px;
    }

    /* --- Sidebar section label --- */
    .sidebar-section-label {
        font-size: 0.7rem;
        font-weight: 700;
        color: #4a5268;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        margin: 18px 0 8px;
    }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #0d1018; }
    ::-webkit-scrollbar-thumb { background: #3a4255; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #4a5268; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# SESSION STATE INIT
# ═══════════════════════════════════════════════════════════

defaults = {
    "step1_done": False,
    "step2_done": False,
    "step3_done": False,
    "private_key_pem": None,
    "csr_base64": None,
    "csr_pem": None,
    "ccsid_data": None,
    "pcsid_data": None,
    "step1_log": "",
    "step2_log": "",
    "step3_log": "",
    "step1_error": False,
    "step2_error": False,
    "step3_error": False,
    "default_serial_number": f"1-TST|2-TST|3-{uuid.uuid4()}",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ═══════════════════════════════════════════════════════════
# SIDEBAR — CONFIGURATION
# ═══════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## ⚙️ Configuration")
    st.markdown("<hr style='border-color:#2a2f3e;margin:8px 0 18px'>", unsafe_allow_html=True)

    # ── Environment Selector ──
    st.markdown('<div class="sidebar-section-label">Environment</div>', unsafe_allow_html=True)
    selected_env = st.selectbox(
        "Select Environment",
        options=list(ENV_OPTIONS.keys()),
        index=0,
        label_visibility="collapsed",
    )
    env_url = ENV_OPTIONS[selected_env]
    st.markdown(f'<div class="env-url-display">🔗 {env_url}</div>', unsafe_allow_html=True)

    st.markdown("<hr style='border-color:#2a2f3e;margin:14px 0 10px'>", unsafe_allow_html=True)

    # ── OTP ──
    st.markdown('<div class="sidebar-section-label">Authentication</div>', unsafe_allow_html=True)
    otp = st.text_input("OTP (One-Time Password)", value="123345", type="password")

    st.markdown("<hr style='border-color:#2a2f3e;margin:14px 0 10px'>", unsafe_allow_html=True)

    # ── CSR Configuration (expandable) ──
    with st.expander("🔧 Configure CSR Parameters", expanded=False):
        tax_number  = st.text_input("Tax Number (UID)", value="399999999900003")
        common_name = st.text_input("Common Name (CN)", value=f"TST-886431145-399999999900003",
                                     help="e.g. TST-886431145-{TaxNumber}")
        serial_number = st.text_input("Serial Number (SN)", value=st.session_state.default_serial_number,
                                       help="Format: 1-CompanyName|2-Version|3-UUID")
        org_name    = st.text_input("Organization Name (O)", value="Maximum Speed Tech Supply LTD")
        org_unit    = st.text_input("Organization Unit (OU)", value="Riyadh Branch")
        country     = st.text_input("Country Code (C)", value="SA", max_chars=2)
        address     = st.text_input("Registered Address", value="RRRD2929")
        biz_cat     = st.text_input("Business Category", value="Supply activities")
        invoice_tp  = st.selectbox("Invoice Type Code (TITLE)", ["1100", "0100", "1000", "0000"])

    st.markdown("<hr style='border-color:#2a2f3e;margin:14px 0 10px'>", unsafe_allow_html=True)

    # ── Session Files ──
    st.markdown("### 📂 Session Files")

    if st.session_state.step1_done:
        st.success("🔑 private_key.pem  ✓")
        st.success("📄 csr.pem  ✓")
    if st.session_state.step2_done:
        st.success("🔐 ccsid.json  ✓")
    if st.session_state.step3_done:
        st.success("🏭 pcsid.json  ✓")

    if not any([st.session_state.step1_done, st.session_state.step2_done, st.session_state.step3_done]):
        st.caption("No files generated yet.")

    st.markdown("<hr style='border-color:#2a2f3e;margin:18px 0 12px'>", unsafe_allow_html=True)

    # ── Reset Button ──
    st.markdown('<div class="reset-btn-container">', unsafe_allow_html=True)
    if st.button("🔄 Reset All Steps", use_container_width=True, type="secondary"):
        for k in defaults:
            st.session_state[k] = defaults[k]
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# BUILD CONFIG FROM SIDEBAR
# ═══════════════════════════════════════════════════════════

CONFIG = {
    "common_name":   common_name,
    "country":       country,
    "org_unit":      org_unit,
    "organization":  org_name,
    "serial_number": serial_number,
    "tax_number":    tax_number,
    "invoice_type":  invoice_tp,
    "address":       address,
    "business_cat":  biz_cat,
}


# ═══════════════════════════════════════════════════════════
# MAIN HEADER
# ═══════════════════════════════════════════════════════════

badge_info = ENV_BADGE_STYLES[selected_env]
st.markdown(f"""
<div class="main-header">
    <div style="font-size:2.6rem">🇸🇦</div>
    <div>
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
            <h1 style="font-size:1.7rem;font-weight:700;color:#e8eaf0;margin:0">
                ZATCA E-Invoicing Integration
            </h1>
            <span class="zatca-badge" style="background:{badge_info['bg']};color:{badge_info['color']}">
                {badge_info['label']}
            </span>
        </div>
        <p style="color:#5a6478;margin:0;font-size:0.88rem">
            Fatoora Platform · {badge_info['label'].title()} Environment · UBL 2.1 · Saudi Arabia VAT
        </p>
    </div>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# PIPELINE PROGRESS BAR
# ═══════════════════════════════════════════════════════════

def pipe_class(step_done, step_active):
    if step_done:   return "pipe-step pipe-step-done"
    if step_active: return "pipe-step pipe-step-active"
    return "pipe-step"

s1_active = not st.session_state.step1_done
s2_active = st.session_state.step1_done and not st.session_state.step2_done
s3_active = st.session_state.step2_done and not st.session_state.step3_done

st.markdown(f"""
<div class="pipeline">
    <div class="{pipe_class(st.session_state.step1_done, s1_active)}">
        {"✅" if st.session_state.step1_done else ("🟡" if s1_active else "○")}
        <br>Step 1<br><small>CSR Generation</small>
    </div>
    <div class="{pipe_class(st.session_state.step2_done, s2_active)}">
        {"✅" if st.session_state.step2_done else ("🟡" if s2_active else "○")}
        <br>Step 2<br><small>Compliance CSID</small>
    </div>
    <div class="{pipe_class(st.session_state.step3_done, s3_active)}">
        {"✅" if st.session_state.step3_done else ("🟡" if s3_active else "○")}
        <br>Step 3<br><small>Production CSID</small>
    </div>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# BACKEND FUNCTIONS
# ═══════════════════════════════════════════════════════════

def run_step1():
    logs = []
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
CN = {CONFIG['common_name']}
OU = {CONFIG['org_unit']}
O  = {CONFIG['organization']}
C  = {CONFIG['country']}

[req_ext]
certificateTemplateName = ASN1:PRINTABLESTRING:TSTZATCA-Code-Signing
subjectAltName = dirName:alt_names

[alt_names]
SN = {CONFIG['serial_number']}
UID = {CONFIG['tax_number']}
title = {CONFIG['invoice_type']}
registeredAddress = {CONFIG['address']}
businessCategory = {CONFIG['business_cat']}
"""
    with open("zatca_csr.cnf", "w") as f:
        f.write(config_content)
    logs.append("📝 CSR config file written → zatca_csr.cnf")

    r1 = subprocess.run(
        ["openssl", "ecparam", "-name", "secp256k1", "-genkey", "-noout", "-out", "private_key.pem"],
        capture_output=True, text=True
    )
    if r1.returncode != 0:
        return None, None, None, "\n".join(logs) + f"\n❌ Key generation failed:\n{r1.stderr}", True

    logs.append("🔑 EC private key generated  →  private_key.pem")

    r2 = subprocess.run(
        ["openssl", "req", "-new", "-sha256",
         "-key", "private_key.pem",
         "-config", "zatca_csr.cnf",
         "-out", "csr.pem"],
        capture_output=True, text=True
    )
    if r2.returncode != 0:
        return None, None, None, "\n".join(logs) + f"\n❌ CSR generation failed:\n{r2.stderr}", True

    logs.append("📄 CSR generated  →  csr.pem")

    with open("csr.pem", "r") as f:
        csr_pem = f.read()
    csr_b64 = base64.b64encode(csr_pem.encode("utf-8")).decode("utf-8")

    with open("csr.txt", "w") as f:
        f.write(csr_b64)

    with open("private_key.pem", "r") as f:
        pk_pem = f.read()

    logs.append("📦 CSR base64 encoded  →  csr.txt")
    logs.append(f"\n✅ Success!")
    logs.append(f"   Common Name   : {CONFIG['common_name']}")
    logs.append(f"   Serial Number : {CONFIG['serial_number']}")
    logs.append(f"   Tax Number    : {CONFIG['tax_number']}")

    return pk_pem, csr_b64, csr_pem, "\n".join(logs), False


def run_step2(csr_b64):
    logs = []
    url = f"{env_url}/compliance"
    headers = {
        "accept":          "application/json",
        "accept-language": "en",
        "Accept-Version":  "V2",
        "Content-Type":    "application/json",
        "OTP":             otp,
    }
    body = {"csr": csr_b64}
    logs.append(f"🌐 POST  {url}")
    logs.append(f"   OTP : {otp}")

    try:
        response = requests.post(url, json=body, headers=headers, timeout=30)
    except requests.RequestException as e:
        return None, "\n".join(logs) + f"\n❌ Network error: {e}", True

    logs.append(f"   HTTP Status : {response.status_code}")

    if response.status_code in [200, 201]:
        data = response.json()
        ccsid = {
            "binarySecurityToken": data.get("binarySecurityToken"),
            "secret":              data.get("secret"),
            "requestID":           data.get("requestID"),
        }
        with open("ccsid.json", "w") as f:
            json.dump(ccsid, f, indent=4)
        logs.append(f"\n✅ Compliance CSID received  →  ccsid.json")
        logs.append(f"   requestID : {ccsid['requestID']}")
        logs.append(f"   Token     : {str(ccsid['binarySecurityToken'])[:60]}...")
        return ccsid, "\n".join(logs), False
    else:
        logs.append(f"\n❌ Request failed")
        logs.append(f"   Response : {response.text[:600]}")
        return None, "\n".join(logs), True


def run_step3(ccsid_data):
    logs = []
    token       = ccsid_data["binarySecurityToken"]
    secret      = ccsid_data["secret"]
    credentials = base64.b64encode(f"{token}:{secret}".encode()).decode()
    url         = f"{env_url}/production/csids"
    headers     = {
        "accept":          "application/json",
        "accept-language": "en",
        "Accept-Version":  "V2",
        "Content-Type":    "application/json",
        "Authorization":   f"Basic {credentials}",
    }
    body = {"compliance_request_id": str(ccsid_data["requestID"])}
    logs.append(f"🌐 POST  {url}")
    logs.append(f"   Compliance Request ID : {ccsid_data['requestID']}")

    try:
        response = requests.post(url, json=body, headers=headers, timeout=30)
    except requests.RequestException as e:
        return None, "\n".join(logs) + f"\n❌ Network error: {e}", True

    logs.append(f"   HTTP Status : {response.status_code}")

    if response.status_code in [200, 201]:
        data = response.json()
        pcsid = {
            "binarySecurityToken": data.get("binarySecurityToken"),
            "secret":              data.get("secret"),
            "requestID":           data.get("requestID"),
        }
        with open("pcsid.json", "w") as f:
            json.dump(pcsid, f, indent=4)
        logs.append(f"\n✅ Production CSID received  →  pcsid.json")
        logs.append(f"   requestID : {pcsid['requestID']}")
        logs.append(f"   Token     : {str(pcsid['binarySecurityToken'])[:60]}...")
        return pcsid, "\n".join(logs), False
    else:
        logs.append(f"\n❌ Request failed")
        logs.append(f"   Response : {response.text[:600]}")
        return None, "\n".join(logs), True


# ═══════════════════════════════════════════════════════════
# STEP 1 — Generate Private Key + CSR
# ═══════════════════════════════════════════════════════════

step1_card_cls = (
    "step-card step-card-done"  if st.session_state.step1_done and not st.session_state.step1_error else
    "step-card step-card-error" if st.session_state.step1_error else
    "step-card step-card-active"
)

st.markdown(f'<div class="{step1_card_cls}">', unsafe_allow_html=True)

num_cls1 = "step-number step-number-done" if st.session_state.step1_done else "step-number step-number-active"
badge1 = (
    '<span class="badge badge-success">✓ Complete</span>' if st.session_state.step1_done else
    '<span class="badge badge-error">✗ Error</span>'     if st.session_state.step1_error else
    '<span class="badge badge-running">● Active</span>'
)

st.markdown(f"""
<div class="step-header">
    <div class="{num_cls1}">1</div>
    <div>
        <div class="step-title">Generate Private Key &amp; CSR</div>
        <div class="step-subtitle">Creates EC secp256k1 private key and Certificate Signing Request</div>
    </div>
    <div style="margin-left:auto">{badge1}</div>
</div>
""", unsafe_allow_html=True)

if not st.session_state.step1_done:
    with st.expander("📋 Configuration Preview", expanded=False):
        st.markdown(f"""
<div class="info-grid">
    <div class="info-item"><div class="info-label">Common Name (CN)</div><div class="info-value">{CONFIG['common_name']}</div></div>
    <div class="info-item"><div class="info-label">Serial Number (SN)</div><div class="info-value">{CONFIG['serial_number']}</div></div>
    <div class="info-item"><div class="info-label">Organization (O)</div><div class="info-value">{CONFIG['organization']}</div></div>
    <div class="info-item"><div class="info-label">Org Unit (OU)</div><div class="info-value">{CONFIG['org_unit']}</div></div>
    <div class="info-item"><div class="info-label">Country (C)</div><div class="info-value">{CONFIG['country']}</div></div>
    <div class="info-item"><div class="info-label">Tax Number (UID)</div><div class="info-value">{CONFIG['tax_number']}</div></div>
    <div class="info-item"><div class="info-label">Invoice Type (TITLE)</div><div class="info-value">{CONFIG['invoice_type']}</div></div>
    <div class="info-item"><div class="info-label">Address</div><div class="info-value">{CONFIG['address']}</div></div>
    <div class="info-item"><div class="info-label">Business Category</div><div class="info-value">{CONFIG['business_cat']}</div></div>
</div>
""", unsafe_allow_html=True)

    if st.button("🚀 Generate CSR & Private Key", key="btn_step1", use_container_width=True):
        with st.spinner("Generating EC key and CSR via OpenSSL..."):
            pk, csr_b64, csr_pem, log, err = run_step1()
        st.session_state.step1_log   = log
        st.session_state.step1_error = err
        if not err:
            st.session_state.private_key_pem = pk
            st.session_state.csr_base64      = csr_b64
            st.session_state.csr_pem         = csr_pem
            st.session_state.step1_done      = True
            st.rerun()

if st.session_state.step1_log:
    cls = "result-box result-box-error" if st.session_state.step1_error else "result-box"
    st.markdown(f'<div class="{cls}">{st.session_state.step1_log}</div>', unsafe_allow_html=True)

if st.session_state.step1_done:
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "⬇️ Download private_key.pem",
            data=st.session_state.private_key_pem,
            file_name="private_key.pem",
            mime="text/plain",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            "⬇️ Download csr.pem",
            data=st.session_state.csr_pem,
            file_name="csr.pem",
            mime="text/plain",
            use_container_width=True,
        )

st.markdown('</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# STEP 2 — Submit CSR → Get Compliance CSID
# ═══════════════════════════════════════════════════════════

step2_card_cls = (
    "step-card step-card-done"  if st.session_state.step2_done and not st.session_state.step2_error else
    "step-card step-card-error" if st.session_state.step2_error else
    "step-card step-card-active" if st.session_state.step1_done else
    "step-card"
)

st.markdown(f'<div class="{step2_card_cls}">', unsafe_allow_html=True)

num_cls2 = (
    "step-number step-number-done"   if st.session_state.step2_done else
    "step-number step-number-active" if st.session_state.step1_done else
    "step-number"
)
badge2 = (
    '<span class="badge badge-success">✓ Complete</span>' if st.session_state.step2_done else
    '<span class="badge badge-error">✗ Error</span>'     if st.session_state.step2_error else
    '<span class="badge badge-running">● Ready</span>'   if st.session_state.step1_done else
    '<span class="badge badge-pending">○ Waiting</span>'
)

st.markdown(f"""
<div class="step-header">
    <div class="{num_cls2}">2</div>
    <div>
        <div class="step-title">Submit CSR — Get Compliance CSID</div>
        <div class="step-subtitle">Sends CSR to ZATCA Fatoora API and retrieves the Compliance Certificate Security ID</div>
    </div>
    <div style="margin-left:auto">{badge2}</div>
</div>
""", unsafe_allow_html=True)

if not st.session_state.step1_done:
    st.info("⬆️ Complete Step 1 first to unlock this step.")
elif not st.session_state.step2_done:
    st.caption(f"🌐 Endpoint: `{env_url}/compliance`   |   OTP: `{'•' * len(otp)}`")
    if st.button("📤 Submit CSR to ZATCA", key="btn_step2", use_container_width=True):
        with st.spinner("Submitting CSR to ZATCA Compliance API..."):
            ccsid, log, err = run_step2(st.session_state.csr_base64)
        st.session_state.step2_log   = log
        st.session_state.step2_error = err
        if not err:
            st.session_state.ccsid_data = ccsid
            st.session_state.step2_done = True
            st.rerun()

if st.session_state.step2_log:
    cls = "result-box result-box-error" if st.session_state.step2_error else "result-box"
    st.markdown(f'<div class="{cls}">{st.session_state.step2_log}</div>', unsafe_allow_html=True)

if st.session_state.step2_done and st.session_state.ccsid_data:
    ccsid = st.session_state.ccsid_data
    token_preview = str(ccsid.get("binarySecurityToken", ""))[:50] + "..."
    st.markdown(f"""
<div class="info-grid">
    <div class="info-item"><div class="info-label">Request ID</div><div class="info-value">{ccsid.get('requestID','—')}</div></div>
    <div class="info-item"><div class="info-label">Binary Security Token</div><div class="info-value">{token_preview}</div></div>
    <div class="info-item"><div class="info-label">Secret</div><div class="info-value">{'•' * 12}</div></div>
</div>
""", unsafe_allow_html=True)
    ccsid_json = json.dumps(ccsid, indent=4)
    st.download_button(
        "⬇️ Download ccsid.json",
        data=ccsid_json,
        file_name="ccsid.json",
        mime="application/json",
    )

st.markdown('</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# STEP 3 — Get Production CSID
# ═══════════════════════════════════════════════════════════

step3_card_cls = (
    "step-card step-card-done"  if st.session_state.step3_done and not st.session_state.step3_error else
    "step-card step-card-error" if st.session_state.step3_error else
    "step-card step-card-active" if st.session_state.step2_done else
    "step-card"
)

st.markdown(f'<div class="{step3_card_cls}">', unsafe_allow_html=True)

num_cls3 = (
    "step-number step-number-done"   if st.session_state.step3_done else
    "step-number step-number-active" if st.session_state.step2_done else
    "step-number"
)
badge3 = (
    '<span class="badge badge-success">✓ Complete</span>' if st.session_state.step3_done else
    '<span class="badge badge-error">✗ Error</span>'     if st.session_state.step3_error else
    '<span class="badge badge-running">● Ready</span>'   if st.session_state.step2_done else
    '<span class="badge badge-pending">○ Waiting</span>'
)

st.markdown(f"""
<div class="step-header">
    <div class="{num_cls3}">3</div>
    <div>
        <div class="step-title">Get Production CSID (PCSID)</div>
        <div class="step-subtitle">Exchanges the Compliance CSID for a Production Certificate Security ID</div>
    </div>
    <div style="margin-left:auto">{badge3}</div>
</div>
""", unsafe_allow_html=True)

if not st.session_state.step2_done:
    st.info("⬆️ Complete Step 2 first to unlock this step.")
elif not st.session_state.step3_done:
    st.caption(f"🌐 Endpoint: `{env_url}/production/csids`")
    if st.button("🏭 Request Production CSID", key="btn_step3", use_container_width=True):
        with st.spinner("Requesting Production CSID from ZATCA..."):
            pcsid, log, err = run_step3(st.session_state.ccsid_data)
        st.session_state.step3_log   = log
        st.session_state.step3_error = err
        if not err:
            st.session_state.pcsid_data = pcsid
            st.session_state.step3_done = True
            st.rerun()

if st.session_state.step3_log:
    cls = "result-box result-box-error" if st.session_state.step3_error else "result-box"
    st.markdown(f'<div class="{cls}">{st.session_state.step3_log}</div>', unsafe_allow_html=True)

if st.session_state.step3_done and st.session_state.pcsid_data:
    pcsid = st.session_state.pcsid_data
    token_preview = str(pcsid.get("binarySecurityToken", ""))[:50] + "..."
    st.markdown(f"""
<div class="info-grid">
    <div class="info-item"><div class="info-label">Request ID</div><div class="info-value">{pcsid.get('requestID','—')}</div></div>
    <div class="info-item"><div class="info-label">Binary Security Token</div><div class="info-value">{token_preview}</div></div>
    <div class="info-item"><div class="info-label">Secret</div><div class="info-value">{'•' * 12}</div></div>
</div>
""", unsafe_allow_html=True)
    pcsid_json = json.dumps(pcsid, indent=4)
    st.download_button(
        "⬇️ Download pcsid.json",
        data=pcsid_json,
        file_name="pcsid.json",
        mime="application/json",
    )

st.markdown('</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# COMPLETION SUMMARY
# ═══════════════════════════════════════════════════════════

if st.session_state.step3_done:
    st.markdown(f"""
<div style="
    background: linear-gradient(135deg, #0e2a1a, #132215);
    border: 1px solid #2a5c3f;
    border-radius: 14px;
    padding: 28px 32px;
    margin-top: 12px;
    text-align: center;
">
    <div style="font-size:2.4rem;margin-bottom:10px">🎉</div>
    <div style="font-size:1.3rem;font-weight:700;color:#4ec98a;margin-bottom:6px">
        Integration Complete!
    </div>
    <div style="color:#5a8a6a;font-size:0.9rem">
        All 3 steps completed successfully on <strong>{badge_info['label']}</strong>. Your Production CSID is ready for use.
    </div>
    <div style="display:flex;justify-content:center;gap:24px;margin-top:18px;flex-wrap:wrap">
        <span style="color:#8a94aa;font-size:0.82rem">✅ private_key.pem</span>
        <span style="color:#8a94aa;font-size:0.82rem">✅ csr.pem</span>
        <span style="color:#8a94aa;font-size:0.82rem">✅ ccsid.json</span>
        <span style="color:#8a94aa;font-size:0.82rem">✅ pcsid.json</span>
    </div>
</div>
""", unsafe_allow_html=True)

    # ── Build settings export JSON ──
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    env_name_map = {
        "🧪 Sandbox (Developer Portal)": "sandbox",
        "🔬 Simulation": "simulation",
        "🏭 Production": "production",
    }
    is_prod = "t" if "Production" in selected_env else "f"
    ccsid = st.session_state.ccsid_data or {}
    pcsid = st.session_state.pcsid_data or {}

    settings_export = {
        "company_information": {
            "company_name": CONFIG["organization"],
            "vat_number": CONFIG["tax_number"],
            "commercial_registration_number": "",
            "organization_identifier": CONFIG["tax_number"],
            "city_name": "",
            "street_name": "",
            "building_number": "",
            "postal_code": "",
            "country_code": CONFIG["country"],
        },
        "solution_information": {
            "solution_name": "",
            "model_name": "",
            "serial_number": CONFIG["serial_number"],
            "organizational_unit_name": CONFIG["org_unit"],
            "business_category": CONFIG["business_cat"],
            "invoice_type": CONFIG["invoice_type"],
        },
        "environment": {
            "environment": env_name_map.get(selected_env, "sandbox"),
            "is_production": is_prod,
            "is_active": "t",
        },
        "certificates": {
            "previous_invoice_hash": "MA==",
            "privateKey": base64.b64encode(
                (st.session_state.private_key_pem or "").encode("utf-8")
            ).decode("utf-8"),
            "csr": st.session_state.csr_base64 or "",
            "ccsid_requestID": str(ccsid.get("requestID", "")),
            "ccsid_binarySecurityToken": ccsid.get("binarySecurityToken", ""),
            "ccsid_secret": ccsid.get("secret", ""),
            "pcsid_binarySecurityToken": pcsid.get("binarySecurityToken", ""),
            "pcsid_secret": pcsid.get("secret", ""),
            "pcsid_requestID": str(pcsid.get("requestID", "")),
            "lastICV": 0,
            "zatcaotp": 0,
        },
        "timestamps": {
            "created_at": now_str,
            "updated_at": now_str,
        },
        "export_info": {
            "exported_at": now_str,
            "exported_by": "owner",
        },
    }

    export_filename = f"zatca_settings_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M%S')}.json"
    st.download_button(
        "⬇️ Download Settings JSON",
        data=json.dumps(settings_export, indent=4, ensure_ascii=False),
        file_name=export_filename,
        mime="application/json",
        use_container_width=True,
        key="btn_export_settings",
    )


# ═══════════════════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════════════════

st.markdown(f"""
<div style="margin-top:40px;padding-top:16px;border-top:1px solid #1e2330;
            text-align:center;color:#3a4255;font-size:0.78rem">
    ZATCA E-Invoicing · Fatoora Platform · {badge_info['label'].title()} Environment
    &nbsp;·&nbsp; UBL 2.1 &nbsp;·&nbsp; secp256k1 &nbsp;·&nbsp; SHA-256
</div>
""", unsafe_allow_html=True)