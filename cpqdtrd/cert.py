# -*- coding: utf-8 -*-
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import ipaddress
from datetime import datetime, timedelta, timezone
import re


def create_self_signed_cert(hostname, cert_path, pkey_path):
    """Generate a certificate and private key, and returns the public key as str."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Sao Paulo"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Campinas"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, hostname),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, hostname),
        ]
    )

    if re.compile(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}").match(hostname):
        subject_alt_name = x509.IPAddress(ipaddress.ip_address(hostname))
    else:
        subject_alt_name = x509.DNSName(hostname)

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(1000)
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName([subject_alt_name]),
            critical=False,
        )
        .sign(private_key=key, algorithm=hashes.SHA512())
    )

    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(pkey_path, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    return
