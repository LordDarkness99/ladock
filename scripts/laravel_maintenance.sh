#!/usr/bin/env bash

set -euo pipefail

APP_KEY_MISSING="${1:-0}"

if [[ ! -f artisan ]]; then
  exit 0
fi

if ! ARTISAN_COMMANDS="$(php artisan list 2>&1)"; then
  printf 'Gagal membaca daftar perintah Artisan:\n%s\n' "$ARTISAN_COMMANDS" >&2
  exit 1
fi

artisan_has_command() {
  awk -v target="$1" '$1 == target { found = 1 } END { exit !found }' \
    <<< "$ARTISAN_COMMANDS"
}

run_optional_artisan_command() {
  local command="$1"
  shift
  if artisan_has_command "$command"; then
    php artisan "$command" "$@"
  else
    printf 'Melewati perintah Artisan yang tidak didukung: %s\n' "$command"
  fi
}

rm -f bootstrap/cache/*.php
rm -f storage/framework/sessions/*
rm -f storage/framework/views/*.php
run_optional_artisan_command clear-compiled
run_optional_artisan_command cache:clear

if [[ "$APP_KEY_MISSING" == "1" ]]; then
  if ! artisan_has_command key:generate; then
    echo 'APP_KEY belum tersedia dan perintah Artisan key:generate tidak didukung.' >&2
    exit 1
  fi
  php artisan key:generate
fi

rm -f bootstrap/cache/*.php

if [[ -d database/migrations ]] \
  && find database/migrations -type f -name '*.php' -print -quit | grep -q .; then
  if ! artisan_has_command migrate; then
    echo 'File migrasi ditemukan tetapi perintah Artisan migrate tidak tersedia.' >&2
    exit 1
  fi
  php artisan migrate
fi

if [[ -e public/storage || -L public/storage ]]; then
  echo 'Melewati storage:link; public/storage sudah tersedia.'
else
  run_optional_artisan_command storage:link
fi
