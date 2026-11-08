"""Boucle commune des canaris de dérive : fetch live, comparaison au seed, verdict.

Un fetch en échec est un blip réseau (warning, exit 0) ; un écart au-delà du
seuil sur un fetch réussi est une dérive amont (exit 1, re-seed humain). Le
mode ``offline`` est refusé : le fetch renverrait le seed et le canari serait
aveugle.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, NamedTuple

import httpx

from kuma_data_core.db.seeds.localites_prefectures_seed_data import (
    COMMUNES_DENSIFICATION,
    NOUVELLES_COMMUNES,
)
from kuma_data_core.db.seeds.localites_seed_data import LOCALITES_SEED
from kuma_data_core.ingestion._mode import MODE_OFFLINE, mode_ingestion

ERREURS_RESEAU: tuple[type[Exception], ...] = (httpx.HTTPError, RuntimeError)
"""Échecs de fetch communs à toutes les sources ; chaque canari y ajoute les siens."""

Payload = dict[str, Any]


class MessagesCanari(NamedTuple):
    """Gabarits ``str.format`` des lignes imprimées (annotations GitHub Actions).

    Champs : ``blip`` {code, erreur} ; ``point`` {code, ecart, statut} ;
    ``derive`` {seuil, derives} ; ``incomplet`` {nb_blips, blips} ;
    ``ok`` {seuil, ecart_global} ; plus ceux de ``contexte``.
    """

    blip: str
    point: str
    derive: str
    incomplet: str
    ok: str


def coordonnees_points(pilotes: Sequence[str]) -> dict[str, tuple[float, float]]:
    """``(lat, lon)`` des ``pilotes`` (``LOCALITES_SEED``) puis des communes densifiées."""
    index = {e["code"]: e for e in (*LOCALITES_SEED, *NOUVELLES_COMMUNES)}
    return {
        code: (float(index[code]["latitude"]), float(index[code]["longitude"]))
        for code in (*pilotes, *COMMUNES_DENSIFICATION)
    }


def executer_canari(
    *,
    pilotes: Sequence[str],
    fetch: Callable[[float, float], Payload],
    seed: Callable[[float, float], Payload],
    ecart: Callable[[Payload, Payload], float],
    erreurs_fetch: tuple[type[Exception], ...],
    seuil: float,
    messages: MessagesCanari,
    contexte: Mapping[str, object] | None = None,
) -> int:
    """Compare chaque point au seed ; code de sortie 0 (OK ou blip) ou 1 (dérive)."""
    if mode_ingestion() == MODE_OFFLINE:
        raise RuntimeError(
            "Le canari requiert KUMA_INGESTION_MODE=live (compare le fetch reel au seed)."
        )
    champs: dict[str, object] = {"seuil": seuil, **(contexte or {})}

    derives: list[tuple[str, float]] = []
    blips: list[str] = []
    ecart_global = 0.0

    for code, (lat, lon) in coordonnees_points(pilotes).items():
        try:
            live = fetch(lat, lon)
        except erreurs_fetch as exc:
            print(messages.blip.format(code=code, erreur=type(exc).__name__, **champs))
            blips.append(code)
            continue

        ecart_point = ecart(live, seed(lat, lon))
        ecart_global = max(ecart_global, ecart_point)
        statut = "DERIVE" if ecart_point > seuil else "OK"
        if ecart_point > seuil:
            derives.append((code, ecart_point))
        print(messages.point.format(code=code, ecart=ecart_point, statut=statut, **champs))

    if derives:
        print(messages.derive.format(derives=derives, **champs))
        return 1
    if blips:
        print(messages.incomplet.format(nb_blips=len(blips), blips=blips, **champs))
        return 0
    print(messages.ok.format(ecart_global=ecart_global, **champs))
    return 0
