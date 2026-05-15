#!/usr/bin/env python3
"""
"ts","light_level","frequency","count","duration","temperature"
"""

import time
import csv
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import argparse
import sys
import gzip
import json
import read_sqmLU as sqmLU
from datetime import date
from enpi import __version__,__log_dir__,__data_dir__,__sitename_file__

with open(__sitename_file__, 'r') as f:
    SITE_NAME = f.read().strip()

# Parse command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument("-d", "--debug", action="store_true", help="Enable debug mode")
parser.add_argument("-dir", help="Data storage directory (default = /data)", type=str, default=__data_dir__)
parser.add_argument("-v", "--verbose", action="store_true", help="Log a lot of messages", default = False)
parser.add_argument("-i","--interval", help="Sample interval in seconds (default is 300s, or 5 minutes)", type=int, default=300)
parser.add_argument("--once", action="store_true", help="Only take one sample and exit")
parser.add_argument("-p", "--port", help="Serial port for the SQM-LU (default is /dev/ttySQM0)", type=str, default='/dev/ttySQM0')
args = parser.parse_args()

# SQM-LU serial port (default is /dev/SQM0, but may need to be changed based on your setup)
PORT_sqmLU = args.port

# Seconds between samples
sampleInterval = args.interval # default: 5 Minutes
    
today = date.today()

def init():
    global ser
    
    setup_logging()
    # Make sure data dir exists
    os.makedirs(__data_dir__, exist_ok=True)
    
    if args.verbose:
        print("[enpi-light] Starting enpi-light version " + __version__)
    logging.info("[enpi-light] Starting enpi-light version " + __version__)
    
    if args.debug:
        print("[enpi-light] ### Running in debug mode")
        logging.info("[enpi-light] ### Running in debug mode")
        
    if args.once:
        print("[enpi-light] ### Sampling only once")
        logging.info("[enpi-light] ### Sampling only once")

    
    if args.verbose:
        print("[enpi-light] Start logging.")
        logging.info("[enpi-light] Start logging.")

    try: 
        success = sqmLU.init( args.verbose, PORT_sqmLU )
        if not success:
            print(json.dumps(["status", "no-dev"]), flush=True)
            stop()

    except Exception as e:
        if args.verbose:
            print(f"[enpi-light] Something went wrong: {e}")
        print(json.dumps(["status", "error"]), flush=True)
        logging.info(f"[enpi-light] Something went wrong: {e}")


def setup_logging():
    handler = TimedRotatingFileHandler(
        f"{__log_dir__}/enpi-light.log",
        when="midnight",
        interval=1,
        backupCount=14,   # keep 14 days of logs
        utc=False
    )
    formatter = logging.Formatter("(%(asctime)s) %(message)s")
    handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)


def read():
    # Read SQM-LU data
    sensor_data = sqmLU.read( )
    if sensor_data is None:
        if args.verbose:
            print("[enpi-light] Error reading data from SQM-LU")
        print(json.dumps(["status", "error"]), flush=True)
        logging.info("[enpi-light] Error reading data from SQM-LU")
        sensor_data = "NA","NA","NA","NA","NA"

    return sensor_data

def stop():
    logging.info("[enpi-light] Exiting...")
    sqmLU.stop()
    sys.exit()
    
def zip_and_remove(path):
    with open(path, "rb") as src, gzip.open(path + ".gz", "wb") as dst:
        dst.writelines(src)

    if args.verbose:
        print(f"[enpi-air] Zipped file {path}")
        logging.info(f"[enpi-air] Zipped file {path}")

    os.remove(path)
    return path + ".gz"

def get_filename(date = date.today()):
    formatted_date = date.strftime('%Y-%m-%d')
    return f"{args.dir}/light_{SITE_NAME}_v{__version__}_{formatted_date}.csv"

def main():
    init()
    try:
        while True:
            global today
            if today != date.today():
                zip_and_remove(get_filename(today))
                today = date.today()

            filename = get_filename(today)
                
            with open(filename, mode="a", newline='') as file:
            
                if args.verbose:
                    print("[enpi-light] Opened CSV for writing...")
                    logging.info("[enpi-light] Opened CSV for writing...")
                writer = csv.writer(file)
                # Write header if file doesn't exist or is empty
                if not os.path.isfile(filename) or os.path.getsize(filename) == 0:
                    writer.writerow(["ts","light_level","frequency","count","duration","temperature"])
                
                ts = time.time() # Time received
                
                # Read sensor data
                sensor_data = read()
                
                if args.verbose:
                    print("[enpi-light] Writing to CSV")
                    logging.info("[enpi-light] Writing to CSV")
                print(json.dumps([ts] + list(sensor_data)), flush=True)
                writer.writerow([ts] + list(sensor_data))
                
                if args.once:
                    stop()

                if args.verbose:
                    print(f"[enpi-light] Sleeping for {sampleInterval} seconds before sampling again")
                    logging.info(f"[enpi-light] Sleeping for {sampleInterval} seconds before sampling again")
                    
                # Sleep until next measurement
                time.sleep( sampleInterval )
        
    except KeyboardInterrupt:
        stop()
        

if __name__ == "__main__":
    main()