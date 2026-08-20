# Node Sanity — Agent

This is the piece that runs on a monitored Linux machine, separate
from the central server. It's what makes "Live Agents" on the
dashboard real: instead of clicking "Scan Now" for a folder, this
process watches its own disk in the background and pushes a report
to the central server automatically once usage crosses a threshold.

It's a completely separate deployable unit from the rest of the
project — its own `pip install`, its own `uvicorn` process, and it
can live on a totally different machine than `server.py`.

## Setup

```bash
cd agent
pip install -r requirements.txt
```

Edit `config.yaml`:

- `central_server` — URL of the machine running `server.py` (the
  central dashboard), e.g. `http://192.168.1.20:8080`.
- `hostname` — unique name for this agent, shown on the dashboard.
- `callback_host` / `agent_port` — how the central server reaches
  *this* machine back for `/execute`. If central and agent are on
  different machines, `callback_host` must be an address the central
  server can actually reach — not `localhost`.
- `disk_threshold` — percent disk usage that triggers a report.
- `scan_paths` — folders this agent is allowed to scan and, later,
  clean up inside. Nothing outside these paths can ever be touched,
  no matter what a report claims.

## Run

```bash
uvicorn agent_app:app --host 0.0.0.0 --port 9001
```

(Port must match `agent_port` in `config.yaml`.)

On startup, the agent registers itself with the central server, then
starts checking its own disk usage every `check_interval_seconds`.
Nothing gets sent anywhere unless `disk_threshold` is actually
crossed.

## Testing without waiting for the disk to fill up

```bash
curl -X POST http://localhost:9001/scan-now
```

This runs the same file-collection logic as the background loop and
returns the results directly, without needing the threshold to be
crossed or the interval to elapse — useful for a demo or for
confirming `scan_paths` is configured correctly.

## What happens end to end

1. Agent starts, registers with the central server (`/register`).
2. Every `check_interval_seconds`, the agent checks its own disk
   usage.
3. Once usage ≥ `disk_threshold`, it walks `scan_paths`, scores each
   file, and POSTs the flagged list to the central server's
   `/agent-report`.
4. The central server asks Ollama for an advisory recommendation per
   file, then validates every candidate against `policy.json` — the
   exact same policy engine local-scan folders use. Nothing here is
   trusted just because an agent sent it.
5. The dashboard's "Live Agents" panel shows the approved/rejected
   list for a human to review.
6. When the human selects actions and clicks execute, the central
   server re-validates centrally, then relays only the approved
   actions to this agent's own `/execute` endpoint.
7. This agent re-validates AGAIN (fetching the current policy fresh)
   and is the only thing that actually touches the file — always via
   the OS Recycle Bin / Trash, never a permanent delete.

Three independent validation passes (central plan generation →
central pre-relay → agent pre-execution) before anything on this
machine's disk actually changes.
