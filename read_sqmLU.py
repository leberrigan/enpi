#!/usr/bin/env python3
import serial
import serial.tools.list_ports
import logging
import json
import time
import os

# Replace with the actual port your SQM is on
SERIAL_PORT = '/dev/ttySQM0'
BAUD_RATE = 115200
VENDOR_ID = 0x0403
PRODUCT_ID = 0x6001

ser = None

def init(set_verbose=False, port=SERIAL_PORT):
    global verbose

    verbose = set_verbose
    if open(port):
        port_info = get_port_info(port)
        if port_info is None:
            if verbose:
                print(f"[SQM-LU] No device at address {port}")
                logging.info(f"[SQM-LU] No device at address {port}")
            print(json.dumps(["status", "no-dev"]), flush=True)
        else:
            vid, pid, desc = get_port_info(port)
            if vid == VENDOR_ID and pid == PRODUCT_ID:
                if verbose:
                    print("[SQM-LU] Device found.")
                    logging.info("[SQM-LU] Device found.")
                print(json.dumps(["status", "connected"]), flush=True)
                return True
            else:
                if verbose:
                    print(f"[SQM-LU] Wrong device found at address \"{port}\": vendor={vid}, product={pid}")
                    logging.info(f"[SQM-LU] Wrong device found at address: {port}")
                print(json.dumps(["status", "no-dev"]), flush=True)
    else:
        if verbose:
            print(f"[SQM-LU] No device at address {port}")
            logging.info(f"[SQM-LU] No device at address {port}")
        print(json.dumps(["status", "no-dev"]), flush=True)
        
    return False

def open(port):
    global ser
    try:
        ser = serial.Serial(
            port,
            115200,
            timeout=2,
            write_timeout=2,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            dsrdtr=True,   # SQM-LU likes DTR high
            rtscts=False
        )
    
        time.sleep(0.2)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        return True
        
    except serial.SerialException as e:
        if verbose:
            print(f"[SQM-LU] Serial error: {e}")
        print(json.dumps(["status", "no-dev"]), flush=True)
        logging.info(f"[SQM-LU] Serial error: {e}")
        return False

def stop():
    global ser
    if ser:
        ser.close()
        ser = None

def read():
    if ser is None:
        print(json.dumps(["status", "no-dev"]), flush=True)
        if verbose:
            print("[SQM-LU] Serial port not open")
        return None

    if verbose:
        print("[SQM-LU] Reading...")
        logging.info("[SQM-LU] Reading...")
    try:
        ser.reset_input_buffer() # clear any stale data
        # Send the read command
        ser.write(b'rx\r\n')
        ser.flush()
        # Read the response
        response = ser.readline().decode('utf-8', errors = "replace").strip()
        print(json.dumps(["status", "connected"]), flush=True)
        if verbose:
            print(f"[SQM-LU] Response: {response}")
            logging.info(f"[SQM-LU] Response: {response}")
        return parse(response)
    except serial.SerialException as e:
        if verbose:
            print(f"[SQM-LU] Serial error: {e}")
        print(json.dumps(["status", "no-dev"]), flush=True)
        logging.info(f"[SQM-LU] Serial error: {e}")
        return None

def parse(data):
    try:
        parts = [part.strip() for part in data.split(',')]
        if len(parts) == 6 and parts[0] == 'r':
            light_level = parts[1].rstrip('m')                 # '11.33'
            frequency = int(parts[2].rstrip('Hz'))              # 2772
            count = int(parts[3].rstrip('c'))                    # 0
            duration = float(parts[4].rstrip('s'))               # 0.0
            temperature = float(parts[5].rstrip('C'))            # 22.8
            return light_level,frequency,count,duration,temperature
        else:
            return None
    except ValueError:
        if verbose:
            print(f"[SQM-LU] Failed to parse: {data}")
        logging.info(f"[SQM-LU] Failed to parse: {data}")
        print(json.dumps(["status", "error"]), flush=True)
        return None

def get_port_info(device):
    # Resolve symlink to real device path
    real_device = os.path.realpath(device)

    ports = serial.tools.list_ports.comports()
    for port in ports:
        if port.device == real_device:
            return port.vid, port.pid, port.description
    return None