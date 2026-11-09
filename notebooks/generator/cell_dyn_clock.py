# ---- DYNAMIC PER-GAME CLOCK (2026-10-02, workflow pace; scheduling plan v2 section 9, policy "[A]") -----------------------------
# House rule: the vendored harness stays byte-identical, so this is a monkeypatch exec'd in cell 14 -- embedded in the notebook
# text by build_notebook.py (CLOCK=dyn), so the frozen bundle dataset is not re-uploaded. Also exec-able by a local runner.
#
# WHAT IT REPLACES. Duck gives every game the same fixed clock: max_runtime_s_per_game (7920 s on the hidden rerun, cell 12)
# from slot acquisition (solver.py:179, 212-226), and one semaphore slot per game for the whole game (solver.py:898-910). With
# 110 games over 28 slots that overcommits (4 x 7920 = 31,680 s > the ~30,860 s from the first game start to soft_end), and a
# game that is still clearing levels is cut on the same clock as one that never will (v5 clears at 7,402-7,508 s).
#
# THE POLICY (pace/sim.py "dyn"; scheduling plan v2 sections 5 and 9):
#   fair share at start : budget = clip((c * (soft_end - now) - running games' committed remaining) / (unstarted + 1),
#                         FLOOR * T0, soft_end - now);  c = solver.concurrency, unstarted counted after this game,
#                         T0 = c * (soft_end - t_first_start) / n_games  (hidden: 28 * 30,860 / 110 = 7,855 s)
#   extension on a clear: deadline = max(deadline, now + EXT) while the pool keeps >= GUARD * T0 for every unstarted game
#   end-of-run release  : once every game has started, every running game may run to soft_end
#   cuts                : NOT here. DUCK_DEAD_GAME_ACTIONS / DUCK_LEVEL_CAP (cell_duck_fixes) end a game early; its unused
#                         time goes back to the pool by itself (it no longer counts as committed).
# The model sees the dynamic deadline as time_remaining_seconds (timing_payload, copied into every action result by
# tool_agent.py:1446), and request timeouts follow it (request_timeout_seconds reads timing_payload).
# Simulated (pace/sched_v2, R=200, CPU only, never measured on a GPU): dyn alone +0.00; with DEAD_K 60 + LEVEL_CAP 100 + EXT
# 5400 +0.51 / +0.77 / +0.24 hidden (H1 / H2 / H3) at the cost of 6-8 games with >= 1 level. One submission cannot confirm it.
#
# SAFETY.
#   - Install: every solver.py anchor below must occur exactly once and the four replaced callables must still be the shipped
#     ones. A mismatch raises on a validation run (TRUE_SUBMISSION False: quota / smoke) and, on the hidden rerun, is printed
#     and the shipped fixed clock stays (v5 behaviour).
#   - Run time: any exception in the clock logic latches the shim OFF for the rest of the run; every game then falls back to
#     the shipped fixed clock (max_runtime_s_per_game from slot acquisition). Loud on both kinds of run.
#   - A deadline never falls below min(FLOOR * T0, soft_end - now). With SMOKE_GATE on, the smoke budget
#     (max_runtime_s_per_game, 600 s) still caps every deadline.
#   - One lock, short critical sections, no I/O under it.
import os as _dc_os, threading as _dc_threading, time as _dc_time, traceback as _dc_tb, json as _dc_json, inspect as _dc_inspect

_DC_ANCHORS = (   # inference/framework/solver.py text this shim depends on -- each must occur exactly once
    # the two methods replaced: a fixed budget from slot acquisition
    "    def runtime_limit_reached(self) -> bool:\n"
    "        if self.solver.max_runtime_s_per_game is None:\n"
    "            return False\n"
    "        return (\n"
    "            time.monotonic() - self.started_at\n"
    "        ) >= self.solver.max_runtime_s_per_game\n",
    "    def timing_payload(self) -> dict[str, float | None]:\n"
    "        elapsed = max(0.0, time.monotonic() - self.started_at)\n"
    "        if self.solver.max_runtime_s_per_game is None:\n"
    "            remaining = None\n"
    "        else:\n"
    "            remaining = max(0.0, self.solver.max_runtime_s_per_game - elapsed)\n"
    '        return {"run_elapsed_seconds": elapsed, "time_remaining_seconds": remaining}\n',
    # should_stop consults the runtime check (cell_duck_fixes' wrappers call this original first)
    "        if self.runtime_limit_reached():\n"
    "            return True\n",
    # the shipped clock starts at slot acquisition, on the monotonic clock
    "    started_at: float = field(default_factory=time.monotonic)\n",
    # one slot per game for the whole game; _play_one(game, ...) runs the game in a pool thread
    "        semaphore = asyncio.Semaphore(max(1, int(self.concurrency)))\n",
    "            async with semaphore:\n"
    "                args = (game, index, pass_index, self._local_server_for_game_index(index))\n",
    "    def _play_one(\n"
    "        self,\n"
    "        game: taaf.game.Game,\n"
    "        index: int,\n"
    "        pass_index: int,\n"
    "        local_server: _LocalServerRuntime | None = None,\n"
    "    ) -> None:\n",
    "    async def _run_games(self, games: list[taaf.game.Game]) -> None:\n",
    "    def soft_time_remaining_seconds(self) -> float | None:\n",
)


def _dc_check_anchors(text):
    """[(anchor index, count)] for every anchor that does not occur exactly once in `text` (empty = all good)."""
    return [(i, text.count(a)) for i, a in enumerate(_DC_ANCHORS) if text.count(a) != 1]


_DC_EXT_S = float(_dc_os.environ.get("DUCK_DYN_EXT_S", "5400"))
_DC_GUARD = float(_dc_os.environ.get("DUCK_DYN_GUARD", "0.85"))
_DC_FLOOR = float(_dc_os.environ.get("DUCK_DYN_FLOOR", "0.5"))
_dc_now = _dc_time.monotonic          # the shipped clock's time source (tests replace it with a fake clock)
# state survives a second exec in the same namespace (installed wrappers look these names up at call time)
_DC_LOCK = globals().get("_DC_LOCK") or _dc_threading.Lock()
_DC_ORIG = globals().get("_DC_ORIG") or {}
_DC = globals().get("_DC") or {"on": False, "broken": None, "n": 0, "c": 0, "t0": 0.0, "soft_end": 0.0, "T0": 0.0, "started": 0,
                               "games": {}, "released_at": None, "cap_s": None, "ext_granted": 0, "ext_denied": 0, "starts": [],
                               "ends": [], "exts": []}


def _dc_log(msg):
    print("DYN CLOCK " + msg, flush=True)


def _dc_break(exc):
    """Latch the shim OFF (called from inside an except block). Every game falls back to the shipped fixed clock."""
    with _DC_LOCK:
        first = _DC["broken"] is None
        if first:
            _DC["broken"] = f"{type(exc).__name__}: {exc}"
    if first:
        _dc_tb.print_exc()
        _dc_log(f"FELL BACK ({type(exc).__name__}: {exc}) -- every game now runs on the shipped fixed clock "
                f"(max_runtime_s_per_game from slot acquisition)")


def _dc_committed(now, se, all_started):
    """Running games' committed remaining time, each capped at soft_end. Caller holds _DC_LOCK."""
    tot = 0.0
    for r in _DC["games"].values():
        tot += max(0.0, (se if all_started else min(r["dl"], se)) - now)
    return tot


def _dc_begin(solver, n):
    """Plan the run when _run_games starts: n games over c slots until soft_end."""
    rem = solver.soft_time_remaining_seconds()
    c = max(1, int(solver.concurrency))
    fixed = solver.max_runtime_s_per_game
    cap = float(fixed) if (globals().get("SMOKE_GATE") and fixed is not None) else None
    now = _dc_now()
    with _DC_LOCK:
        _DC.update(on=False, broken=None, n=int(n), c=c, t0=now, started=0, games={}, released_at=None, cap_s=cap,
                   ext_granted=0, ext_denied=0, starts=[], ends=[], exts=[])
        why = ("no soft_end_time" if rem is None else "no games" if n <= 0
               else "max_runtime_s_per_game is None (the shipped harness has no clock either)" if fixed is None else None)
        if why is None:
            _DC.update(on=True, soft_end=now + float(rem), T0=c * float(rem) / int(n))
    if why is not None:
        _dc_log(f"OFF for this run: {why} -- the shipped clock applies")
        return
    _dc_log(f"PLAN n_games={n} concurrency={c} soft_end_in={float(rem):.0f}s T0={_DC['T0']:.0f}s (shipped fixed clock "
            f"{float(fixed):.0f}s) ext={_DC_EXT_S:.0f}s guard={_DC_GUARD} floor={_DC_FLOOR}xT0"
            + (f" smoke_cap={cap:.0f}s" if cap is not None else ""))


def _dc_game_id(game):
    try:
        return str(getattr(game.game_run, "game_id", None) or getattr(game, "env_name", None) or "?")
    except Exception:
        return "?"


def _dc_on_start(game):
    """A game acquired its slot: give it the fair share of what is left."""
    gid = _dc_game_id(game)
    now = _dc_now()
    with _DC_LOCK:
        if not _DC["on"] or _DC["broken"] is not None:
            return
        _DC["started"] += 1
        n, c, se, T0 = _DC["n"], _DC["c"], _DC["soft_end"], _DC["T0"]
        U = max(0, n - _DC["started"])
        left = max(0.0, se - now)
        avail = c * left - _dc_committed(now, se, False)
        T = min(max(avail / (U + 1), 0.0), left)
        floor = min(_DC_FLOOR * T0, left)
        floored = T < floor
        T = max(T, floor)
        _DC["games"][id(game)] = {"gid": gid, "dl": now + T, "t_start": now, "budget0": T, "lv": 0, "ext": 0}
        rec = {"gid": gid, "t": round(now - _DC["t0"], 1), "budget": round(T, 1), "unstarted": U, "running": len(_DC["games"]),
               "floored": floored}
        _DC["starts"].append(rec)
        release = _DC["started"] >= n and _DC["released_at"] is None
        if release:
            _DC["released_at"] = now
        started = _DC["started"]
    _dc_log(f"start {gid} #{started}/{n} at +{rec['t']:.0f}s budget={T:.0f}s unstarted={U} running={rec['running']}"
            + (" (FLOOR)" if floored else ""))
    if release:
        _dc_log(f"all {n} games started at +{rec['t']:.0f}s -- every running game may now run to soft_end")


def _dc_on_end(game):
    now = _dc_now()
    with _DC_LOCK:
        r = _DC["games"].pop(id(game), None)
        if r is None:
            return
        rec = {"gid": r["gid"], "t": round(now - _DC["t0"], 1), "elapsed": round(now - r["t_start"], 1),
               "budget0": round(r["budget0"], 1), "final_deadline_rel": round(min(r["dl"], _DC["soft_end"]) - r["t_start"], 1),
               "levels": r["lv"], "extensions": r["ext"]}
        _DC["ends"].append(rec)
    _dc_log(f"end {rec['gid']} after {rec['elapsed']:.0f}s (budget at start {rec['budget0']:.0f}s, extensions {rec['extensions']}, "
            f"levels seen {rec['levels']})")


def _dc_deadline(session):
    """Effective monotonic deadline of this session's game, or None if the shim does not manage it. Detects a level clear
    (levels_completed went up) and applies the extension rule."""
    game = session.game
    run = game.game_run
    lv = int(getattr(run, "levels_completed", 0) or 0) if run is not None else 0
    now = _dc_now()
    msg = None
    with _DC_LOCK:
        r = _DC["games"].get(id(game))
        if r is None:
            return None
        se, n = _DC["soft_end"], _DC["n"]
        all_started = _DC["started"] >= n
        if lv > r["lv"]:
            r["lv"] = lv
            U = max(0, n - _DC["started"])
            if U > 0 and _DC_EXT_S > 0:
                pool = _DC["c"] * max(0.0, se - now) - _dc_committed(now, se, all_started)
                ok = pool - _DC_EXT_S >= _DC_GUARD * _DC["T0"] * U
                if ok and now + _DC_EXT_S > r["dl"]:
                    old = r["dl"]; r["dl"] = now + _DC_EXT_S; r["ext"] += 1; _DC["ext_granted"] += 1
                    _DC["exts"].append({"gid": r["gid"], "t": round(now - _DC["t0"], 1), "level": lv, "granted": True,
                                        "pool": round(pool, 1), "unstarted": U, "added": round(r["dl"] - old, 1)})
                    msg = f"+ext {r['gid']} level {lv} at +{now - _DC['t0']:.0f}s: deadline +{r['dl'] - old:.0f}s (pool {pool:.0f}s, unstarted {U})"
                elif not ok:
                    _DC["ext_denied"] += 1
                    _DC["exts"].append({"gid": r["gid"], "t": round(now - _DC["t0"], 1), "level": lv, "granted": False,
                                        "pool": round(pool, 1), "unstarted": U, "added": 0.0})
                    msg = f"ext DENIED {r['gid']} level {lv} at +{now - _DC['t0']:.0f}s (pool {pool:.0f}s < {_DC_EXT_S:.0f}s + {_DC_GUARD} x T0 x {U} unstarted)"
        dl = se if all_started else min(r["dl"], se)
        if _DC["cap_s"] is not None:
            dl = min(dl, r["t_start"] + _DC["cap_s"])
    if msg:
        _dc_log(msg)
    return dl


# ---- the replacements --------------------------------------------------------------------------------------------------------
def _dc_runtime_limit_reached(self):
    if _DC["on"] and _DC["broken"] is None:
        try:
            dl = _dc_deadline(self)
            if dl is not None:
                return _dc_now() >= dl
        except Exception as exc:
            _dc_break(exc)
    return _DC_ORIG["runtime_limit_reached"](self)


def _dc_timing_payload(self):
    out = _DC_ORIG["timing_payload"](self)
    if _DC["on"] and _DC["broken"] is None and out.get("time_remaining_seconds") is not None:
        try:
            dl = _dc_deadline(self)
            if dl is not None:
                out = dict(out, time_remaining_seconds=max(0.0, dl - _dc_now()))
        except Exception as exc:
            _dc_break(exc)
            out = _DC_ORIG["timing_payload"](self)
    return out


def _dc_play_one(self, game, *args, **kwargs):
    if _DC["on"] and _DC["broken"] is None:
        try:
            _dc_on_start(game)
        except Exception as exc:
            _dc_break(exc)
    try:
        return _DC_ORIG["_play_one"](self, game, *args, **kwargs)
    finally:
        try:
            _dc_on_end(game)
        except Exception as exc:
            _dc_break(exc)


async def _dc_run_games(self, games):
    try:
        _dc_begin(self, len(games))
    except Exception as exc:
        _dc_break(exc)
    try:
        return await _DC_ORIG["_run_games"](self, games)
    finally:
        try:
            _dc_summary()
        except Exception:
            _dc_tb.print_exc()


def _dc_summary():
    with _DC_LOCK:
        snap = {k: (list(v) if isinstance(v, list) else v) for k, v in _DC.items() if k != "games"}
        snap["still_running"] = len(_DC["games"])
    floored = sum(1 for s in snap["starts"] if s["floored"])
    _dc_log(f"SUMMARY on={snap['on']} fell_back={snap['broken']} started={snap['started']}/{snap['n']} ended={len(snap['ends'])} "
            f"extensions granted={snap['ext_granted']} denied={snap['ext_denied']} floored_starts={floored} "
            f"released_at={'+%.0fs' % (snap['released_at'] - snap['t0']) if snap['released_at'] else 'never'}")
    wd = globals().get("WORKING_DIR")
    if wd is not None:
        try:
            snap.update(ext_s=_DC_EXT_S, guard=_DC_GUARD, floor=_DC_FLOOR)
            open(_dc_os.path.join(str(wd), "dyn_clock.json"), "w").write(_dc_json.dumps(snap, indent=1, default=str))
        except Exception:
            _dc_tb.print_exc()


def _dc_install():
    import inference.framework.solver as _sv
    S, H = _sv._HarnessGameSession, _sv.HarnessSolver
    if getattr(S.__dict__.get("runtime_limit_reached"), "_dc_dyn", False):
        return "already installed"
    with open(_sv.__file__, encoding="utf-8") as fh:
        bad = _dc_check_anchors(fh.read())
    if bad:
        raise RuntimeError(f"solver.py anchors {bad} (index, count; want count 1) -- not the bundle this shim was written against")
    for cls, name in ((S, "runtime_limit_reached"), (S, "timing_payload"), (H, "_play_one"), (H, "_run_games")):
        fn = cls.__dict__.get(name)
        if getattr(fn, "__qualname__", None) != f"{cls.__name__}.{name}" or getattr(fn, "__module__", None) != _sv.__name__:
            raise RuntimeError(f"{cls.__name__}.{name} is not the shipped function (wrapped by another shim?): {fn!r}")
    if not _dc_inspect.iscoroutinefunction(H.__dict__["_run_games"]):
        raise RuntimeError("HarnessSolver._run_games is not a coroutine function")
    for name, cls, new in (("runtime_limit_reached", S, _dc_runtime_limit_reached), ("timing_payload", S, _dc_timing_payload),
                           ("_play_one", H, _dc_play_one), ("_run_games", H, _dc_run_games)):
        _DC_ORIG[name] = cls.__dict__[name]
        new._dc_dyn = True
    S.runtime_limit_reached = _dc_runtime_limit_reached
    S.timing_payload = _dc_timing_payload
    H._play_one = _dc_play_one
    H._run_games = _dc_run_games
    return f"installed on {S.__name__} (runtime_limit_reached, timing_payload) + {H.__name__} (_play_one, _run_games)"


_DC_FAIL_OPEN = bool(globals().get("TRUE_SUBMISSION", True))
if globals().get("_DC_BUILD_CHECK"):
    pass   # the generator only reads _DC_ANCHORS / _dc_check_anchors
elif _dc_os.environ.get("DUCK_DYN_CLOCK", "0") != "1":
    print("DYN CLOCK: NOT INSTALLED (DUCK_DYN_CLOCK != 1) -- the shipped fixed per-game clock applies", flush=True)
else:
    try:
        _dc_status = _dc_install()
    except Exception as _dc_exc:
        if not _DC_FAIL_OPEN:
            raise
        _dc_tb.print_exc()
        _dc_status = f"NOT INSTALLED ({type(_dc_exc).__name__}: {_dc_exc}) -- TRUE_SUBMISSION: the shipped fixed clock stays"
    print(f"DYN CLOCK: {_dc_status} | ext {_DC_EXT_S:.0f}s guard {_DC_GUARD} floor {_DC_FLOOR}xT0 | cuts: "
          f"dead_k={_dc_os.environ.get('DUCK_DEAD_GAME_ACTIONS', '120(default)')} "
          f"level_cap={_dc_os.environ.get('DUCK_LEVEL_CAP', '200(default)')}", flush=True)
