#!/usr/bin/env bash
# review_with_qwen.sh <prompt-file> <out-md> [max_turns] [model]
# Runs the Claude Code loop on Qwen's token-plan Anthropic endpoint with READ-ONLY tools over this repo, so the model
# that plays under the harness can review it citing the code it actually read. Key read at launch from
# QWEN_API_KEY_FILE (default ~/.qwen_cloud_key, mode 600); never written anywhere. Fresh HOME: no plugins, no MCP,
# no user CLAUDE.md. The final answer is written to <out-md>; the full stream to <out-md>.stream.jsonl.
set -euo pipefail
PROMPT_FILE=$1; OUT=$2; MAX_TURNS=${3:-80}; MODEL=${4:-qwen3.8-flash}
KEY_FILE="${QWEN_API_KEY_FILE:-$HOME/.qwen_cloud_key}"
[ -r "$KEY_FILE" ] || { echo "no readable key file at $KEY_FILE" >&2; exit 1; }
perm=$(stat -c %a "$KEY_FILE"); case "$perm" in 600|400) ;; *) echo "$KEY_FILE has mode $perm; make it 600" >&2; exit 1;; esac
REPO=/home/ignaz/github/arc-prize-2026
WORK=$(mktemp -d /tmp/qwen_review.XXXXXX); mkdir -p "$WORK/home"
cd "$REPO"
MARK="${REVIEW_MARKER:-# Review by}"
run_claude() {  # $1 = prompt text, $2 = extra flags
  HOME="$WORK/home" ANTHROPIC_BASE_URL="${QWEN_ANTHROPIC_BASE:-https://token-plan.maas.qwencloudapi.com/apps/anthropic}" \
  ANTHROPIC_AUTH_TOKEN="$(head -n1 "$KEY_FILE" | tr -d '[:space:]')" ANTHROPIC_API_KEY="qwen-token-plan-placeholder" \
  ANTHROPIC_MODEL="$MODEL" ANTHROPIC_DEFAULT_OPUS_MODEL="$MODEL" ANTHROPIC_DEFAULT_SONNET_MODEL="$MODEL" ANTHROPIC_DEFAULT_HAIKU_MODEL="$MODEL" \
  CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 DISABLE_TELEMETRY=1 DISABLE_AUTOUPDATER=1 \
  timeout "${REVIEW_WALL_S:-3600}" claude -p "$1" --model "$MODEL" --strict-mcp-config $2 \
    --allowedTools "Read,Grep,Glob" --disallowedTools "Bash,Write,Edit,MultiEdit,NotebookEdit,WebFetch,WebSearch,Agent,Task" \
    --permission-mode dontAsk --max-turns "$MAX_TURNS" --output-format json < /dev/null
}
run_claude "$(cat "$PROMPT_FILE")" "" > "$WORK/result.json" 2> "$WORK/stderr.log" || true
n=0
while ! python3 -I -c "import json,sys;d=json.load(open(sys.argv[1]));sys.exit(0 if sys.argv[2] in (d.get('result') or '') else 1)" "$WORK/result.json" "$MARK" 2>/dev/null; do
  n=$((n+1)); [ "$n" -gt "${REVIEW_MAX_CONTINUES:-8}" ] && { echo "gave up after $n continuations" >&2; break; }
  echo "continuation $n (no marker yet)" >&2
  run_claude "You stopped before finishing. You wrote a sentence of intent instead of calling a tool, which ends your session. Continue now: call Read/Grep/Glob for what you still need, then write the complete review. Its first line must be '$MARK Qwen3.8-Flash-Next'." "--continue" > "$WORK/result.json" 2>> "$WORK/stderr.log" || true
done
python3 -I - "$WORK/result.json" "$OUT" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); txt=d.get('result') or ''
open(sys.argv[2],'w').write(txt+'\n')
print(f"turns={d.get('num_turns')} subtype={d.get('subtype')} is_error={d.get('is_error')} duration_s={round((d.get('duration_ms') or 0)/1000)} out={sys.argv[2]} chars={len(txt)}")
u=d.get('usage') or {}; print('usage:',{k:u.get(k) for k in ('input_tokens','cache_read_input_tokens','cache_creation_input_tokens','output_tokens')})
PY
cp "$WORK/result.json" "$OUT.result.json"; tail -3 "$WORK/stderr.log" || true
