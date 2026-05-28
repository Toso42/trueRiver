#!/usr/bin/env bash

TRIVER_SEMVER_REGEX='^v?[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z][0-9A-Za-z-]*(\.[0-9A-Za-z][0-9A-Za-z-]*)*)?(\+[0-9A-Za-z][0-9A-Za-z-]*(\.[0-9A-Za-z][0-9A-Za-z-]*)*)?$'

triver_version_strip_v() {
  local version="$1"
  printf '%s\n' "${version#v}"
}

triver_version_with_v() {
  local version
  version="$(triver_version_strip_v "$1")"
  printf 'v%s\n' "$version"
}

triver_version_is_semver() {
  local version="$1"
  [[ "$version" =~ $TRIVER_SEMVER_REGEX ]]
}

triver_version_read() {
  local version_file="$1"
  local version

  [ -f "$version_file" ] || return 1
  version="$(grep -m 1 -E '[^[:space:]]' "$version_file" | tr -d '[:space:]')" || return 1
  [ -n "$version" ] || return 1
  printf '%s\n' "$version"
}

triver_version_normalize_release() {
  local version="$1"

  if triver_version_is_semver "$version"; then
    triver_version_with_v "$version"
    return 0
  fi

  printf '%s\n' "$version"
}
