"""Niveaux de confiance A/B/C : dérivation R1-R4, propagation P + override.

Périmètre tables : ``mesures_ressource``, ``grandeurs_metier``.

3 valeurs autorisées (`frozenset` miroir de la CHECK constraint SQL) :

- ``A`` (haute) : donnée mesurée directement par instrument de référence,
  ou calculée par méthode reconnue à partir de mesures elles-mêmes A.
- ``B`` (moyenne) : donnée modélisée, interpolée ou extrapolée selon
  méthodologie documentée, sur source ``fiabilite ∈ {'haute', 'moyenne'}``.
- ``C`` (basse) : donnée estimée par expertise sans validation
  instrumentale, ou produite à partir d'une source ``fiabilite='faible'``.

Règles de dérivation R1-R4 et P, évaluées dans l'ordre.
La **première** qui matche détermine la valeur :

| Ordre | Condition | Résultat |
|---|---|---|
| R1 | ``source.fiabilite = 'faible'`` | ``C`` |
| R2 | ``methode_collecte = 'expertise_humaine'`` (R1 ne matche pas) | ``C`` |
| R3 | ``methode_collecte = 'mesure_directe'`` ET ``source.fiabilite = 'haute'`` | ``A`` |
| P | ``methode_collecte = 'calcul_derive'``, entrées connues | entrées et plafond, le plus bas |
| R4 | tous les autres cas (catch-all) | ``B`` |

(R3 ne matche qu'après évaluation négative de R1 et R2.)

Règle de propagation P (ADR-0008) : une grandeur calculée prend le niveau
effectif (override sinon dérivé) le plus bas des valeurs dont elle est tirée,
sans dépasser le plafond de sa méthode. Le plafond est ``B`` par défaut :
seul un calcul exact, sans modèle ni hypothèse de l'utilisateur (agrégation,
ratio, formule fermée, statistique), le relève à ``A``, et seulement si la
source du calcul est de fiabilité ``haute``. ``NiveauxEntrees`` range les
niveaux par jour et par mois pour donner à chaque valeur calculée le niveau
des seules entrées de sa période.

Override éditorial : ``overrider_niveau_confiance``
pose ``niveau_confiance_override`` sur la ligne avec une justification
obligatoire dans ``commentaire_editorial``. ``retirer_override`` annule
l'override (revient au dérivé).

Ce module reste indépendant de SQLAlchemy pour la dérivation pure
(R1-R4 fonction pure). Les fonctions override/retirer mutent un objet
ligne fourni par le caller (SQLAlchemy ORM ou Pydantic, selon contexte).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Iterable
from datetime import date, datetime
from typing import Literal, Protocol

from kuma_data_core.exceptions import JustificationRequise, NiveauConfianceInvalide

NIVEAUX_CONFIANCE_AUTORISES: frozenset[str] = frozenset({"A", "B", "C"})
"""Constante miroir de la CHECK constraint SQL ``ck_<table>_niveau_confiance_*_valide``.

Pattern hérité du module ``statuts``.
"""

NiveauConfiance = Literal["A", "B", "C"]

_RANG_NIVEAU: dict[str, int] = {"C": 0, "B": 1, "A": 2}
_NIVEAU_DU_RANG: dict[int, NiveauConfiance] = {0: "C", 1: "B", 2: "A"}


class _LigneAvecOverride(Protocol):
    """Protocol structurel pour une ligne supportant les opérations override.

    Permet d'écrire les fonctions override/retirer sans dépendance dure
    sur ``MesureRessource``. Compatible avec ``GrandeurMetier`` à venir
    si elle expose la même surface.
    """

    niveau_confiance_override: str | None
    commentaire_editorial: str | None


def valider_niveau_confiance(niveau: str) -> None:
    """Vérifie que ``niveau`` ∈ ``{'A', 'B', 'C'}`` ; sinon
    ``NiveauConfianceInvalide``.
    """
    if niveau not in NIVEAUX_CONFIANCE_AUTORISES:
        raise NiveauConfianceInvalide(valeur_recue=niveau)


def propager_niveau_confiance(
    niveaux_entrees: Iterable[str], plafond: NiveauConfiance = "B"
) -> NiveauConfiance:
    """Règle P : niveau d'une valeur calculée, le plus bas de ses entrées et de son plafond.

    Args:
        niveaux_entrees : niveaux effectifs (override sinon dérivé) des
            valeurs dont la valeur calculée est tirée.
        plafond : niveau le plus haut que la méthode de calcul permet.
            ``'B'`` par défaut ; ``'A'`` pour un calcul exact, sans modèle
            ni hypothèse de l'utilisateur.

    Returns:
        Le plus bas des niveaux d'entrée et du plafond.

    Raises:
        TypeError : si les entrées sont une chaîne (``'AB'`` n'est pas une
            liste de niveaux).
        ValueError : si aucune entrée n'est fournie.
        NiveauConfianceInvalide : si une entrée ou le plafond n'est pas A, B ou C.
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
    """Applique les règles R1, R2, R3, P puis R4 séquentiellement.

    Args:
        methode_collecte : valeur de ``series_metadonnees.methode_collecte``
            de la série hébergeant la mesure. Peut être None
            (série sans méthode renseignée).
        fiabilite_source : valeur de ``sources.fiabilite`` de la source
            primaire de la série. Valeurs typiques : 'haute', 'moyenne',
            'faible' (cf. modèle ``Source`` migration 004 + 006). Peut
            être None.
        niveaux_entrees : pour une grandeur calculée (``calcul_derive``),
            niveaux effectifs des valeurs d'entrée de la ligne calculée.
            Absent ou vide, la règle P ne s'applique pas et R4 donne B.
        plafond : niveau le plus haut que la méthode de calcul permet (P).
            Ramené à ``'B'`` si la source du calcul n'est pas de fiabilité
            ``'haute'``, comme R3 l'exige pour une mesure.

    Returns:
        'A', 'B' ou 'C' selon R1, R2, R3, P et R4.

    Notes:
        R1 est évaluée en premier (priorité à la qualité de source faible).
        R4 est le catch-all terminal - couvre notamment les cas
        ``modele_satellitaire`` qui sont les plus fréquents
        (NASA POWER → niveau B par défaut).
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
    son jour UTC (à convertir par l'appelant), une entrée mensuelle sous son
    mois. Chaque valeur calculée prend le niveau
    des entrées de sa période : un jour (entrées du jour et entrées
    mensuelles de son mois), un mois, ou une période d'années éventuellement
    restreinte à un mois calendaire (climatologies).
    """

    def __init__(self) -> None:
        self._jours: dict[date, set[str]] = defaultdict(set)
        self._mois_seuls: dict[tuple[int, int], set[str]] = defaultdict(set)
        self._mois: dict[tuple[int, int], set[str]] = defaultdict(set)

    def ajouter(self, instant: date | tuple[int, int], niveau: str) -> None:
        """Range le niveau d'une entrée sous son jour ou sous son mois ``(année, mois)``.

        Raises:
            TypeError : si ``instant`` est un ``datetime`` : une heure se range
                sous son jour UTC, que l'appelant calcule.
        """
        if isinstance(instant, datetime):
            raise TypeError("Ranger une entrée horaire sous son jour UTC (date), pas son instant.")
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
    """Pose ``niveau_confiance_override`` sur la ligne avec justification.

    Args:
        ligne : objet exposant les attributs ``niveau_confiance_override``
            (str | None) et ``commentaire_editorial`` (str | None).
            Typiquement une instance SQLAlchemy ``MesureRessource``.
        nouveau_niveau : 'A', 'B' ou 'C'.
        justification : texte non vide expliquant la décision éditoriale.
            Posé dans ``commentaire_editorial``. Concatène si une
            justification précédente existe pour préserver l'historique
            éditorial.

    Raises:
        NiveauConfianceInvalide : si ``nouveau_niveau`` n'est pas A/B/C.
        JustificationRequise : si ``justification`` est None ou vide après
            ``str.strip()``.

    Side-effects :
        Mute ``ligne.niveau_confiance_override`` et
        ``ligne.commentaire_editorial``. Le caller doit s'occuper de
        commit/flush SQLAlchemy.
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
    """Annule l'override sur la ligne (revient au niveau dérivé).

    Args:
        ligne : idem ``overrider_niveau_confiance``.
        justification : texte non vide. Concaténé à ``commentaire_editorial``
            pour tracer le retrait. Symétrie avec ``overrider`` : un retrait
            est aussi une décision éditoriale à motiver.

    Raises:
        JustificationRequise : si ``justification`` est None ou vide.

    Side-effects :
        Mute ``ligne.niveau_confiance_override`` à None et
        ``ligne.commentaire_editorial``.
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
