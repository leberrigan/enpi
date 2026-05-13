# ENPI

### _Particulate and light level monitoring with the Raspberry Pi_

## Details

#### A total of three sensors on two hardware components are used to measure:
- Particulates (pm1.0, pm2.5,pm10) - PMS5003
- Humidity, temperature, air pressure - BME280 (or BMP280)
- Light levels - SQM-LU


#### Air sensors are all attached to a custom-built "bonnet" for the Raspberry Pi purpose-built for Motus
- Daughter board used for external sensors.
- No EEPROM means other HATs can be used in conjuction without conflict.
- UART is bit-banged on GPIO 24 to avoid conflict with GPS HAT and Cell HAT.


#### Light level sensor is a USB device made by UniHedron used to detect light pollution.
- Auto detected using custom udev rules.
- Device shares same FTDI chip vendor and product IDs as Cornell XCVR so this script overrides that.
  - Could develop a checking script to accommodate both, but this is unlikely necessary given the Cornell XCVR's rarity.


#### Data is uploaded to AWS
- Each device is provisioned with a unique X.509 certificate via AWS IoT Fleet Provisioning on first boot (triggered by sensorgnome-control).
- Temporary S3 credentials are fetched at upload time from the AWS IoT Credentials Provider — no static keys stored on the device.
- Data is stored in a per-device folder in S3 named after the site name (e.g. `enpi-sensors/SG-BC4ERPI3CF2A/`).
- Daily file rotation.


## Installation
With internet connection, run: 
```
curl -sSL https://raw.githubusercontent.com/sensorgnome-org/enpi/sensorgnome/install.sh | sudo bash
```

Or try a different branch with:
```
curl -sSL https://raw.githubusercontent.com/sensorgnome-org/enpi/sensorgnome/install.sh | sudo bash -s -- <BRANCH>
```

## SensorGnome integration

- Installs sensorgnome-control files from https://github.com/leberrigan/sensorgnome-control/tree/enpi.
- Web interface displays sensor info and controls.

![SensorGnome web interface showing plots and controls for enpi](demo.png){width=50%}




## Testing

### Set up python environment
```
cd /opt/sensorgnome/enpi
source env/bin/activate
```

### Test PMS5003 and BME280
```
/opt/sensorgnome/enpi/env/bin/python3 /opt/sensorgnome/enpi/enpi-air.py -d -v
```

### Test PMS5003 
```
sudo systemctl stop sg-control
cd /opt/sensorgnome/enpi/
sudo killall pigpiod
sudo pigpiod
env/bin/python3 test-pms5003.py

```

### Test SQM-LU
```
cd /opt/sensorgnome/enpi
env/bin/python3 test-sqmlu.py
```

### Test Uploader
```
/opt/sensorgnome/enpi/env/bin/python3 /opt/sensorgnome/enpi/enpi-upload.py
```

---

## Raspberry Pi Pins being used
- (1) 3v3
- (2) 5v
- (3) GPIO 2 (SDA1, I2C) - BME280
- (5) GPIO 3 (SCL1, I2C) - BME280
- (9) Ground
- (10) GPIO 15 (UART_RXD0) - Not used by default
- (18) GPIO 24 (UART_RX, bit-banged) - PMS5003


---

## Next steps



---

## Manual install

## Requirements

### Python virtual environment
Latest RPi OS locks down the Python environment, preventing you from installing packages into the system interpreter using Pip. For this reason, you need to use a virtual environment.
- Run this code:
    ```
    sudo apt install python3-venv
    python3 -m venv env
    source env/bin/activate
    ```
- Install required packages from `requirements.txt`
    ```
    pip install -r requirements.txt
    ```

### Modifying services
```
sudo mv /home/enpi/enpi-*.yml /etc/shiftwrap/services/
sudo mv /home/enpi/*.rules /etc/udev/rules.d/
sudo mv /home/enpi/*.py /opt/enpi/
sudo mv /home/enpi/env/ /opt/enpi/env/
sudo mv /home/enpi/update.sh /opt/enpi/
sudo mv /home/enpi/enpi-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable enpi-air
sudo systemctl start enpi-air 
```
- See if modifications worked by checking the status: `sudo systemctl status enpi-air`
```
sudo systemctl daemon-reload
sudo systemctl restart enpi-air
sudo systemctl status enpi-air

journalctl -u enpi -n 50 --no-pager
```
- Make log folder if it doesn't exist
```
sudo mkdir -p /var/log/enpi
sudo chown ampi:ampi /var/log/enpi
sudo chmod 755 /var/log/enpi
```
- update udev rules
```
sudo mv /home/enpi/*.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```
### PMS5003
Uses UART interface which is disabled by default. Steps to make it work:
- Edit `/boot/firmware/config.txt` and add line `enable_uart=1`
- Enter `raspi-config` and select `Interface Options --> Serial Port` and answer the questions:
  - Login shell over serial --> NO
  - Enable serial hardware --> YES
- Reboot

- Notes: might try to reconfigure uart to use miniuart (ttyS0) so that it's compatible with GPS HAT
  - /boot/config.txt -> dtoverlay=uart1,txd1_pin=32,rxd1_pin=33

### BME280
- Enter `raspi-config` and select `Interface Options --> I2C --> Enable`
- Reboot

### SQM-LU
- 


---
## TESTING
  


    