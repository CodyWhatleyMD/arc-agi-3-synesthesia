# ---- BAYESIAN INDEX STOPPING POLICY (findings 53, corrected by findings 55) ----------------------
# House rule: /home/ignaz/duck-harness is third-party and stays byte-identical, so this is a
# monkeypatch, the same shape as cell_duck_fixes.py / cell_breaker.py.
#
# WHAT WAS MISSING
# ----------------
# findings 53 worked out a stopping rule and nothing ever implemented it. The should_stop() the
# Duck runs actually execute (inference/framework/solver.py:246-261) has five clauses -- run not
# playing, stop_event, run complete, runtime limit, max_actions_per_game -- and no progress or
# hazard clause at all. A game that will never clear holds its concurrency slot for the whole
# per-game wall clock. On the hidden set that is decisive: 110 games over 28 slots means a dead
# game costs a queued game its entire turn.
#
# THE MODEL (findings 53, verbatim)
#   n_i ~ Poisson(lambda_i T_i),  lambda_i ~ Gamma(a, b)   -- clears are events, stalls are
#                                                             CENSORED exposure, not zeros
#   posterior_i   Gamma(a + clears_i, b + exposure_i)
#   predictive    P_i(D) = 1 - (b_i / (b_i + D))^{a_i}      -- P(>=1 clear in the next D actions)
#   weight        w(j)   = j / (n(n+1)/2) * 100             -- score weights level k by k, so the
#                                                             NEXT level j = depth+1 is the payoff
#   index_i       P_i(D) * w(depth_i + 1)
#   decision      cut game i when index_i < the index of a FRESH slot (prior only, depth 0)
# Declining hazard is not fitted, it emerges: exposure without events grows b, so P falls by itself.
#
# THE NUMBERS ARE findings 55's, NOT findings 53's. 53 is superseded in part: it counted 82 clears
# / 24 censored, treating a stall as an event; the corpus is 59 clears / 47 censored, so the prior
# is Gamma(1.38, 149) -- mean 9.23 clears per 1000 actions -- not Gamma(1.50, 110) / 13.60, and the
# fresh-slot index is 0.912, not 1.192. The keep/cut verdicts are unchanged because the index is a
# ratio and the error was near-multiplicative, but the absolute rate and the prior must come from
# 55. The install-time self-test below reproduces 55's fresh-slot index and 53's whole verdict
# table, so a future edit that reverts to the 82/24 numbers fails loudly instead of silently.
#
# IMPLEMENTABLE ON THE HIDDEN SET: w(j) needs `number_of_levels`, which taaf/game.py:294 makes a
# required field -- unlike `base_actions_per_level`, which is None in submission mode (findings 52).
#
# GATED OFF BY DEFAULT: INDEX_POLICY=1 to install. This one really is a policy change -- it ends
# games early -- so it does not belong in a comparison run that was not designed for it. But the
# gate PRINTS EITHER WAY: findings 4adb4d7's third defect was a shim that shipped switched off and
# silently never applied, so "not installed" must be as visible in the log as "installed".
#
# OVERLAP, stated rather than discovered later: cell_duck_fixes.py already installs a never-started
# kill at DUCK_DEAD_GAME_ACTIONS=120 actions with 0 levels, which is the same cut this policy's
# second clause makes (the index puts the never-started cut between 100 and 150 actions -- an
# independent rediscovery of findings 49's empirical K~100). This cell WRAPS whatever should_stop
# is bound at install time, so the two compose rather than clobber; with both on, the earlier of
# the two fires.
import os as _os

INDEX_POLICY_ON = _os.environ.get("INDEX_POLICY", "0") == "1"
INDEX_PRIOR_A = float(_os.environ.get("INDEX_PRIOR_A", "1.38"))    # findings 55
INDEX_PRIOR_B = float(_os.environ.get("INDEX_PRIOR_B", "149"))     # findings 55, in actions
INDEX_HORIZON_D = float(_os.environ.get("INDEX_HORIZON_D", "50"))  # findings 53's D
INDEX_MIN_ACTIONS = int(_os.environ.get("INDEX_MIN_ACTIONS", "60"))  # never cut before this


def _index_P(a_i, b_i, D):
    """predictive P(>=1 clear in the next D actions) under Gamma(a_i, b_i)"""
    return 1.0 - (b_i / (b_i + D)) ** a_i


def _index_w(j, n_levels):
    """payoff weight of reaching level j, normalised over the game's own ladder"""
    n = max(1, int(n_levels))
    return j / (n * (n + 1) / 2.0) * 100.0


def index_of(clears, exposure, n_levels, D=INDEX_HORIZON_D):
    a_i = INDEX_PRIOR_A + clears
    b_i = INDEX_PRIOR_B + exposure
    return _index_P(a_i, b_i, D) * _index_w(clears + 1, n_levels)


def fresh_slot_index(n_levels=8, D=INDEX_HORIZON_D):
    """a brand-new game: prior only, depth 0. findings 53's table used an 8-level game."""
    return index_of(0, 0, n_levels, D)


# ---- SELF-TEST: the published table, reproduced, before anything is installed -------------------
_fresh = fresh_slot_index()
assert abs(_fresh - 0.912) < 0.005, (
    f"index policy self-test FAILED: fresh-slot index {_fresh:.4f}, findings 55 says 0.912. "
    f"The prior is probably back to findings 53's superseded Gamma(1.50, 110).")
_TABLE = [   # (clears, exposure, expected verdict) -- findings 53's policy table at D=50
    (0, 150, "CUT"), (0, 400, "CUT"),
    (1, 300, "keep"), (2, 300, "keep"), (5, 300, "keep"),
    (7, 1500, "keep"),
    (2, 2152, "CUT"),        # ka59's 2,152-action stall, cut with no hand-set threshold
]
for _c, _e, _want in _TABLE:
    _got = "CUT" if index_of(_c, _e, 8) < _fresh else "keep"
    assert _got == _want, (f"index policy self-test FAILED: {_c} levels / {_e} actions -> {_got}, "
                           f"findings 53 says {_want} (index {index_of(_c, _e, 8):.3f} vs fresh {_fresh:.3f})")

if not INDEX_POLICY_ON:
    print(f"INDEX POLICY: NOT INSTALLED (INDEX_POLICY=0). Self-test passed: fresh-slot index "
          f"{_fresh:.3f}, {len(_TABLE)}/{len(_TABLE)} table rows reproduced. Set INDEX_POLICY=1 "
          f"to enable early stopping.", flush=True)
else:
    import inference.framework.solver as _sv

    def _install_index_policy():
        if getattr(_sv, "_cc_index_policy", False):
            return "already installed"
        holder = None
        for _name in dir(_sv):
            _obj = getattr(_sv, _name)
            if isinstance(_obj, type) and "should_stop" in _obj.__dict__:
                holder = _obj
                break
        if holder is None:
            return "NOT INSTALLED (no class defining should_stop)"
        _orig = holder.should_stop      # whatever is bound NOW, so this stacks on cell_duck_fixes

        def _patched(self):
            if _orig(self):
                return True
            try:
                run = self.game.game_run
                if run is None or getattr(run, "state", None) != "playing":
                    return False
                exposure = int(getattr(self, "action_count", 0))
                if exposure < INDEX_MIN_ACTIONS:
                    return False
                clears = int(getattr(run, "levels_completed", 0) or 0)
                n_levels = int(getattr(run, "number_of_levels", 0) or 0)
                if n_levels <= 0:
                    return False       # cannot weight the payoff; do not guess, do not cut
                idx = index_of(clears, exposure, n_levels)
                fresh = fresh_slot_index(n_levels)
                if idx < fresh:
                    if not getattr(self, "_cc_index_logged", False):
                        self._cc_index_logged = True
                        why = ("never started" if clears == 0 else f"stalled after {clears} level(s)")
                        print(f"INDEX POLICY CUT: {getattr(run, 'game_id', '?')} {why} -- "
                              f"index {idx:.3f} < fresh slot {fresh:.3f} "
                              f"({clears} levels / {exposure} actions / {n_levels} levels total); "
                              f"releasing the slot", flush=True)
                    return True
            except Exception:
                return False           # a broken read must never end a live game
            return False

        holder.should_stop = _patched
        _sv._cc_index_policy = True
        return f"installed on {holder.__name__}"

    _status = _install_index_policy()
    print(f"INDEX POLICY INSTALLED: {_status}  prior=Gamma({INDEX_PRIOR_A}, {INDEX_PRIOR_B}) "
          f"D={INDEX_HORIZON_D} min_actions={INDEX_MIN_ACTIONS} fresh_slot_index={_fresh:.3f} "
          f"(self-test {len(_TABLE)}/{len(_TABLE)} table rows reproduced)", flush=True)
