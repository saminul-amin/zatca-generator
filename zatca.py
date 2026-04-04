import uuid
import json
import base64
import hashlib
import requests
import subprocess
from datetime import datetime, timezone
from lxml import etree

# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════

TAX_NUMBER = "399999999900003"

CONFIG = {
    "common_name":   f"TST-886431145-{TAX_NUMBER}",
    "country":       "SA",
    "org_unit":      "Riyadh Branch",
    "organization":  "Maximum Speed Tech Supply LTD",
    "serial_number": f"1-TST|2-TST|3-{uuid.uuid4()}",
    "tax_number":    TAX_NUMBER,
    "invoice_type":  "1100",
    "address":       "RRRD2929",
    "business_cat":  "Supply activities",
}

SANDBOX_BASE_URL = "https://gw-fatoora.zatca.gov.sa/e-invoicing/developer-portal"

# XML Namespaces
NS = {
    "inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
}


# ═══════════════════════════════════════════════════════════
# STEP 1 — Generate Private Key + CSR
# ═══════════════════════════════════════════════════════════

def step1_generate_csr():
    print("\n" + "═"*60)
    print("  STEP 1 — Generating Private Key and CSR")
    print("═"*60)

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

    result = subprocess.run(
        ["openssl", "ecparam", "-name", "secp256k1", "-genkey", "-noout", "-out", "private_key.pem"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("❌ Failed to generate private key:", result.stderr)
        return None, None

    result = subprocess.run(
        ["openssl", "req", "-new", "-sha256",
         "-key", "private_key.pem",
         "-config", "zatca_csr.cnf",
         "-out", "csr.pem"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("❌ Failed to generate CSR:", result.stderr)
        return None, None

    with open("csr.pem", "r") as f:
        csr_pem = f.read()

    csr_base64 = base64.b64encode(csr_pem.encode("utf-8")).decode("utf-8")

    with open("csr.txt", "w") as f:
        f.write(csr_base64)

    print("✅ private_key.pem saved")
    print("✅ csr.pem saved")
    print("✅ csr.txt saved")
    print(f"   Common Name   : {CONFIG['common_name']}")
    print(f"   Serial Number : {CONFIG['serial_number']}")
    print(f"   Tax Number    : {CONFIG['tax_number']}")

    with open("private_key.pem", "r") as f:
        private_key_pem = f.read()

    return private_key_pem, csr_base64


# ═══════════════════════════════════════════════════════════
# STEP 2 — Submit CSR → Get Compliance CSID
# ═══════════════════════════════════════════════════════════

def step2_get_compliance_csid(csr_base64):
    print("\n" + "═"*60)
    print("  STEP 2 — Submitting CSR → Getting Compliance CSID")
    print("═"*60)

    OTP = "123345"
    url = f"{SANDBOX_BASE_URL}/compliance"
    headers = {
        "accept":          "application/json",
        "accept-language": "en",
        "Accept-Version":  "V2",
        "Content-Type":    "application/json",
        "OTP":             OTP
    }
    body = {"csr": csr_base64}

    print(f"   URL  : {url}")
    print(f"   OTP  : {OTP}")

    response = requests.post(url, json=body, headers=headers)
    print(f"   HTTP : {response.status_code}")

    if response.status_code in [200, 201]:
        data = response.json()
        ccsid_data = {
            "binarySecurityToken": data.get("binarySecurityToken"),
            "secret":              data.get("secret"),
            "requestID":           data.get("requestID")
        }
        with open("ccsid.json", "w") as f:
            json.dump(ccsid_data, f, indent=4)

        print("✅ Compliance CSID received → saved to ccsid.json")
        print(f"   requestID : {ccsid_data['requestID']}")
        print(f"   Token     : {str(ccsid_data['binarySecurityToken'])[:60]}...")
        return ccsid_data
    else:
        print("❌ FAILED")
        print(f"   Response : {response.text}")
        return None


# ═══════════════════════════════════════════════════════════
# INVOICE HASHING — The correct ZATCA way
# ═══════════════════════════════════════════════════════════

def canonicalize_xml(xml_string: str) -> bytes:
    """
    Canonicalize XML using C14N (Canonical XML 1.1).
    ZATCA requires C14N before hashing.
    """
    root = etree.fromstring(xml_string.encode("utf-8"))

    # Remove UBLExtensions (signature placeholder) before hashing
    # ZATCA hashes the invoice WITHOUT the signature block
    for ext in root.findall(".//ext:UBLExtensions", NS):
        ext.getparent().remove(ext)

    # Remove Signature element if present
    for sig in root.findall(".//cac:Signature", NS):
        sig.getparent().remove(sig)

    # Remove QR code reference if present
    for ref in root.findall(".//cac:AdditionalDocumentReference", NS):
        id_elem = ref.find("cbc:ID", NS)
        if id_elem is not None and id_elem.text == "QR":
            ref.getparent().remove(ref)

    # Canonicalize using C14N
    output = etree.tostring(root, method="c14n", exclusive=False, with_comments=False)
    return output


def hash_invoice(xml_string: str) -> str:
    """
    Hash the invoice XML the ZATCA way:
    1. Remove UBLExtensions, Signature, QR tags
    2. Canonicalize (C14N)
    3. SHA-256 hash
    4. Base64 encode
    """
    canonical = canonicalize_xml(xml_string)
    sha256_hash = hashlib.sha256(canonical).digest()
    return base64.b64encode(sha256_hash).decode("utf-8")


# ═══════════════════════════════════════════════════════════
# BUILD SAMPLE INVOICE
# ═══════════════════════════════════════════════════════════

def build_sample_invoice(invoice_type="standard", icv=1):
    """
    Build a ZATCA-compliant UBL 2.1 XML invoice.
    icv = Invoice Counter Value (sequential number)
    """
    invoice_uuid = str(uuid.uuid4())
    now          = datetime.now(timezone.utc)
    issue_date   = now.strftime("%Y-%m-%d")
    issue_time   = now.strftime("%H:%M:%S")

    type_map = {
        "standard": ("388", "0100000"),
        "credit":   ("381", "0100000"),
        "debit":    ("383", "0100000"),
    }
    type_code, subtype = type_map.get(invoice_type, ("388", "0100000"))

    # PIH = Previous Invoice Hash
    # For the very first invoice, use this fixed value (ZATCA spec)
    pih = "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZlNWU2Ng=="

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
    xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
    xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
    xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2">
    <ext:UBLExtensions>
        <ext:UBLExtension>
            <ext:ExtensionURI>urn:oasis:names:specification:ubl:dsig:enveloped:xades</ext:ExtensionURI>
            <ext:ExtensionContent/>
        </ext:UBLExtension>
    </ext:UBLExtensions>
    <cbc:ProfileID>reporting:1.0</cbc:ProfileID>
    <cbc:ID>SME00010</cbc:ID>
    <cbc:UUID>{invoice_uuid}</cbc:UUID>
    <cbc:IssueDate>{issue_date}</cbc:IssueDate>
    <cbc:IssueTime>{issue_time}</cbc:IssueTime>
    <cbc:InvoiceTypeCode name="{subtype}">{type_code}</cbc:InvoiceTypeCode>
    <cbc:DocumentCurrencyCode>SAR</cbc:DocumentCurrencyCode>
    <cbc:TaxCurrencyCode>SAR</cbc:TaxCurrencyCode>
    <cac:AdditionalDocumentReference>
        <cbc:ID>ICV</cbc:ID>
        <cbc:UUID>{icv}</cbc:UUID>
    </cac:AdditionalDocumentReference>
    <cac:AdditionalDocumentReference>
        <cbc:ID>PIH</cbc:ID>
        <cac:Attachment>
            <cbc:EmbeddedDocumentBinaryObject mimeCode="text/plain">{pih}</cbc:EmbeddedDocumentBinaryObject>
        </cac:Attachment>
    </cac:AdditionalDocumentReference>
    <cac:AccountingSupplierParty>
        <cac:Party>
            <cac:PartyIdentification>
                <cbc:ID schemeID="CRN">{CONFIG['tax_number']}</cbc:ID>
            </cac:PartyIdentification>
            <cac:PostalAddress>
                <cbc:StreetName>Main Street</cbc:StreetName>
                <cbc:BuildingNumber>1234</cbc:BuildingNumber>
                <cbc:CitySubdivisionName>Al-Murabbaa</cbc:CitySubdivisionName>
                <cbc:CityName>Riyadh</cbc:CityName>
                <cbc:PostalZone>23333</cbc:PostalZone>
                <cac:Country>
                    <cbc:IdentificationCode>SA</cbc:IdentificationCode>
                </cac:Country>
            </cac:PostalAddress>
            <cac:PartyTaxScheme>
                <cbc:CompanyID>{CONFIG['tax_number']}</cbc:CompanyID>
                <cac:TaxScheme>
                    <cbc:ID>VAT</cbc:ID>
                </cac:TaxScheme>
            </cac:PartyTaxScheme>
            <cac:PartyLegalEntity>
                <cbc:RegistrationName>{CONFIG['organization']}</cbc:RegistrationName>
            </cac:PartyLegalEntity>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:AccountingCustomerParty>
        <cac:Party>
            <cac:PostalAddress>
                <cbc:StreetName>Customer Street</cbc:StreetName>
                <cbc:BuildingNumber>1111</cbc:BuildingNumber>
                <cbc:CitySubdivisionName>Al-Murooj</cbc:CitySubdivisionName>
                <cbc:CityName>Riyadh</cbc:CityName>
                <cbc:PostalZone>12222</cbc:PostalZone>
                <cac:Country>
                    <cbc:IdentificationCode>SA</cbc:IdentificationCode>
                </cac:Country>
            </cac:PostalAddress>
            <cac:PartyTaxScheme>
                <cbc:CompanyID>399999999800003</cbc:CompanyID>
                <cac:TaxScheme>
                    <cbc:ID>VAT</cbc:ID>
                </cac:TaxScheme>
            </cac:PartyTaxScheme>
            <cac:PartyLegalEntity>
                <cbc:RegistrationName>Test Customer</cbc:RegistrationName>
            </cac:PartyLegalEntity>
        </cac:Party>
    </cac:AccountingCustomerParty>
    <cac:Delivery>
        <cbc:ActualDeliveryDate>{issue_date}</cbc:ActualDeliveryDate>
    </cac:Delivery>
    <cac:PaymentMeans>
        <cbc:PaymentMeansCode>10</cbc:PaymentMeansCode>
    </cac:PaymentMeans>
    <cac:TaxTotal>
        <cbc:TaxAmount currencyID="SAR">15.00</cbc:TaxAmount>
    </cac:TaxTotal>
    <cac:TaxTotal>
        <cbc:TaxAmount currencyID="SAR">15.00</cbc:TaxAmount>
        <cac:TaxSubtotal>
            <cbc:TaxableAmount currencyID="SAR">100.00</cbc:TaxableAmount>
            <cbc:TaxAmount currencyID="SAR">15.00</cbc:TaxAmount>
            <cac:TaxCategory>
                <cbc:ID schemeAgencyID="6" schemeID="UN/ECE 5305">S</cbc:ID>
                <cbc:Percent>15.00</cbc:Percent>
                <cac:TaxScheme>
                    <cbc:ID schemeAgencyID="6" schemeID="UN/ECE 5153">VAT</cbc:ID>
                </cac:TaxScheme>
            </cac:TaxCategory>
        </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="SAR">100.00</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="SAR">100.00</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="SAR">115.00</cbc:TaxInclusiveAmount>
        <cbc:AllowanceTotalAmount currencyID="SAR">0.00</cbc:AllowanceTotalAmount>
        <cbc:PrepaidAmount currencyID="SAR">0.00</cbc:PrepaidAmount>
        <cbc:PayableAmount currencyID="SAR">115.00</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="PCE">1.000000</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="SAR">100.00</cbc:LineExtensionAmount>
        <cac:TaxTotal>
            <cbc:TaxAmount currencyID="SAR">15.00</cbc:TaxAmount>
            <cbc:RoundingAmount currencyID="SAR">115.00</cbc:RoundingAmount>
        </cac:TaxTotal>
        <cac:Item>
            <cbc:Name>Test Item</cbc:Name>
            <cac:ClassifiedTaxCategory>
                <cbc:ID>S</cbc:ID>
                <cbc:Percent>15.00</cbc:Percent>
                <cac:TaxScheme>
                    <cbc:ID>VAT</cbc:ID>
                </cac:TaxScheme>
            </cac:ClassifiedTaxCategory>
        </cac:Item>
        <cac:Price>
            <cbc:PriceAmount currencyID="SAR">100.00</cbc:PriceAmount>
            <cac:AllowanceCharge>
                <cbc:ChargeIndicator>true</cbc:ChargeIndicator>
                <cbc:AllowanceChargeReason>discount</cbc:AllowanceChargeReason>
                <cbc:Amount currencyID="SAR">0.00</cbc:Amount>
            </cac:AllowanceCharge>
        </cac:Price>
    </cac:InvoiceLine>
</Invoice>"""

    # Compute hash the ZATCA way
    invoice_hash = hash_invoice(xml)
    invoice_b64  = base64.b64encode(xml.encode("utf-8")).decode("utf-8")

    return invoice_uuid, invoice_hash, invoice_b64


# ═══════════════════════════════════════════════════════════
# STEP 3 — Compliance Check with correct hashing
# ═══════════════════════════════════════════════════════════

def step3_compliance_check(ccsid_data):
    print("\n" + "═"*60)
    print("  STEP 3 — Compliance Check (Sample Invoices)")
    print("═"*60)

    token       = ccsid_data["binarySecurityToken"]
    secret      = ccsid_data["secret"]
    credentials = base64.b64encode(f"{token}:{secret}".encode()).decode()
    url         = f"{SANDBOX_BASE_URL}/compliance/invoices"
    headers     = {
        "accept":          "application/json",
        "accept-language": "en",
        "Accept-Version":  "V2",
        "Content-Type":    "application/json",
        "Authorization":   f"Basic {credentials}"
    }

    invoice_types = ["standard", "credit", "debit"]
    for i, inv_type in enumerate(invoice_types, start=1):
        inv_uuid, inv_hash, inv_b64 = build_sample_invoice(inv_type, icv=i)
        body = {
            "invoiceHash": inv_hash,
            "uuid":        inv_uuid,
            "invoice":     inv_b64
        }
        response = requests.post(url, json=body, headers=headers)
        ok   = response.status_code in [200, 202]
        icon = "✅" if ok else "❌"
        print(f"   {icon} {inv_type.upper()} invoice → HTTP {response.status_code}")

        if ok:
            try:
                result = response.json()
                status = result.get("validationResults", {}).get("status", "")
                print(f"      Validation : {status}")
            except:
                pass
        else:
            print(f"      Error : {response.text[:400]}")


# ═══════════════════════════════════════════════════════════
# STEP 4 — Get Production CSID
# ═══════════════════════════════════════════════════════════

def step4_get_production_csid(ccsid_data):
    print("\n" + "═"*60)
    print("  STEP 4 — Getting Production CSID (PCSID)")
    print("═"*60)

    token       = ccsid_data["binarySecurityToken"]
    secret      = ccsid_data["secret"]
    credentials = base64.b64encode(f"{token}:{secret}".encode()).decode()
    url         = f"{SANDBOX_BASE_URL}/production/csids"
    headers     = {
        "accept":          "application/json",
        "accept-language": "en",
        "Accept-Version":  "V2",
        "Content-Type":    "application/json",
        "Authorization":   f"Basic {credentials}"
    }
    body = {"compliance_request_id": str(ccsid_data["requestID"])}

    response = requests.post(url, json=body, headers=headers)
    print(f"   HTTP : {response.status_code}")

    if response.status_code in [200, 201]:
        data = response.json()
        pcsid_data = {
            "binarySecurityToken": data.get("binarySecurityToken"),
            "secret":              data.get("secret"),
            "requestID":           data.get("requestID")
        }
        with open("pcsid.json", "w") as f:
            json.dump(pcsid_data, f, indent=4)
        print("✅ Production CSID received → saved to pcsid.json")
        print(f"   Token : {str(pcsid_data['binarySecurityToken'])[:60]}...")
        return pcsid_data
    else:
        print("❌ FAILED")
        print(f"   Response : {response.text}")
        return None


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n🚀 ZATCA Sandbox — Full Integration Flow")

    private_key_pem, csr_base64 = step1_generate_csr()
    if not csr_base64:
        print("\n🛑 Stopped at Step 1.")
        exit(1)

    ccsid_data = step2_get_compliance_csid(csr_base64)
    if not ccsid_data:
        print("\n🛑 Stopped at Step 2.")
        exit(1)

    step3_compliance_check(ccsid_data)

    pcsid_data = step4_get_production_csid(ccsid_data)

    print("\n" + "═"*60)
    print("  FILES SAVED")
    print("═"*60)
    print("  private_key.pem  → Keep secret, never share!")
    print("  csr.pem          → CSR in PEM format")
    print("  csr.txt          → CSR in base64")
    print("  ccsid.json       → Compliance CSID (temporary)")
    print("  pcsid.json       → Production CSID ⭐")
    print("\n✅ All done!")