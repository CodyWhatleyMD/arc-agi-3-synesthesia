#!/bin/bash
# Native vs student for the write-up's slot, computed NOW over every native run that is finished plus the server run
# read where it stands (Cody, 11-09 01:31: finish under the assumption the server run gains no more levels).
# Pre-stated comparison (compare_arm_groups --cluster, runs then games) against the four untimed students.
# Writes notes/writeup/native_final.json in assemble_description.py's field names. Re-run before the final paste.
set -u
K=$HOME/kaggle_local; R=$HOME/github/arc-prize-2026; S=${TMPDIR:-/tmp}/native_now_$$.json
declare -A LOG=( [r5x1b]=$K/vast_runs/r5x1b/run.log [r5x2b]=$K/vast_runs/r5x2b/run.log [r5sb]=$K/server_runs/r5sb_final/stdout.log \
  [r5k1]=$K/kaggle_runs/r5k1/stdout.log [r5k2]=$K/kaggle_runs/r5k2/stdout.log [r5l1]=$K/run_synesthesia_r5l1.log )
# a run counts if its log has a final summary; r5sb's final log is in server_runs/r5sb_final (the VM is off; the refresh below is a no-op)
timeout 90 gcloud compute ssh sakshis-server --zone us-central1-b --tunnel-through-iap --quiet \
  --command 'sudo cat /data/runs/r5sb/working/stdout.log' 2>/dev/null > $K/server_runs/r5sb_live/stdout.log.new \
  && [ -s $K/server_runs/r5sb_live/stdout.log.new ] && mv $K/server_runs/r5sb_live/stdout.log.new $K/server_runs/r5sb_live/stdout.log
have=""; arms=""
for t in r5x1b r5x2b r5k1 r5k2 r5l1 r5sb; do f=${LOG[$t]}; [ -s "$f" ] || continue
  if [ "$t" = r5sb ] || grep -a -E "^ended: " "$f" | tail -1 | grep -q -v "in progress"; then have="$have $t"; arms="$arms $f"; fi; done
CTRL="$K/run_synesthesia_r0c14.log $K/run_synesthesia_r0c14b.log $K/vast_runs/r0x1/run.log $K/vast_runs/r0x2/run.log"
cd $R && nice -n 10 python3 -I scripts/compare_arm_groups.py --arm $arms --control $CTRL --cluster --json $S >/dev/null 2>&1 || { echo "compare FAILED"; exit 2; }
python3 -I - "$S" "$have" $arms > notes/writeup/native_final.json <<'PY'
import json, re, sys, datetime
d = json.load(open(sys.argv[1])); tags = sys.argv[2].split(); logs = sys.argv[3:]
won = []
for f in logs:
    m = [int(x) for x in re.findall(r'runs:\s+25 \(won: (\d+)\)', open(f, errors='replace').read())]; won.append(m[-1] if m else None)
s, l = d['score'], d['levels']; v = s['cluster']['verdict']; verdict = 'NOT RESOLVED' if 'not resolved' in v else v.upper()
w = [x for x in won if x is not None]
out = {"n_native": len(d['arm']), "n_student": len(d['control']),
 "native_mean": round(s['arm_mean'], 2), "student_mean": round(s['control_mean'], 2), "delta_score": round(s['mean_delta'], 2),
 "ci_lo": round(s['cluster']['ci95'][0], 2), "ci_hi": round(s['cluster']['ci95'][1], 2),
 "up": s['arm_better'], "down": s['control_better'], "tied": s['ties'],
 "native_clears": (f"{min(w)} to {max(w)}" if w and min(w) != max(w) else (str(w[0]) if w else "?")),
 "verdict": verdict, "tags": ", ".join(tags), "runs_in": dict(zip(tags, logs)), "native_won_per_run": dict(zip(tags, won)),
 "levels": {"native_mean": l['arm_mean'], "student_mean": l['control_mean'], "delta": l['mean_delta'], "game_ci95": l['ci95'],
            "sign": [l['arm_better'], l['control_better'], l['ties']], "cluster_ci95": l['cluster']['ci95'], "cluster_verdict": l['cluster']['verdict']},
 "score_game_ci95": s['ci95'], "run_means": {"native": s['cluster']['arm_run_means'], "student": s['cluster']['control_run_means']},
 "students": ["r0c14", "r0c14b", "r0x1", "r0x2"],
 "computed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M CST"),
 "note": "r5sb COMPLETE: 25 games, 15 won, mean 58.98, 20 h 49 m; its last game su15 ended by the 5,184-action cap at level 8 of 9 ([finished] line, stdout.log:5260); the uploaded benchmark.json is one periodic write older (5,147 actions) than the log. Kaggle pair (r5k1, r5k2),"}
print(json.dumps(out, indent=1))
PY
echo "native_final.json: runs in:$have"
cp $R/notes/writeup/native_final.json $R/notes/native_final_2026-11-09.json; python3 -c "import json; d=json.load(open('$R/notes/writeup/native_final.json')); print(f\"score {d['delta_score']:+.2f} [{d['ci_lo']:+.2f}, {d['ci_hi']:+.2f}] {d['verdict']} | clears {d['native_clears']} | computed {d['computed_at']}\")"
