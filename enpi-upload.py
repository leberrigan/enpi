#!/usr/bin/env python3
import os
import ssl
import json
import argparse
import logging
import urllib.request
from logging.handlers import TimedRotatingFileHandler
from datetime import date, datetime
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from enpi import __version__, __log_dir__, __data_dir__, __sitename_file__

INSTALL_DIR = "/opt/sensorgnome/enpi"
PROVISIONING_DIR = f"{INSTALL_DIR}/provisioning"
DEVICE_CERT_DIR = "/etc/enpi"

with open(__sitename_file__, 'r') as f:
    SITE_NAME = f.read().strip()

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--data-dir", type=str, default=__data_dir__)
parser.add_argument("-v", "--verbose", action="store_true", default=False)
parser.add_argument("-ld", "--log-dir", type=str, default=INSTALL_DIR)
parser.add_argument("-p", "--poll", action="store_true")
args = parser.parse_args()

DATA_DIR = args.data_dir
LOG_FILE = f"{__log_dir__}/uploader.log"


def setup_logging():
    handler = TimedRotatingFileHandler(LOG_FILE, when="midnight", interval=1, backupCount=14, utc=False)
    handler.setFormatter(logging.Formatter("(%(asctime)s) %(message)s"))
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)


def fetch_iot_credentials(endpoint, role_alias):
    url = f"https://{endpoint}/role-aliases/{role_alias}/credentials"
    ctx = ssl.create_default_context(cafile=f"{PROVISIONING_DIR}/AmazonRootCA1.pem")
    ctx.load_cert_chain(
        certfile=f"{DEVICE_CERT_DIR}/device-cert.pem",
        keyfile=f"{DEVICE_CERT_DIR}/device-private-key.pem",
    )
    with urllib.request.urlopen(urllib.request.Request(url), context=ctx) as resp:
        creds = json.loads(resp.read())["credentials"]
    return creds["accessKeyId"], creds["secretAccessKey"], creds["sessionToken"]


def mark_uploaded(filename, filepath):
    os.rename(filepath, os.path.join(DATA_DIR, "uploaded_" + filename))


def is_completed_daily_csv(filename):
    try:
        date_str = filename.split("_")[-1].replace(".csv", "").replace(".gz", "")
        return datetime.strptime(date_str, "%Y-%m-%d").date() < date.today()
    except Exception:
        return False


def upload_file(s3, bucket, filepath):
    filename = os.path.basename(filepath)
    s3_key = SITE_NAME + "/" + filename.replace("@", "/")
    logging.info(f"Uploading {filename} → s3://{bucket}/{s3_key}")
    try:
        s3.upload_file(filepath, bucket, s3_key)
        logging.info(f"Upload succeeded for {filename}")
        return True
    except (BotoCoreError, ClientError) as e:
        logging.error(f"Upload failed for {filename}: {e}")
        return False


def is_upload_candidate(f):
    return (
        f.endswith((".csv.gz", ".csv"))
        and not f.startswith("uploaded_")
        and not f.startswith("_")
        and is_completed_daily_csv(f)
    )


def poll(s3, bucket):
    try:
        s3.head_bucket(Bucket=bucket)
        print(json.dumps(["status", "connected"]), flush=True)
        logging.info("S3 bucket is accessible")
        return True
    except ClientError as e:
        code = e.response['Error']['Code']
        if code == '403':
            print(json.dumps(["status", "auth-error"]), flush=True)
            logging.error("S3 auth error")
        elif code == '404':
            print(json.dumps(["status", "no-bucket"]), flush=True)
            logging.error(f"S3 bucket {bucket} not found")
        else:
            print(json.dumps(["status", "error"]), flush=True)
            logging.error(f"S3 error: {e}")
        return False
    except (BotoCoreError, Exception) as e:
        print(json.dumps(["status", "no-network"]), flush=True)
        logging.error(f"Network error: {e}")
        return False


def main():
    setup_logging()
    logging.info("Uploader started")

    if not os.path.isdir(DATA_DIR):
        print(json.dumps(["status", "no-data-dir"]), flush=True)
        logging.error(f"Data directory missing: {DATA_DIR}")
        return

    if not os.path.exists(f"{DEVICE_CERT_DIR}/device-cert.pem") or not os.path.exists(f"{DEVICE_CERT_DIR}/thing-name"):
        print(json.dumps(["status", "not-provisioned"]), flush=True)
        logging.error("Device not provisioned — enpi-provision.service has not run successfully")
        return


    with open(f"{PROVISIONING_DIR}/iot-config.json") as f:
        config = json.load(f)
    bucket = config["bucket_name"]
    endpoint = config["iot_endpoint"]
    role_alias = config["iot_role_alias"]

    if not args.poll:
        files = [f for f in os.listdir(DATA_DIR) if is_upload_candidate(f)]
        if not files:
            logging.info("No files to upload")
            print(json.dumps(["status", "connected-no-files"]), flush=True)
            return

    try:
        aws_id, aws_key, aws_token = fetch_iot_credentials(endpoint, role_alias)
    except Exception as e:
        print(json.dumps(["status", "no-secrets"]), flush=True)
        logging.error(f"Failed to fetch IoT credentials: {e}")
        return

    print(json.dumps(["data", {"bucket_name": bucket, "auth": "iot-core"}]), flush=True)

    s3 = boto3.client(
        "s3",
        aws_access_key_id=aws_id,
        aws_secret_access_key=aws_key,
        aws_session_token=aws_token,
    )

    bucket_exists = poll(s3, bucket)

    if args.poll:
        return

    if not bucket_exists:
        print(json.dumps(["status", "no-s3-connection"]), flush=True)
        logging.error("Cannot reach S3, aborting upload")
        return

    for f in files:
        full_path = os.path.join(DATA_DIR, f)
        if upload_file(s3, bucket, full_path):
            mark_uploaded(f, full_path)

    print(json.dumps(["status", "done"]), flush=True)
    logging.info("Uploader finished")


if __name__ == "__main__":
    main()
