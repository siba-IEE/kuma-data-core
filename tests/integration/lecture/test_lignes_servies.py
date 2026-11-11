"""Lignes servies : chaque lecteur applique la règle de sélection qu'il déclare.

Deux règles (``editorial.selection``) : les mesures journalières, mensuelles et
les valeurs de grandeur sont servies en vigueur et non dépréciées ; les mesures
horaires, en vigueur et validées. Un pays d'essai (code ``zzs``, ISO3 ``ZZS`` de
la plage qu'ISO 3166-1 réserve aux usages privés) porte des séries synthétiques.
Chaque test change le statut d'une ligne, ou la version de formule d'une
grandeur, puis relit par ``lecture``, par l'acquisition de la capsule ou par
l'API.

Tout se passe dans une transaction annulée en fin de test, que l'API lit par la
même connexion : rien ne reste en base.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from kuma_data_core.db.session import get_engine, obtenir_session
from kuma_data_core.editorial.niveaux_confiance import NiveauxEntrees
from kuma_data_core.lecture.atlas import (
    lire_degenerescence_pixel,
    lire_ecarts_mensuels,
    lister_points_atlas,
)
from kuma_data_core.lecture.mesures import (
    lire_page_journaliere,
    lire_page_mensuelle,
    lire_points_horaires,
    lire_serie_mensuelle_entiere,
    lire_valeurs_horaires,
    lire_valeurs_journalieres,
    lire_valeurs_mensuelles,
    lister_localites_de_meme_serie_mensuelle,
)
from kuma_data_core.lecture.series import SerieHoraireStockee, chercher_serie_horaire_stockee
from kuma_data_core.services.capsule.acquisition import SourceCore

pytestmark = pytest.mark.integration

_ISO3 = "ZZS"

# (code, nom, type, code du parent, latitude, longitude). Tera et Tibo sont dans
# la même cellule de 1° x 1°.
_LOCALITES = [
    ("zzs", "Pays d'essai", "pays", "afrique", 12.0, 8.5),
    ("zzs_centre", "Région du Centre", "region_administrative", "zzs", 12.5, 8.5),
    ("zzs_tera", "Tera", "commune", "zzs_centre", 12.3, 8.4),
    ("zzs_tibo", "Tibo", "commune", "zzs_centre", 12.7, 8.6),
]
_POINT_PRES_DE_TERA = (12.31, 8.41)

_GHI_MENSUEL = "zzs_tera_ghi_power_1991_2020"
_GHI_MENSUEL_JUMELLE = "zzs_tibo_ghi_power_1991_2020"
_GHI_JOURNALIER = "zzs_tera_ghi_nasa_power_2022"
_T_MIN = "zzs_tera_t2m_min_nasa_power_2022"
_T_MAX = "zzs_tera_t2m_max_nasa_power_2022"
_GHI_HORAIRE = "zzs_tera_ghi_nasa_power_horaire_2022"
_DNI_HORAIRE_REJETE = "zzs_tera_dni_nasa_power_horaire_2022"
_ECARTS = "zzs_tera_ecart_ghi_kuma_calculs_2021_2023"
_ECART_SEUL = "zzs_tibo_ecart_ghi_kuma_calculs_2021_2023"

_ECART_GHI = "ecart_relatif_referentiel"
_DEGENERESCENCE = "degenerescence_pixel"

_CLIMATOLOGIE = (date(1991, 1, 1), date(2020, 12, 31))
_AN_2022 = (date(2022, 1, 1), date(2022, 12, 31))
_FENETRE_ATLAS = (date(2021, 1, 1), date(2023, 12, 31))

# (code, localité, grandeur, source, granularité, période)
_SERIES = [
    (_GHI_MENSUEL, "zzs_tera", "ghi", "nasa_power", "mensuel", _CLIMATOLOGIE),
    (_GHI_MENSUEL_JUMELLE, "zzs_tibo", "ghi", "nasa_power", "mensuel", _CLIMATOLOGIE),
    (_GHI_JOURNALIER, "zzs_tera", "ghi", "nasa_power", "journalier", _AN_2022),
    (_T_MIN, "zzs_tera", "t2m_min", "nasa_power", "journalier", _AN_2022),
    (_T_MAX, "zzs_tera", "t2m_max", "nasa_power", "journalier", _AN_2022),
    (_GHI_HORAIRE, "zzs_tera", "ghi", "nasa_power", "horaire", _AN_2022),
    (_DNI_HORAIRE_REJETE, "zzs_tera", "dni", "nasa_power", "horaire", _AN_2022),
    (_ECARTS, "zzs_tera", _ECART_GHI, "kuma_calculs", None, _FENETRE_ATLAS),
    (_ECART_SEUL, "zzs_tibo", _ECART_GHI, "kuma_calculs", None, _FENETRE_ATLAS),
]

# (série, jour, valeur, niveau de confiance). Le 15 juin, seul de niveau C, laisse
# suivre son niveau ; les 11 janvier et 11 avril sont les records de température.
_JOURNALIERES = [
    (_GHI_JOURNALIER, date(2022, 6, 14), 5.1, "B"),
    (_GHI_JOURNALIER, date(2022, 6, 15), 5.2, "C"),
    (_GHI_JOURNALIER, date(2022, 6, 16), 5.3, "B"),
    (_T_MIN, date(2022, 1, 10), 14.0, "B"),
    (_T_MIN, date(2022, 1, 11), 9.0, "B"),
    (_T_MAX, date(2022, 4, 10), 38.0, "B"),
    (_T_MAX, date(2022, 4, 11), 44.0, "B"),
]

_JOUR_HORAIRE = date(2022, 6, 15)


def _heure(heure: int) -> datetime:
    return datetime(2022, 6, 15, heure, tzinfo=UTC)


# (série, instant, valeur, statut)
_HORAIRES = [
    (_GHI_HORAIRE, _heure(9), 100.0, "valide_auto"),
    (_GHI_HORAIRE, _heure(10), 200.0, "valide_auto"),
    (_GHI_HORAIRE, _heure(11), 300.0, "valide_auto"),
    (_DNI_HORAIRE_REJETE, _heure(9), 50.0, "brut"),
    (_DNI_HORAIRE_REJETE, _heure(10), 60.0, "brut"),
]

# (grandeur, série, type de période, année de début, année de fin, mois, valeur)
_GRANDEURS = [
    (_ECART_GHI, _ECARTS, "mensuel", 2021, 2021, 1, -2.0),
    (_ECART_GHI, _ECARTS, "mensuel", 2021, 2021, 2, 1.5),
    (_ECART_GHI, _ECARTS, "mensuel", 2021, 2021, 3, 4.0),
    (_ECART_GHI, _ECART_SEUL, "mensuel", 2021, 2021, 1, 3.0),
    (_DEGENERESCENCE, _GHI_MENSUEL, "statique", 1991, 2020, None, 1.0),
]


def _ghi_mensuel(annee: int, mois: int) -> float:
    """Valeur mensuelle synthétique, la même pour Tera et pour Tibo."""
    return 5.0 + (annee - 1991) + 0.1 * mois


def _creer_pays_d_essai(session: Session) -> None:
    """Insère le pays, ses localités, ses séries, leurs mesures et leurs valeurs de grandeur."""
    for code, nom, type_localite, parent, latitude, longitude in _LOCALITES:
        session.execute(
            text(
                "INSERT INTO localites (code, nom, type_localite, parent_id, pays_iso3, "
                "latitude, longitude, fuseau_horaire) "
                "SELECT :code, :nom, :type, p.id, :iso3, :latitude, :longitude, 'UTC' "
                "FROM localites p WHERE p.code = :parent"
            ),
            {
                "code": code,
                "nom": nom,
                "type": type_localite,
                "parent": parent,
                "iso3": _ISO3,
                "latitude": latitude,
                "longitude": longitude,
            },
        )
    # La capsule lit ses records de température sur ces deux grandeurs.
    session.execute(
        text(
            "INSERT INTO grandeurs_referentiel "
            "(code, libelle, unite_id, famille, strategie_calcul) "
            "SELECT c.code, 'Température synthétique ' || c.code, gr.unite_id, gr.famille, "
            "gr.strategie_calcul "
            "FROM grandeurs_referentiel gr, (VALUES ('t2m_min'), ('t2m_max')) AS c(code) "
            "WHERE gr.code = 't2m'"
        )
    )
    for code, localite, grandeur, source, granularite, (debut, fin) in _SERIES:
        session.execute(
            text(
                "INSERT INTO series_metadonnees (code, libelle, localite_id, grandeur_code, "
                "source_id, periode_debut, periode_fin, granularite, methode_collecte) "
                "SELECT :code, :libelle, l.id, :grandeur, s.id, :debut, :fin, "
                "CAST(:granularite AS VARCHAR), :methode "
                "FROM localites l, sources s WHERE l.code = :localite AND s.code = :source"
            ),
            {
                "code": code,
                "libelle": f"Série synthétique {code}",
                "localite": localite,
                "grandeur": grandeur,
                "source": source,
                "granularite": granularite,
                "methode": "calcul_derive" if source == "kuma_calculs" else "modele_satellitaire",
                "debut": debut,
                "fin": fin,
            },
        )

    for code in (_GHI_MENSUEL, _GHI_MENSUEL_JUMELLE):
        for annee in (1991, 1992):
            for mois in range(1, 13):
                session.execute(
                    text(
                        "INSERT INTO mesures_ressource_mensuelles "
                        "(serie_id, annee, mois, valeur, statut, niveau_confiance_derive) "
                        "SELECT sm.id, :annee, :mois, :valeur, 'brut', 'B' "
                        "FROM series_metadonnees sm WHERE sm.code = :code"
                    ),
                    {
                        "code": code,
                        "annee": annee,
                        "mois": mois,
                        "valeur": _ghi_mensuel(annee, mois),
                    },
                )
    for code, jour, valeur, niveau in _JOURNALIERES:
        session.execute(
            text(
                "INSERT INTO mesures_ressource "
                "(serie_id, instant_mesure, valeur, statut, niveau_confiance_derive) "
                "SELECT sm.id, :jour, :valeur, 'brut', :niveau "
                "FROM series_metadonnees sm WHERE sm.code = :code"
            ),
            {"code": code, "jour": jour, "valeur": valeur, "niveau": niveau},
        )
    for code, instant, valeur, statut in _HORAIRES:
        _inserer_horaire(session, code, instant, valeur, statut)
    for grandeur, serie, periode_type, debut, fin, mois, valeur in _GRANDEURS:
        session.execute(
            text(
                "INSERT INTO grandeurs_metier (grandeur_code, localite_id, series_metadonnees_id, "
                "periode_type, annee_debut, annee_fin, mois, version_formule, valeur, statut, "
                "niveau_confiance_derive, commentaire_editorial) "
                "SELECT gr.code, sm.localite_id, sm.id, :periode_type, :debut, :fin, "
                "CAST(:mois AS INTEGER), gr.version_formule_actuelle, :valeur, 'brut', 'B', "
                "'Valeur synthétique' "
                "FROM series_metadonnees sm, grandeurs_referentiel gr "
                "WHERE sm.code = :serie AND gr.code = :grandeur"
            ),
            {
                "grandeur": grandeur,
                "serie": serie,
                "periode_type": periode_type,
                "debut": debut,
                "fin": fin,
                "mois": mois,
                "valeur": valeur,
            },
        )


def _inserer_horaire(
    session: Session, code_serie: str, instant: datetime, valeur: float, statut: str
) -> None:
    session.execute(
        text(
            "INSERT INTO mesures_ressource_horaires "
            "(serie_id, instant_mesure, valeur, statut, niveau_confiance_derive) "
            "SELECT sm.id, :instant, :valeur, :statut, 'B' "
            "FROM series_metadonnees sm WHERE sm.code = :code"
        ),
        {"code": code_serie, "instant": instant, "valeur": valeur, "statut": statut},
    )


def _poser_statut(
    session: Session, table: str, code_serie: str, statut: str, **repere: object
) -> None:
    """Donne ``statut`` à la ligne de la série que ``repere`` désigne : une seule, sinon échec."""
    cle_serie = "series_metadonnees_id" if table == "grandeurs_metier" else "serie_id"
    conditions = "".join(f" AND t.{colonne} = :{colonne}" for colonne in repere)
    resultat = session.execute(
        text(
            f"UPDATE {table} t SET statut = :statut FROM series_metadonnees sm "
            f"WHERE sm.id = t.{cle_serie} AND sm.code = :code_serie{conditions}"
        ),
        {"statut": statut, "code_serie": code_serie, **repere},
    )
    assert resultat.rowcount == 1


def _remplacer_la_formule(session: Session, grandeur: str) -> None:
    """Fait passer la grandeur à une nouvelle version de formule, sans recalculer ses valeurs."""
    session.execute(
        text(
            "UPDATE grandeurs_referentiel "
            "SET version_formule_actuelle = version_formule_actuelle + 1 WHERE code = :code"
        ),
        {"code": grandeur},
    )


def _id_serie(session: Session, code_serie: str) -> int:
    return int(
        session.execute(
            text("SELECT id FROM series_metadonnees WHERE code = :code"), {"code": code_serie}
        ).scalar_one()
    )


@contextmanager
def _transaction_annulee() -> Iterator[Session]:
    """Session servie à l'API, dans une transaction annulée à la sortie."""
    from kuma_data_core.api.main import app

    connection = get_engine().connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    def _session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[obtenir_session] = _session
    try:
        yield session
    finally:
        app.dependency_overrides.pop(obtenir_session, None)
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def essai() -> Iterator[Session]:
    """Le pays d'essai existe le temps du test, pour l'API comme pour la session rendue."""
    with _transaction_annulee() as session:
        _creer_pays_d_essai(session)
        yield session


def _mesures_servies(
    client: TestClient, headers_auth: dict[str, str], code_serie: str
) -> list[dict[str, object]]:
    """Mesures de la série, telles que ``GET /v1/series/{code_serie}`` les rend."""
    reponse = client.get(f"/v1/series/{code_serie}", headers=headers_auth)
    assert reponse.status_code == 200, reponse.text
    return reponse.json()["mesures"]


# Mesures journalières : en vigueur et non dépréciées.


def test_journaliere_depreciee_absente_des_lectures(essai: Session) -> None:
    serie_id = _id_serie(essai, _GHI_JOURNALIER)
    fenetre = (date(2022, 6, 1), date(2022, 6, 30))
    page = lire_page_journaliere(essai, serie_id, fenetre, 10, 0)
    assert [(ligne.instant_mesure, ligne.valeur) for ligne in page] == [
        (date(2022, 6, 14), 5.1),
        (date(2022, 6, 15), 5.2),
        (date(2022, 6, 16), 5.3),
    ]

    _poser_statut(
        essai, "mesures_ressource", _GHI_JOURNALIER, "deprecie", instant_mesure=date(2022, 6, 15)
    )

    page = lire_page_journaliere(essai, serie_id, fenetre, 10, 0)
    assert [(ligne.instant_mesure, ligne.statut) for ligne in page] == [
        (date(2022, 6, 14), "brut"),
        (date(2022, 6, 16), "brut"),
    ]
    # La ligne retirée n'occupe plus de rang dans la pagination.
    assert [
        ligne.instant_mesure for ligne in lire_page_journaliere(essai, serie_id, fenetre, 10, 1)
    ] == [date(2022, 6, 16)]

    niveaux = NiveauxEntrees()
    valeurs = lire_valeurs_journalieres(essai, serie_id, *fenetre, niveaux=niveaux)
    assert valeurs == {date(2022, 6, 14): 5.1, date(2022, 6, 16): 5.3}
    assert niveaux.du_mois(2022, 6) == {"B"}


def test_journaliere_depreciee_absente_de_la_serie_servie(
    client: TestClient, headers_auth: dict[str, str], essai: Session
) -> None:
    avant = _mesures_servies(client, headers_auth, _GHI_JOURNALIER)
    assert [m["instant_mesure"] for m in avant] == ["2022-06-14", "2022-06-15", "2022-06-16"]

    _poser_statut(
        essai, "mesures_ressource", _GHI_JOURNALIER, "deprecie", instant_mesure=date(2022, 6, 15)
    )

    apres = _mesures_servies(client, headers_auth, _GHI_JOURNALIER)
    assert [(m["instant_mesure"], m["valeur"], m["statut"]) for m in apres] == [
        ("2022-06-14", 5.1, "brut"),
        ("2022-06-16", 5.3, "brut"),
    ]


# Mesures mensuelles : même règle.


def test_mensuelle_depreciee_absente_des_lectures(essai: Session) -> None:
    serie_id = _id_serie(essai, _GHI_MENSUEL)
    annee_1991 = (date(1991, 1, 1), date(1991, 12, 31))
    assert len(lire_page_mensuelle(essai, serie_id, annee_1991, 100, 0)) == 12

    _poser_statut(
        essai, "mesures_ressource_mensuelles", _GHI_MENSUEL, "deprecie", annee=1991, mois=3
    )

    mois_restants = [mois for mois in range(1, 13) if mois != 3]
    page = lire_page_mensuelle(essai, serie_id, annee_1991, 100, 0)
    assert [(ligne.annee, ligne.mois) for ligne in page] == [(1991, mois) for mois in mois_restants]

    niveaux = NiveauxEntrees()
    valeurs = lire_valeurs_mensuelles(essai, serie_id, *annee_1991, niveaux=niveaux)
    assert sorted(valeurs) == [(1991, mois) for mois in mois_restants]
    assert niveaux.du_mois(1991, 3) == set()

    entiere = lire_serie_mensuelle_entiere(essai, serie_id, niveaux=NiveauxEntrees())
    assert len(entiere) == 23
    assert (1991, 3) not in {(annee, mois) for annee, mois, _ in entiere}
    assert (1992, 3, pytest.approx(_ghi_mensuel(1992, 3))) in entiere


def test_mensuelle_depreciee_absente_de_la_serie_servie(
    client: TestClient, headers_auth: dict[str, str], essai: Session
) -> None:
    assert len(_mesures_servies(client, headers_auth, _GHI_MENSUEL)) == 24

    _poser_statut(
        essai, "mesures_ressource_mensuelles", _GHI_MENSUEL, "deprecie", annee=1991, mois=3
    )

    apres = _mesures_servies(client, headers_auth, _GHI_MENSUEL)
    assert len(apres) == 23
    assert (1991, 3) not in {(m["annee"], m["mois"]) for m in apres}
    assert {m["statut"] for m in apres} == {"brut"}


def test_localite_dont_un_mois_est_deprecie_n_est_plus_jumelle(essai: Session) -> None:
    """Deux séries ne sont égales que par leurs valeurs servies."""
    tera, tibo = _id_serie(essai, _GHI_MENSUEL), _id_serie(essai, _GHI_MENSUEL_JUMELLE)
    assert lister_localites_de_meme_serie_mensuelle(essai, tera) == ["zzs_tibo"]
    assert lister_localites_de_meme_serie_mensuelle(essai, tibo) == ["zzs_tera"]

    _poser_statut(
        essai, "mesures_ressource_mensuelles", _GHI_MENSUEL_JUMELLE, "deprecie", annee=1992, mois=7
    )

    assert lister_localites_de_meme_serie_mensuelle(essai, tera) == []
    assert lister_localites_de_meme_serie_mensuelle(essai, tibo) == []


# Atlas : valeurs de grandeur en vigueur, de la version de formule actuelle.


def _ecarts_de_tera(session: Session) -> tuple[list[float], list[tuple[str, str | None]]]:
    return lire_ecarts_mensuels(session, "zzs_tera", _ECART_GHI, 2021, 2023)


def _points_d_essai(session: Session) -> list[str]:
    """Localités du pays d'essai parmi les points de l'atlas."""
    return [
        point.code for point in lister_points_atlas(session, 2021) if point.code.startswith("zzs_")
    ]


def test_ecart_deprecie_absent_de_l_atlas(essai: Session) -> None:
    assert _ecarts_de_tera(essai) == ([-2.0, 1.5, 4.0], [("B", None)] * 3)
    assert _points_d_essai(essai) == ["zzs_tera", "zzs_tibo"]

    _poser_statut(essai, "grandeurs_metier", _ECARTS, "deprecie", mois=2)
    _poser_statut(essai, "grandeurs_metier", _ECART_SEUL, "deprecie", mois=1)

    assert _ecarts_de_tera(essai) == ([-2.0, 4.0], [("B", None)] * 2)
    # Tibo n'avait que cet écart : la localité n'est plus un point de l'atlas.
    assert _points_d_essai(essai) == ["zzs_tera"]


def test_ecart_d_une_formule_remplacee_absent_de_l_atlas(essai: Session) -> None:
    """Une valeur calculée par une formule que le référentiel a remplacée n'est plus servie."""
    assert _ecarts_de_tera(essai)[0] == [-2.0, 1.5, 4.0]

    _remplacer_la_formule(essai, _ECART_GHI)

    assert _ecarts_de_tera(essai) == ([], [])
    assert _points_d_essai(essai) == []


def test_degenerescence_depreciee_absente_de_l_atlas(essai: Session) -> None:
    degenerescence = lire_degenerescence_pixel(essai, "zzs_tera")
    assert degenerescence is not None
    assert (degenerescence.n_jumeaux, degenerescence.niveau_derive) == (1, "B")

    _poser_statut(
        essai, "grandeurs_metier", _GHI_MENSUEL, "deprecie", grandeur_code=_DEGENERESCENCE
    )

    assert lire_degenerescence_pixel(essai, "zzs_tera") is None


def test_degenerescence_d_une_formule_remplacee_absente_de_l_atlas(essai: Session) -> None:
    assert lire_degenerescence_pixel(essai, "zzs_tera") is not None

    _remplacer_la_formule(essai, _DEGENERESCENCE)

    assert lire_degenerescence_pixel(essai, "zzs_tera") is None


# Mesures horaires : en vigueur et validées.


def _ghi_horaires_servis(session: Session) -> dict[str, list[float]]:
    """GHI horaire de Tera le 15 juin, tel que le rend chacun des trois lecteurs."""
    serie_id = _id_serie(session, _GHI_HORAIRE)
    valeurs = lire_valeurs_horaires(
        session, serie_id, _JOUR_HORAIRE, _JOUR_HORAIRE, fuseau="UTC", niveaux=NiveauxEntrees()
    )
    points = lire_points_horaires(session, serie_id, _JOUR_HORAIRE, _JOUR_HORAIRE)
    capsule = SourceCore(session=session).acquerir(*_POINT_PRES_DE_TERA)
    return {
        "lire_valeurs_horaires": list(valeurs.values()),
        "lire_points_horaires": [point.valeur for point in points],
        "capsule": capsule.sequence["ghi"],
    }


def _par_les_trois_lecteurs(valeurs: list[float]) -> dict[str, list[float]]:
    return dict.fromkeys(("lire_valeurs_horaires", "lire_points_horaires", "capsule"), valeurs)


def test_horaire_valide_par_un_editeur_puis_publie_servi_par_les_trois_lecteurs(
    essai: Session,
) -> None:
    assert _ghi_horaires_servis(essai) == _par_les_trois_lecteurs([100.0, 200.0, 300.0])

    for statut in ("valide_humain", "publie"):
        _poser_statut(
            essai, "mesures_ressource_horaires", _GHI_HORAIRE, statut, instant_mesure=_heure(10)
        )
        assert _ghi_horaires_servis(essai) == _par_les_trois_lecteurs([100.0, 200.0, 300.0]), statut


def _horaire_de_tera(
    client: TestClient, headers_auth: dict[str, str], format_sortie: str
) -> httpx.Response:
    """Réponse de ``/v1/horaire`` pour le GHI de Tera le 15 juin, lu dans la série stockée."""
    with patch("kuma_data_core.api.v1.horaire.fetch_hourly") as relais_amont:
        reponse = client.get(
            "/v1/horaire/zzs_tera/ghi",
            params={
                "periode_debut": _JOUR_HORAIRE.isoformat(),
                "periode_fin": _JOUR_HORAIRE.isoformat(),
                "format": format_sortie,
            },
            headers=headers_auth,
        )
    assert reponse.status_code == 200, reponse.text
    relais_amont.assert_not_called()
    return reponse


def test_horaire_servi_par_la_route_avec_le_statut_de_sa_ligne(
    client: TestClient, headers_auth: dict[str, str], essai: Session
) -> None:
    """Un point validé par un éditeur, puis publié, sort avec ce statut, pas ``valide_auto``."""
    for statut in ("valide_auto", "valide_humain", "publie"):
        if statut != "valide_auto":
            _poser_statut(
                essai, "mesures_ressource_horaires", _GHI_HORAIRE, statut, instant_mesure=_heure(10)
            )

        resultats = _horaire_de_tera(client, headers_auth, "json").json()["resultats"]
        assert [(r["instant"], r["valeur"], r["statut_editorial"]) for r in resultats] == [
            ("2022-06-15T09:00:00", 100.0, "valide_auto"),
            ("2022-06-15T10:00:00", 200.0, statut),
            ("2022-06-15T11:00:00", 300.0, "valide_auto"),
        ]
        assert _horaire_de_tera(client, headers_auth, "csv").text.splitlines() == [
            "instant,valeur,unite,statut_editorial",
            "2022-06-15T09:00:00,100.0,Wh/m²,valide_auto",
            f"2022-06-15T10:00:00,200.0,Wh/m²,{statut}",
            "2022-06-15T11:00:00,300.0,Wh/m²,valide_auto",
        ]


def test_horaire_rejete_ou_deprecie_servi_par_aucun_lecteur(essai: Session) -> None:
    _inserer_horaire(essai, _GHI_HORAIRE, _heure(12), 400.0, "brut")
    _poser_statut(
        essai, "mesures_ressource_horaires", _GHI_HORAIRE, "deprecie", instant_mesure=_heure(11)
    )

    assert _ghi_horaires_servis(essai) == _par_les_trois_lecteurs([100.0, 200.0])


def test_serie_horaire_dont_tout_est_rejete_n_est_pas_stockee(essai: Session) -> None:
    assert chercher_serie_horaire_stockee(essai, "zzs_tera", "ghi") == SerieHoraireStockee(
        serie_id=_id_serie(essai, _GHI_HORAIRE),
        periode_debut=_AN_2022[0],
        periode_fin=_AN_2022[1],
    )
    assert chercher_serie_horaire_stockee(essai, "zzs_tera", "dni") is None

    # Une seule ligne validée suffit à la rendre servie.
    _poser_statut(
        essai,
        "mesures_ressource_horaires",
        _DNI_HORAIRE_REJETE,
        "valide_auto",
        instant_mesure=_heure(9),
    )
    stockee = chercher_serie_horaire_stockee(essai, "zzs_tera", "dni")
    assert stockee is not None
    assert stockee.serie_id == _id_serie(essai, _DNI_HORAIRE_REJETE)


# Capsule : climatologie mensuelle et records de température, en vigueur et non dépréciés.


def test_capsule_ecarte_la_mensuelle_depreciee_de_la_climatologie(essai: Session) -> None:
    avant = SourceCore(session=essai).acquerir(*_POINT_PRES_DE_TERA).climatologie_hep
    assert avant == pytest.approx(
        [(_ghi_mensuel(1991, mois) + _ghi_mensuel(1992, mois)) / 2 for mois in range(1, 13)]
    )

    _poser_statut(
        essai, "mesures_ressource_mensuelles", _GHI_MENSUEL, "deprecie", annee=1991, mois=3
    )

    apres = SourceCore(session=essai).acquerir(*_POINT_PRES_DE_TERA).climatologie_hep
    assert apres[2] == pytest.approx(_ghi_mensuel(1992, 3))
    assert apres[:2] + apres[3:] == avant[:2] + avant[3:]


def test_capsule_ecarte_la_journaliere_depreciee_des_extremes_de_temperature(
    essai: Session,
) -> None:
    avant = SourceCore(session=essai).acquerir(*_POINT_PRES_DE_TERA).temperatures_conception
    assert avant is not None
    assert (avant["froidC"], avant["chaudC"]) == (9.0, 44.0)

    _poser_statut(essai, "mesures_ressource", _T_MIN, "deprecie", instant_mesure=date(2022, 1, 11))
    _poser_statut(essai, "mesures_ressource", _T_MAX, "deprecie", instant_mesure=date(2022, 4, 11))

    apres = SourceCore(session=essai).acquerir(*_POINT_PRES_DE_TERA).temperatures_conception
    assert apres is not None
    assert (apres["froidC"], apres["chaudC"]) == (14.0, 38.0)


# Isolation.


def _empreinte(connexion: Connection, depuis: datetime) -> dict[str, int]:
    """Lignes du pays d'essai, état du référentiel et audit écrit depuis ``depuis``.

    Toute écriture sur une table auditée, mesures comprises, laisse une ligne d'audit.
    """

    def compte(sql: str, **params: object) -> int:
        return int(connexion.execute(text(sql), params).scalar_one())

    series = (
        "SELECT sm.id FROM series_metadonnees sm JOIN localites l ON l.id = sm.localite_id "
        f"WHERE l.pays_iso3 = '{_ISO3}'"
    )
    return {
        "localites": compte("SELECT count(*) FROM localites WHERE pays_iso3 = :iso3", iso3=_ISO3),
        "series": compte(f"SELECT count(*) FROM ({series}) s"),
        "journalieres": compte(
            f"SELECT count(*) FROM mesures_ressource WHERE serie_id IN ({series})"
        ),
        "mensuelles": compte(
            f"SELECT count(*) FROM mesures_ressource_mensuelles WHERE serie_id IN ({series})"
        ),
        "horaires": compte(
            f"SELECT count(*) FROM mesures_ressource_horaires WHERE serie_id IN ({series})"
        ),
        "grandeurs": compte(
            f"SELECT count(*) FROM grandeurs_metier WHERE series_metadonnees_id IN ({series})"
        ),
        "referentiel": compte("SELECT count(*) FROM grandeurs_referentiel"),
        "versions_de_formule": compte(
            "SELECT sum(version_formule_actuelle) FROM grandeurs_referentiel"
        ),
        "audit": compte(
            "SELECT count(*) FROM audit_log WHERE horodatage >= :depuis", depuis=depuis
        ),
    }


def test_rien_ne_reste_en_base() -> None:
    """Pendant le test, seule sa connexion voit le pays et ses changements ; après, personne."""
    with get_engine().connect() as temoin:
        depuis = temoin.execute(text("SELECT clock_timestamp()")).scalar_one()
        avant = _empreinte(temoin, depuis)
        assert avant["localites"] == avant["series"] == avant["audit"] == 0

        with _transaction_annulee() as session:
            _creer_pays_d_essai(session)
            _poser_statut(
                session,
                "mesures_ressource",
                _GHI_JOURNALIER,
                "deprecie",
                instant_mesure=date(2022, 6, 15),
            )
            _remplacer_la_formule(session, _ECART_GHI)
            pendant = _empreinte(session.connection(), depuis)
            assert pendant == {
                "localites": len(_LOCALITES),
                "series": len(_SERIES),
                "journalieres": len(_JOURNALIERES),
                "mensuelles": 48,
                "horaires": len(_HORAIRES),
                "grandeurs": len(_GRANDEURS),
                "referentiel": avant["referentiel"] + 2,
                "versions_de_formule": avant["versions_de_formule"] + 3,
                "audit": pendant["audit"],
            }
            assert pendant["audit"] > len(_LOCALITES) + len(_SERIES)
            assert _empreinte(temoin, depuis) == avant

        assert _empreinte(temoin, depuis) == avant
