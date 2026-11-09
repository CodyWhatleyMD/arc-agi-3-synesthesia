#!/usr/bin/env python3
"""Perceptual colour distance between the 16 ARC palette colours (CL1/the investigator 14:40: colour is not discrete).

sRGB (D65) -> CIELAB, then CIE76 (Euclidean in Lab) and CIEDE2000 (Sharma, Wu & Dalal 2005, the formula as
published; checked below against their test pairs). `de_matrix()` gives the 16x16 matrix for the engine palette
(arc_agi.rendering.COLOR_MAP, = notebooks_duck/synth_tokens/palette.engine_rgb, verified equal 10-30).
Run directly: the Sharma checks, then the palette's adjacent-pair distances.
"""
from __future__ import annotations

import math

import numpy as np


def srgb_to_lab(rgb255) -> np.ndarray:
    c = np.asarray(rgb255, float) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    eps, kappa = 216 / 24389, 24389 / 27
    f = np.where(xyz > eps, np.cbrt(xyz), (kappa * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def de76(lab1, lab2) -> float:
    return float(np.linalg.norm(np.asarray(lab1, float) - np.asarray(lab2, float)))


def de2000(lab1, lab2) -> float:
    L1, a1, b1 = lab1; L2, a2, b2 = lab2
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if (a1p or b1) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if (a2p or b2) else 0.0
    dLp = L2 - L1; dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    else:
        dhp = h2p - h1p
        if dhp > 180:
            dhp -= 360
        elif dhp < -180:
            dhp += 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp) / 2)
    Lbp = (L1 + L2) / 2; Cbp = (C1p + C2p) / 2
    if C1p * C2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hbp = (h1p + h2p + 360) / 2
    else:
        hbp = (h1p + h2p - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hbp - 30)) + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6)) - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    dtheta = 30 * math.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / math.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp; Sh = 1 + 0.015 * Cbp * T
    Rt = -math.sin(math.radians(2 * dtheta)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def palette_rgb() -> np.ndarray:
    from arc_agi.rendering import COLOR_MAP, hex_to_rgb
    return np.array([hex_to_rgb(COLOR_MAP[v])[:3] for v in range(16)], float)


def de_matrix(kind: str = "2000") -> np.ndarray:
    lab = srgb_to_lab(palette_rgb())
    f = de2000 if kind == "2000" else de76
    return np.array([[f(lab[a], lab[b]) for b in range(16)] for a in range(16)])


SHARMA = [  # (Lab1, Lab2, published dE2000) -- Sharma, Wu & Dalal 2005, Table 1, pairs 1, 2, 3, 7, 17, 25
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
    ((50.0000, 0.0000, 0.0000), (50.0000, -1.0000, 2.0000), 2.3669),
    ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
]

if __name__ == "__main__":
    for l1, l2, want in SHARMA:
        got = de2000(l1, l2)
        print(f"Sharma {l1} vs {l2}: dE2000 {got:.4f} (published {want}) {'OK' if abs(got - want) < 1e-3 else 'MISMATCH'}")
    S = "WwgGcBMPRbSYOrNp"
    d00, d76 = de_matrix("2000"), de_matrix("76")
    for a, b in ((5, 4), (4, 3), (3, 2), (2, 1), (1, 0), (5, 3), (5, 9), (5, 10), (5, 6), (8, 12), (6, 7)):
        print(f"{a:2d}{S[a]}-{b:2d}{S[b]}: dE2000 {d00[a, b]:5.1f}  dE76 {d76[a, b]:5.1f}")
    print("pairs within dE2000 <= 25:", [f"{S[a]}{S[b]}" for a in range(16) for b in range(a + 1, 16) if d00[a, b] <= 25])
