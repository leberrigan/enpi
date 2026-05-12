#!/usr/bin/env python3
"""First-boot provisioning. Exchanges the shared claim cert for a device-unique cert
via AWS IoT Fleet Provisioning. Runs once; exits immediately if already provisioned."""

import json
import os
import sys
import socket
import threading
from awsiot import mqtt_connection_builder
from awsiot.iotidentity import (
    IotIdentityClient,
    CreateKeysAndCertificateRequest,
    CreateKeysAndCertificateSubscriptionRequest,
    RegisterThingRequest,
    RegisterThingSubscriptionRequest,
)
from awscrt import mqtt

INSTALL_DIR = "/opt/sensorgnome/enpi"
PROVISIONING_DIR = f"{INSTALL_DIR}/provisioning"
DEVICE_CERT_DIR = "/etc/enpi"
DEVICE_CERT = f"{DEVICE_CERT_DIR}/device-cert.pem"
DEVICE_KEY = f"{DEVICE_CERT_DIR}/device-private-key.pem"
TEMPLATE_NAME = "enpi-provisioning-template"


def get_serial():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("Serial"):
                    return line.split(":")[1].strip().lstrip("0") or "unknown"
    except Exception:
        pass
    return socket.gethostname()


def provision():
    if os.path.exists(DEVICE_CERT) and os.path.exists(DEVICE_KEY):
        print("Already provisioned.")
        sys.exit(0)

    with open(f"{INSTALL_DIR}/enpi-config.json") as f:
        config = json.load(f)

    endpoint = config["iot_endpoint"]
    serial = get_serial()

    conn = mqtt_connection_builder.mtls_from_path(
        endpoint=endpoint,
        cert_filepath=f"{PROVISIONING_DIR}/claim-cert.pem",
        pri_key_filepath=f"{PROVISIONING_DIR}/claim-private-key.pem",
        ca_filepath=f"{PROVISIONING_DIR}/AmazonRootCA1.pem",
        client_id=f"provisioning-{serial}",
        clean_session=True,
        keep_alive_secs=30,
    )
    conn.connect().result()
    print(f"Connected with claim cert, serial={serial}")

    client = IotIdentityClient(conn)
    cert_data = {}
    create_done = threading.Event()
    register_done = threading.Event()

    def on_cert_accepted(response):
        cert_data.update({
            "pem": response.certificate_pem,
            "key": response.private_key,
            "token": response.certificate_ownership_token,
        })
        create_done.set()

    def on_cert_rejected(response):
        print(f"Certificate creation rejected: {response}", file=sys.stderr)
        sys.exit(1)

    def on_register_accepted(response):
        register_done.set()

    def on_register_rejected(response):
        print(f"Registration rejected: {response}", file=sys.stderr)
        sys.exit(1)

    client.subscribe_to_create_keys_and_certificate_accepted(
        request=CreateKeysAndCertificateSubscriptionRequest(),
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_cert_accepted,
    ).result()

    client.subscribe_to_create_keys_and_certificate_rejected(
        request=CreateKeysAndCertificateSubscriptionRequest(),
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_cert_rejected,
    ).result()

    client.publish_create_keys_and_certificate(
        request=CreateKeysAndCertificateRequest(),
        qos=mqtt.QoS.AT_LEAST_ONCE,
    ).result()

    if not create_done.wait(timeout=30):
        print("Timed out waiting for certificate", file=sys.stderr)
        sys.exit(1)

    client.subscribe_to_register_thing_accepted(
        request=RegisterThingSubscriptionRequest(template_name=TEMPLATE_NAME),
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_register_accepted,
    ).result()

    client.subscribe_to_register_thing_rejected(
        request=RegisterThingSubscriptionRequest(template_name=TEMPLATE_NAME),
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_register_rejected,
    ).result()

    client.publish_register_thing(
        request=RegisterThingRequest(
            template_name=TEMPLATE_NAME,
            certificate_ownership_token=cert_data["token"],
            parameters={"SerialNumber": serial},
        ),
        qos=mqtt.QoS.AT_LEAST_ONCE,
    ).result()

    if not register_done.wait(timeout=30):
        print("Timed out waiting for registration", file=sys.stderr)
        sys.exit(1)

    conn.disconnect().result()

    os.makedirs(DEVICE_CERT_DIR, mode=0o700, exist_ok=True)
    for path, content in [(DEVICE_CERT, cert_data["pem"]), (DEVICE_KEY, cert_data["key"])]:
        with open(path, "w") as fh:
            fh.write(content)
        os.chmod(path, 0o600)

    print(f"Provisioned successfully as enpi-{serial}")


if __name__ == "__main__":
    provision()
