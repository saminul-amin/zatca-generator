"""
ZATCA E-Invoice Signer Module
Handles UBL 2.1 XML invoice generation, XAdES-BES signing, and QR code generation
for ZATCA Phase 2 compliance.
"""

import base64
import hashlib
import json
import os
import uuid as uuid_mod
import xml.etree.ElementTree as StdET
from datetime import date, datetime

from lxml import etree
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_private_key
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils

# Base directory for resource files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESOURCE_DIR = os.path.join(BASE_DIR, "resources")

XSL_FILE = os.path.join(RESOURCE_DIR, "xslfile.xsl")
UBL_TEMPLATE = os.path.join(RESOURCE_DIR, "zatca_ubl.xml")
SIGNATURE_TEMPLATE = os.path.join(RESOURCE_DIR, "zatca_signature.xml")
INVOICE_TEMPLATE = os.path.join(RESOURCE_DIR, "invoice.xml")

NS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
}

INITIAL_PIH = "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="

DOCUMENT_TYPES = [
    {"prefix": "STDSI", "type_code": "388", "label": "Standard Invoice",
     "type_name": "0100000", "instruction_note": ""},
    {"prefix": "STDCN", "type_code": "383", "label": "Standard CreditNote",
     "type_name": "0100000", "instruction_note": "InstructionNotes for Standard CreditNote"},
    {"prefix": "STDDN", "type_code": "381", "label": "Standard DebitNote",
     "type_name": "0100000", "instruction_note": "InstructionNotes for Standard DebitNote"},
    {"prefix": "SIMSI", "type_code": "388", "label": "Simplified Invoice",
     "type_name": "0200000", "instruction_note": ""},
    {"prefix": "SIMCN", "type_code": "383", "label": "Simplified CreditNote",
     "type_name": "0200000", "instruction_note": "InstructionNotes for Simplified CreditNote"},
    {"prefix": "SIMDN", "type_code": "381", "label": "Simplified DebitNote",
     "type_name": "0200000", "instruction_note": "InstructionNotes for Simplified DebitNote"},
]


# ─── Invoice XML Modification ───────────────────────────────────────────────

def modify_invoice_xml(base_document, inv_id, type_name, type_code, icv, pih, instruction_note):
    """Clone the base invoice template and modify it for a specific invoice type."""
    new_doc = etree.ElementTree(
        etree.fromstring(etree.tostring(base_document.getroot(), pretty_print=True))
    )
    guid = str(uuid_mod.uuid4()).upper()

    # Set invoice ID
    id_node = new_doc.find(".//cbc:ID", namespaces=NS)
    if id_node is not None:
        id_node.text = inv_id

    # Set UUID
    uuid_node = new_doc.find(".//cbc:UUID", namespaces=NS)
    if uuid_node is not None:
        uuid_node.text = guid

    # Set InvoiceTypeCode and name attribute
    itc_node = new_doc.find(".//cbc:InvoiceTypeCode", namespaces=NS)
    if itc_node is not None:
        itc_node.text = type_code
        itc_node.set("name", type_name)

    # Update dates to today
    today = date.today().strftime("%Y-%m-%d")
    issue_date = new_doc.find(".//cbc:IssueDate", namespaces=NS)
    if issue_date is not None:
        issue_date.text = today
    delivery_date = new_doc.find(".//cac:Delivery/cbc:ActualDeliveryDate", namespaces=NS)
    if delivery_date is not None:
        delivery_date.text = today

    # Update ICV (Invoice Counter Value)
    icv_node = new_doc.find(
        ".//cac:AdditionalDocumentReference[cbc:ID='ICV']/cbc:UUID", namespaces=NS
    )
    if icv_node is not None:
        icv_node.text = str(icv)

    # Update PIH (Previous Invoice Hash)
    pih_node = new_doc.find(
        ".//cac:AdditionalDocumentReference[cbc:ID='PIH']/cac:Attachment/cbc:EmbeddedDocumentBinaryObject",
        namespaces=NS,
    )
    if pih_node is not None:
        pih_node.text = pih

    # For credit/debit notes: add InstructionNote; for invoices: remove BillingReference
    if instruction_note:
        pm_node = new_doc.find(".//cac:PaymentMeans", namespaces=NS)
        if pm_node is not None:
            note_el = etree.Element(
                "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}InstructionNote"
            )
            note_el.text = instruction_note
            pm_node.append(note_el)
    else:
        billing_refs = new_doc.findall(".//cac:BillingReference", namespaces=NS)
        for br in billing_refs:
            parent = new_doc.find(".//cac:BillingReference/..", namespaces=NS)
            if parent is not None:
                parent.remove(br)

    return new_doc


# ─── XML Signing Engine ─────────────────────────────────────────────────────

def pretty_print_xml(xml):
    xml_string = etree.tostring(xml, pretty_print=True, encoding="UTF-8").decode("UTF-8")
    return etree.fromstring(xml_string)


def extract_uuid(xml):
    nodes = xml.xpath("//cbc:UUID", namespaces=NS)
    if not nodes:
        raise Exception("UUID not found in the XML document.")
    return nodes[0].text


def is_simplified(xml):
    nodes = xml.xpath("//cbc:InvoiceTypeCode", namespaces=NS)
    if nodes:
        name_attr = nodes[0].get("name", "")
        return name_attr.startswith("02")
    return False


def transform_xml(xml):
    """Apply XSLT to strip UBLExtensions, QR, and Signature elements."""
    xsl = etree.parse(XSL_FILE)
    transform = etree.XSLT(xsl)
    result = transform(xml)
    if result is None:
        raise Exception("XSLT transformation failed.")
    return result


def canonicalize_xml(transformed_xml):
    return etree.tostring(transformed_xml, method="c14n").decode("utf-8")


def generate_base64_hash(canonical_xml):
    hash_bytes = hashlib.sha256(canonical_xml.encode("utf-8")).digest()
    return base64.b64encode(hash_bytes).decode()


def encode_invoice(xml_declaration, canonical_xml):
    updated = f"{xml_declaration}\n{canonical_xml}"
    return base64.b64encode(updated.encode("utf-8")).decode("utf-8")


def wrap_certificate(cert_content):
    lines = [cert_content[i : i + 64] for i in range(0, len(cert_content), 64)]
    return "-----BEGIN CERTIFICATE-----\n" + "\n".join(lines) + "\n-----END CERTIFICATE-----"


def generate_public_key_hashing(cert_content):
    hash_bytes = hashlib.sha256(cert_content.encode("utf-8")).digest()
    return base64.b64encode(hash_bytes.hex().encode("utf-8")).decode("utf-8")


def get_issuer_name(certificate):
    issuer = certificate.issuer
    issuer_dict = {}
    for attr in issuer:
        key = attr.oid._name
        if key in issuer_dict:
            if isinstance(issuer_dict[key], list):
                issuer_dict[key].append(attr.value)
            else:
                issuer_dict[key] = [issuer_dict[key], attr.value]
        else:
            issuer_dict[key] = attr.value

    parts = []
    if "commonName" in issuer_dict:
        parts.append(f"CN={issuer_dict['commonName']}")
    if "domainComponent" in issuer_dict:
        dc_list = issuer_dict["domainComponent"]
        if isinstance(dc_list, list):
            dc_list.reverse()
            for dc in dc_list:
                if dc:
                    parts.append(f"DC={dc}")
    return ", ".join(parts)


def get_signed_properties_hash(signing_time, digest_value, issuer_name, serial_number):
    xml_string = (
        '<xades:SignedProperties xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" Id="xadesSignedProperties">\n'
        "                                    <xades:SignedSignatureProperties>\n"
        "                                        <xades:SigningTime>{}</xades:SigningTime>\n".format(signing_time)
        + "                                        <xades:SigningCertificate>\n"
        "                                            <xades:Cert>\n"
        "                                                <xades:CertDigest>\n"
        '                                                    <ds:DigestMethod xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>\n'
        '                                                    <ds:DigestValue xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{}</ds:DigestValue>\n'.format(
            digest_value
        )
        + "                                                </xades:CertDigest>\n"
        "                                                <xades:IssuerSerial>\n"
        '                                                    <ds:X509IssuerName xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{}</ds:X509IssuerName>\n'.format(
            issuer_name
        )
        + '                                                    <ds:X509SerialNumber xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{}</ds:X509SerialNumber>\n'.format(
            serial_number
        )
        + "                                                </xades:IssuerSerial>\n"
        "                                            </xades:Cert>\n"
        "                                        </xades:SigningCertificate>\n"
        "                                    </xades:SignedSignatureProperties>\n"
        "                                </xades:SignedProperties>"
    )
    xml_string = xml_string.replace("\r\n", "\n").strip()
    hash_bytes = hashlib.sha256(xml_string.encode("utf-8")).digest()
    return base64.b64encode(hash_bytes.hex().encode("utf-8")).decode("utf-8")


def get_digital_signature(xml_hashing, private_key_content):
    hash_bytes = base64.b64decode(xml_hashing)
    pk = private_key_content.strip()
    if "-----BEGIN" in pk:
        pem_bytes = pk.encode("utf-8")
    else:
        pk = pk.replace("\n", "").replace("\t", "")
        pem_bytes = f"-----BEGIN EC PRIVATE KEY-----\n{pk}\n-----END EC PRIVATE KEY-----".encode("utf-8")
    private_key = load_pem_private_key(pem_bytes, password=None, backend=default_backend())
    signature = private_key.sign(hash_bytes, ec.ECDSA(asym_utils.Prehashed(hashes.SHA256())))
    return base64.b64encode(signature).decode()


def get_public_key_and_signature(certificate_base64):
    """Extract DER public key and certificate signature from an X.509 certificate."""
    pem = wrap_certificate(certificate_base64)
    cert = x509.load_pem_x509_certificate(pem.encode(), default_backend())

    # Public key in DER SubjectPublicKeyInfo format
    pub_key_der = cert.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)

    # Certificate signature (DER encoded)
    cert_signature = cert.signature

    return {
        "public_key": pub_key_der,
        "signature": cert_signature,
    }


# ─── QR Code Generation (TLV) ───────────────────────────────────────────────

def _write_tlv(tag, value):
    if value is None:
        return b""
    if isinstance(value, str):
        value = value.encode("utf-8")
    length = len(value)
    return bytes([tag]) + bytes([length]) + bytes(value)


def _get_invoice_details(canonical_xml):
    """Extract TLV fields 1-5 from canonical XML using stdlib ElementTree."""
    root = StdET.fromstring(canonical_xml)

    ns_cac = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
    ns_cbc = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

    # Tag 1: Seller Name
    seller_name = ""
    reg_name = root.find(f".//{{{ns_cac}}}AccountingSupplierParty//{{{ns_cbc}}}RegistrationName")
    if reg_name is not None and reg_name.text:
        seller_name = reg_name.text

    # Tag 2: VAT Number
    company_id = ""
    cid = root.find(f".//{{{ns_cac}}}AccountingSupplierParty//{{{ns_cbc}}}CompanyID")
    if cid is not None and cid.text:
        company_id = cid.text

    # Tag 3: Timestamp
    issue_date = ""
    issue_time = ""
    d = root.find(f".//{{{ns_cbc}}}IssueDate")
    if d is not None and d.text:
        issue_date = d.text
    t = root.find(f".//{{{ns_cbc}}}IssueTime")
    if t is not None and t.text:
        issue_time = t.text
    timestamp = f"{issue_date}T{issue_time}"

    # Tag 4: Invoice Total (PayableAmount)
    payable = ""
    pa = root.find(f".//{{{ns_cac}}}LegalMonetaryTotal/{{{ns_cbc}}}PayableAmount")
    if pa is not None and pa.text:
        payable = pa.text

    # Tag 5: VAT Total (first TaxTotal/TaxAmount)
    tax_amount = ""
    ta = root.find(f".//{{{ns_cac}}}TaxTotal/{{{ns_cbc}}}TaxAmount")
    if ta is not None and ta.text:
        tax_amount = ta.text

    return [seller_name, company_id, timestamp, payable, tax_amount]


def generate_qr_code(canonical_xml, invoice_hash, signature_value, ecdsa_result):
    """Generate base64-encoded TLV QR code data."""
    details = _get_invoice_details(canonical_xml)

    data = b""
    # Tags 1-5: invoice details
    for i, val in enumerate(details, start=1):
        data += _write_tlv(i, val)

    # Tag 6: Invoice Hash
    data += _write_tlv(6, invoice_hash)

    # Tag 7: ECDSA Signature Value
    data += _write_tlv(7, signature_value)

    # Tag 8: Public Key (DER)
    data += _write_tlv(8, ecdsa_result["public_key"])

    # Tag 9: Certificate Signature (DER)
    data += _write_tlv(9, ecdsa_result["signature"])

    return base64.b64encode(data).decode()


# ─── Main Signing Orchestration ─────────────────────────────────────────────

def sign_invoice(xml_doc, x509_cert_content, private_key_content):
    """
    Sign a UBL 2.1 invoice XML document.

    For Standard invoices: returns hash + base64 invoice (no XAdES signing).
    For Simplified invoices: performs full XAdES-BES signing + QR code.

    Returns: dict with {invoiceHash, uuid, invoice}
    """
    xml = pretty_print_xml(xml_doc)

    xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>'
    inv_uuid = extract_uuid(xml)
    simplified = is_simplified(xml)

    # XSLT transform -> strip UBLExtensions, QR, Signature
    transformed = transform_xml(xml)

    # Canonicalize
    canonical = canonicalize_xml(transformed)

    # Hash of the clean (unsigned) invoice
    base64_hash = generate_base64_hash(canonical)

    # For Standard invoices: no signing needed
    if not simplified:
        base64_invoice = encode_invoice(xml_declaration, canonical)
        return {"invoiceHash": base64_hash, "uuid": inv_uuid, "invoice": base64_invoice}

    # For Simplified invoices: full XAdES-BES signing
    sig_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # Certificate processing
    pub_key_hash = generate_public_key_hashing(x509_cert_content)
    pem_cert = wrap_certificate(x509_cert_content)
    certificate = x509.load_pem_x509_certificate(pem_cert.encode(), default_backend())
    issuer_name = get_issuer_name(certificate)
    serial_number = certificate.serial_number

    # SignedProperties hash
    signed_props_hash = get_signed_properties_hash(
        sig_timestamp, pub_key_hash, issuer_name, serial_number
    )

    # ECDSA digital signature of the invoice hash
    sig_value = get_digital_signature(base64_hash, private_key_content)

    # Public key + cert signature for QR
    ecdsa_result = get_public_key_and_signature(x509_cert_content)

    # Populate UBL signature template
    with open(UBL_TEMPLATE, "r") as f:
        ubl_content = f.read().strip()
    ubl_content = ubl_content.replace("INVOICE_HASH", base64_hash)
    ubl_content = ubl_content.replace("SIGNED_PROPERTIES", signed_props_hash)
    ubl_content = ubl_content.replace("SIGNATURE_VALUE", sig_value)
    ubl_content = ubl_content.replace("CERTIFICATE_CONTENT", x509_cert_content)
    ubl_content = ubl_content.replace("SIGNATURE_TIMESTAMP", sig_timestamp)
    ubl_content = ubl_content.replace("PUBLICKEY_HASHING", pub_key_hash)
    ubl_content = ubl_content.replace("ISSUER_NAME", issuer_name)
    ubl_content = ubl_content.replace("SERIAL_NUMBER", str(serial_number))

    # Insert UBL Extensions after root opening tag
    insert_pos = canonical.find(">") + 1
    updated_xml = canonical[:insert_pos] + ubl_content + canonical[insert_pos:]

    # Generate QR code
    qr_code = generate_qr_code(canonical, base64_hash, sig_value, ecdsa_result)

    # Insert QR + Signature reference before <cac:AccountingSupplierParty>
    # Compact to one line: whitespace between the QR reference and cac:Signature
    # would survive the XSLT strip and change the invoice hash.
    with open(SIGNATURE_TEMPLATE, "r") as f:
        sig_content = "".join(line.strip() for line in f.read().splitlines())
    sig_content = sig_content.replace("BASE64_QRCODE", qr_code)

    supplier_pos = updated_xml.find("<cac:AccountingSupplierParty>")
    if supplier_pos == -1:
        raise Exception("<cac:AccountingSupplierParty> tag not found in XML.")
    updated_xml = updated_xml[:supplier_pos] + sig_content + updated_xml[supplier_pos:]

    # Build the final signed XML string
    signed_xml_str = xml_declaration + "\n" + updated_xml

    # Re-compute hash from the COMPLETE signed XML the same way ZATCA would:
    # parse → XSLT strip → C14N → SHA-256. It must equal the hash already
    # embedded in the signature and QR code, or ZATCA rejects the invoice.
    signed_doc = etree.fromstring(updated_xml.encode("utf-8"))
    re_transformed = transform_xml(signed_doc)
    re_canonical = canonicalize_xml(re_transformed)
    final_hash = generate_base64_hash(re_canonical)
    if final_hash != base64_hash:
        raise Exception("Signed invoice hash does not match the hash in its signature and QR code.")

    # Encode the full signed invoice
    base64_invoice = base64.b64encode(signed_xml_str.encode("utf-8")).decode("utf-8")

    return {"invoiceHash": final_hash, "uuid": inv_uuid, "invoice": base64_invoice}


# ─── Auto-Compliance: Generate & Sign All 6 Invoice Types ───────────────────

def document_types_for(invoice_type_code):
    """
    Pick the document types ZATCA expects for the CSR's invoice type code
    (TITLE): first digit = standard (B2B), second digit = simplified (B2C).
    """
    wants_standard = invoice_type_code[0] == "1"
    wants_simplified = invoice_type_code[1] == "1"
    return [
        d for d in DOCUMENT_TYPES
        if (wants_standard and d["type_name"].startswith("01"))
        or (wants_simplified and d["type_name"].startswith("02"))
    ]


def _set_seller(base_doc, seller_name, seller_vat):
    supplier = ".//cac:AccountingSupplierParty/cac:Party"
    if seller_vat:
        node = base_doc.find(f"{supplier}/cac:PartyTaxScheme/cbc:CompanyID", namespaces=NS)
        if node is not None:
            node.text = seller_vat
    if seller_name:
        node = base_doc.find(f"{supplier}/cac:PartyLegalEntity/cbc:RegistrationName", namespaces=NS)
        if node is not None:
            node.text = seller_name


def generate_all_compliance_invoices(x509_cert_content, private_key_content,
                                     seller_name=None, seller_vat=None, invoice_type_code="1100"):
    """
    Generate, sign, and prepare the compliance invoices required for the
    given invoice type code (all 6 for "1100", 3 for "1000" or "0100").

    Returns a list of dicts, each with:
        {prefix, label, type_name, invoiceHash, uuid, invoice}
    """
    parser = etree.XMLParser(remove_blank_text=False)
    base_doc = etree.parse(INVOICE_TEMPLATE, parser)
    _set_seller(base_doc, seller_name, seller_vat)

    results = []
    icv = 0
    pih = INITIAL_PIH

    for doc_type in document_types_for(invoice_type_code):
        icv += 1
        new_doc = modify_invoice_xml(
            base_doc,
            f"{doc_type['prefix']}-0001",
            doc_type["type_name"],
            doc_type["type_code"],
            icv,
            pih,
            doc_type["instruction_note"],
        )

        payload = sign_invoice(new_doc, x509_cert_content, private_key_content)

        # Current invoice's hash becomes the PIH for the next
        pih = payload["invoiceHash"]

        results.append(
            {
                "prefix": doc_type["prefix"],
                "label": doc_type["label"],
                "type_name": doc_type["type_name"],
                "invoiceHash": payload["invoiceHash"],
                "uuid": payload["uuid"],
                "invoice": payload["invoice"],
            }
        )

    return results
