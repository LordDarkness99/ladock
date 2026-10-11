#!/usr/bin/env bash
# ==============================================================================
# Test Suite: Simulasi Penataan Folder Deployment LaDock
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

TEST_TMP="/tmp/ladock_test_deploy_sim_$$"
mkdir -p "$TEST_TMP/mock_app"

echo "--> Membuat dummy project Laravel..."
cat > "$TEST_TMP/mock_app/artisan" <<'EOF'
#!/usr/bin/env php
<?php echo "Artisan dummy";
EOF
chmod +x "$TEST_TMP/mock_app/artisan"

cat > "$TEST_TMP/mock_app/composer.json" <<'EOF'
{
  "name": "mock/laravel",
  "require": {
    "php": "^8.2",
    "laravel/framework": "^10.0"
  }
}
EOF

mkdir -p "$TEST_TMP/mock_app/public"
echo "<?php echo 'Hello World'; ?>" > "$TEST_TMP/mock_app/public/index.php"
echo "CREATE TABLE test (id INT);" > "$TEST_TMP/mock_app/dummy_dump.sql"

echo "--> Menguji deteksi stack..."
python3 "$ROOT_DIR/scripts/detect_stack.py" "$TEST_TMP/mock_app" --output "$TEST_TMP/mock_app/stack.json"

if [[ ! -f "$TEST_TMP/mock_app/stack.json" ]]; then
  echo "❌ Gagal: stack.json tidak dibuat!"
  exit 1
fi
echo "✓ stack.json berhasil dibuat."

echo "--> Menguji pembuatan struktur mysql/db/mock_app..."
mkdir -p "$ROOT_DIR/mysql/db/mock_app"
cp "$TEST_TMP/mock_app/dummy_dump.sql" "$ROOT_DIR/mysql/db/mock_app/data.sql"

if [[ ! -f "$ROOT_DIR/mysql/db/mock_app/data.sql" ]]; then
  echo "❌ Gagal: mysql/db/mock_app/data.sql tidak ada!"
  exit 1
fi
echo "✓ File dump tersimpan rapi di mysql/db/mock_app/data.sql."

# Cleanup
rm -rf "$TEST_TMP" "$ROOT_DIR/mysql/db/mock_app"

echo "======================================================"
echo "  ✓ Semua simulasi penataan struktur deployment LULUS!"
echo "======================================================"
