#!/bin/bash

job_agent_runtime_default_root() {
  local loader_dir=""
  loader_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  (cd "$loader_dir/.." && pwd)
}

job_agent_runtime_canonical_path() {
  local path="$1"

  if [[ -d "$path" ]]; then
    (cd "$path" && pwd -P)
    return 0
  fi

  local parent=""
  parent="$(cd "$(dirname "$path")" && pwd -P)"
  printf '%s/%s\n' "$parent" "$(basename "$path")"
}

job_agent_runtime_validate_secrets_file() {
  local secrets_file="$1"
  local root="$2"
  local canonical_root=""
  local canonical_secrets=""

  if [[ "$secrets_file" != /* ]]; then
    echo "JOB_AGENT_SECRETS_FILE must be an absolute path outside JOB_AGENT_ROOT: $secrets_file" >&2
    return 2
  fi

  if [[ ! -f "$secrets_file" ]]; then
    echo "JOB_AGENT_SECRETS_FILE does not exist: $secrets_file" >&2
    return 1
  fi

  canonical_root="$(job_agent_runtime_canonical_path "$root")"
  canonical_secrets="$(job_agent_runtime_canonical_path "$secrets_file")"
  case "$canonical_secrets" in
    "$canonical_root"|"$canonical_root"/*)
      echo "JOB_AGENT_SECRETS_FILE must point outside JOB_AGENT_ROOT: $secrets_file" >&2
      return 2
      ;;
  esac
}

job_agent_runtime_source_file() {
  local path="$1"

  if [[ ! -f "$path" ]]; then
    return 0
  fi

  set +u
  # shellcheck disable=SC1090
  source "$path"
  set -u
}

job_agent_load_runtime_env() {
  local with_secrets=0
  local default_root=""
  local root=""
  local env_file=""
  local secrets_file=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --with-secrets)
        with_secrets=1
        ;;
      *)
        echo "Unsupported job_agent_load_runtime_env option: $1" >&2
        return 2
        ;;
    esac
    shift
  done

  default_root="$(job_agent_runtime_default_root)"
  root="${JOB_AGENT_ROOT:-$default_root}"
  env_file="${JOB_AGENT_ENV_FILE:-$root/.env.local}"

  job_agent_runtime_source_file "$env_file" || return $?

  root="${JOB_AGENT_ROOT:-$root}"
  env_file="${JOB_AGENT_ENV_FILE:-$env_file}"
  unset JOB_AGENT_RUNTIME_SECRETS_FILE_LOADED

  if [[ -n "${JOB_AGENT_SMTP_PASSWORD:-}" ]]; then
    echo "JOB_AGENT_SMTP_PASSWORD is no longer supported in .env.local or the ambient runtime environment. Move it into JOB_AGENT_SECRETS_FILE or use JOB_AGENT_SMTP_PASSWORD_CMD." >&2
    return 2
  fi

  if [[ "$with_secrets" -ne 1 ]]; then
    return 0
  fi

  secrets_file="${JOB_AGENT_SECRETS_FILE:-}"
  if [[ -z "$secrets_file" ]]; then
    return 0
  fi

  job_agent_runtime_validate_secrets_file "$secrets_file" "$root" || return $?
  job_agent_runtime_source_file "$secrets_file" || return $?
  export JOB_AGENT_RUNTIME_SECRETS_FILE_LOADED=1
}

job_agent_emit_runtime_env() {
  job_agent_load_runtime_env "$@" || return $?
  env -0
}
