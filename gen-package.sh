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
# Adjust this list if the repo layout changes
install -m 755 enpi-*.py "$DESTDIR$INSTALL_ROOT"
install -m 644 requirements.txt "$DESTDIR$INSTALL_ROOT"
install -m 644 enpi-config.json "$DESTDIR$INSTALL_ROOT" 2>/dev/null || true
install -m 644 read-*.py "$DESTDIR$INSTALL_ROOT"
install -m 644 test-*.py "$DESTDIR$INSTALL_ROOT" 2>/dev/null || true

# Copy any additional supporting files
# (Safe even if empty)
cp -r extra-files/* "$DESTDIR$INSTALL_ROOT" 2>/dev/null || true

# Install DEBIAN control files
cp -r DEBIAN "$DESTDIR"

# Set package version: YYYY.DDD (same convention as sensorgnome-control)
sed -e "/^Version/s/:.*/: $(TZ=PST8PDT date +%Y.%j)/" \
  -i "$DESTDIR/DEBIAN/control"

# Build the package
mkdir -p packages
dpkg-deb -Zxz --build "$DESTDIR" packages

# Show result
ls -lh packages