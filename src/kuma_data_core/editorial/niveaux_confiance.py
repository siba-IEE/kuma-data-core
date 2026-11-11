"""Niveaux de confiance A/B/C : dérivation, propagation et override.

- ``A`` : mesure directe par instrument de référence, ou calcul exact à
  partir de valeurs elles-mêmes A.
- ``B`` : donnée modélisée, interpolée ou extrapolée selon une méthode
  documentée, sur une source de fiabilité haute ou moyenne.
- ``C`` : estimation par expertise sans validation instrumentale, ou source
  de fiabilité faible.

Règles de dérivation, évaluées dans l'ordre ; la première qui s'applique
donne le niveau :

| Règle | Condition | Résultat |
|---|---|---|
| R1 | ``source.fiabilite = 'faible'`` | ``C`` |
| R2 | ``methode_collecte = 'expertise_humaine'`` | ``C`` |
| R3 | ``methode_collecte = 'mesure_directe'`` et ``source.fiabilite = 'haute'`` | ``A`` |
| P | ``methode_collecte = 'calcul_derive'``, entrées connues | entrées et plafond, le plus bas |
| R4 | tous les autres cas | ``B`` |

Règle de propagation P (ADR-0008) : une grandeur calculée prend le niveau
effectif (override sinon dérivé) le plus bas des valeurs dont elle est tirée,
sans dépasser le plafond de sa méthode. Le plafond est ``B`` par défaut :
seul un calcul exact, sans modèle ni hypothèse de l'utilisateur (agrégation,
ratio, formule fermée, statistique), le relève à ``A``, et seulement si la
source du calcul est de fiabilité ``haute``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Iterable
from datetime import date, datetime
from typing import Literal, Protocol

from kuma_data_core.exceptions import JustificationRequise, NiveauConfianceInvalide

NIVEAUX_CONFIANCE_AUTORISES: frozenset[str] = frozenset({"A", "B", "C"})
"""Miroir des contraintes SQL ``ck_<table>_niveau_confiance_*_valide``."""

NiveauConfiance = Literal["A", "B", "C"]

_RANG_NIVEAU: dict[str, int] = {"C": 0, "B": 1, "A": 2}
_NIVEAU_DU_RANG: dict[int, NiveauConfiance] = {0: "C", 1: "B", 2: "A"}


class _LigneAvecOverride(Protocol):
    """Ce qu'une ligne doit exposer pour recevoir un override, quel que soit son modèle."""

    niveau_confiance_override: str | None
    commentaire_editorial: str | None


def valider_niveau_confiance(niveau: str) -> None:
    """Lève ``NiveauConfianceInvalide`` si ``niveau`` n'est pas A, B ou C."""
    if niveau not in NIVEAUX_CONFIANCE_AUTORISES:
        raise NiveauConfianceInvalide(valeur_recue=niveau)


def propager_niveau_confiance(
    niveaux_entrees: Iterable[str], plafond: NiveauConfiance = "B"
) -> NiveauConfiance:
    """Règle P : le plus bas des niveaux d'entrée et du plafond de la méthode.

    Lève ``ValueError`` sans entrée, ``TypeError`` si les entrées sont une
    chaîne (``'AB'`` n'est pas une liste de niveaux) et
    ``NiveauConfianceInvalide`` pour un niveau hors A, B, C.
    """
    if isinstance(niveaux_entrees, str):
        raise TypeError("Les niveaux d'entrée sont une collection de niveaux, pas une chaîne.")
    niveaux = set(niveaux_entrees)
    if not niveaux:
        raise ValueError("Propagation du niveau de confiance sans aucune entrée.")
    for niveau in (*niveaux, plafond):
        valider_niveau_confiance(niveau)
    return _NIVEAU_DU_RANG[min(_RANG_NIVEAU[niveau] for niveau in (*niveaux, plafond))]


def calculer_niveau_confiance_derive(
    methode_collecte: str | None,
    fiabilite_source: str | None,
    niveaux_entrees: Collection[str] | None = None,
    plafond: NiveauConfiance = "B",
) -> str:
    """Applique R1, R2, R3, P puis R4 ; la première règle qui s'applique l'emporte.

    Sans ``niveaux_entrees``, P ne s'applique pas et R4 donne B. ``plafond``
    est ramené à B si la source du calcul n'est pas de fiabilité haute.
    """
    if fiabilite_source == "faible":
        return "C"
    if methode_collecte == "expertise_humaine":
        return "C"
    if methode_collecte == "mesure_directe" and fiabilite_source == "haute":
        return "A"
    if methode_collecte == "calcul_derive" and niveaux_entrees:
        valider_niveau_confiance(plafond)
        plafond_source: NiveauConfiance = plafond if fiabilite_source == "haute" else "B"
        return propager_niveau_confiance(
            niveaux_entrees, plafond=min(plafond, plafond_source, key=_RANG_NIVEAU.__getitem__)
        )
    return "B"


class NiveauxEntrees:
    """Niveaux effectifs des valeurs d'entrée d'un calcul, par jour et par mois.

    Une entrée journalière est rangée sous son jour, une entrée horaire sous
    son jour local, une entrée mensuelle sous son mois. Chaque valeur calculée
    prend le niveau des seules entrées de sa période.
    """

    def __init__(self) -> None:
        self._jours: dict[date, set[str]] = defaultdict(set)
        self._mois_seuls: dict[tuple[int, int], set[str]] = defaultdict(set)
        self._mois: dict[tuple[int, int], set[str]] = defaultdict(set)

    def ajouter(self, instant: date | tuple[int, int], niveau: str) -> None:
        """Range le niveau d'une entrée sous son jour ou sous son mois ``(année, mois)``.

        Lève ``TypeError`` pour un ``datetime`` : une heure se range sous son
        jour local, que l'appelant calcule.
        """
        if isinstance(instant, datetime):
            raise TypeError(
                "Ranger une entrée horaire sous son jour local (date), pas son instant."
            )
        valider_niveau_confiance(niveau)
        if isinstance(instant, date):
            self._jours[instant].add(niveau)
            self._mois[(instant.year, instant.month)].add(niveau)
        else:
            self._mois_seuls[instant].add(niveau)
            self._mois[instant].add(niveau)

    def du_jour(self, jour: date) -> set[str]:
        """Niveaux des entrées d'un jour et des entrées mensuelles de son mois."""
        return self._jours.get(jour, set()) | self._mois_seuls.get((jour.year, jour.month), set())

    def du_mois(self, annee: int, mois: int) -> set[str]:
        """Niveaux de toutes les entrées d'un mois."""
        return set(self._mois.get((annee, mois), set()))

    def de_periode(self, annee_debut: int, annee_fin: int, mois: int | None = None) -> set[str]:
        """Niveaux des entrées des années ``annee_debut`` à ``annee_fin``.

        Restreint à un mois calendaire si ``mois`` est donné.
        """
        return {
            niveau
            for (annee, m), niveaux in self._mois.items()
            if annee_debut <= annee <= annee_fin and (mois is None or m == mois)
            for niveau in niveaux
        }

    def tous(self) -> set[str]:
        """Niveaux de toutes les entrées."""
        return {niveau for niveaux in self._mois.values() for niveau in niveaux}


def overrider_niveau_confiance(
    ligne: _LigneAvecOverride,
    nouveau_niveau: str,
    justification: str,
) -> None:
    """Pose l'override et ajoute la justification à ``commentaire_editorial``.

    Lève ``NiveauConfianceInvalide`` hors A, B, C et ``JustificationRequise``
    pour une justification vide. Modifie la ligne sans flush ni commit.
    """
    valider_niveau_confiance(nouveau_niveau)
    if not justification or not justification.strip():
        raise JustificationRequise(operation="overrider_niveau_confiance")
    ligne.niveau_confiance_override = nouveau_niveau
    if ligne.commentaire_editorial:
        ligne.commentaire_editorial = (
            f"{ligne.commentaire_editorial}\n[Override -> {nouveau_niveau}] {justification.strip()}"
        )
    else:
        ligne.commentaire_editorial = f"[Override -> {nouveau_niveau}] {justification.strip()}"


def retirer_override_niveau_confiance(
    ligne: _LigneAvecOverride,
    justification: str,
) -> None:
    """Annule l'override (retour au niveau dérivé) et trace le retrait.

    Le retrait est lui aussi une décision à motiver : ``JustificationRequise``
    si la justification est vide. Modifie la ligne sans flush ni commit.
    """
    if not justification or not justification.strip():
        raise JustificationRequise(operation="retirer_override_niveau_confiance")
    ligne.niveau_confiance_override = None
    if ligne.commentaire_editorial:
        ligne.commentaire_editorial = (
            f"{ligne.commentaire_editorial}\n[Retrait override] {justification.strip()}"
        )
    else:
        ligne.commentaire_editorial = f"[Retrait override] {justification.strip()}"
