"""Un pays ajouté par de simples lignes est servi comme le pays pilote.

Le pays est une donnée : le moteur lit le pays, le fuseau et les localités
dans la base. Ce test crée un « Pays fictif » (code ``zzf``, ISO3 ``ZZF`` de la
plage qu'ISO 3166-1 réserve aux usages privés, fuseau ``Africa/Lagos`` soit
UTC+1 sans heure d'été), ses localités, ses séries et ses mesures, puis les
relit par l'API. Ajouter ce pays ne demande ni migration de schéma ni
changement de code : des lignes dans ``localites``, ``series_metadonnees`` et
les tables de mesures, rattachées aux sources et aux grandeurs du référentiel.

Tout se passe dans une transaction annulée en fin de test, que l'API lit par la
même connexion : rien ne reste en base.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from kuma_data_core.db.session import get_engine, obtenir_session
from kuma_data_core.services.capsule import fichier_kuma

pytestmark = pytest.mark.integration

_ISO3 = "ZZF"
_FUSEAU = "Africa/Lagos"

# (code, nom, type, code du parent, latitude, longitude). Alma et Bari sont dans
# la même cellule de 1° x 1° ; la troisième commune porte le code court d'une
# commune du pays pilote et se trouve dans une autre cellule.
_LOCALITES = [
    ("zzf", "Pays fictif", "pays", "afrique", 12.0, 8.5),
    ("zzf_nord", "Région du Nord", "region_administrative", "zzf", 12.5, 8.5),
    ("zzf_alma", "Alma", "commune", "zzf_nord", 12.3, 8.4),
    ("zzf_bari", "Bari", "commune", "zzf_nord", 12.7, 8.6),
    ("zzf_kankan", "Kankan du pays fictif", "commune", "zzf_nord", 13.4, 9.6),
]
_POINT_PRES_D_ALMA = {"lat": 12.31, "lon": 8.41}
# Au sud d'Alma, sur son méridien : dans la cellule voisine, puis deux cellules plus loin.
_POINT_DE_LA_CELLULE_VOISINE = {"lat": 11.6, "lon": 8.4}
_POINT_A_DEUX_CELLULES = {"lat": 10.5, "lon": 8.4}

_GHI_MENSUEL_ALMA = "zzf_alma_ghi_power_1991_2020"
_GHI_MENSUEL_BARI = "zzf_bari_ghi_power_1991_2020"
_GHI_MENSUEL_KANKAN = "zzf_kankan_ghi_power_1991_2020"
_GHI_JOURNALIER_ALMA = "zzf_alma_ghi_nasa_power_2022"
_GHI_HORAIRE_ALMA = "zzf_alma_ghi_nasa_power_horaire_2022"
_GHI_HORAIRE_KANKAN = "zzf_kankan_ghi_nasa_power_horaire_2022"
_T2M_HORAIRE_ALMA = "zzf_alma_t2m_nasa_power_horaire_2022"

# (code, localité, grandeur, granularité, début, fin)
_SERIES = [
    (_GHI_MENSUEL_ALMA, "zzf_alma", "ghi", "mensuel", date(1991, 1, 1), date(2020, 12, 31)),
    (_GHI_MENSUEL_BARI, "zzf_bari", "ghi", "mensuel", date(1991, 1, 1), date(2020, 12, 31)),
    (_GHI_MENSUEL_KANKAN, "zzf_kankan", "ghi", "mensuel", date(1991, 1, 1), date(2020, 12, 31)),
    (_GHI_JOURNALIER_ALMA, "zzf_alma", "ghi", "journalier", date(2022, 1, 1), date(2022, 12, 31)),
    (_GHI_HORAIRE_ALMA, "zzf_alma", "ghi", "horaire", date(2022, 1, 1), date(2022, 12, 31)),
    (_GHI_HORAIRE_KANKAN, "zzf_kankan", "ghi", "horaire", date(2022, 1, 1), date(2022, 12, 31)),
    (_T2M_HORAIRE_ALMA, "zzf_alma", "t2m", "horaire", date(2022, 1, 1), date(2022, 12, 31)),
]

# Seule heure plus chaude que la base des degrés-jours : 23 h UTC le 31 janvier,
# soit 0 h le 1er février en heure locale. Le jour et le mois changent avec le fuseau.
_HEURE_CHAUDE = datetime(2022, 1, 31, 23, tzinfo=UTC)
_T_BASE, _T_CHAUDE, _T_FRAICHE = 24.0, 34.0, 20.0


def _creer_pays_fictif(session: Session) -> None:
    """Insère le pays, ses localités, ses séries et leurs mesures."""
    for code, nom, type_localite, parent, latitude, longitude in _LOCALITES:
        session.execute(
            text(
                "INSERT INTO localites (code, nom, type_localite, parent_id, pays_iso3, "
                "latitude, longitude, fuseau_horaire) "
                "SELECT :code, :nom, :type, p.id, :iso3, :latitude, :longitude, :fuseau "
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
                "fuseau": _FUSEAU,
            },
        )
    for code, localite, grandeur, granularite, debut, fin in _SERIES:
        session.execute(
            text(
                "INSERT INTO series_metadonnees (code, libelle, localite_id, grandeur_code, "
                "source_id, periode_debut, periode_fin, granularite, methode_collecte) "
                "SELECT :code, :libelle, l.id, :grandeur, s.id, :debut, :fin, :granularite, "
                "'modele_satellitaire' "
                "FROM localites l, sources s WHERE l.code = :localite AND s.code = 'nasa_power'"
            ),
            {
                "code": code,
                "libelle": f"Série synthétique {code}",
                "localite": localite,
                "grandeur": grandeur,
                "granularite": granularite,
                "debut": debut,
                "fin": fin,
            },
        )

    # GHI mensuel 1991-2020 : même série pour Alma et Bari, une autre pour la troisième
    # commune. Six décimales : aucune série réelle n'a ces valeurs.
    for code, decalage in (
        (_GHI_MENSUEL_ALMA, 0.0),
        (_GHI_MENSUEL_BARI, 0.0),
        (_GHI_MENSUEL_KANKAN, 0.25),
    ):
        session.execute(
            text(
                "INSERT INTO mesures_ressource_mensuelles "
                "(serie_id, annee, mois, valeur, statut, niveau_confiance_derive) "
                "SELECT sm.id, a, m, 5.0 + 0.123457 * m + 0.0011 * (a - 1991) + :decalage, "
                "'brut', 'B' "
                "FROM series_metadonnees sm, generate_series(1991, 2020) a, "
                "generate_series(1, 12) m WHERE sm.code = :code"
            ),
            {"code": code, "decalage": decalage},
        )

    session.execute(
        text(
            "INSERT INTO mesures_ressource "
            "(serie_id, instant_mesure, valeur, statut, niveau_confiance_derive) "
            "SELECT sm.id, j::date, 5.5, 'brut', 'B' FROM series_metadonnees sm, "
            "generate_series(DATE '2022-06-14', DATE '2022-06-16', INTERVAL '1 day') j "
            "WHERE sm.code = :code"
        ),
        {"code": _GHI_JOURNALIER_ALMA},
    )

    # GHI horaire : une valeur à 11 h UTC (midi en heure locale) le 15 de chaque mois.
    insertion_horaire = text(
        "INSERT INTO mesures_ressource_horaires "
        "(serie_id, instant_mesure, valeur, statut, niveau_confiance_derive) "
        "SELECT sm.id, :instant, :valeur, 'valide_auto', :niveau "
        "FROM series_metadonnees sm WHERE sm.code = :code"
    )
    for mois in range(1, 13):
        session.execute(
            insertion_horaire,
            {
                "code": _GHI_HORAIRE_ALMA,
                "instant": datetime(2022, mois, 15, 11, tzinfo=UTC),
                "valeur": 600.0 + 10 * mois,
                "niveau": "B",
            },
        )
    session.execute(
        insertion_horaire,
        {
            "code": _GHI_HORAIRE_KANKAN,
            "instant": datetime(2022, 6, 15, 11, tzinfo=UTC),
            "valeur": 700.0,
            "niveau": "B",
        },
    )

    # T2M horaire sur les jours locaux du 31 janvier et du 1er février : 20 °C, sauf
    # l'heure chaude, de niveau C pour suivre aussi le jour où son niveau est rangé.
    session.execute(
        text(
            "INSERT INTO mesures_ressource_horaires "
            "(serie_id, instant_mesure, valeur, statut, niveau_confiance_derive) "
            "SELECT sm.id, h, CASE WHEN h = :chaude THEN :t_chaude ELSE :t_fraiche END, "
            "'valide_auto', CASE WHEN h = :chaude THEN 'C' ELSE 'B' END "
            "FROM series_metadonnees sm, generate_series("
            "TIMESTAMPTZ '2022-01-30 23:00+00', TIMESTAMPTZ '2022-02-01 22:00+00', "
            "INTERVAL '1 hour') h WHERE sm.code = :code"
        ),
        {
            "code": _T2M_HORAIRE_ALMA,
            "chaude": _HEURE_CHAUDE,
            "t_chaude": _T_CHAUDE,
            "t_fraiche": _T_FRAICHE,
        },
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
def pays_fictif() -> Iterator[Session]:
    """Le pays fictif existe le temps du test, pour l'API comme pour la session rendue."""
    with _transaction_annulee() as session:
        _creer_pays_fictif(session)
        yield session


def _empreinte(connexion: Connection, depuis: datetime) -> dict[str, int]:
    """Localités, séries, et lignes d'audit écrites depuis ``depuis``, vues par ``connexion``.

    Toute écriture sur une table auditée, mesures comprises, laisse une ligne d'audit.
    """
    return {
        "localites": connexion.execute(text("SELECT count(*) FROM localites")).scalar_one(),
        "series": connexion.execute(text("SELECT count(*) FROM series_metadonnees")).scalar_one(),
        "audit": connexion.execute(
            text("SELECT count(*) FROM audit_log WHERE horodatage >= :depuis"), {"depuis": depuis}
        ).scalar_one(),
    }


def _mensuels(reponse: dict[str, list[dict[str, object]]]) -> dict[object, tuple[object, object]]:
    """``{mois: (valeur, niveau de confiance)}`` d'une réponse de degrés-jours."""
    return {r["instant"]: (r["valeur"], r["niveau_confiance"]) for r in reponse["resultats"]}


def _degres_jours(
    client: TestClient, headers_auth: dict[str, str], debut: str, fin: str
) -> dict[object, tuple[object, object]]:
    reponse = client.get(
        "/v1/grandeurs/degre_jour_climatisation",
        params={
            "code_serie_source": _T2M_HORAIRE_ALMA,
            "periode_debut": debut,
            "periode_fin": fin,
            "base_temperature_degc": _T_BASE,
            "methode": "integration_horaire",
        },
        headers=headers_auth,
    )
    assert reponse.status_code == 200, reponse.text
    return _mensuels(reponse.json())


def test_localites_du_pays_listees_et_detaillees_avec_leur_fuseau(
    client: TestClient, headers_auth: dict[str, str], pays_fictif: Session
) -> None:
    liste = client.get("/v1/localites", params={"pays_iso3": _ISO3}, headers=headers_auth)
    assert liste.status_code == 200
    corps = liste.json()
    assert corps["total"] == len(_LOCALITES)
    assert [(item["code"], item["fuseau_horaire"]) for item in corps["items"]] == sorted(
        (code, _FUSEAU) for code, *_ in _LOCALITES
    )

    detail = client.get("/v1/localites/zzf_alma", headers=headers_auth)
    assert detail.status_code == 200
    alma = detail.json()
    assert (alma["nom"], alma["type_localite"], alma["parent_code"]) == (
        "Alma",
        "commune",
        "zzf_nord",
    )
    assert (alma["pays_iso3"], alma["fuseau_horaire"]) == (_ISO3, _FUSEAU)
    assert (alma["latitude"], alma["longitude"]) == (12.3, 8.4)


def test_series_journaliere_et_mensuelle_servies(
    client: TestClient, headers_auth: dict[str, str], pays_fictif: Session
) -> None:
    liste = client.get("/v1/series", params={"localite": "zzf_alma"}, headers=headers_auth)
    assert liste.status_code == 200
    items = liste.json()["items"]
    assert [item["code"] for item in items] == sorted(
        code for code, localite, *_ in _SERIES if localite == "zzf_alma"
    )
    assert {item["localite_iso3"] for item in items} == {_ISO3}

    mensuelle = client.get(f"/v1/series/{_GHI_MENSUEL_ALMA}", headers=headers_auth)
    assert mensuelle.status_code == 200
    mesures = mensuelle.json()["mesures"]
    assert len(mesures) == 360
    assert (mesures[0]["annee"], mesures[0]["mois"]) == (1991, 1)
    assert mesures[0]["valeur"] == pytest.approx(5.123457)

    journaliere = client.get(f"/v1/series/{_GHI_JOURNALIER_ALMA}", headers=headers_auth)
    assert journaliere.status_code == 200
    assert [(m["instant_mesure"], m["valeur"]) for m in journaliere.json()["mesures"]] == [
        ("2022-06-14", 5.5),
        ("2022-06-15", 5.5),
        ("2022-06-16", 5.5),
    ]


def test_code_court_complete_par_le_code_du_pays(
    client: TestClient, headers_auth: dict[str, str], pays_fictif: Session
) -> None:
    """``alma`` se lit comme ``zzf_alma`` : le préfixe est le code d'un pays du référentiel."""
    with patch("kuma_data_core.api.v1.horaire.fetch_hourly") as relais_amont:
        reponse = client.get(
            "/v1/horaire/alma/ghi",
            params={"periode_debut": "2022-06-15", "periode_fin": "2022-06-15"},
            headers=headers_auth,
        )
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["resultats"] == [
        {
            "instant": "2022-06-15T11:00:00",
            "valeur": 660.0,
            "unite": "Wh/m²",
            "statut_editorial": "valide_auto",
        }
    ]
    relais_amont.assert_not_called()


def test_code_court_porte_par_deux_pays_ambigu(
    client: TestClient, headers_auth: dict[str, str], pays_fictif: Session
) -> None:
    """``kankan`` désigne une commune de chaque pays : seuls les codes complets répondent."""
    fenetre = {"periode_debut": "2022-06-15", "periode_fin": "2022-06-15"}
    with patch("kuma_data_core.api.v1.horaire.fetch_hourly") as relais_amont:
        court = client.get("/v1/horaire/kankan/ghi", params=fenetre, headers=headers_auth)
        complets = {
            code: client.get(f"/v1/horaire/{code}/ghi", params=fenetre, headers=headers_auth)
            for code in ("gin_kankan", "zzf_kankan")
        }
    assert court.status_code == 404
    assert court.json()["erreur"] == {
        "code": "RESSOURCE_LOCALITE_INCONNUE",
        "message": "Code court 'kankan' ambigu : utiliser le code complet de la localité.",
        "details": {"candidats": ["gin_kankan", "zzf_kankan"]},
    }
    assert {code: reponse.status_code for code, reponse in complets.items()} == {
        "gin_kankan": 200,
        "zzf_kankan": 200,
    }
    assert [r["valeur"] for r in complets["zzf_kankan"].json()["resultats"]] == [700.0]
    assert len(complets["gin_kankan"].json()["resultats"]) == 24
    relais_amont.assert_not_called()


def test_degres_jours_horaires_comptes_au_jour_local(
    client: TestClient, headers_auth: dict[str, str], pays_fictif: Session
) -> None:
    """L'heure chaude, 31 janvier en UTC, compte pour le 1er février, son jour local."""
    mensuels = _degres_jours(client, headers_auth, "2022-01-31", "2022-02-01")
    assert mensuels == {
        "2022-01": (0.0, "B"),
        "2022-02": (pytest.approx((_T_CHAUDE - _T_BASE) / 24), "C"),
    }


def test_fenetre_horaire_bornee_au_jour_local(
    client: TestClient, headers_auth: dict[str, str], pays_fictif: Session
) -> None:
    """Une fenêtre d'un jour retient les 24 heures de ce jour local, pas du jour UTC."""
    premier_fevrier = _degres_jours(client, headers_auth, "2022-02-01", "2022-02-01")
    assert premier_fevrier == {"2022-02": (pytest.approx((_T_CHAUDE - _T_BASE) / 24), "C")}

    trente_et_un_janvier = _degres_jours(client, headers_auth, "2022-01-31", "2022-01-31")
    assert trente_et_un_janvier == {"2022-01": (0.0, "B")}


def test_localites_de_meme_cellule_nommees_par_ghi_exceedance(
    client: TestClient, headers_auth: dict[str, str], pays_fictif: Session
) -> None:
    """Alma et Bari ont la même série GHI mensuelle : chacune voit l'autre nommée."""
    fiches = {}
    for code in ("zzf_alma", "zzf_bari", "zzf_kankan", "gin_kankan"):
        reponse = client.get(f"/v1/grandeurs/ghi_exceedance/{code}", headers=headers_auth)
        assert reponse.status_code == 200, reponse.text
        fiches[code] = reponse.json()

    assert (
        "Cette localité et 'zzf_bari' tombent dans la même cellule"
        in (fiches["zzf_alma"]["limite"])
    )
    assert (
        "Cette localité et 'zzf_alma' tombent dans la même cellule"
        in (fiches["zzf_bari"]["limite"])
    )
    assert (fiches["zzf_alma"]["p50"], fiches["zzf_alma"]["p90"]) == (
        fiches["zzf_bari"]["p50"],
        fiches["zzf_bari"]["p90"],
    )
    assert fiches["zzf_alma"]["base_annees"] == 30

    assert "même cellule" not in fiches["zzf_kankan"]["limite"]
    assert fiches["zzf_kankan"]["p50"] != fiches["zzf_alma"]["p50"]
    # Une localité du pays pilote ne se découvre pas de jumelle dans le pays fictif.
    assert "zzf_" not in fiches["gin_kankan"]["limite"]


def test_point_resolu_sur_la_localite_du_pays(
    client: TestClient, headers_auth: dict[str, str], pays_fictif: Session
) -> None:
    reponse = client.get(
        "/v1/localites/resolution", params=_POINT_PRES_D_ALMA, headers=headers_auth
    )
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["localite"]["code"] == "zzf_alma"
    assert corps["meme_cellule"] is True
    assert corps["serie_climatologie"] == _GHI_MENSUEL_ALMA
    assert corps["distance_km"] < 5


def test_capsule_en_heures_locales(
    client: TestClient, headers_auth: dict[str, str], pays_fictif: Session
) -> None:
    """Le GHI posé à 11 h UTC ressort à 12 h, heure du fuseau de la localité."""
    reponse = client.get("/v1/etudes/capsule", params=_POINT_PRES_D_ALMA, headers=headers_auth)
    assert reponse.status_code == 200, reponse.text
    capsule = fichier_kuma.lire(reponse.text)
    assert capsule["metadonnees"]["provenance"]["resolution"]["localite"] == "zzf_alma"
    sequence = capsule["ressource"]["enregistrementType"]["sequence"]
    assert sequence["mois"] == list(range(1, 13))
    assert sequence["heures"] == [12] * 12
    assert sequence["ghi"] == [600.0 + 10 * mois for mois in range(1, 13)]


@pytest.mark.parametrize(
    ("point", "meme_cellule", "distance_km"),
    [
        pytest.param(_POINT_PRES_D_ALMA, True, 1.6, id="cellule d'Alma"),
        # 0,7° de méridien.
        pytest.param(_POINT_DE_LA_CELLULE_VOISINE, False, 77.8, id="cellule voisine, vide"),
    ],
)
def test_route_et_capsule_resolvent_le_point_de_la_meme_facon(
    client: TestClient,
    headers_auth: dict[str, str],
    pays_fictif: Session,
    point: dict[str, float],
    meme_cellule: bool,
    distance_km: float,
) -> None:
    """Alma est retenue dans sa cellule comme depuis la cellule voisine, et la réponse le dit."""
    resolution = client.get("/v1/localites/resolution", params=point, headers=headers_auth)
    assert resolution.status_code == 200, resolution.text
    corps = resolution.json()
    assert corps["localite"]["code"] == "zzf_alma"
    assert corps["serie_climatologie"] == _GHI_MENSUEL_ALMA
    assert corps["meme_cellule"] is meme_cellule
    assert corps["distance_km"] == distance_km

    capsule = client.get("/v1/etudes/capsule", params=point, headers=headers_auth)
    assert capsule.status_code == 200, capsule.text
    assert fichier_kuma.lire(capsule.text)["metadonnees"]["provenance"]["resolution"] == {
        "localite": "zzf_alma",
        "serieReference": _GHI_MENSUEL_ALMA,
        "distanceKm": distance_km,
        "memeCellule": meme_cellule,
    }


def test_point_a_deux_cellules_du_pays_refuse_par_la_route_et_par_la_capsule(
    client: TestClient, headers_auth: dict[str, str], pays_fictif: Session
) -> None:
    """La zone couverte du pays s'arrête aux cellules voisines de ses points d'ingestion."""
    message = (
        "Point hors de la zone couverte : aucun point d'ingestion de climatologie "
        "dans sa cellule de grille ni dans une cellule voisine."
    )
    resolution = client.get(
        "/v1/localites/resolution", params=_POINT_A_DEUX_CELLULES, headers=headers_auth
    )
    assert resolution.status_code == 404
    assert resolution.json()["erreur"] == {
        "code": "RESSOURCE_INTROUVABLE",
        "message": message,
        # 1,8° de méridien.
        "details": {"localite_la_plus_proche": "zzf_alma", "distance_km": 200.2},
    }

    capsule = client.get("/v1/etudes/capsule", params=_POINT_A_DEUX_CELLULES, headers=headers_auth)
    assert capsule.status_code == 404
    assert capsule.json()["erreur"] == {"code": "RESSOURCE_INTROUVABLE", "message": message}


def test_rien_ne_reste_en_base() -> None:
    """Pendant le test, seule sa connexion voit le pays ; après, plus personne."""
    with get_engine().connect() as temoin:
        depuis = temoin.execute(text("SELECT clock_timestamp()")).scalar_one()
        avant = _empreinte(temoin, depuis)
        assert avant["audit"] == 0

        with _transaction_annulee() as session:
            _creer_pays_fictif(session)
            pendant = _empreinte(session.connection(), depuis)
            assert pendant["localites"] == avant["localites"] + len(_LOCALITES)
            assert pendant["series"] == avant["series"] + len(_SERIES)
            assert pendant["audit"] > len(_LOCALITES) + len(_SERIES)
            assert _empreinte(temoin, depuis) == avant

        assert _empreinte(temoin, depuis) == avant
