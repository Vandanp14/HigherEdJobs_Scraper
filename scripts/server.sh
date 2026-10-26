# Sourced by run.sh, clear.sh and daily.sh. Another project may use port 8000, so this dashboard
# takes the first free port from 8000 to 8010 and records it in data/server.port.
PORT_FILE=data/server.port
APP_ID=higheredjobs-review

# Print this dashboard's URL if it is running (identified by /api/health), else nothing.
running_url() {
  local port
  for port in $([ -f "$PORT_FILE" ] && cat "$PORT_FILE") $(seq 8000 8010); do
    if curl -sf --max-time 1 "http://127.0.0.1:$port/api/health" 2>/dev/null | grep -q "\"$APP_ID\""; then
      echo "http://127.0.0.1:$port"
      return
    fi
  done
}

free_port() {
  local port
  for port in $(seq 8000 8010); do
    if ! lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "$port"
      return
    fi
  done
  return 1
}
