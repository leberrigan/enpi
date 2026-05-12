#! /bin/bash -e
DESTDIR=build-temp
PKGNAME=enpi
INSTALL_ROOT=/opt/sensorgnome/enpi

# Clean previous build
rm -rf "$DESTDIR"
mkdir -p "$DESTDIR"

# Create target directory
install -d "$DESTDIR$INSTALL_ROOT"

# Install Python scripts and assets
install -m 755 enpi-*.py "$DESTDIR$INSTALL_ROOT"
install -m 644 requirements.txt "$DESTDIR$INSTALL_ROOT"
install -m 644 enpi-config.json "$DESTDIR$INSTALL_ROOT" 2>/dev/null || true
install -m 644 read_*.py "$DESTDIR$INSTALL_ROOT"
install -m 644 test-*.py "$DESTDIR$INSTALL_ROOT" 2>/dev/null || true

# Install the enpi Python subpackage
cp -r enpi "$DESTDIR$INSTALL_ROOT/"

# Install udev rules (postinst installs them to /etc/udev/rules.d/)
cp -r udev "$DESTDIR$INSTALL_ROOT/"

# Install provisioning assets (claim cert, root CA, provision script, service file)
cp -r provisioning "$DESTDIR$INSTALL_ROOT/"

# Copy any additional supporting files
cp -r extra-files/* "$DESTDIR$INSTALL_ROOT" 2>/dev/null || true

# Install DEBIAN control files
cp -r DEBIAN "$DESTDIR"
chmod 0755 "$DESTDIR"/DEBIAN/post* || true
chmod 0755 "$DESTDIR"/DEBIAN/pre* || true

# Set package version: YYYY.DDD (same convention as sensorgnome-control)
sed -e "/^Version/s/:.*/: $(TZ=PST8PDT date +%Y.%j)/" \
  -i "$DESTDIR/DEBIAN/control"

# Build the package
mkdir -p packages
dpkg-deb -Zxz --build "$DESTDIR" packages

# Show result
ls -lh packages