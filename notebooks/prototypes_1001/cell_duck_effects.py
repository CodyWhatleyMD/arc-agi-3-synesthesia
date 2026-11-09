"""EFFECTS DIGEST for the Duck harness (opt-in DUCK_EFFECTS=1; default off, so v5 is byte-identical).

Push, not pull: after every executed action the HARNESS (not the model's code) computes what changed, object by object,
with the HUD masked, and puts it in the next turn's state header (the user prompt), outside the 1,024-token tool-output
cap. q25 (our quant, public 25): 2,083 python calls, act_until in 4, moved() in 5, report() in 1, tried() in 0; 297 calls
branched on `board_changed`, which was True on all 312 actions whose only change was a HUD tick.

Per action (one record, computed in the solver from the in-memory pre/post grids):
  (a) gameplay_changed: changed cells minus HUD ticks. A HUD tick = an 8-connected changed blob of <= 8 cells lying
      entirely in the outer 4-cell border (Franzen's interior width, ARC3_NOOP_GUARD_BORDER=4). On the public 25 every
      recurring tick line sits in rows 0-1/61-63 or cols 0/62-63.
  (b) objects = same-colour 4-connected components (Duck's segmentation rule). Matched in this order, and the line
      names the rule used: [same shape] exact colour+shape, nearest first (moves grouped by vector, so a carried
      object reads as "moved together"); [same shape, same place] recolour; [same colour+size, nearest] turn;
      [same colour, overlapping] reshape/merge/split; [same bbox] recolour+reshape; then vanished/appeared, tagged
      when they overlap a mover's new/old spot. >= 3 identical copies with mixed vectors are never matched one by one.
  (c) components >= 20% of the board are background; >= 400 px are regions (only reported when recoloured in place).
  (d) view shift: axis shifts up to 40 of the changed region, accepted when one explains >= 85% of a >= 50% overlap.
  (e) revert: hash of the interior board (border excluded) vs every earlier board of this level/attempt.
Delivery: ToolAgent._build_user_prompt gets a block before "Current state: step"; one line per action, identical
HUD-only/no-change runs collapsed, <= DUCK_EFFECTS_LINES lines. last_action_result gains `gameplay_changed`.
act_until (natives) stops on an action that changed nothing but the HUD (DUCK_EFFECTS_ACT_UNTIL=0 restores it).
Fail-open: any exception in a wrapper is logged once and the original result is returned unchanged.
Shared exec namespace (findings 79): every module-level name is _fx_*.
"""
import os as _fx_os, re as _fx_re, time as _fx_time
import inference.agent.tool_agent as _fx_ta
import inference.framework.solver as _fx_sv
import inference.utils.grid_utils as _fx_gu
try:
    import numpy as _fx_np
except Exception:
    _fx_np = None

_FX_ON = _fx_os.environ.get("DUCK_EFFECTS", "0") == "1"
_FX_BORDER = int(_fx_os.environ.get("DUCK_EFFECTS_BORDER", "4"))
_FX_LINES = int(_fx_os.environ.get("DUCK_EFFECTS_LINES", "10"))
_FX_ACT_UNTIL = _fx_os.environ.get("DUCK_EFFECTS_ACT_UNTIL", "1") == "1"
_FX_HUD_BLOB, _FX_BG_FRAC, _FX_BIG, _FX_SCROLL_MIN, _FX_SCROLL_MAX, _FX_AMBIG = 8, 0.20, 400, 200, 40, 3
_FX_HEADER = ("Effects of your last actions (harness-computed from the frames; HUD = small changes in the 4-cell border; "
              "[..] = how the object was matched; last_action_result['gameplay_changed'] = the same test):")
_fx_errors = {}


def _fx_err(where, exc):
    if where not in _fx_errors:
        print(f"EFFECTS: {where} failed ({type(exc).__name__}: {exc}); falling back to the unpatched result", flush=True)
    _fx_errors[where] = _fx_errors.get(where, 0) + 1


def _fx_namer():
    """glyph(+legend word) for a colour value, from the LIVE carrier and legend (lownorm/qwen, baseline letters, or no key)."""
    chars = _fx_gu.ARC_COLOR_CHARS
    m = _fx_re.search(r"Color legend: (.*?)\.\n", getattr(_fx_ta, "GAME_OVERVIEW_ADDENDUM", "") or "")
    words = {}
    if m:
        for part in m.group(1).split(", "):
            k, _, v = part.partition("=")
            if k and v: words[k] = v
    return lambda v: (f"{chars[v]}({words[chars[v]]})" if chars[v] in words else chars[v]) if 0 <= v < len(chars) else str(v)


def _fx_cc(grid):
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


def _fx_shape(o):
    if 'shape' not in o: o['shape'] = frozenset((r - o['r0'], c - o['c0']) for r, c in o['cells'])
    return o['shape']


def _fx_blobs8(cells):
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


def _fx_box(o): return (o['r0'], o['c0'], o['r1'], o['c1'])
def _fx_hw(o): return f"{o['r1']-o['r0']+1}x{o['c1']-o['c0']+1}"
def _fx_at(o): return f"r{o['r0']}c{o['c0']}"
def _fx_ovl(a, b): return not (a['r1'] < b['r0'] or b['r1'] < a['r0'] or a['c1'] < b['c0'] or b['c1'] < a['c0'])


def _fx_view_shift(pre, post, cells):
    if _fx_np is None: return None
    A = _fx_np.asarray(pre); B = _fx_np.asarray(post)
    rs = [p[0] for p in cells]; cs = [p[1] for p in cells]
    r0, r1, c0, c1 = min(rs), max(rs) + 1, min(cs), max(cs) + 1
    a = A[r0:r1, c0:c1]; b = B[r0:r1, c0:c1]; h, w = a.shape
    if h * w < 256: return None
    zero = float((a != b).mean()); best = None
    for d in range(1, _FX_SCROLL_MAX + 1):
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


class _FxTracker:
    """One per game session. feed() -> record {num, act, kind, gameplay_changed, hud, facts, revert}."""
    def __init__(self, border=_FX_BORDER):
        self.b = border; self.nm = None; self.sigs = {}; self.level = None; self.level_start = None; self.last = None

    def _isig(self, g):
        b = self.b
        return hash(tuple(tuple(row[b:len(row) - b]) for row in g[b:len(g) - b]))

    def _restart(self, grid, num):
        self.level_start = num; self.last = self._isig(grid); self.sigs = {self.last: num}

    def feed(self, pre, post, act, num, lvl_before, lvl_after, flags):
        if self.nm is None: self.nm = _fx_namer()
        H = len(post); W = len(post[0]) if H else 0
        rec = {'num': num, 'act': act, 'facts': [], 'revert': None, 'hud': '', 'kind': 'change', 'gameplay_changed': True}
        if self.level != lvl_before or self.level_start is None:
            self.level = lvl_before; self._restart(pre, num)
        if len(pre) != H or (H and len(pre[0]) != W):
            rec['facts'] = ["frame shape changed"]; return rec
        changed = [(r, c) for r in range(H) for c in range(W) if pre[r][c] != post[r][c]]
        if flags.get('level_completed') or (lvl_after is not None and lvl_after != lvl_before):
            rec.update(kind='level', facts=[f"LEVEL COMPLETE -> level {lvl_after}"])
            self.level = lvl_after; self._restart(post, num + 1); return rec
        if str(act).upper().startswith('RESET'):
            rec.update(kind='reset', gameplay_changed=bool(changed)); self._restart(post, num + 1); return rec
        if flags.get('game_over'):
            self.last = self._isig(post)
            rec.update(kind='game_over', facts=["GAME_OVER: this attempt failed; the level restarts"]); return rec
        if not changed:
            rec.update(kind='none', gameplay_changed=False); return self._revert(rec, post, num)
        b = self.b; inb = lambda p: p[0] < b or p[0] >= H - b or p[1] < b or p[1] >= W - b
        hud, game = [], []
        for blob in _fx_blobs8(changed):
            (hud if len(blob) <= _FX_HUD_BLOB and all(inb(p) for p in blob) else game).extend(blob)
        if hud:
            rs = sorted({p[0] for p in hud}); cs = sorted({p[1] for p in hud})
            rec['hud'] = (f"HUD {len(hud)} cell{'s' * (len(hud) > 1)} r{rs[0]}{'-%d' % rs[-1] if len(rs) > 1 else ''} "
                          f"c{cs[0]}{'-%d' % cs[-1] if len(cs) > 1 else ''}")
        if not game:
            rec.update(kind='hud_only', gameplay_changed=False); return self._revert(rec, post, num)
        rec['ncells'] = len(game)
        shift = _fx_view_shift(pre, post, game) if len(game) >= _FX_SCROLL_MIN else None
        if shift:
            dr, dc, frac, reg = shift
            rec['facts'].append(f"VIEW SHIFT: region r{reg[0]}-{reg[2]} c{reg[1]}-{reg[3]} scrolled by ({dr:+d},{dc:+d}) "
                                f"[one axis shift explains {frac:.0%} of it]")
        rec['facts'] += self._objects(pre, post, set(game), shift)
        return self._revert(rec, post, num)

    def _revert(self, rec, post, num):
        s = self._isig(post); hit = self.sigs.get(s)
        if hit is not None and s != self.last:   # equal to the board just before this action = "unchanged", already said
            rec['revert'] = ("interior board == this level's start" if hit == self.level_start
                             else f"interior board == the board before a{hit}")
        self.sigs.setdefault(s, num + 1); self.last = s
        return rec

    def _objects(self, pre, post, gcells, shift):
        nm = self.nm
        A, la = _fx_cc(pre); B, lb = _fx_cc(post)
        H = len(pre); W = len(pre[0]); bg = _FX_BG_FRAC * H * W
        if shift:
            dr, dc = shift[0], shift[1]; rr0, cc0, rr1, cc1 = shift[3]
            for o in A:
                o['cells'] = [(r + dr, c + dc) for r, c in o['cells']]; o['r0'] += dr; o['r1'] += dr; o['c0'] += dc; o['c1'] += dc
            g2 = set()
            for r in range(rr0, rr1 + 1):
                for c in range(cc0, cc1 + 1):
                    r_, c_ = r - dr, c - dc
                    if rr0 <= r_ <= rr1 and cc0 <= c_ <= cc1 and pre[r_][c_] != post[r][c]: g2.add((r, c))
            gcells = g2 | {p for p in gcells if not (rr0 <= p[0] <= rr1 and cc0 <= p[1] <= cc1)}
            pa = {o['id'] for o in A if any(p in gcells for p in o['cells'])}
        else:
            pa = {la[r][c] for r, c in gcells}
        pb = {lb[r][c] for r, c in gcells}
        PA = [A[i] for i in pa if A[i]['n'] < bg]; PB = [B[i] for i in pb if B[i]['n'] < bg]
        out = []; ua = set(); ub = set(); moves = {}
        key = lambda o: (o['v'], o['n'], _fx_shape(o))
        ga, gb = {}, {}
        for o in PA: ga.setdefault(key(o), []).append(o)
        for o in PB: gb.setdefault(key(o), []).append(o)
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
            if max(len(xs), len(ys)) >= _FX_AMBIG and len(vecs) > 1:
                o = xs[0]
                out.append((5, f"{len(xs)}->{len(ys)} identical {nm(o['v'])} {o['n']}px {_fx_hw(o)} pieces rearranged [identical copies: not tracked]"))
                for a in xs: ua.add(a['id'])
                for b_ in ys: ub.add(b_['id'])
                continue
            for a, b_ in mv:
                v = (b_['r0'] - a['r0'], b_['c0'] - a['c0'])
                if v != (0, 0): moves.setdefault(v, []).append(a)
        for (dr, dc), objs_ in sorted(moves.items(), key=lambda kv: -sum(o['n'] for o in kv[1])):
            desc = ', '.join(f"{nm(o['v'])} {o['n']}px {_fx_hw(o)} at {_fx_at(o)}" for o in objs_[:4]) + (f" +{len(objs_) - 4}" if len(objs_) > 4 else '')
            tag = "same shape" if abs(dr) + abs(dc) <= 8 else "same shape, far jump: may be another copy"
            out.append((0, f"moved{' together' if len(objs_) > 1 else ''} by ({dr:+d},{dc:+d}): {desc} [{tag}]"))
        for a in PA:
            if a['id'] in ua: continue
            for b_ in PB:
                if b_['id'] in ub or b_['v'] == a['v'] or _fx_box(a) != _fx_box(b_) or a['n'] != b_['n'] or _fx_shape(a) != _fx_shape(b_): continue
                ua.add(a['id']); ub.add(b_['id'])
                out.append((1, f"recoloured {nm(a['v'])}->{nm(b_['v'])} {a['n']}px {_fx_hw(a)} at {_fx_at(a)} [same shape, same place]")); break
        for a in PA:
            if a['id'] in ua or a['n'] >= _FX_BIG: continue
            best = None
            for b_ in PB:
                if b_['id'] in ub or b_['v'] != a['v'] or b_['n'] != a['n'] or _fx_box(a) == _fx_box(b_): continue
                d = abs(a['r0'] - b_['r0']) + abs(a['c0'] - b_['c0'])
                if d <= 2 * max(a['r1'] - a['r0'] + 1, a['c1'] - a['c0'] + 1) and (best is None or d < best[0]): best = (d, b_)
            if best:
                b_ = best[1]; ua.add(a['id']); ub.add(b_['id'])
                out.append((2, f"moved+reshaped {nm(a['v'])} {a['n']}px {_fx_hw(a)} at {_fx_at(a)} -> {_fx_hw(b_)} at {_fx_at(b_)} [same colour+size, nearest]"))
        for a in PA:
            if a['id'] in ua: continue
            ov = [b_ for b_ in PB if b_['id'] not in ub and b_['v'] == a['v'] and _fx_ovl(a, b_)]
            if not ov: continue
            if len(ov) == 1:
                b_ = ov[0]
                others = [x for x in PA if x['id'] not in ua and x['id'] != a['id'] and x['v'] == a['v'] and _fx_ovl(x, b_)]
                for x in others: ua.add(x['id'])
                ua.add(a['id']); ub.add(b_['id'])
                if others:
                    out.append((3, f"merged {1 + len(others)} {nm(a['v'])} pieces into one {b_['n']}px {_fx_hw(b_)} at {_fx_at(b_)} [same colour, overlapping]"))
                elif (a['n'] < _FX_BIG or b_['n'] < _FX_BIG) and not (_fx_box(a) == _fx_box(b_) and a['n'] == b_['n']):
                    out.append((4, f"reshaped {nm(a['v'])} {a['n']}px {_fx_hw(a)} at {_fx_at(a)} -> {b_['n']}px {_fx_hw(b_)} at {_fx_at(b_)} [same colour, overlapping]"))
            else:
                ua.add(a['id'])
                for b_ in ov: ub.add(b_['id'])
                out.append((3, f"split {nm(a['v'])} {a['n']}px at {_fx_at(a)} into {len(ov)} pieces [same colour, overlapping]"))
        for a in PA:
            if a['id'] in ua: continue
            for b_ in PB:
                if b_['id'] in ub or _fx_box(a) != _fx_box(b_): continue
                ua.add(a['id']); ub.add(b_['id'])
                out.append((1, f"recoloured+reshaped {_fx_hw(a)} at {_fx_at(a)}: {nm(a['v'])} {a['n']}px -> {nm(b_['v'])} {b_['n']}px [same bbox]")); break
        movers_new = [b_ for b_ in PB if b_['id'] in ub]; movers_old = [a for a in PA if a['id'] in ua]
        van = [a for a in PA if a['id'] not in ua and a['n'] < _FX_BIG]; app = [b_ for b_ in PB if b_['id'] not in ub and b_['n'] < _FX_BIG]
        for o in van: o['tag'] = ' [under a moved/changed object now]' if any(_fx_ovl(o, m) for m in movers_new) else ''
        for o in app: o['tag'] = ' [where a moved/changed object was]' if any(_fx_ovl(o, m) for m in movers_old) else ''
        for objs_, verb in ((van, 'vanished'), (app, 'appeared')):
            g = {}
            for o in objs_: g.setdefault((o['v'], o['n'], _fx_hw(o), o['tag']), []).append(o)
            for (v, n, hw, tag), os_ in sorted(g.items(), key=lambda kv: -kv[0][1] * len(kv[1])):
                where = ', '.join(_fx_at(o) for o in os_[:2]) + (f" +{len(os_) - 2}" if len(os_) > 2 else '')
                out.append((6, f"{verb} {str(len(os_)) + 'x ' if len(os_) > 1 else ''}{nm(v)} {n}px {hw} at {where}{tag}"))
        out.sort(key=lambda x: x[0])
        return [s for _, s in out]


def _fx_render(records, max_lines=_FX_LINES, max_facts=3, line_chars=240):
    def body(r):
        k = r['kind']
        if k in ('level', 'game_over'): return r['facts'][0]
        if k == 'reset': return "RESET (auto, after GAME_OVER): the level restarted"
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
        k = max_lines - 4
        lines = lines[:3] + [f"... {len(lines) - 3 - k} more action lines omitted ..."] + lines[-k:]
    return lines


# ---------------------------------------------------------------------------- patches (installed only when DUCK_EFFECTS=1)
def _fx_install():
    S = _fx_sv._HarnessGameSession; T = _fx_ta.ToolAgent
    if getattr(S, "_fx_installed", False): return "already installed"
    _orig_exec, _orig_step = S._execute_action, S.step_env
    _orig_compact, _orig_bup = T._compact_action_result, T._build_user_prompt

    def _execute_action(self, action, *a, **k):
        try:
            pre = _fx_sv._grid_from_state(self.game.current_state); lvl0 = _fx_sv._level_number(self.game)
        except Exception as e:
            _fx_err("pre-grid", e); return _orig_exec(self, action, *a, **k)
        payload = _orig_exec(self, action, *a, **k)
        try:
            post = _fx_sv._grid_from_state(self.game.current_state)
            tr = self.__dict__.get("_fx_tracker")
            if tr is None: tr = self.__dict__["_fx_tracker"] = _FxTracker()
            rec = tr.feed(pre, post, payload.get("action_display") or action.id.name, payload.get("action_num"), lvl0, payload.get("level"), payload)
            self.__dict__.setdefault("_fx_log", []).append(rec)
            payload["gameplay_changed"] = rec["gameplay_changed"]
        except Exception as e:
            _fx_err("record", e)
        return payload

    def step_env(self, arguments):
        n0 = len(self.__dict__.get("_fx_log", []))
        out = _orig_step(self, arguments)
        try:
            recs = self.__dict__.get("_fx_log", [])[n0:]
            if recs and isinstance(out, dict) and out.get("executed"):
                out["gameplay_changed"] = any(r["gameplay_changed"] for r in recs)
        except Exception as e:
            _fx_err("step_env", e)
        return out

    def _compact_action_result(self, payload):
        c = _orig_compact(self, payload)
        if isinstance(payload, dict) and "gameplay_changed" in payload: c["gameplay_changed"] = bool(payload["gameplay_changed"])
        return c

    def _build_user_prompt(self, *a, **k):
        text = _orig_bup(self, *a, **k)
        try:
            sess = getattr(self._step_env_callback, "__self__", None)
            log = getattr(sess, "__dict__", {}).get("_fx_log") if sess is not None else None
            if log:
                seen = self.__dict__.get("_fx_seen", 0)
                if len(log) > seen:   # new actions since the last prompt; a retried turn reuses the cached block
                    self._fx_block = "\n".join([_FX_HEADER] + _fx_render(log[seen:])); self._fx_seen = len(log)
            block = self.__dict__.get("_fx_block")
            if block and isinstance(text, str):
                i = text.find("\nCurrent state: step ")
                text = text[:i] + "\n" + block + text[i:] if i >= 0 else block + "\n" + text
        except Exception as e:
            _fx_err("prompt", e)
        return text

    S._execute_action, S.step_env = _execute_action, step_env
    T._compact_action_result, T._build_user_prompt = _compact_action_result, _build_user_prompt
    S._fx_installed = True
    return "installed (solver._execute_action/step_env, ToolAgent._compact_action_result/_build_user_prompt)"


def _fx_patch_act_until():
    g = globals()
    if "_NAT_SRC" not in g: return "act_until: natives not loaded, untouched"
    src = g["_NAT_SRC"]
    o1 = "def act_until(actions, stop=('level_completed', 'game_over', 'done'), max_steps=None):"
    n1 = "def act_until(actions, stop=('level_completed', 'game_over', 'done'), max_steps=None, stop_on_no_change=True):"
    o2 = "        if hit:\n            stopped = hit[0]; break\n"
    n2 = o2 + "        if stop_on_no_change and r.get('gameplay_changed') is False:\n            stopped = 'no_gameplay_change'; break\n"
    if src.count(o1) != 1 or src.count(o2) != 1: return "act_until: anchor drift, untouched"
    g["_NAT_SRC"] = src.replace(o1, n1).replace(o2, n2)
    od = "-> run a sequence and stop on level_completed/game_over."
    nd = "-> run a sequence and stop on level_completed/game_over, or on an action that changed nothing but the HUD (stop_on_no_change=False to keep going)."
    if "_NAT_DOC" in g and od in g["_NAT_DOC"]: g["_NAT_DOC"] = g["_NAT_DOC"].replace(od, nd)
    _fx_ta._PYTHON_TOOL_DESCRIPTION = _fx_ta._PYTHON_TOOL_DESCRIPTION.replace(od, nd)
    return "act_until: stops on no gameplay change"


if _FX_ON:
    print(f"EFFECTS -- {_fx_install()}; {_fx_patch_act_until() if _FX_ACT_UNTIL else 'act_until: unchanged (DUCK_EFFECTS_ACT_UNTIL=0)'}; "
          f"border={_FX_BORDER} lines={_FX_LINES} numpy={'yes' if _fx_np is not None else 'no (view-shift off)'}", flush=True)
else:
    print("EFFECTS available but off (DUCK_EFFECTS=1 enables)", flush=True)
