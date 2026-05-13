#!/usr/bin/env python3
"""Provision this device with AWS IoT Fleet Provisioning.

Exchanges the shared claim cert for a device-unique cert. Safe to call repeatedly —
exits immediately with status "already-provisioned" if the device cert already exists.

Output: JSON lines on stdout, one per event:
  ["status", "already-provisioned", {"thing_name": "<site-name>", "certificate_id": "<id>"}]
  ["status", "connecting"]
  ["status", "provisioning"]
  ["status", "provisioned", {"thing_name": "<site-name>", "certificate_id": "<id>"}]
  ["error", "<reason>", {"detail": "<message>"}]

Exit codes: 0 = success or already provisioned, 1 = failure.
"""

import json
import os
import sys
import threading
import uuid
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
THING_NAME_FILE = f"{DEVICE_CERT_DIR}/thing-name"
CERT_ID_FILE = f"{DEVICE_CERT_DIR}/certificate-id"
TEMPLATE_NAME = "enpi-provisioning-template"


def emit(event):
    print(json.dumps(event), flush=True)


def fail(reason, detail=None):
    emit(["error", reason, {"detail": str(detail)}] if detail else ["error", reason])
    sys.exit(1)


def get_site_name():
    try:
        with open("/etc/sensorgnome/id") as f:
            return f.read().strip()
    except Exception:
        pass
    return socket.gethostname()


def read_file(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return None


def provision():
    if os.path.exists(DEVICE_CERT) and os.path.exists(DEVICE_KEY):
        emit(["status", "already-provisioned", {
            "thing_name": read_file(THING_NAME_FILE),
            "certificate_id": read_file(CERT_ID_FILE),
        }])
        sys.exit(0)

    try:
        with open(f"{PROVISIONING_DIR}/iot-config.json") as f:
            config = json.load(f)
    except Exception as e:
        fail("config-error", e)

    endpoint = config["iot_mqtt_endpoint"]
    site_name = get_site_name()

    emit(["status", "connecting"])
    try:
        conn = mqtt_connection_builder.mtls_from_path(
            endpoint=endpoint,
            cert_filepath=f"{PROVISIONING_DIR}/claim-cert.pem",
            pri_key_filepath=f"{PROVISIONING_DIR}/claim-private-key.pem",
            ca_filepath=f"{PROVISIONING_DIR}/AmazonRootCA1.pem",
            client_id=f"provisioning-{site_name}-{uuid.uuid4().hex[:8]}",
            clean_session=False,
            keep_alive_secs=30,
        )
        conn.connect().result(timeout=30)
    except Exception as e:
        fail("connection-failed", e)

    emit(["status", "connected"])

    client = IotIdentityClient(conn)
    cert_data = {}
    result_data = {}
    error_info = {}
    create_done = threading.Event()
    register_done = threading.Event()

    def on_cert_accepted(response):
        cert_data.update({
            "pem": response.certificate_pem,
            "key": response.private_key,
            "id": response.certificate_id,
            "token": response.certificate_ownership_token,
        })
        create_done.set()

    def on_cert_rejected(response):
        error_info.update({"reason": "certificate-rejected", "detail": str(response)})
        create_done.set()

    def on_register_accepted(response):
        result_data["thing_name"] = response.thing_name
        register_done.set()

    def on_register_rejected(response):
        error_info.update({"reason": "registration-rejected", "detail": str(response)})
        register_done.set()

    try:
        future, _ = client.subscribe_to_create_keys_and_certificate_accepted(
            request=CreateKeysAndCertificateSubscriptionRequest(),
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_cert_accepted,
        )
        future.result(timeout=30)
    except Exception as e:
        fail("subscribe-cert-accepted-failed", e)
    emit(["status", "subscribed-cert"])

    try:
        future, _ = client.subscribe_to_create_keys_and_certificate_rejected(
            request=CreateKeysAndCertificateSubscriptionRequest(),
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_cert_rejected,
        )
        future.result(timeout=30)
    except Exception as e:
        fail("subscribe-cert-rejected-failed", e)

    client.publish_create_keys_and_certificate(
        request=CreateKeysAndCertificateRequest(),
        qos=mqtt.QoS.AT_LEAST_ONCE,
    ).result()

    if not create_done.wait(timeout=30):
        fail("timeout", "Timed out waiting for certificate creation")
    if error_info:
        fail(error_info["reason"], error_info.get("detail"))

    emit(["status", "provisioning"])

    future, _ = client.subscribe_to_register_thing_accepted(
        request=RegisterThingSubscriptionRequest(template_name=TEMPLATE_NAME),
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_register_accepted,
    )
    future.result(timeout=30)

    future, _ = client.subscribe_to_register_thing_rejected(
        request=RegisterThingSubscriptionRequest(template_name=TEMPLATE_NAME),
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_register_rejected,
    )
    future.result(timeout=30)

    client.publish_register_thing(
        request=RegisterThingRequest(
            template_name=TEMPLATE_NAME,
            certificate_ownership_token=cert_data["token"],
            parameters={"SerialNumber": site_name},
        ),
        qos=mqtt.QoS.AT_LEAST_ONCE,
    ).result()

    if not register_done.wait(timeout=30):
        fail("timeout", "Timed out waiting for Thing registration")
    if error_info:
        fail(error_info["reason"], error_info.get("detail"))

    conn.disconnect().result()

    thing_name = result_data.get("thing_name") or site_name

    os.makedirs(DEVICE_CERT_DIR, mode=0o700, exist_ok=True)
    for path, content in [(DEVICE_CERT, cert_data["pem"]), (DEVICE_KEY, cert_data["key"])]:
        with open(path, "w") as fh:
            fh.write(content)
        os.chmod(path, 0o600)

    for path, content in [(THING_NAME_FILE, thing_name), (CERT_ID_FILE, cert_data["id"])]:
        with open(path, "w") as fh:
            fh.write(content)
        os.chmod(path, 0o644)

    emit(["status", "provisioned", {
        "thing_name": thing_name,
        "certificate_id": cert_data["id"],
    }])


if __name__ == "__main__":
    provision()
