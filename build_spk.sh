#!/bin/bash
# Build Filamind.spk package — DSM 7.2 compatible
set -e

SRC=/mnt/c/Users/Eg2/Desktop/saynolgy/spk-source
OUT=/mnt/c/Users/Eg2/Desktop/saynolgy/Filamind.spk
WORK=$(mktemp -d)

echo "=== Building SPK in $WORK ==="

cp -r $SRC/* $WORK/
cd $WORK

# Strip CR/BOM from text files (Windows -> Unix)
for f in INFO scripts/* conf/* WIZARD_UIFILES/*; do
    if [ -f "$f" ]; then
        # Remove UTF-8 BOM if present
        sed -i '1s/^\xEF\xBB\xBF//' "$f"
        # Convert CRLF -> LF
        sed -i 's/\r$//' "$f"
    fi
done

# Make scripts executable
chmod +x scripts/* package/bin/* 2>/dev/null || true

# Create package.tgz (inner archive, gzipped tar of package/ contents)
echo "--> Creating package.tgz..."
cd package
tar czf ../package.tgz --owner=0 --group=0 .
cd ..
rm -rf package

# Add extractsize (KB of uncompressed package contents)
EXTRACT_SIZE_BYTES=$(gzip -dc package.tgz | wc -c)
EXTRACT_SIZE_KB=$(( (EXTRACT_SIZE_BYTES + 1023) / 1024 ))
if ! grep -q "^extractsize=" INFO; then
    echo "extractsize=\"${EXTRACT_SIZE_KB}\"" >> INFO
fi

# Compute checksum of package.tgz
CHECKSUM=$(md5sum package.tgz | awk '{print $1}')
if ! grep -q "^checksum=" INFO; then
    echo "checksum=\"${CHECKSUM}\"" >> INFO
fi

echo "--> SPK contents:"
ls -la
echo ""
echo "--> INFO file:"
grep -v "^package_icon" INFO
echo ""

# Final SPK is a tar (NOT gzipped) of the outer structure
# INFO MUST be first in the archive
echo "--> Building $OUT..."
SPK_FILES="INFO package.tgz scripts conf WIZARD_UIFILES"
for f in LICENSE LICENSE_enu; do
    [ -f "$f" ] && SPK_FILES="$SPK_FILES $f"
done
tar cf $OUT --format=ustar --owner=0 --group=0 $SPK_FILES

echo ""
echo "=== Done ==="
ls -lh $OUT
echo ""
echo "Verifying SPK structure:"
tar tf $OUT
echo ""
echo "SPK ready: C:\\Users\\Eg2\\Desktop\\saynolgy\\Filamind.spk"

# Cleanup
rm -rf $WORK
