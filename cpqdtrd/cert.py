# -*- coding: utf-8 -*-
from OpenSSL import crypto
import re


def create_self_signed_cert(hostname, cert_path, pkey_path):
    """Generate a certificate and private key, and returns the public key as str."""
    # create a key pair
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 2048)

    # create a self-signed cert
    cert = crypto.X509()
    cert.get_subject().C = "BR"
    cert.get_subject().ST = "Sao Paulo"
    cert.get_subject().L = "Campinas"
    cert.get_subject().O = hostname
    cert.get_subject().OU = hostname
    cert.set_serial_number(1000)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)
    cert.set_issuer(cert.get_subject())

    if re.compile(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}").match(hostname):
        alt_name = "IP:" + hostname
    else:
        alt_name = "DNS:" + hostname
    cert.add_extensions(
        [crypto.X509Extension(b"subjectAltName", False, alt_name.encode())]
    )

    cert.set_pubkey(k)
    cert.sign(k, "sha512")

    with open(cert_path, "wb") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    with open(pkey_path, "wb") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))

    return
