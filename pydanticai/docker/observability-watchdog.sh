#!/bin/sh
# Polls weather-app's running state and stops the observability containers
# (grafana/prometheus/tempo/otel-collector by default) once weather-app has
# been down for WATCHDOG_GRACE_PERIOD_SECONDS - there's nothing worth
# tracing/scraping/dashboarding once the app itself isn't running.
#
# Deliberately counts elapsed *poll intervals* rather than parsing Docker's
# FinishedAt timestamp - RFC3339Nano parsing via `date -d` is inconsistent
# across busybox/coreutils versions, and a poll-counter needs no date
# parsing at all. Trade-off, stated plainly: if weather-app was already
# down before this watchdog started, the grace period counts from watchdog
# startup, not from the app's actual stop time.
#
# Resolves container names via the `com.docker.compose.service` label
# (not a hardcoded `<project>-<service>-1` name) so it keeps working
# regardless of the compose project name.
set -eu

CHECK_INTERVAL="${WATCHDOG_CHECK_INTERVAL_SECONDS:-30}"
GRACE_PERIOD="${WATCHDOG_GRACE_PERIOD_SECONDS:-600}"
APP_SERVICE="${WATCHDOG_APP_SERVICE:-weather-app}"
DEPENDENT_SERVICES="${WATCHDOG_DEPENDENT_SERVICES:-grafana prometheus tempo otel-collector}"

log() { echo "[watchdog] $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }

find_container() {
  docker ps -a --filter "label=com.docker.compose.service=$1" --format '{{.Names}}' | head -n1
}

is_running() {
  [ -n "$1" ] && [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null || echo false)" = "true" ]
}

down_seconds=0
already_stopped=0

log "started. app_service=$APP_SERVICE grace_period=${GRACE_PERIOD}s check_interval=${CHECK_INTERVAL}s dependents=[$DEPENDENT_SERVICES]"

while true; do
  app_container="$(find_container "$APP_SERVICE")"

  if is_running "$app_container"; then
    if [ "$down_seconds" -gt 0 ]; then
      log "$APP_SERVICE is back up after ${down_seconds}s - resetting downtime tracking"
    fi
    down_seconds=0
    already_stopped=0
  else
    down_seconds=$((down_seconds + CHECK_INTERVAL))
    if [ "$down_seconds" -ge "$GRACE_PERIOD" ] && [ "$already_stopped" -eq 0 ]; then
      log "$APP_SERVICE has been down for ~${down_seconds}s (>= ${GRACE_PERIOD}s) - stopping dependent services"
      for svc in $DEPENDENT_SERVICES; do
        c="$(find_container "$svc")"
        if is_running "$c"; then
          log "stopping $svc ($c)"
          docker stop "$c" >/dev/null 2>&1 || log "failed to stop $c"
        fi
      done
      already_stopped=1
    fi
  fi

  sleep "$CHECK_INTERVAL"
done
