"""COVERAGE LEDGER for the Duck harness (prototype, 10-01; design: affordance + attempt coverage pushed into each prompt).

What it does: at the start of every analyzer turn, compute -- from Duck's own runtime history, with HUD meter lines
masked -- a short block that says, for the CURRENT level: which actions and which clicked object kinds were tried, in how
many distinct board states, with what effect; which no-effect controls were never tried in the current state; which
actions are untried; which object kinds on the board were never clicked (click games) or never touched (others);
repeated identical attempts (same control, same state, same result); the move sequences that ended in each death, and a
warning when the moves since the last reset repeat the start of one. It ends with one sentence: a no-effect result holds
only for the state you tested. The model is told nothing about what the game IS; the ledger is a record of its own moves.

Why: Flash-Next voiced the decisive untested pair and then ran it in the wrong state, or never generated it (findings
88: most actions are spent after the last clear). natives-v2 `tried()` hashes the whole board including the timer, and
matches clicks by their coordinate string, so it never matches (findings 151). This puts the coverage table in front of
the model instead of asking it to compute one.

Mechanism (monkeypatch only; the vendored harness stays byte-identical; shared exec namespace -> every name `_ldg_*`):
  - ToolAgent.analyze (tool_agent.py:1706): wrap `step_env` to record GAME_OVER action numbers (the auto-RESET that
    follows a death runs outside step_env, solver.py:281) and reset the model-call counter on every executed action.
  - ToolAgent._build_user_prompt (:1161): it already receives the FULL history (solver.py:693 appends every action,
    auto-RESETs included; entry 0 is the seed). Insert the ledger after "end of world model. ".
  - ToolAgent._persistent_history_messages (:1653): replace every ledger block in the persisted history with a one-line
    stub BEFORE the token trim, so only the newest ledger ever costs context (30 turns x ~260 tokens otherwise).
  - ToolAgent._chat_completion (:1282): count model calls since the last executed action (shown only when >= 3).
Every hook is wrapped in try/except: a ledger failure logs once per agent and returns the unmodified prompt.
Enable with DUCK_LEDGER=1 (default off; when off this cell patches NOTHING). Knobs: DUCK_LEDGER_MAX_CHARS (1200),
DUCK_LEDGER_LOG (jsonl of per-turn gaps for the A/B uptake analysis; default <artifacts>/ledger.jsonl).
"""
import os as _ldg_os, re as _ldg_re, json as _ldg_json, hashlib as _ldg_hashlib, threading as _ldg_threading, time as _ldg_time
import inference.agent.tool_agent as _ldg_ta

_LDG_ON = _ldg_os.environ.get("DUCK_LEDGER", "0") == "1"
_LDG_MAX_CHARS = int(_ldg_os.environ.get("DUCK_LEDGER_MAX_CHARS", "1200"))
_LDG_HEAD = "Coverage ledger ("
_LDG_END = "End of coverage ledger."
_LDG_STUB = "\n"   # an old ledger is stale state, not history: removed outright (30 one-line stubs would still cost ~600 tokens)
_LDG_STUB_RE = _ldg_re.compile(r"\n?" + _ldg_re.escape(_LDG_HEAD) + r".*?" + _ldg_re.escape(_LDG_END) + r"\n?", _ldg_re.S)
_LDG_ANCHOR = "end of world model. "
_LDG_DIRS = ("UP", "DOWN", "LEFT", "RIGHT")
_LDG_MOUSE = _ldg_re.compile(r"MOUSE\(row=(-?\d+), col=(-?\d+)\)")
_ldg_log_lock = _ldg_threading.Lock()


def _ldg_rows_changed(a, b):
    return [r for r in range(min(len(a), len(b))) if a[r] != b[r]]


class _LdgLedger:
    """Pure: E = [(action_display, grid, level)] (entry 0 = seed), deaths = set of history indices that hit GAME_OVER."""

    def __init__(self, band=3, min_n=4, frac=0.4, max_cells=3, max_chars=1200, cap=4):
        self.band, self.min_n, self.frac, self.max_cells, self.max_chars, self.cap = band, min_n, frac, max_cells, max_chars, cap
        self.mask = (frozenset(), frozenset())
        self.rec = []
        self.events = []          # per transition k>=1: [(r, c, A, B)] (all changed cells; eligibility applied at use)
        self.kind_cache = {}
        self._last_kinds = []
        self._learned_at = 0

    # ---- HUD = meter lines (greedy, <= 4) ----
    def _learn_mask(self, E, deaths):
        H = len(E[0][1]); W = len(E[0][1][0]) if H else 0
        for k in range(len(self.events) + 1, len(E)):
            a, b = E[k - 1][1], E[k][1]
            self.events.append([(r, c, a[r][c], b[r][c]) for r in _ldg_rows_changed(a, b) for c in range(W) if a[r][c] != b[r][c]])
        if self._learned_at and len(E) - self._learned_at < 8:
            return self.mask                     # relearn every 8 actions; the meter does not move between prompts
        elig = [(k, self.events[k - 1]) for k in range(1, len(E))
                if E[k][0] != "RESET" and E[k][2] == E[k - 1][2] and k not in deaths][-300:]
        n = len(elig)
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

    def _effect(self, a, b):
        mr, mc = self.mask
        n = 0
        for r in _ldg_rows_changed(a, b):
            if r not in mr:
                ra, rb = a[r], b[r]
                n += sum(1 for c in range(len(ra)) if ra[c] != rb[c] and c not in mc)
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
            act, g, lv = E[k]; pa, pg, plv = E[k - 1]
            m = _LDG_MOUSE.fullmatch(act or "")
            if m:
                rr, cc = int(m.group(1)), int(m.group(2))
                comp = self._component(pg, rr, cc)
                ctl = "MOUSE@" + (self._kind_of(*comp) if comp else "off"); at = (rr, cc)
                dims = self._dims(comp[1]) if comp else "off-board"
            else:
                ctl = (act or "").split("(")[0]; at = None; dims = None
            self.rec.append({"k": k, "act": act, "ctl": ctl, "at": at, "dims": dims, "lv": plv, "adv": lv > plv,
                             "s0": self._sig(pg), "s1": self._sig(g), "eff": self._effect(pg, g), "death": k in deaths,
                             "reset": act == "RESET", "first": k == 1 or pa == "RESET" or lv != plv or (k - 1) in deaths})
        for x in self.rec:          # a death can be recorded after its transition was first seen
            x["death"] = x["k"] in deaths
        return self.rec

    # ---- render ----
    def _glyph(self, col):
        try:
            import inference.utils.grid_utils as _gu        # patched by the glyph cell at load time: read at call time
            return _gu.ARC_COLOR_CHARS[int(col)]
        except Exception:
            return str(col)

    def _name(self, ctl, xs):
        if not ctl.startswith("MOUSE@"):
            return ctl
        k = ctl[6:]; x = xs[-1]
        col = k.split(":")[1] if k.startswith("bg:") else k.split(":")[0]
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

    def render(self, E, deaths, valid_actions, calls_since_action=0):
        recs = self.update(E, deaths)
        cur_lv = E[-1][2]; cur_sig = self._sig(E[-1][1])
        lvrecs = [x for x in recs if x["lv"] == cur_lv and not x["adv"]]
        sid = {}
        for x in lvrecs:
            for s in (x["s0"], x["s1"]):
                sid.setdefault(s, f"S{len(sid) + 1}")
        sid.setdefault(cur_sig, f"S{len(sid) + 1}")
        cur_id = sid[cur_sig]
        mr, mc = self.mask
        hud = ([f"rows {','.join(map(str, sorted(mr)))}"] if mr else []) + ([f"cols {','.join(map(str, sorted(mc)))}"] if mc else [])
        hudtxt = ("HUD " + " and ".join(hud) + " ignored") if hud else "no HUD found"
        lines = [f"{_LDG_HEAD}computed by the harness from your own moves on level {cur_lv}; {hudtxt}): "
                 f"the board is now state {cur_id}, {len(sid)} distinct states seen this level."]
        gaps = {"untried": [], "retest": [], "swallowed": [], "kinds": [], "repeat": [], "death_prefix": 0}
        va = [v for v in (valid_actions or []) if v and v not in ("RESET", "MOUSE")]
        ctls = list(va)
        for x in lvrecs:
            if x["ctl"].startswith("MOUSE@") and x["ctl"] not in ctls:
                ctls.append(x["ctl"])
        untried, retest, swallowed, noeff_here, worked = [], [], [], [], []
        for ctl in ctls:
            xs = [x for x in lvrecs if x["ctl"] == ctl and not x["reset"]]
            if not xs:
                untried.append(ctl); gaps["untried"].append(ctl); continue
            tries = len(xs); states = len({x["s0"] for x in xs}); eff = sum(1 for x in xs if x["eff"] > 0)
            name = self._name(ctl, xs)
            if eff:
                worked.append((-eff, f"{name} {eff}/{tries}")); continue
            here = sum(1 for x in xs if x["s0"] == cur_sig)
            tag = f"{name} [{tries} tries, {states} states]"
            if all(x["first"] for x in xs):
                swallowed.append(tag); gaps["swallowed"].append(ctl)
            elif here:
                noeff_here.append(f"{name} x{here}")
            else:
                retest.append(((ctl.startswith("MOUSE@bg:"), states, -tries), tag, ctl))   # objects before background; fewest states first
        if untried:
            lines.append("Untried on this level: " + ", ".join(untried) + ".")
        if swallowed:
            lines.append("Only ever tried as the first action after a start/RESET/level change, with no effect (one such try is weak evidence; retest once): "
                         + "; ".join(swallowed) + ".")
        if retest:
            retest.sort(key=lambda t: t[0])
            gaps["retest"] = [t[2] for t in retest[: self.cap]]
            lines.append(f"No effect so far, but never tried in the current state {cur_id}: " + "; ".join(t[1] for t in retest[: self.cap])
                         + (f"; +{len(retest) - self.cap} more" if len(retest) > self.cap else "") + ".")
        dsegs, cur = self._segments(recs, cur_lv)
        if dsegs:
            shown = dsegs[-3:]; off = len(dsegs) - len(shown)
            lines.append(f"Deaths on this level ({len(dsegs)}), moves since the reset: "
                         + " | ".join(f"#{off + i + 1} ({len(s)}): {self._rle([x['act'] for x in s], 90)}" for i, s in enumerate(shown)) + ".")
            ca = [x["act"] for x in cur]
            if ca:
                for j, s in enumerate(dsegs):
                    acts = [x["act"] for x in s]
                    if len(ca) < len(acts) and acts[: len(ca)] == ca:
                        lines.append(f"Your {len(ca)} moves since the last reset repeat the start of death #{j + 1}, which continued "
                                     f"{self._rle(acts[len(ca):], 60)} and died.")
                        gaps["death_prefix"] = 1
                        break
        rep = {}
        for x in lvrecs:
            if x["ctl"] not in _LDG_DIRS and not x["reset"]:
                rep.setdefault((x["ctl"], x["s0"]), []).append(x)
        reps = sorted(((k, v) for k, v in rep.items() if len(v) >= 2 and len({y["s1"] for y in v}) == 1), key=lambda kv: -len(kv[1]))
        if reps:
            gaps["repeat"] = [k for k, _ in reps]
            lines.append("Repeated identical attempts (same action, same state, same result): "
                         + "; ".join(f"{self._name(k[0], v)} in {sid.get(k[1], '?')} x{len(v)}" for k, v in reps[:3]) + ".")
        click_game = "MOUSE" in (valid_actions or [])
        nk = self._new_kinds(E, recs, cur_lv, click_game)
        if nk:
            gaps["kinds"] = list(self._last_kinds)
            lines.append(("Objects on the board never clicked on this level: " if click_game else
                          "Objects never touched on this level (nothing changed within one cell of them): ") + "; ".join(nk) + ".")
        if noeff_here:
            lines.append(f"Already no effect in this exact state {cur_id}: " + "; ".join(noeff_here[: self.cap]) + ".")
        if worked:
            worked.sort(key=lambda t: t[0])
            lines.append("Changed the board (effect/tries): " + "; ".join(t for _, t in worked[: self.cap])
                         + (f"; +{len(worked) - self.cap} more" if len(worked) > self.cap else "") + ".")
        if calls_since_action >= 3:
            lines.append(f"{calls_since_action} model calls since your last action.")
        tail = f"A no-effect result holds only for the state you tested. {_LDG_END}"
        keep, n = [], len(tail) + 1
        for ln in lines:
            if n + len(ln) + 1 > self.max_chars:
                keep.append(ln[: max(0, self.max_chars - n - 5)] + " ..."); break
            keep.append(ln); n += len(ln) + 1
        keep.append(tail)
        text = "\n".join(keep)
        return text, {"chars": len(text), "state": cur_id, "nstates": len(sid), "mask": [sorted(mr), sorted(mc)], "gaps": gaps}

    def _objects(self, g):
        H = len(g); W = len(g[0]) if H else 0; seen = [[False] * W for _ in range(H)]; out = []
        for r in range(H):
            for c in range(W):
                if seen[r][c]:
                    continue
                col = g[r][c]; cells = [(r, c)]; seen[r][c] = True; i = 0
                while i < len(cells):
                    y, x = cells[i]; i += 1
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < H and 0 <= xx < W and not seen[yy][xx] and g[yy][xx] == col:
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
                        heat.update((r, c) for c in range(W) if a[r][c] != b[r][c] and c not in mc)
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


# ------------------------------------------------------------------ hooks ------------------------------------------------------------------
def _ldg_log(agent, rec):
    path = _ldg_os.environ.get("DUCK_LEDGER_LOG") or (str(agent.__dict__.get("_ldg_art") or ".") + "/ledger.jsonl")
    try:
        with _ldg_log_lock, open(path, "a") as fh:
            fh.write(_ldg_json.dumps(rec, default=list) + "\n")
    except Exception:
        pass

def _ldg_fail(agent, where, e):
    if not agent.__dict__.get("_ldg_failed"):
        agent.__dict__["_ldg_failed"] = True
        print(f"LEDGER: {where} error {type(e).__name__}: {e} (prompt left unmodified; logged once per agent)", flush=True)

def _ldg_wrap_analyze(orig):
    def analyze(self, state_path, *a, **k):
        try:
            self.__dict__["_ldg_art"] = str(_ldg_os.path.dirname(str(state_path)))
            self.__dict__["_ldg_stem"] = _ldg_re.sub(r"_tool_runtime_state$", "", _ldg_os.path.splitext(_ldg_os.path.basename(str(state_path)))[0])
            self.__dict__.setdefault("_ldg_deaths", set())
            se = k.get("step_env", a[2] if len(a) > 2 else None)
            if se is not None and not getattr(se, "_ldg_wrapped", False):
                def step_env(arguments, _se=se, _self=self):
                    p = _se(arguments)
                    try:
                        if isinstance(p, dict) and (p.get("executed") or p.get("executed_count")):
                            _self.__dict__["_ldg_calls"] = 0
                            if p.get("game_over"):
                                _self.__dict__.setdefault("_ldg_deaths", set()).add(int(p.get("action_num") or 0))
                    except Exception:
                        pass
                    return p
                step_env._ldg_wrapped = True
                if "step_env" in k or len(a) <= 2:
                    k["step_env"] = step_env
                else:
                    a = a[:2] + (step_env,) + a[3:]
        except Exception as e:
            _ldg_fail(self, "analyze", e)
        return orig(self, state_path, *a, **k)
    return analyze

def _ldg_wrap_prompt(orig):
    def _build_user_prompt(self, action_num, *a, **k):
        r = orig(self, action_num, *a, **k)
        try:
            hist = k.get("history_entries") or []
            if not isinstance(r, str) or len(hist) < 1:
                return r
            E = [(str(h.action or ""), h.frame.grid, int(h.frame.level)) for h in hist if h.frame is not None and h.frame.grid]
            if not E:
                return r
            led = self.__dict__.get("_ldg")
            if led is None or self.__dict__.get("_ldg_for") != self.__dict__.get("_ldg_stem"):
                led = self.__dict__["_ldg"] = _LdgLedger(max_chars=_LDG_MAX_CHARS)
                self.__dict__["_ldg_for"] = self.__dict__.get("_ldg_stem")
            va = _ldg_ta._normalize_valid_actions(k.get("valid_actions"))
            t0 = _ldg_time.time()
            text, st = led.render(E, set(self.__dict__.get("_ldg_deaths", set())), va, int(self.__dict__.get("_ldg_calls", 0) or 0))
            _ldg_log(self, {"stem": self.__dict__.get("_ldg_stem"), "action_num": action_num, "level": E[-1][2], "ms": round(1000 * (_ldg_time.time() - t0), 1),
                            "chars": st["chars"], "state": st["state"], "nstates": st["nstates"], "mask": st["mask"], "gaps": st["gaps"]})
            if _LDG_ANCHOR in r:
                i = r.index(_LDG_ANCHOR) + len(_LDG_ANCHOR)
                return r[:i] + "\n" + text + "\n" + r[i:]
            return r + "\n" + text
        except Exception as e:
            _ldg_fail(self, "prompt", e)
            return r
    return _build_user_prompt

def _ldg_stub_messages(messages):
    out = []
    for m in messages:
        if isinstance(m, dict) and m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str) and _LDG_END in c:
                m = {**m, "content": _LDG_STUB_RE.sub(_LDG_STUB, c)}
            elif isinstance(c, list):
                parts = [({**p, "text": _LDG_STUB_RE.sub(_LDG_STUB, p["text"])} if isinstance(p, dict) and isinstance(p.get("text"), str) and _LDG_END in p["text"] else p) for p in c]
                m = {**m, "content": parts}
        out.append(m)
    return out

def _ldg_wrap_persist(orig):
    def _persistent_history_messages(self, messages, *a, **k):
        try:
            messages = _ldg_stub_messages(messages)
        except Exception as e:
            _ldg_fail(self, "persist", e)
        return orig(self, messages, *a, **k)
    return _persistent_history_messages

def _ldg_wrap_chat(orig):
    def _chat_completion(self, *a, **k):
        self.__dict__["_ldg_calls"] = int(self.__dict__.get("_ldg_calls", 0) or 0) + 1
        return orig(self, *a, **k)
    return _chat_completion

if _LDG_ON:
    _ldg_TA = _ldg_ta.ToolAgent
    assert "_ldg_installed" not in vars(_ldg_TA), "cell_duck_ledger.py exec'ed twice"
    _ldg_TA.analyze = _ldg_wrap_analyze(_ldg_TA.analyze)
    _ldg_TA._build_user_prompt = _ldg_wrap_prompt(_ldg_TA._build_user_prompt)
    _ldg_TA._persistent_history_messages = _ldg_wrap_persist(_ldg_TA._persistent_history_messages)
    _ldg_TA._chat_completion = _ldg_wrap_chat(_ldg_TA._chat_completion)
    _ldg_TA._ldg_installed = True
    print(f"LEDGER installed: coverage ledger in every user prompt (<= {_LDG_MAX_CHARS} chars; old blocks stubbed in history); "
          f"log {_ldg_os.environ.get('DUCK_LEDGER_LOG') or '<artifacts>/ledger.jsonl'}", flush=True)
else:
    print("LEDGER available but off (DUCK_LEDGER=1 enables)", flush=True)
