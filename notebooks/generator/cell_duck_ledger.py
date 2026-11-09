"""UNTRIED-ACTIONS LEDGER (fix #5 of the 10-01 Opus-vs-Flash-Next comparison, findings 153; from the prototype
notebooks_duck/prototypes_1001/cell_duck_ledger.py). Opt-in: DUCK_LEDGER=1. With DUCK_LEDGER unset or "0" this cell imports
nothing from the harness, patches nothing, and only defines `_ldg*` / `_LDG*` names (shared exec namespace, findings 79).

WHAT THE MODEL GETS: one block inside every user prompt, right after Duck's "end of world model. " line, computed by the
harness from the game's own runtime history (HUD meter lines masked) for the CURRENT level:
  - the valid actions never tried on this level;
  - controls (an action, or a click on one object kind) that had no effect so far but were never tried on a board of the
    current TYPE -- a board type is the set of object kinds on the board, positions ignored. This is the frontier: a
    no-effect result only holds for the board it was tried on. A click on an object lying entirely on a masked HUD line
    is never listed as a gap (its effect is scored with that line masked, so it is always 0; the 10-01 judge's tn36
    noise case) -- it stays in the tried table. (On q25, 81-87% of the controls tried so far were never
    tried on the exact current board at a typical prompt -- the 10-01 challenger's "not selective" -- vs 56-58% on the
    current board type; tests/cmp_fixes/f5-ledger/test_recorded_q25.py.)
  - controls only ever tried as the first move after a start/reset/new level, with no effect (10-01 challenger: in q25,
    18 of 41 such first moves changed nothing; "weak evidence, retest once");
  - object kinds on the board never clicked (click games) / never touched (others) on this level;
  - the moves since the reset that ended in each death, and a warning when the current moves repeat the start of one;
  - repeats of the same control on the same exact board with the same result;
  - a compact table of every tried control: board changes / tries;
  - "No action in your last N prompts." when N >= 3 (10-01 challenger: 66% of q25's calls took no action, streaks of 42-53).
The model is told nothing about what the game is; the block is a record of its own moves.

COST CONTROL (measured on two recorded Kaggle runs of the deployed v5 config, every analyze() call replayed through the
real ToolAgent.analyze() with the shipped 32k trim: tests/cmp_fixes/f5-ledger/cost_f5.json = q25 09-30, cost_f5_B.json = B
10-01; re-measured 10-03 after the review fixes): the block is 257.3 / 254.8 tokens per request on average (median 241 /
231, max 473 / 430; char cap 1000). THAT GROSS
FIGURE is what the model reads on every request; the "net" figures below are smaller only because once the 32k window is
full Duck's trim drops whole old turns to make room -- in lumps: on v10's 1,027 logged requests (review 10-03) 4.8% of
requests lost whole turns, median 2,661 tokens (p90 9,772, max 20,265), 2.4 assistant turns on average (up to 10). Two history
modes, DUCK_LEDGER_HISTORY:
  strip (default)  before Duck persists a turn, every block is cut out of the user messages byte-exactly, so only the
                   newest block is ever in context. Net +63 / +93 prompt tokens per request (+0.3% / +0.4%): once the 32k
                   window is full the block displaces the oldest history (-0.08 / -0.07 assistant turns in the window), and
                   that displacement is persisted -- the persisted history equals vanilla Duck's only while the window is
                   not full. Price: a game's previous user prompt differs from what was sent, so a game's next request never
                   extends its previous one; on the shipped engine at c28 KV saturation that costs nothing (a game's own
                   history ~never hits, findings 154/157); under an unlimited cache (the ceiling KEEP_CKPT's checkpoint
                   retention could reach) it is +2,170 / +1,822 computed tokens per request (+18.5% / +15.0%) -- and the split
                   fix alone already gives own-history hits (findings 160: sf14 0.47), so the generator's =1 picks lazy
                   whenever SPLIT_FIX=1.
  lazy             blocks stay in history exactly as sent until a request is over Duck's budget, then all but the newest
                   are cut first and Duck's trim runs on the result. +276 / +313 per request (+1.3% / +1.5%) on the deployed
                   engine, +1,025 / +1,042 (+8.7% / +8.6%) under an unlimited cache. For a SPLIT_FIX / KEEP_CKPT arm (the
                   generator knob picks it automatically when SPLIT_FIX=1, knobs/f5-ledger.py). The cut keeps the block of the
                   newest user message that HAS one (review 10-03: Duck's "You have not acted yet" follow-up is a later user
                   message without a block, and keeping only the last user message cut the current task prompt's block).

HOOKS (monkeypatch only; the vendored harness is never edited):
  - ToolAgent.analyze (tool_agent.py:1706): per-game state keyed by the runtime-state stem; wraps `step_env` (passed by the
    solver, solver.py:293) to record GAME_OVER action numbers and executed actions. The auto-RESET after a death runs
    outside step_env (solver.py:281), so deaths can only be seen here.
  - ToolAgent._build_user_prompt (:1161): it receives the solver's FULL history (entry 0 = the seed; every action,
    auto-RESETs included, carries frame.step = the action count, the same number step_env reports as action_num).
  - ToolAgent._persistent_history_messages (:1653), strip mode: cut the blocks out before Duck's trim + turn cap.
  - ToolAgent._trim_messages_for_context (:1672), lazy mode: cut all but the newest block when over budget, then trim.
Every hook is wrapped in try/except: a ledger failure prints once per agent and leaves the prompt/history untouched. If
cutting blocks out of the history fails (strip at persist, lazy at trim), the agent stops inserting blocks for the rest of
its game, so the failure reverts to stock prompts instead of piling blocks up in history (review 10-03: 5.5 per request).
HUD LEARNER (review 10-03): a candidate meter line INSIDE the board (not within `band` lines of an edge) is rejected when a
neighbouring line (+-1) changes in at least half of its events -- a meter ticks on its own, a thick moving or growing object
changes its neighbours too (s5i5: a 3-row bar growing along rows 9-11 had rows 9 and 11 and col 9 masked and announced as
HUD; their neighbours co-changed in 78-100% of events, while the real interior meters, sb26/sk48 row 53, 0%). Lines in the
edge band keep the old rule (two-line edge meters ls20 rows 61-62 and sc25 cols 62-63 co-change 100%; vc33 row 0 up to
69%). A one-line object moving inside the board stays indistinguishable from a meter by these statistics.
MEMORY: only the transitions the learner can still use are kept (the last 300 eligible ones and everything after them).
STATS: lazy cuts made while agent._duck_trim_probe is set (f2-wm's dedupe survival probe runs the installed trim chain on a
stand-in prompt) are counted as probe_cuts, not as lazy_cuts / stripped (review 10-03: they polluted the diagnostics).
Knobs: DUCK_LEDGER_HISTORY (strip | lazy), DUCK_LEDGER_MAX_CHARS (1000), DUCK_LEDGER_LOG (jsonl of per-prompt gaps for the
uptake analysis; default <dir of the runtime state>/ledger.jsonl; "0" = no log).
"""
import os as _ldg_os, re as _ldg_re, json as _ldg_json, hashlib as _ldg_hashlib, threading as _ldg_threading, time as _ldg_time, sys as _ldg_sys

_LDG_ON = _ldg_os.environ.get("DUCK_LEDGER", "0") == "1"
try:
    _LDG_MAX_CHARS = int(_ldg_os.environ.get("DUCK_LEDGER_MAX_CHARS", "1000") or "1000")
except ValueError:
    _LDG_MAX_CHARS = None     # refused at install; with the switch off a bad sub-knob must not raise
_LDG_HISTORY = _ldg_os.environ.get("DUCK_LEDGER_HISTORY", "strip").strip() or "strip"   # strip | lazy (see COST CONTROL)
_LDG_HEAD = "Action ledger, level "
_LDG_END = "End of action ledger."
_LDG_ANCHOR = "end of world model. "
_LDG_DIRS = ("UP", "DOWN", "LEFT", "RIGHT")
_LDG_MOUSE = _ldg_re.compile(r"MOUSE\(row=(-?\d+), col=(-?\d+)\)")
_LDG_STEM_RE = _ldg_re.compile(r"_tool_runtime_state$")
_LDG_ORDER = ("head", "untried", "frontier", "swallowed", "table", "kinds", "prefix", "deaths", "repeat", "idle")   # reading order
_LDG_PRIO = ("untried", "frontier", "swallowed", "prefix", "table", "kinds", "idle", "repeat", "deaths")   # survival order under the cap
_ldg_log_lock = _ldg_threading.Lock()


def _ldg_rows_changed(a, b):
    return [r for r in range(min(len(a), len(b))) if a[r] != b[r]]


class _LdgLedger:
    """Pure. E = [(action_display, grid, level, step)] (entry 0 = the seed), deaths = set of steps that hit GAME_OVER."""

    def __init__(self, band=3, min_n=4, frac=0.4, max_cells=3, max_chars=1000, cap=4):
        self.band, self.min_n, self.frac, self.max_cells, self.max_chars, self.cap = band, min_n, frac, max_cells, max_chars, cap
        self.mask = (frozenset(), frozenset())
        self.rec = []
        self.events = {}          # transition k>=1 -> all changed cells [(r, c, A, B)] (eligibility applied at use); pruned
        self._ev_next = 1         # the next transition index to record
        self.kind_cache = {}
        self.fam_cache = {}
        self._last_kinds = []
        self._learned_at = 0

    # ---- HUD = meter lines (greedy, <= 4); prototype logic, validated on q25 by the 10-01 judges ----
    def _learn_mask(self, E, deaths):
        H = len(E[0][1]); W = len(E[0][1][0]) if H else 0
        for k in range(self._ev_next, len(E)):
            a, b = E[k - 1][1], E[k][1]
            self.events[k] = [(r, c, a[r][c], b[r][c]) for r in _ldg_rows_changed(a, b) for c in range(min(len(a[r]), len(b[r])))
                              if a[r][c] != b[r][c]]
        self._ev_next = max(self._ev_next, len(E))
        if self._learned_at and len(E) - self._learned_at < 8:
            return self.mask                     # relearn every 8 actions; the meter does not move between prompts
        ek = [k for k in range(1, len(E)) if k in self.events
              and E[k][0] != "RESET" and E[k][2] == E[k - 1][2] and E[k][3] not in deaths]
        if len(ek) > 300 + 64:   # keep the last 300 eligible transitions + a 64-transition margin before them (a death can
            keep = ek[-300 - 64]  # only make a RECENT transition ineligible later); older ones can never be used again
            for k in [k for k in self.events if k < keep]:
                del self.events[k]
        elig = [(k, self.events[k]) for k in ek[-300:]]
        n = len(elig)
        lines_of = {k: ({r for r, c, A, B in ev}, {c for r, c, A, B in ev}) for k, ev in elig}
        if n < 2:
            return self.mask
        self._learned_at = len(E) if n >= 12 else 0
        picked = []
        for _ in range(4):
            stats = {}
            for k, ev in elig:
                per = {}
                for r, c, A, B in ev:
                    if any((t == "r" and r == i) or (t == "c" and c == i) for t, i in picked):
                        continue
                    per.setdefault(("r", r), []).append((A, B, r, c, k)); per.setdefault(("c", c), []).append((A, B, r, c, k))
                for key, ch in per.items():
                    stats.setdefault(key, []).append(ch)
            best = None
            for key, evs in stats.items():
                m = len(evs)
                if m < 2 or (best is not None and m <= best[0]):
                    continue
                small = sum(1 for ch in evs if len(ch) <= self.max_cells)
                pc = {}
                for ch in evs:
                    for p in {(x[0], x[1]) for x in ch}:
                        pc[p] = pc.get(p, 0) + 1
                dom = max(pc, key=pc.get)
                mono = sum(1 for ch in evs if {(x[0], x[1]) for x in ch} == {dom})
                edge = key[1] < self.band or key[1] >= (H if key[0] == "r" else W) - self.band
                ok = small >= 0.8 * m and (mono >= 0.8 * m or (edge and n >= self.min_n and m >= self.frac * n))
                if ok and not edge:   # inside the board: a neighbour that co-changes in >= half the events = a thick object
                    ax = 0 if key[0] == "r" else 1
                    ks = {ch[0][4] for ch in evs}
                    ok = all(sum(1 for k in ks if key[1] + d in lines_of[k][ax]) < 0.5 * m for d in (-1, 1))
                if ok and self._bar_shaped(E, key, evs[-1][0]):
                    best = (m, key)
            if best is None:
                break
            picked.append(best[1])
        return (frozenset(i for t, i in picked if t == "r"), frozenset(i for t, i in picked if t == "c"))

    def _bar_shaped(self, E, key, x):
        A, B, r, c, k = x
        for g in (E[k][1], E[k - 1][1]):
            comp = self._component(g, r, c, limit=4096)
            if comp is None or comp[1] is None:
                continue
            ys = [y for y, _ in comp[1]]; xs = [x_ for _, x_ in comp[1]]
            h = max(ys) - min(ys) + 1; w = max(xs) - min(xs) + 1
            along, across = (w, h) if key[0] == "r" else (h, w)
            if along >= 8 and across <= 3:
                return True
        return False

    def _sig(self, g):
        mr, mc = self.mask
        rows = [tuple(v for c, v in enumerate(row) if c not in mc) if mc else tuple(row) for r, row in enumerate(g) if r not in mr]
        return _ldg_hashlib.sha1(repr(rows).encode()).hexdigest()[:10]

    def _fam(self, g):
        """Board TYPE: the set of object kinds on the board (positions ignored), HUD masked."""
        key = (hash(g), self.mask)
        hit = self.fam_cache.get(key)
        if hit is None:
            hit = _ldg_hashlib.sha1(repr(sorted(self._kinds(g))).encode()).hexdigest()[:10]
            if len(self.fam_cache) > 4096:
                self.fam_cache.clear()
            self.fam_cache[key] = hit
        return hit

    def _effect(self, a, b):
        mr, mc = self.mask
        n = 0
        for r in _ldg_rows_changed(a, b):
            if r not in mr:
                ra, rb = a[r], b[r]
                n += sum(1 for c in range(min(len(ra), len(rb))) if ra[c] != rb[c] and c not in mc)
        return n

    def _component(self, g, r, c, limit=1200):
        H = len(g); W = len(g[0]) if H else 0
        if not (0 <= r < H and 0 <= c < W):
            return None
        col = g[r][c]; seen = {(r, c)}; st = [(r, c)]
        while st:
            y, x = st.pop()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < H and 0 <= xx < W and (yy, xx) not in seen and g[yy][xx] == col:
                    seen.add((yy, xx)); st.append((yy, xx))
                    if len(seen) > limit:
                        return (col, None)
        return (col, frozenset(seen))

    @staticmethod
    def _kind_of(col, cells):
        if cells is None:
            return f"bg:{col}"
        r0 = min(y for y, _ in cells); c0 = min(x for _, x in cells)
        norm = tuple(sorted((y - r0, x - c0) for y, x in cells))
        return f"{col}:" + _ldg_hashlib.sha1(repr((col, norm)).encode()).hexdigest()[:6]

    @staticmethod
    def _dims(cells):
        if cells is None:
            return "background"
        ys = [y for y, _ in cells]; xs = [x for _, x in cells]
        return f"{max(ys) - min(ys) + 1}x{max(xs) - min(xs) + 1}"

    def update(self, E, deaths):
        new_mask = self._learn_mask(E, deaths)
        if new_mask != self.mask:
            self.mask = new_mask; self.rec = []
        for k in range(len(self.rec) + 1, len(E)):
            act, g, lv, step = E[k]; pa, pg, plv, pstep = E[k - 1]
            m = _LDG_MOUSE.fullmatch(act or "")
            hud = False
            if m:
                rr, cc = int(m.group(1)), int(m.group(2))
                comp = self._component(pg, rr, cc)
                ctl = "MOUSE@" + (self._kind_of(*comp) if comp else "off"); at = (rr, cc)
                dims = self._dims(comp[1]) if comp else "off-board"
                mr, mc = self.mask      # a click on a masked meter line: its effect is scored with that line masked, so always 0
                hud = bool(comp and comp[1] and (mr or mc) and all(y in mr or x in mc for y, x in comp[1]))
            else:
                ctl = (act or "").split("(")[0]; at = None; dims = None
            self.rec.append({"k": k, "step": step, "act": act, "ctl": ctl, "at": at, "dims": dims, "lv": plv, "adv": lv > plv, "hud": hud,
                             "s0": self._sig(pg), "s1": self._sig(g), "f0": self._fam(pg), "eff": self._effect(pg, g),
                             "death": step in deaths, "reset": act == "RESET",
                             "first": k == 1 or pa == "RESET" or lv != plv or pstep in deaths})
        for x in self.rec:          # a death can be recorded after its transition was first seen
            x["death"] = x["step"] in deaths
        return self.rec

    # ---- render ----
    def _glyph(self, col):
        try:
            return _ldg_sys.modules["inference.utils.grid_utils"].ARC_COLOR_CHARS[int(col)]   # the glyph cell patches it: read at call time
        except Exception:
            return str(col)

    def _name(self, ctl, xs):
        if not ctl.startswith("MOUSE@"):
            return ctl
        k = ctl[6:]; x = xs[-1]
        col = k.split(":")[1] if k.startswith("bg:") else k.split(":")[0]
        if k == "off":
            return f"MOUSE off-board at ({x['at'][0]},{x['at'][1]})"
        return f"MOUSE '{self._glyph(col)}' {x['dims']} at ({x['at'][0]},{x['at'][1]})"

    @staticmethod
    def _rle(acts, maxlen=150):
        out = []
        for a in acts:
            a = a.replace("MOUSE(row=", "M(").replace(", col=", ",")
            if out and out[-1][0] == a:
                out[-1][1] += 1
            else:
                out.append([a, 1])
        s = " ".join(a if n == 1 else f"{a}x{n}" for a, n in out)
        return s if len(s) <= maxlen else s[:maxlen - 3] + "..."

    @staticmethod
    def _segments(recs, lv):
        deaths, cur = [], []
        for x in recs:
            if x["lv"] != lv or x["adv"] or x["reset"]:
                cur = []; continue
            cur.append(x)
            if x["death"]:
                deaths.append(cur); cur = []
        return deaths, cur

    def render(self, E, deaths, valid_actions, idle_prompts=0):
        recs = self.update(E, deaths)
        cur_lv = E[-1][2]; cur_sig = self._sig(E[-1][1]); cur_fam = self._fam(E[-1][1])
        lvrecs = [x for x in recs if x["lv"] == cur_lv and not x["adv"]]
        nstates = len({x["s0"] for x in lvrecs} | {x["s1"] for x in lvrecs} | {cur_sig})
        nfams = len({x["f0"] for x in lvrecs} | {cur_fam})
        mr, mc = self.mask
        hud = ([f"rows {','.join(map(str, sorted(mr)))}"] if mr else []) + ([f"cols {','.join(map(str, sorted(mc)))}"] if mc else [])
        hudtxt = ("; HUD " + " and ".join(hud) + " ignored") if hud else ""
        L = {}                      # slot -> line; slots are the reading order, _PRIO the order lines survive the char cap in
        L["head"] = (f"{_LDG_HEAD}{cur_lv} (from your own moves on this level{hudtxt}; board type = the set of object kinds on "
                     f"the board, positions ignored):")
        gaps = {"untried": [], "frontier": [], "swallowed": [], "kinds": [], "repeat": [], "death_prefix": 0}
        va = [v for v in (valid_actions or []) if v and v not in ("RESET", "MOUSE")]
        ctls = list(va)
        for x in lvrecs:
            if not x["reset"] and x["ctl"] not in ctls and x["ctl"] not in ("RESET", ""):
                ctls.append(x["ctl"])
        untried, frontier, swallowed, table = [], [], [], []
        for ctl in ctls:
            xs = [x for x in lvrecs if x["ctl"] == ctl and not x["reset"]]
            if not xs:
                untried.append(ctl); continue
            tries = len(xs); eff = sum(1 for x in xs if x["eff"] > 0)
            here = cur_fam in {x["f0"] for x in xs}
            name = self._name(ctl, xs)
            table.append(((-tries, -eff), f"{name}{'' if here else '*'} {eff}/{tries}"))
            if eff or all(x["hud"] for x in xs):      # clicks only ever on a masked HUD line: a recorded try, never a gap
                continue
            if all(x["first"] for x in xs):
                swallowed.append(name); gaps["swallowed"].append(ctl)
            elif not here:
                nb = len({x["s0"] for x in xs})
                frontier.append(((ctl.startswith("MOUSE@bg:"), nb, -tries), f"{name} ({tries} {'try' if tries == 1 else 'tries'})", ctl))
        gaps["untried"] = list(untried)
        if untried:
            L["untried"] = "Never tried on this level: " + ", ".join(untried) + "."
        if frontier:
            frontier.sort(key=lambda t: t[0])
            gaps["frontier"] = [t[2] for t in frontier[: self.cap]]
            L["frontier"] = ("No effect so far, but never tried on a board of the current type: " + "; ".join(t[1] for t in frontier[: self.cap])
                             + (f"; +{len(frontier) - self.cap} more" if len(frontier) > self.cap else "") + ".")
        if swallowed:
            L["swallowed"] = ("Only ever tried as the first move after a start/reset/new level, with no effect (weak evidence; retest once): "
                              + "; ".join(swallowed) + ".")
        if table:
            table.sort(key=lambda t: t[0])
            k = self.cap + 2
            L["table"] = ("Tried on this level, board changes/tries (* = never on a board of the current type): " + "; ".join(t for _, t in table[:k])
                          + (f"; +{len(table) - k} more" if len(table) > k else "") + ".")
        click_game = "MOUSE" in (valid_actions or [])
        nk = self._new_kinds(E, recs, cur_lv, click_game)
        if nk:
            gaps["kinds"] = list(self._last_kinds)
            L["kinds"] = (("Objects on the board never clicked on this level: " if click_game else
                           "Objects never touched on this level (nothing changed within one cell of them): ") + "; ".join(nk) + ".")
        dsegs, cur = self._segments(recs, cur_lv)
        if dsegs:
            ca = [x["act"] for x in cur]
            if ca:
                for j, sg in enumerate(dsegs):
                    acts = [x["act"] for x in sg]
                    if len(ca) < len(acts) and acts[: len(ca)] == ca:
                        L["prefix"] = (f"Your {len(ca)} move{'s' if len(ca) > 1 else ''} since the last reset repeat{'' if len(ca) > 1 else 's'} the start of death #{j + 1}, which continued "
                                       f"{self._rle(acts[len(ca):], 60)} and died.")
                        gaps["death_prefix"] = 1
                        break
            shown = dsegs[-3:]; off = len(dsegs) - len(shown)
            L["deaths"] = (f"Deaths on this level ({len(dsegs)}), moves since the reset: "
                           + " | ".join(f"#{off + i + 1} ({len(sg)}): {self._rle([x['act'] for x in sg], 90)}" for i, sg in enumerate(shown)) + ".")
        rep = {}
        for x in lvrecs:
            if x["ctl"] not in _LDG_DIRS and not x["reset"] and not x["hud"]:
                rep.setdefault((x["ctl"], x["s0"]), []).append(x)
        agg = {}                    # per control: [tries in same-board same-result groups, boards, the records]
        for (ctl, _s0), v in rep.items():
            if len(v) >= 2 and len({y["s1"] for y in v}) == 1:
                t = agg.setdefault(ctl, [0, 0, v]); t[0] += len(v); t[1] += 1; t[2] = v
        if agg:
            reps = sorted(agg.items(), key=lambda kv: -kv[1][0])
            gaps["repeat"] = [k for k, _ in reps]
            spots = {}   # a click control is an object KIND: say so when the repeats hit several objects of that kind
            for (ctl, _s0), v in rep.items():
                if ctl in agg and len(v) >= 2 and len({y["s1"] for y in v}) == 1:
                    spots.setdefault(ctl, set()).update(y["at"] for y in v)
            L["repeat"] = ("Repeated on the same exact board with the same result: "
                           + "; ".join(f"{self._name(k, t[2])}" + (f" (same kind, {len(spots[k])} different spots)" if len(spots.get(k, ())) > 1 else "")
                                       + f" {t[0]} times" + (f" on {t[1]} boards" if t[1] > 1 else "") for k, t in reps[:3]) + ".")
        if idle_prompts >= 3:
            L["idle"] = f"No action in your last {idle_prompts} prompts."
        tail = f"A no-effect result holds only for the board it was tried on. {_LDG_END}"
        n, kept = len(L["head"]) + len(tail) + 2, {"head"}
        for slot in _LDG_PRIO:              # a line that does not fit the cap is dropped whole
            if slot in L and n + len(L[slot]) + 1 <= self.max_chars:
                kept.add(slot); n += len(L[slot]) + 1
        text = "\n".join([L[s] for s in _LDG_ORDER if s in kept] + [tail])
        return text, {"chars": len(text), "nstates": nstates, "nfams": nfams, "mask": [sorted(mr), sorted(mc)], "gaps": gaps,
                      "lines": sorted(kept), "dropped": sorted(set(L) - kept)}

    def _objects(self, g):
        H = len(g); W = len(g[0]) if H else 0; seen = [[False] * W for _ in range(H)]; out = []
        for r in range(H):
            row = g[r]
            for c in range(min(W, len(row))):
                if seen[r][c]:
                    continue
                col = row[c]; cells = [(r, c)]; seen[r][c] = True; i = 0
                while i < len(cells):
                    y, x = cells[i]; i += 1
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < H and 0 <= xx < len(g[yy]) and xx < W and not seen[yy][xx] and g[yy][xx] == col:
                            seen[yy][xx] = True; cells.append((yy, xx))
                out.append((col, cells))
        return out

    def _kinds(self, g):
        key = hash(g)
        hit = self.kind_cache.get(key)
        if hit is not None and hit[0] == self.mask:
            return hit[1]
        res = {}
        mr, mc = self.mask
        for col, cells in self._objects(g):
            if len(cells) > 400 or any(y in mr or x in mc for y, x in cells):
                continue
            ys = [y for y, _ in cells]; xs = [x for _, x in cells]
            if max(ys) - min(ys) >= 32 or max(xs) - min(xs) >= 32:
                continue                          # frames, walls, outlines: not things to click
            k = self._kind_of(col, frozenset(cells))
            res.setdefault(k, []).append((min(ys), min(xs), max(ys), max(xs), len(cells), cells[len(cells) // 2]))
        if len(self.kind_cache) > 64:
            self.kind_cache.clear()
        self.kind_cache[key] = (self.mask, res)
        return res

    def _new_kinds(self, E, recs, lv, click_game):
        first, last = {}, {}
        for k in range(len(E)):
            first.setdefault(E[k][2], k); last[E[k][2]] = k
        old = set()
        for L in first:
            if L < lv:
                old |= set(self._kinds(E[first[L]][1])) | set(self._kinds(E[last[L]][1]))
        at_start = set(self._kinds(E[first[lv]][1])) if lv in first else set()
        g = E[-1][1]; W = len(g[0]) if g else 0; mr, mc = self.mask
        heat, clicked = set(), set()
        for x in recs:
            if x["lv"] != lv:
                continue
            if x["ctl"].startswith("MOUSE@"):
                clicked.add(x["ctl"][6:])
            if not click_game and x["eff"] > 0:
                a = E[x["k"] - 1][1]; b = E[x["k"]][1]
                for r in _ldg_rows_changed(a, b):
                    if r not in mr:
                        heat.update((r, c) for c in range(min(W, len(a[r]), len(b[r]))) if a[r][c] != b[r][c] and c not in mc)
        out = []
        for k, inst in self._kinds(g).items():
            if k in clicked:
                continue
            free = inst if click_game else [i for i in inst if not any((y, x) in heat for y in range(i[0] - 1, i[2] + 2) for x in range(i[1] - 1, i[3] + 2))]
            if not free:
                continue
            appeared = k not in at_start; new = k not in old
            if lv == 1 and not appeared and len(inst) > 6:
                continue
            r0, c0, r1, c1, n, cell = free[0]
            tag = " (appeared this level)" if appeared else (" (new this level)" if new and lv > 1 else "")
            out.append((not appeared, not new, len(inst), n, f"'{self._glyph(k.split(':')[0])}' {r1 - r0 + 1}x{c1 - c0 + 1}"
                        + (f" x{len(inst)}" if len(inst) > 1 else "") + f" at ({cell[0]},{cell[1]}){tag}", k))
        out.sort(key=lambda t: t[:4])
        self._last_kinds = [t[5] for t in out[: self.cap + 1]]
        return [t[4] for t in out[: self.cap + 1]]


# ------------------------------------------------------------------ text helpers (pure) ------------------------------------------------------------------
def _ldg_insert(prompt, block):
    """Put the block right after Duck's world-model anchor (or at the end); _ldg_strip undoes it exactly."""
    if _LDG_ANCHOR in prompt:
        i = prompt.index(_LDG_ANCHOR) + len(_LDG_ANCHOR)
        return prompt[:i] + "\n" + block + "\n" + prompt[i:]
    return prompt + "\n" + block + "\n"


def _ldg_strip(text):
    """Remove every block exactly as _ldg_insert added it (the leading and the trailing newline go with it). Each END is
    paired with the NEAREST head line before it, so a stray line that merely starts like a head earlier in the prompt (a
    shim that renders multi-line model text above the anchor) is never cut together with the text that follows it; an END
    with no head before it is left alone."""
    if _LDG_END not in text:
        return text
    out, i = [], 0
    while True:
        e = text.find(_LDG_END, i)
        if e < 0:
            break
        j = text.rfind("\n" + _LDG_HEAD, i, e)
        e += len(_LDG_END)
        if j < 0:
            out.append(text[i:e]); i = e
            continue
        if text.startswith("\n", e):
            e += 1
        out.append(text[i:j]); i = e
    out.append(text[i:])
    return "".join(out)


def _ldg_strip_messages(messages, keep_last=False):
    """Cut every block out of the user messages (keep_last: except the block of the newest user message that HAS one -- a
    later follow-up user message without a block must not cost the current prompt its block). New dicts; input untouched."""
    out, n = [], 0
    last = max((i for i, m in enumerate(messages) if isinstance(m, dict) and m.get("role") == "user" and _LDG_END in str(m.get("content"))),
               default=-1) if keep_last else -1
    for i, m in enumerate(messages):
        if isinstance(m, dict) and m.get("role") == "user" and i != last:
            c = m.get("content")
            if isinstance(c, str) and _LDG_END in c:
                m = {**m, "content": _ldg_strip(c)}; n += 1
            elif isinstance(c, list):
                parts = []
                for p in c:
                    if isinstance(p, dict) and isinstance(p.get("text"), str) and _LDG_END in p["text"]:
                        p = {**p, "text": _ldg_strip(p["text"])}; n += 1
                    parts.append(p)
                m = {**m, "content": parts}
        out.append(m)
    return out, n


# ------------------------------------------------------------------ hooks ------------------------------------------------------------------
_ldg_stats = {"prompts": 0, "blocks": 0, "stripped": 0, "lazy_cuts": 0, "errors": 0, "chars": 0, "ms": 0.0}


def _ldg_log(agent, rec):
    path = _ldg_os.environ.get("DUCK_LEDGER_LOG")
    if path == "0":
        return
    path = path or _ldg_os.path.join(str(agent.__dict__.get("_ldg_art") or "."), "ledger.jsonl")
    try:
        with _ldg_log_lock, open(path, "a") as fh:
            fh.write(_ldg_json.dumps(rec, default=list) + "\n")
    except Exception:
        pass


def _ldg_fail(agent, where, e):
    _ldg_stats["errors"] += 1
    if where in ("persist", "trim"):   # history can no longer be cleaned: stop adding blocks (revert to stock prompts)
        agent.__dict__["_ldg_off"] = True
    if not agent.__dict__.get("_ldg_failed"):
        agent.__dict__["_ldg_failed"] = True
        print(f"LEDGER: {where} error {type(e).__name__}: {e} (prompt/history left unmodified; printed once per agent)", flush=True)


def _ldg_game_state(agent, stem):
    """Per-game state on the agent (one ToolAgent per game-pass, solver.py:1223; reset anyway if the stem changes)."""
    d = agent.__dict__
    if d.get("_ldg_for") != stem:
        d["_ldg_for"] = stem
        d["_ldg"] = None; d["_ldg_deaths"] = set(); d["_ldg_idle"] = 0; d["_ldg_failed"] = False; d["_ldg_off"] = False
    return d


def _ldg_wrap_analyze(orig):
    def analyze(self, state_path, *a, **k):
        d = self.__dict__
        try:
            stem = _LDG_STEM_RE.sub("", _ldg_os.path.splitext(_ldg_os.path.basename(str(state_path)))[0])
            _ldg_game_state(self, stem)
            d["_ldg_art"] = _ldg_os.path.dirname(str(state_path))
            d["_ldg_acted"] = False
            se = k.get("step_env") if "step_env" in k else (a[2] if len(a) > 2 else None)
            if se is not None and not getattr(se, "_ldg_wrapped", False):
                def step_env(arguments, _se=se, _d=d):
                    p = _se(arguments)
                    try:
                        if isinstance(p, dict) and p.get("executed"):
                            _d["_ldg_acted"] = True; _d["_ldg_idle"] = 0
                            if p.get("game_over"):
                                _d.setdefault("_ldg_deaths", set()).add(int(p.get("action_num") or 0))
                    except Exception:
                        pass
                    return p
                step_env._ldg_wrapped = True
                if "step_env" in k:
                    k["step_env"] = step_env
                else:
                    a = a[:2] + (step_env,) + a[3:]
        except Exception as e:
            _ldg_fail(self, "analyze", e)
        res = orig(self, state_path, *a, **k)
        try:   # idle = prompts the model answered without acting; a retryable failure / early exit was never answered
            if not d.get("_ldg_acted") and res is not None and not getattr(res, "retryable_failure", False):
                d["_ldg_idle"] = int(d.get("_ldg_idle", 0) or 0) + 1
        except Exception:
            pass
        return res
    return analyze


def _ldg_wrap_prompt(orig):
    def _build_user_prompt(self, action_num, *a, **k):
        r = orig(self, action_num, *a, **k)
        try:
            hist = k.get("history_entries")
            if not isinstance(r, str) or not hist or any(h.frame is None or not h.frame.grid for h in hist):
                return r
            d = self.__dict__
            if d.get("_ldg_off"):
                return r
            if "_ldg_for" not in d:
                _ldg_game_state(self, None)
            E = [(str(h.action or ""), h.frame.grid, int(h.frame.level), int(h.frame.step)) for h in hist]
            led = d.get("_ldg")
            if led is None:
                led = d["_ldg"] = _LdgLedger(max_chars=_LDG_MAX_CHARS)
            va = _ldg_ta._normalize_valid_actions(k.get("valid_actions"))
            t0 = _ldg_time.time()
            text, st = led.render(E, set(d.get("_ldg_deaths") or ()), va, int(d.get("_ldg_idle", 0) or 0))
            ms = round(1000 * (_ldg_time.time() - t0), 1)
            _ldg_stats["prompts"] += 1; _ldg_stats["blocks"] += 1; _ldg_stats["chars"] += st["chars"]; _ldg_stats["ms"] += ms
            _ldg_log(self, {"stem": d.get("_ldg_for"), "action_num": action_num, "level": E[-1][2], "ms": ms, "chars": st["chars"],
                            "nstates": st["nstates"], "nfams": st["nfams"], "mask": st["mask"], "gaps": st["gaps"],
                            "idle": int(d.get("_ldg_idle", 0) or 0)})
            return _ldg_insert(r, text)
        except Exception as e:
            _ldg_fail(self, "prompt", e)
            return r
    return _build_user_prompt


def _ldg_wrap_persist(orig):
    def _persistent_history_messages(self, messages, *a, **k):
        try:
            messages, n = _ldg_strip_messages(messages)
            _ldg_stats["stripped"] += n
        except Exception as e:
            _ldg_fail(self, "persist", e)
        return orig(self, messages, *a, **k)
    return _persistent_history_messages


def _ldg_wrap_trim(orig):
    """DUCK_LEDGER_HISTORY=lazy: old blocks stay in history byte-identical to what was sent (a game's prompts stay pure
    extensions of each other, so a cross-turn prefix-cache hit stays possible) until the request is over Duck's budget,
    i.e. exactly when Duck's own trim would change the front of the prompt anyway; then every block but the newest is cut
    first, and Duck's trim runs on the result."""
    def _trim_messages_for_context(self, messages, *a, **k):
        try:
            if messages and sum(1 for m in messages if isinstance(m, dict) and m.get("role") == "user"
                                and _LDG_END in str(m.get("content"))) > 1:
                extra = k.get("extra_safety_tokens", 0) or 0
                budget = max(1, int(self._context_budget_tokens) - max(0, int(extra)))
                if self._estimate_request_input_tokens(list(messages), tools=k.get("tools")) > budget:
                    messages, n = _ldg_strip_messages(messages, keep_last=True)
                    if self.__dict__.get("_duck_trim_probe"):   # f2-wm's dedupe survival probe: same cut, not a real request
                        _ldg_stats["probe_cuts"] = _ldg_stats.get("probe_cuts", 0) + 1
                    else:
                        _ldg_stats["stripped"] += n; _ldg_stats["lazy_cuts"] += 1
        except Exception as e:
            _ldg_fail(self, "trim", e)
        return orig(self, messages, *a, **k)
    return _trim_messages_for_context


def _ldg_install():
    """All-or-nothing: every check and every wrapper is built before the first ToolAgent attribute is replaced."""
    global _ldg_ta
    if _LDG_HISTORY not in ("strip", "lazy"):
        raise ValueError(f"DUCK_LEDGER_HISTORY must be strip or lazy, got {_LDG_HISTORY!r}")
    if _LDG_MAX_CHARS is None:
        raise ValueError(f"DUCK_LEDGER_MAX_CHARS must be an integer, got {_ldg_os.environ.get('DUCK_LEDGER_MAX_CHARS')!r}")
    import inference.agent.tool_agent as ta
    T = ta.ToolAgent
    if getattr(T, "_ldg_installed", False):
        print("LEDGER: already installed (second exec ignored)", flush=True)
        return
    ta._normalize_valid_actions       # read at call time by the prompt wrapper: must exist now
    w = {"analyze": _ldg_wrap_analyze(T.analyze), "_build_user_prompt": _ldg_wrap_prompt(T._build_user_prompt)}
    if _LDG_HISTORY == "strip":
        w["_persistent_history_messages"] = _ldg_wrap_persist(T._persistent_history_messages)
    else:
        w["_trim_messages_for_context"] = _ldg_wrap_trim(T._trim_messages_for_context)
    _ldg_ta = ta
    for name, fn in w.items():
        setattr(T, name, fn)
    T._ldg_installed = True
    ta._ldg_stats = _ldg_stats
    print(f"LEDGER INSTALLED: action ledger in every user prompt (<= {_LDG_MAX_CHARS} chars, after the world-model anchor; history="
          f"{_LDG_HISTORY}: " + ("cut out of history before Duck persists a turn" if _LDG_HISTORY == "strip" else
          "kept in history as sent until a request is over budget, then all but the newest cut") + "); log "
          f"{_ldg_os.environ.get('DUCK_LEDGER_LOG') or '<artifacts>/ledger.jsonl'}", flush=True)


if _LDG_ON:
    try:
        _ldg_install()
    except Exception as _ldg_e:
        if not bool(globals().get("TRUE_SUBMISSION", False)):   # a validation / quota run fails loudly
            raise
        print(f"LEDGER: NOT INSTALLED ({type(_ldg_e).__name__}: {_ldg_e}) -- TRUE_SUBMISSION: the shipped harness runs unchanged",
              flush=True)
else:
    print("LEDGER: off (DUCK_LEDGER != 1)", flush=True)
