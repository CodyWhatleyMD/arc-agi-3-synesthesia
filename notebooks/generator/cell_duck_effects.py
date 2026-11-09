"""EFFECTS DIGEST for the Duck harness -- comparison fix #1 (findings 153; opus-vs-flashnext archive, intervention 0).

OPT-IN: DUCK_EFFECTS=1. Unset / any other value = completely inert: nothing is imported from the harness, nothing is
patched, nothing is printed (only stdlib imports, constants and function definitions land in the namespace).

WHAT THE MODEL GETS. The next turn's user prompt carries one block, inserted right before "Current state: step N", with
one line per action executed since the previous digest, computed by the HARNESS from the frames (push, not pull: q25
called moved() 5x and report() 1x in 2,085 python calls). Example (q25 lf52, a21-a24):
    Effects of your last actions (harness-computed from the frames; HUD = small changes within 4 cells of the edge; [..] = how an object was matched):
    a21 LEFT: 149 gameplay cells changed; HUD 1 cell r0 c1: moved together by (+0,-6): 뀌(yellow) 20px 6x6 at r32c30, ... [same shape]; +5 more
    a22 RIGHT: ... | interior board == this level's start
    a23-a24 UP,DOWN: gameplay unchanged (HUD tick 1 cell r0 c3 only)
Per action: gameplay cells changed with HUD ticks separated (a HUD tick = an 8-connected changed blob of <= 8 cells
lying entirely in the outer DUCK_EFFECTS_BORDER cells; Franzen's interior width); objects (same-colour 4-connected
components, Duck's segmentation rule) moved / moved together / recoloured / turned / reshaped / merged / split /
appeared / vanished, each tagged with the matching rule used, ALWAYS in absolute board coordinates; a view-shift line
only when a region's content moved as a whole (object-checked, see VIEW SHIFT below); a revert line when the interior
board equals an earlier board of this level/attempt; LEVEL COMPLETE / GAME_OVER / RESET lines. Identical
consecutive no-change / HUD-only outcomes collapse into one line; at most DUCK_EFFECTS_LINES lines (first 3, an
"omitted" line, the last ones). A frame pair the tracker cannot read (e.g. a ragged grid) gets a placeholder line and the
digest goes on with the next pair.
VIEW SHIFT (review 10-03: the pixel-level estimate alone fired on ar25, a MIRROR game -- the bar moves 3, its reflection 6,
the source stays -- and the old code then re-expressed every object relative to that made-up scroll, which produced move
and vanish/appear claims that were false in board terms). Now the pixel-level shift is only a CANDIDATE; it is reported
iff, among the pre objects of more than one cell (and < 20% of the board) overlapping the changed region and not leaving
it, at least 3 and >= 70% sit at the shifted place as exact copies and <= 25% stayed put (recorded: sk48 / most bp35
pass, ar25 / cn04 / sp80 never do). The objects that moved exactly with it are summarised in that line; every other
object is matched in absolute coordinates as if there were no shift. No line ever states a position or vector relative to
a scroll, and an object that is unchanged in board terms is never reported.

HOW (two prompt-side hooks; the action path, the sandbox, the natives, the tool text and the system prompt are untouched):
  ToolAgent._build_user_prompt (tool_agent.py:1161)  -- the digest is a pure function of `history_entries`, which
      analyze() already passes (tool_agent.py:1727-1733: the full per-game history from the runtime state file, one
      HistoryEntry(action display, Frame(grid, step, level)) per executed action incl. the solver's auto-RESET), plus
      previous_step_summary's game_over/end_action_num (the only place GAME_OVER is visible: the frame does not say).
      Entries are fed once, incrementally, per agent; a yielded/retried turn (no new actions) repeats the cached block,
      exactly as Duck repeats its own "The code executed N actions in the previous sequence" line.
  ToolAgent._persistent_history_messages (tool_agent.py:1653) -- unless DUCK_EFFECTS_KEEP=1, the block is removed from
      the copy of the prompt saved into history, so only the NEWEST user message ever carries a digest (cost = one block
      per request, not one per retained turn, and yield-repeats never pile up). The price of that cut-out: the previous
      turn's prompt then differs from what was sent, so a prefix cache cannot reuse the previous turn. Free on the shipped
      engine (a game's own history ~never hits at KV saturation, findings 154/157); +23-25% computed prompt tokens under
      an unlimited cache (tests/cmp_fixes/f1-effects/measure_replay.py on q25/B), so with SPLIT_FIX/KEEP_CKPT use
      DUCK_EFFECTS_KEEP=1 instead (+2.5% computed; ~7% fewer history turns in the 32k window).
Synthesis of the two judged designs: design 2's tracker/renderer (prototypes_1001/cell_duck_effects.py; the HUD rule the
skeptic judge checked for false positives on q25/Vercel/Opus; colour words from the live legend) delivered the way design 0
delivers (prompt-side only, history-derived, newest message only). Left out on purpose (second variables; findings 156:
FIXES=1 changed every python call and cost 20% tokens/action): the prototype's act_until stop-on-no-change, its edit of
the natives source/tool doc, and its `gameplay_changed` key in last_action_result (both needed a hook in solver
._execute_action, i.e. inside the python tool's deadline).

KNOBS (read at exec): DUCK_EFFECTS=1 (switch), DUCK_EFFECTS_LINES (10), DUCK_EFFECTS_BORDER (4), DUCK_EFFECTS_KEEP (0; 1 =
blocks stay in history: a game's requests stay pure extensions of each other, the setting for a working prefix cache),
DUCK_EFFECTS_BUDGET_S (1.5: CPU seconds per prompt for object matching -- the analyze thread's own CPU time, not wall time,
so machine load and GIL contention do not change what the digest says -- spent NEWEST action first; the newest changed
action is always matched -- unless its changed pieces would need more than _EFX_MATCH_MAX pair comparisons (a board of
noise), which reports the counts and "too many pieces to match"; older ones past the budget keep cell counts, HUD and
revert only. Recorded runs (review 10-03, thread CPU per prompt): max 92-183 ms; synthetic noise replaced by new noise
1.21 s before the pair cap. Malformed DUCK_EFFECTS_LINES / _BORDER / _BUDGET_S values fall back to the default, printed).
FAIL-OPEN: any exception in a wrapper is printed once per site and the unpatched result is returned; an exception for one
frame pair costs only that pair's line (placeholder), never the rest of the game's digest.
Shared exec namespace (findings 79): every module-level name is _efx_* / _EFX_*. ORDER: the history strip removes only
the exact segment this cell inserted, so it composes with wrappers that come after it (in the generator f5-ledger,
f2-wm and f7-anim append after this cell; review 10-03 composition plays: no digest lost, no block left in history) as
long as none of them rewrites the digest text itself.
"""
import os as _efx_os, re as _efx_re, time as _efx_time

_EFX_ON = _efx_os.environ.get("DUCK_EFFECTS", "0") == "1"


def _efx_knob(name, default, conv, ok, why):
    """A numeric knob, parsed so that a malformed value can never raise at exec (outside the fail-open install)."""
    raw = _efx_os.environ.get(name, "")
    if not raw.strip():
        return default
    try:
        v = conv(raw.strip())
        if ok(v):
            return v
    except (TypeError, ValueError, OverflowError):
        pass
    if _EFX_ON:
        print(f"EFFECTS: {name}={raw!r} ignored ({why}); using {default}", flush=True)
    return default


_EFX_BORDER = _efx_knob("DUCK_EFFECTS_BORDER", 4, int, lambda v: 0 <= v <= 16, "an integer 0..16")
_EFX_LINES = _efx_knob("DUCK_EFFECTS_LINES", 10, int, lambda v: v >= 5, "an integer >= 5: first 3, an 'omitted' line, the last ones")
_EFX_KEEP = _efx_os.environ.get("DUCK_EFFECTS_KEEP", "0") == "1"
_EFX_BUDGET_S = _efx_knob("DUCK_EFFECTS_BUDGET_S", 1.5, float, lambda v: 0.0 <= v <= 60.0, "seconds, 0..60")
_EFX_HUD_BLOB, _EFX_BG_FRAC, _EFX_BIG, _EFX_SCROLL_MIN, _EFX_SCROLL_MAX, _EFX_AMBIG = 8, 0.20, 400, 200, 40, 3
_EFX_FOLLOW_MIN, _EFX_FOLLOW_FRAC, _EFX_STAY_FRAC = 3, 0.70, 0.25   # VIEW SHIFT object gate (see the docstring)
_EFX_MATCH_MAX = 250000   # changed pre pieces x changed post pieces above this: counts only ("too many pieces to match")
_EFX_ANCHOR = "\nCurrent state: step "
_EFX_STATS = {"prompts": 0, "blocks": 0, "actions": 0, "cheap": 0, "stripped": 0, "max_ms": 0.0}
_efx_errors = {}


def _efx_header(border=None):
    b = _EFX_BORDER if border is None else border
    return ("Effects of your last actions (harness-computed from the frames; HUD = small changes within %d cells of the edge; "
            "[..] = how an object was matched):" % b)


def _efx_err(where, exc):
    if where not in _efx_errors:
        print(f"EFFECTS: {where} failed ({type(exc).__name__}: {exc}); falling back to the unpatched result", flush=True)
    _efx_errors[where] = _efx_errors.get(where, 0) + 1


def _efx_namer():
    """glyph(+legend word) for a colour value, from the LIVE carrier and legend (lownorm/qwen, baseline letters, or no key)."""
    import inference.utils.grid_utils as _gu
    import inference.agent.tool_agent as _ta
    chars = _gu.ARC_COLOR_CHARS
    m = _efx_re.search(r"Color legend: (.*?)\.\n", getattr(_ta, "GAME_OVERVIEW_ADDENDUM", "") or "")
    words = {}
    if m:
        for part in m.group(1).split(", "):
            k, _, v = part.partition("=")
            if k and v: words[k] = v
    return lambda v: (f"{chars[v]}({words[chars[v]]})" if chars[v] in words else chars[v]) if 0 <= v < len(chars) else str(v)


def _efx_cc(grid):
    H = len(grid); W = len(grid[0]) if H else 0
    lab = [[-1] * W for _ in range(H)]; comps = []
    for r in range(H):
        for c in range(W):
            if lab[r][c] != -1: continue
            v = grid[r][c]; cid = len(comps); st = [(r, c)]; lab[r][c] = cid; cells = []
            while st:
                y, x = st.pop(); cells.append((y, x))
                if y > 0 and lab[y-1][x] == -1 and grid[y-1][x] == v: lab[y-1][x] = cid; st.append((y-1, x))
                if y < H-1 and lab[y+1][x] == -1 and grid[y+1][x] == v: lab[y+1][x] = cid; st.append((y+1, x))
                if x > 0 and lab[y][x-1] == -1 and grid[y][x-1] == v: lab[y][x-1] = cid; st.append((y, x-1))
                if x < W-1 and lab[y][x+1] == -1 and grid[y][x+1] == v: lab[y][x+1] = cid; st.append((y, x+1))
            rs = [p[0] for p in cells]; cs = [p[1] for p in cells]
            comps.append({'id': cid, 'v': v, 'cells': cells, 'n': len(cells), 'r0': min(rs), 'c0': min(cs), 'r1': max(rs), 'c1': max(cs)})
    return comps, lab


def _efx_shape(o):
    if 'shape' not in o: o['shape'] = frozenset((r - o['r0'], c - o['c0']) for r, c in o['cells'])
    return o['shape']


def _efx_blobs8(cells):
    cs = set(cells); seen = set(); out = []
    for s in cells:
        if s in seen: continue
        st = [s]; seen.add(s); comp = []
        while st:
            p = st.pop(); comp.append(p)
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    q = (p[0] + dr, p[1] + dc)
                    if q in cs and q not in seen: seen.add(q); st.append(q)
        out.append(comp)
    return out


def _efx_box(o): return (o['r0'], o['c0'], o['r1'], o['c1'])
def _efx_hw(o): return f"{o['r1']-o['r0']+1}x{o['c1']-o['c0']+1}"
def _efx_at(o): return f"r{o['r0']}c{o['c0']}"
def _efx_ovl(a, b): return not (a['r1'] < b['r0'] or b['r1'] < a['r0'] or a['c1'] < b['c0'] or b['c1'] < a['c0'])


def _efx_view_shift(pre, post, cells):
    """CANDIDATE only: the one-axis shift that best explains the pixels of the changed region. _efx_scroll_check decides."""
    try:
        import numpy as _np
    except Exception:
        return None
    A = _np.asarray(pre); B = _np.asarray(post)
    rs = [p[0] for p in cells]; cs = [p[1] for p in cells]
    r0, r1, c0, c1 = min(rs), max(rs) + 1, min(cs), max(cs) + 1
    a = A[r0:r1, c0:c1]; b = B[r0:r1, c0:c1]; h, w = a.shape
    if h * w < 256: return None
    zero = float((a != b).mean()); best = None
    for d in range(1, _EFX_SCROLL_MAX + 1):
        for dr, dc in ((d, 0), (-d, 0), (0, d), (0, -d)):
            if abs(dr) >= h or abs(dc) >= w: continue
            pa = a[max(0, -dr):h - max(0, dr), max(0, -dc):w - max(0, dc)]
            pb = b[max(0, dr):max(0, dr) + pa.shape[0], max(0, dc):max(0, dc) + pa.shape[1]]
            if pa.size < 0.5 * h * w or pa.size < 256: continue
            m = float((pa != pb).mean())
            if best is None or m < best[0]: best = (m, dr, dc)
    if best and best[0] < 0.4 * zero and best[0] < 0.15:
        return best[1], best[2], 1.0 - best[0], (r0, c0, r1 - 1, c1 - 1)
    return None


def _efx_same_at(o, B, lb, ddr, ddc, H, W):
    """The post component at o's own seed cell moved by (ddr, ddc), if it is exactly o moved by (ddr, ddc); else None."""
    r, c = o['cells'][0]
    r, c = r + ddr, c + ddc
    if not (0 <= r < H and 0 <= c < W): return None
    b = B[lb[r][c]]
    if (b['v'] != o['v'] or b['n'] != o['n'] or b['r0'] != o['r0'] + ddr or b['c0'] != o['c0'] + ddc
            or _efx_shape(b) != _efx_shape(o)):
        return None
    return b


def _efx_scroll_check(A, B, lb, H, W, shift):
    """Object-level gate for a candidate shift (review 10-03, ar25). Counted: pre objects of 1 < n < _EFX_BG_FRAC of the
    board whose box overlaps the region and whose shifted box stays inside it; follow = an exact copy at the shifted place
    and not at the old one, stay = still at the old place and not at the shifted one (both = ambiguous, not counted).
    Confirmed iff follow >= _EFX_FOLLOW_MIN, >= _EFX_FOLLOW_FRAC of the counted and stay <= _EFX_STAY_FRAC of them.
    Returns ({pre id: post id} of EVERY follower overlapping the region, 1-cell ones included; the fact line) or (None, None)."""
    dr, dc, _frac, (R0, C0, R1, C1) = shift
    bg = _EFX_BG_FRAC * H * W
    fol, F, S, O, X = {}, 0, 0, 0, 0
    for o in A:
        if o['n'] >= bg or o['r1'] < R0 or o['r0'] > R1 or o['c1'] < C0 or o['c0'] > C1: continue
        moved = _efx_same_at(o, B, lb, dr, dc, H, W); kept = _efx_same_at(o, B, lb, 0, 0, H, W)
        if moved is not None and kept is None:
            fol[o['id']] = moved['id']
        if o['n'] <= 1 or (moved is not None and kept is not None): continue
        if o['r0'] + dr < R0 or o['r1'] + dr > R1 or o['c0'] + dc < C0 or o['c1'] + dc > C1:
            X += 1   # leaves the region: says nothing either way
        elif moved is not None: F += 1
        elif kept is not None: S += 1
        else: O += 1
    N = F + S + O
    if F < _EFX_FOLLOW_MIN or F < _EFX_FOLLOW_FRAC * N or S > _EFX_STAY_FRAC * N:
        return None, None
    return fol, (f"VIEW SHIFT: the content of region r{R0}-{R1} c{C0}-{C1} moved by ({dr:+d},{dc:+d}) as a whole: {F} of {N} "
                 f"objects there moved by exactly that, {S} stayed" + (f", {X} left the region" if X else "")
                 + " [object check; those objects are not listed again]")


class _EfxTracker:
    """One per game (per ToolAgent). feed() -> record {num, act, kind, gameplay_changed, hud, facts, revert}; object
    matching for a 'change' record is deferred to fill() so the per-prompt CPU budget goes to the NEWEST actions first.
    sigs maps an interior-board hash to the action number that board PRECEDES (the prototype's convention)."""
    def __init__(self, border=None, namer=None):
        self.b = _EFX_BORDER if border is None else border
        self.nm = namer; self.sigs = {}; self.level = None; self.level_start = None; self.last = None

    def _isig(self, g):
        b = self.b
        return hash(tuple(tuple(row[b:len(row) - b]) for row in g[b:len(g) - b]))

    def _restart(self, grid, before_num):
        self.level_start = before_num; self.last = self._isig(grid); self.sigs = {self.last: before_num}

    def feed(self, pre, post, act, num, lvl_before, lvl_after, game_over=False, auto_reset=False):
        if self.nm is None:
            try:
                self.nm = _efx_namer()
            except Exception as e:   # no live legend/carrier: plain colour numbers, not a lost digest
                _efx_err("namer", e); self.nm = lambda v: f"colour{v}"
        H = len(post); W = len(post[0]) if H else 0
        rec = {'num': num, 'act': act, 'facts': [], 'revert': None, 'hud': '', 'kind': 'change', 'gameplay_changed': True}
        if self.level != lvl_before or self.level_start is None:
            self.level = lvl_before; self._restart(pre, num)
        if len(pre) != H or (H and len(pre[0]) != W):
            rec['facts'] = ["frame shape changed"]; self._restart(post, num + 1); return rec
        if lvl_after is not None and lvl_after != lvl_before:
            back = isinstance(lvl_before, int) and isinstance(lvl_after, int) and lvl_after < lvl_before
            rec.update(kind='level', facts=[f"level went back to {lvl_after} (game reset)" if back
                                            else f"LEVEL COMPLETE -> level {lvl_after}"])
            self.level = lvl_after; self._restart(post, num + 1); return rec
        changed = [(r, c) for r in range(H) for c in range(W) if pre[r][c] != post[r][c]]
        if str(act).strip().upper().startswith('RESET'):
            rec.update(kind='reset', auto=bool(auto_reset), gameplay_changed=bool(changed)); self._restart(post, num + 1); return rec
        if game_over:
            self.last = self._isig(post)
            rec.update(kind='game_over', facts=["GAME_OVER: this attempt failed; the level restarts"]); return rec
        if not changed:
            rec.update(kind='none', gameplay_changed=False); return self._revert(rec, post, num)
        b = self.b; inb = lambda p: p[0] < b or p[0] >= H - b or p[1] < b or p[1] >= W - b
        hud, game = [], []
        for blob in _efx_blobs8(changed):
            (hud if len(blob) <= _EFX_HUD_BLOB and all(inb(p) for p in blob) else game).extend(blob)
        if hud:
            rs = sorted({p[0] for p in hud}); cs = sorted({p[1] for p in hud})
            rec['hud'] = (f"HUD {len(hud)} cell{'s' * (len(hud) > 1)} r{rs[0]}{'-%d' % rs[-1] if len(rs) > 1 else ''} "
                          f"c{cs[0]}{'-%d' % cs[-1] if len(cs) > 1 else ''}")
        if not game:
            rec.update(kind='hud_only', gameplay_changed=False); return self._revert(rec, post, num)
        rec['ncells'] = len(game)
        rec['_pp'] = (pre, post, game)   # object matching deferred to fill()
        return self._revert(rec, post, num)

    def fill(self, rec):
        pre, post, game = rec.pop('_pp')
        A, la = _efx_cc(pre); B, lb = _efx_cc(post)
        H = len(pre); W = len(pre[0]) if H else 0
        follow = {}
        shift = _efx_view_shift(pre, post, game) if len(game) >= _EFX_SCROLL_MIN else None
        if shift:
            fol, line = _efx_scroll_check(A, B, lb, H, W, shift)
            if line:
                follow = fol; rec['facts'].append(line)
        rec['facts'] += self._objects(pre, post, set(game), A, la, B, lb, follow)
        return rec

    def _revert(self, rec, post, num):
        s = self._isig(post); hit = self.sigs.get(s)
        if hit is not None and s != self.last:   # equal to the board just before this action = "unchanged", already said
            rec['revert'] = ("interior board == this level's start" if hit == self.level_start
                             else f"interior board == the board before a{hit}")
        self.sigs.setdefault(s, num + 1); self.last = s
        return rec

    def _objects(self, pre, post, gcells, A, la, B, lb, follow):
        """Every position and vector is in ABSOLUTE board coordinates (pre position -> post position). `follow` = objects
        already reported by a confirmed VIEW SHIFT line (pre id -> post id): matched up front, not listed again."""
        nm = self.nm
        H = len(pre); W = len(pre[0]); bg = _EFX_BG_FRAC * H * W
        pa = {la[r][c] for r, c in gcells}; pb = {lb[r][c] for r, c in gcells}
        PA = [A[i] for i in pa if A[i]['n'] < bg]; PB = [B[i] for i in pb if B[i]['n'] < bg]
        out = []; ua = set(follow); ub = set(follow.values()); moves = {}
        if len(PA) * len(PB) > _EFX_MATCH_MAX:   # a board of noise: the pair loops below would cost seconds
            return [f"objects not analysed ({len(PA)} -> {len(PB)} changed pieces: too many to match)"]
        key = lambda o: (o['v'], o['n'], _efx_shape(o))
        ga, gb = {}, {}
        for o in PA:
            if o['id'] not in ua: ga.setdefault(key(o), []).append(o)
        for o in PB:
            if o['id'] not in ub: gb.setdefault(key(o), []).append(o)
        for k in ga:
            if k not in gb: continue
            xs, ys = ga[k], gb[k]
            pairs = sorted((abs(a['r0'] - b_['r0']) + abs(a['c0'] - b_['c0']), i, j) for i, a in enumerate(xs) for j, b_ in enumerate(ys))
            mi, mj, mv = set(), set(), []
            for d, i, j in pairs:
                if i in mi or j in mj: continue
                mi.add(i); mj.add(j); mv.append((xs[i], ys[j]))
            vecs = {(b_['r0'] - a['r0'], b_['c0'] - a['c0']) for a, b_ in mv}
            for a, b_ in mv: ua.add(a['id']); ub.add(b_['id'])
            if max(len(xs), len(ys)) >= _EFX_AMBIG and len(vecs) > 1:
                o = xs[0]
                out.append((5, f"{len(xs)}->{len(ys)} identical {nm(o['v'])} {o['n']}px {_efx_hw(o)} pieces rearranged [identical copies: not tracked]"))
                for a in xs: ua.add(a['id'])
                for b_ in ys: ub.add(b_['id'])
                continue
            for a, b_ in mv:
                v = (b_['r0'] - a['r0'], b_['c0'] - a['c0'])
                if v != (0, 0): moves.setdefault(v, []).append(a)
        for (dr, dc), objs_ in sorted(moves.items(), key=lambda kv: -sum(o['n'] for o in kv[1])):
            grp = {}   # identical copies moved by the same vector are one entry ("21x #0 1px 1x1 (first at ..)")
            for o in objs_: grp.setdefault((o['v'], o['n'], _efx_shape(o)), []).append(o)
            gl = sorted(grp.values(), key=lambda g: -g[0]['n'] * len(g))
            desc = ', '.join(f"{nm(g[0]['v'])} {g[0]['n']}px {_efx_hw(g[0])} at {_efx_at(g[0])}" if len(g) == 1 else
                             f"{len(g)}x {nm(g[0]['v'])} {g[0]['n']}px {_efx_hw(g[0])} (first at {_efx_at(min(g, key=_efx_box))})"
                             for g in gl[:4]) + (f" +{sum(len(g) for g in gl[4:])}" if len(gl) > 4 else '')
            tag = "same shape" if abs(dr) + abs(dc) <= 8 else "same shape, far jump: may be another copy"
            out.append((0, f"moved{' together' if len(objs_) > 1 else ''} by ({dr:+d},{dc:+d}): {desc} [{tag}]"))
        for a in PA:
            if a['id'] in ua: continue
            for b_ in PB:
                if b_['id'] in ub or b_['v'] == a['v'] or _efx_box(a) != _efx_box(b_) or a['n'] != b_['n'] or _efx_shape(a) != _efx_shape(b_): continue
                ua.add(a['id']); ub.add(b_['id'])
                out.append((1, f"recoloured {nm(a['v'])}->{nm(b_['v'])} {a['n']}px {_efx_hw(a)} at {_efx_at(a)} [same shape, same place]")); break
        for a in PA:
            if a['id'] in ua or a['n'] >= _EFX_BIG: continue
            best = None
            for b_ in PB:
                if b_['id'] in ub or b_['v'] != a['v'] or b_['n'] != a['n'] or _efx_box(a) == _efx_box(b_): continue
                d = abs(a['r0'] - b_['r0']) + abs(a['c0'] - b_['c0'])
                if d <= 2 * max(a['r1'] - a['r0'] + 1, a['c1'] - a['c0'] + 1) and (best is None or d < best[0]): best = (d, b_)
            if best:
                b_ = best[1]; ua.add(a['id']); ub.add(b_['id'])
                out.append((2, f"moved+reshaped {nm(a['v'])} {a['n']}px {_efx_hw(a)} at {_efx_at(a)} -> {_efx_hw(b_)} at {_efx_at(b_)} [same colour+size, nearest]"))
        for a in PA:
            if a['id'] in ua: continue
            ov = [b_ for b_ in PB if b_['id'] not in ub and b_['v'] == a['v'] and _efx_ovl(a, b_)]
            if not ov: continue
            if len(ov) == 1:
                b_ = ov[0]
                others = [x for x in PA if x['id'] not in ua and x['id'] != a['id'] and x['v'] == a['v'] and _efx_ovl(x, b_)]
                for x in others: ua.add(x['id'])
                ua.add(a['id']); ub.add(b_['id'])
                if others:
                    out.append((3, f"merged {1 + len(others)} {nm(a['v'])} pieces into one {b_['n']}px {_efx_hw(b_)} at {_efx_at(b_)} [same colour, overlapping]"))
                elif (a['n'] < _EFX_BIG or b_['n'] < _EFX_BIG) and not (_efx_box(a) == _efx_box(b_) and a['n'] == b_['n']):
                    out.append((4, f"reshaped {nm(a['v'])} {a['n']}px {_efx_hw(a)} at {_efx_at(a)} -> {b_['n']}px {_efx_hw(b_)} at {_efx_at(b_)} [same colour, overlapping]"))
            else:
                ua.add(a['id'])
                for b_ in ov: ub.add(b_['id'])
                out.append((3, f"split {nm(a['v'])} {a['n']}px at {_efx_at(a)} into {len(ov)} pieces [same colour, overlapping]"))
        for a in PA:
            if a['id'] in ua: continue
            for b_ in PB:
                if b_['id'] in ub or _efx_box(a) != _efx_box(b_): continue
                ua.add(a['id']); ub.add(b_['id'])
                out.append((1, f"recoloured+reshaped {_efx_hw(a)} at {_efx_at(a)}: {nm(a['v'])} {a['n']}px -> {nm(b_['v'])} {b_['n']}px [same bbox]")); break
        movers_new = [b_ for b_ in PB if b_['id'] in ub]; movers_old = [a for a in PA if a['id'] in ua]
        van = [a for a in PA if a['id'] not in ua and a['n'] < _EFX_BIG]; app = [b_ for b_ in PB if b_['id'] not in ub and b_['n'] < _EFX_BIG]
        for o in van: o['tag'] = ' [under a moved/changed object now]' if any(_efx_ovl(o, m) for m in movers_new) else ''
        for o in app: o['tag'] = ' [where a moved/changed object was]' if any(_efx_ovl(o, m) for m in movers_old) else ''
        for objs_, verb in ((van, 'vanished'), (app, 'appeared')):
            g = {}
            for o in objs_: g.setdefault((o['v'], o['n'], _efx_hw(o), o['tag']), []).append(o)
            for (v, n, hw, tag), os_ in sorted(g.items(), key=lambda kv: -kv[0][1] * len(kv[1])):
                where = ', '.join(_efx_at(o) for o in os_[:2]) + (f" +{len(os_) - 2}" if len(os_) > 2 else '')
                out.append((6, f"{verb} {str(len(os_)) + 'x ' if len(os_) > 1 else ''}{nm(v)} {n}px {hw} at {where}{tag}"))
        out.sort(key=lambda x: x[0])
        return [s for _, s in out]


def _efx_render(records, max_lines=None, max_facts=3, line_chars=240):
    max_lines = _EFX_LINES if max_lines is None else max_lines
    def body(r):
        k = r['kind']
        if k == 'error': return "effects not computed for this action (the frames could not be read)"
        if k in ('level', 'game_over'): return r['facts'][0]
        if k == 'reset': return "auto-reset after GAME_OVER: the level restarted" if r.get('auto') else "the level restarted"
        if k == 'none': return "nothing changed, HUD included"
        if k == 'hud_only': return f"gameplay unchanged ({r['hud'].replace('HUD ', 'HUD tick ', 1)} only)"
        f = r['facts']; head = f"{r.get('ncells', 0)} gameplay cells changed" + (f"; {r['hud']}" if r['hud'] else '')
        if r.get('revert'): head += f" | {r['revert']}"
        if not f: return head + "; no object-level match"
        shown = []
        for x in f:
            if len(shown) >= max_facts or len(head) + sum(len(y) + 2 for y in shown) + len(x) > line_chars - 40: break
            shown.append(x)
        if not shown: shown = [f[0]]   # the most important fact is never cut mid-way
        return head + ": " + "; ".join(shown) + (f"; +{len(f) - len(shown)} more" if len(f) > len(shown) else '')
    rows = []
    for r in records:
        b = body(r)
        if r.get('revert') and r['kind'] != 'change': b += f" | {r['revert']}"
        if rows and rows[-1][1] == b and r['kind'] in ('none', 'hud_only'):
            rows[-1][0].append(r); continue
        rows.append(([r], b))
    lines = []
    for grp, b in rows:
        if len(grp) == 1:
            lab = f"a{grp[0]['num']} {grp[0]['act']}"
        else:
            acts = [g['act'] for g in grp]
            lab = f"a{grp[0]['num']}-a{grp[-1]['num']} " + (f"{acts[0]} x{len(acts)}" if len(set(acts)) == 1 else ','.join(acts[:4]) + (',...' if len(acts) > 4 else ''))
        s = f"{lab}: {b}"
        lines.append(s if len(s) <= 2 * line_chars else s[:2 * line_chars - 3] + '...')
    if len(lines) > max_lines:
        k = max(1, max_lines - 4)
        lines = lines[:3] + [f"... {len(lines) - 3 - k} more action lines omitted ..."] + lines[-k:]
    return lines


class _EfxState:
    """Per-agent (= per game per pass) digest state; lives in agent.__dict__['_efx_st']."""
    def __init__(self):
        self.n = 0; self.tr = _EfxTracker(); self.block = None; self.segs = []; self.go = set()


def _efx_update(st, entries, summary):
    """Feed history entries not seen yet; return the current block (None before the first action). Pure in the entries:
    a retried/yielded turn with no new entries returns the cached block."""
    n = len(entries)
    if n < st.n:   # history shrank: a new game/pass on a reused agent -> start over
        st.__init__()
    if summary and summary.get("game_over"):   # GAME_OVER is not in the frame; the step summary names the action
        try:
            st.go.add(int(summary.get("end_action_num")))
        except (TypeError, ValueError):
            pass
    if n > max(st.n, 1):
        t0 = _efx_time.monotonic(); c0 = _efx_time.thread_time(); recs = []
        for i in range(max(st.n, 1), n):
            act = "?"; num = i
            try:
                prev, cur = entries[i - 1], entries[i]
                act = str(getattr(cur, "action", "") or "").strip() or "?"
                pf, cf = prev.frame, cur.frame
                num = cf.step
                recs.append(st.tr.feed(pf.grid, cf.grid, act, cf.step, pf.level, cf.level,
                                       game_over=(cf.step in st.go and not act.upper().startswith("RESET")),
                                       auto_reset=pf.step in st.go))
            except Exception as e:   # one unreadable frame pair costs its own line, not the rest of the game's digest
                _efx_err("frames", e)
                recs.append({'num': num, 'act': act, 'kind': 'error', 'facts': [], 'revert': None, 'hud': '',
                             'gameplay_changed': None})
                st.tr.level_start = None   # the next readable pair restarts the tracker's level/revert state
        st.n = n   # fed (or placeholdered) once: a later failure below must not re-feed or stall these entries
        st.block = None   # if matching/rendering below raises, no STALE block is repeated on a later yield
        filled = 0
        for rec in reversed(recs):   # newest first: past the CPU budget, older actions keep counts + revert only
            if '_pp' not in rec: continue
            if filled and (_efx_time.thread_time() - c0) > _EFX_BUDGET_S:   # this thread's CPU: load/GIL-independent
                rec.pop('_pp'); rec['facts'] = ["objects not analysed (digest time budget)"]; _EFX_STATS["cheap"] += 1
                continue
            try:
                st.tr.fill(rec)
            except Exception as e:   # one unmatched action must not cost the whole digest
                _efx_err("objects", e); rec.pop('_pp', None); rec['facts'] = ["objects not analysed (error)"]
            filled += 1
        st.block = "\n".join([_efx_header(st.tr.b)] + _efx_render(recs))
        _EFX_STATS["blocks"] += 1; _EFX_STATS["actions"] += len(recs)
        _EFX_STATS["max_ms"] = max(_EFX_STATS["max_ms"], 1000.0 * (_efx_time.monotonic() - t0))
    elif st.n == 0:
        st.n = n
    return st.block


def _efx_insert(text, block):
    """(new text, the exact inserted segment) -- before the state line, else prepended."""
    i = text.find(_EFX_ANCHOR)
    if i >= 0:
        seg = "\n" + block
        return text[:i] + seg + text[i:], seg
    seg = block + "\n"
    return seg + text, seg


def _efx_strip_content(content, segs):
    def one(t):
        for s in segs:
            if s in t: t = t.replace(s, "", 1)
        return t
    if isinstance(content, str):
        return one(content)
    if isinstance(content, list):
        return [dict(p, text=one(p["text"])) if isinstance(p, dict) and isinstance(p.get("text"), str) else p for p in content]
    return content


def _efx_install():
    import inference.agent.tool_agent as _ta
    T = _ta.ToolAgent
    if getattr(T, "_efx_installed", False): return "already installed"
    _orig_bup, _orig_phm = T._build_user_prompt, T._persistent_history_messages

    def _build_user_prompt(self, *a, **k):
        text = _orig_bup(self, *a, **k)
        try:
            if not isinstance(text, str): return text
            _EFX_STATS["prompts"] += 1
            st = self.__dict__.get("_efx_st")
            if st is None: st = self.__dict__["_efx_st"] = _EfxState()
            block = _efx_update(st, k.get("history_entries") or [], k.get("previous_step_summary"))
            if not block: return text
            new, seg = _efx_insert(text, block)
            if seg not in st.segs: st.segs = (st.segs + [seg])[-4:]
            return new
        except Exception as e:
            _efx_err("prompt", e)
            return text
    _build_user_prompt.__wrapped__ = _orig_bup

    def _persistent_history_messages(self, *a, **k):
        out = _orig_phm(self, *a, **k)
        if _EFX_KEEP: return out
        try:
            st = self.__dict__.get("_efx_st")
            if st is None or not st.segs: return out
            res = []
            for m in out:
                if isinstance(m, dict) and m.get("role") == "user":
                    c = _efx_strip_content(m.get("content"), st.segs)
                    if c != m.get("content"):
                        m = dict(m, content=c); _EFX_STATS["stripped"] += 1
                res.append(m)
            return res
        except Exception as e:
            _efx_err("history", e)
            return out
    _persistent_history_messages.__wrapped__ = _orig_phm

    T._build_user_prompt, T._persistent_history_messages = _build_user_prompt, _persistent_history_messages
    T._efx_installed = True
    _ta._efx_stats = _EFX_STATS
    return "installed (ToolAgent._build_user_prompt, ToolAgent._persistent_history_messages)"


if _EFX_ON:
    try:
        _efx_msg = _efx_install()
    except Exception as _efx_e:   # fail-open at install: the run proceeds unpatched, loudly
        _efx_msg = f"NOT INSTALLED ({type(_efx_e).__name__}: {_efx_e}) -- running without the digest"
    print(f"EFFECTS DIGEST -- {_efx_msg}; border={_EFX_BORDER} lines={_EFX_LINES} "
          f"history={'kept' if _EFX_KEEP else 'newest prompt only'} budget={_EFX_BUDGET_S}s", flush=True)
