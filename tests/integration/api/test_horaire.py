"""Tests d'integration des endpoints `/api/v1/horaire/<localite>/<grandeur>`.

Passe-plat horaire :

- endpoint data (succes, erreurs auth/validation/plage).
- format CSV + sentinelles + format Kt nocturne.
- lever du stocke valide (dont regression series coquilles, ti111-112).
- endpoint disponibilite (succes + format coherent).

Plus 1 pre-test empirique `empirique_nasa_power` (exclu de la suite
reguliere) qui valide empiriquement la plage max 366 jours avec un
appel reel a l'API externe.

TestClient FastAPI synchrone + fixture
``headers_auth`` (conftest racine).

Fixtures NASA POWER mockees via :func:`unittest.mock.patch` sur
``fetch_hourly``. La reponse mockee respecte le contrat
``NasaPowerResponse`` (cles ``YYYYMMDDHH`` -> float, sentinelles
-999.0 conservees pour declenchement de la conversion -> null).
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from kuma_data_core.api.codes_erreur import CodeErreur

pytestmark = pytest.mark.integration


_LOCALITE_TEST = "conakry_kaloum"
_GRANDEUR_TEST = "ghi"


def _construire_payload_amont_mock(
    debut: date,
    fin: date,
    grandeur_code_amont: str,
    *,
    sentinelles: bool = False,
) -> Any:
    """Construit un mock minimal de NasaPowerResponse pour la plage donnee.

    Genere 24 valeurs par jour entre debut et fin (inclusif). Si
    ``sentinelles=True``, toutes les valeurs sont a -999.0 ; sinon des
    valeurs croissantes deterministes.

    Utilise ``SimpleNamespace`` pour exposer la seule attribute path
    consommee par le routeur (``reponse.properties.parameter``), evitant
    la validation complete du schema NasaPowerResponse (qui exige des
    champs metadata header / parameters non pertinents pour les tests
    d'integration du routeur Kuma).
    """
    valeurs: dict[str, float] = {}
    jour = debut
    while jour <= fin:
        for heure in range(24):
            cle = f"{jour.strftime('%Y%m%d')}{heure:02d}"
            valeurs[cle] = -999.0 if sentinelles else 100.0 + heure
        jour += timedelta(days=1)

    return SimpleNamespace(properties=SimpleNamespace(parameter={grandeur_code_amont: valeurs}))


# === Endpoint data ========================================================


def test_ti94_data_sans_auth_rejete(client: TestClient) -> None:
    """GET /v1/horaire/.../... sans auth -> 401."""
    r = client.get(
        f"/v1/horaire/{_LOCALITE_TEST}/{_GRANDEUR_TEST}",
        params={"periode_debut": "2024-06-01", "periode_fin": "2024-06-05"},
    )
    assert r.status_code == 401
    assert r.json()["erreur"]["code"] == CodeErreur.AUTH_HEADER_MANQUANT.value


def test_ti95_data_succes_donnees_reelles(client: TestClient, headers_auth: dict[str, str]) -> None:
    """data avec auth + plage valide + GHI -> 200 + valeurs reelles."""
    mock_response = _construire_payload_amont_mock(
        date(2024, 6, 1), date(2024, 6, 2), "ALLSKY_SFC_SW_DWN"
    )
    with patch("kuma_data_core.api.v1.horaire.fetch_hourly", return_value=mock_response):
        r = client.get(
            f"/v1/horaire/{_LOCALITE_TEST}/{_GRANDEUR_TEST}",
            params={"periode_debut": "2024-06-01", "periode_fin": "2024-06-02"},
            headers=headers_auth,
        )
    assert r.status_code == 200
    payload = r.json()
    assert payload["localite"] == _LOCALITE_TEST
    assert payload["grandeur"] == _GRANDEUR_TEST
    assert payload["periode_demandee"] == {"debut": "2024-06-01", "fin": "2024-06-02"}
    assert len(payload["resultats"]) == 48  # 2 jours * 24 heures
    for r_jour in payload["resultats"]:
        assert r_jour["statut_editorial"] == "passe_plat_non_valide"
        assert r_jour["unite"] == "Wh/m²"
        assert r_jour["valeur"] is not None


def test_ti96_data_sentinelles_converties_en_null(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """sentinelles -999.0 cote amont -> valeur null cote Kuma."""
    mock_response = _construire_payload_amont_mock(
        date(2024, 6, 1), date(2024, 6, 1), "ALLSKY_SFC_SW_DWN", sentinelles=True
    )
    with patch("kuma_data_core.api.v1.horaire.fetch_hourly", return_value=mock_response):
        r = client.get(
            f"/v1/horaire/{_LOCALITE_TEST}/{_GRANDEUR_TEST}",
            params={"periode_debut": "2024-06-01", "periode_fin": "2024-06-01"},
            headers=headers_auth,
        )
    assert r.status_code == 200
    payload = r.json()
    assert all(r_jour["valeur"] is None for r_jour in payload["resultats"])


def test_ti97_data_localite_invalide(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Localite hors referentiel : 404 RESSOURCE_LOCALITE_INCONNUE.

    Contrat generalise (genericite pays, residu 1) : l'enumeration
    fermee des 6 villes (422) laisse place a la resolution contre la
    table des localites, avec erreur honnete pour un code inconnu.
    """
    r = client.get(
        "/v1/horaire/atlantide/ghi",
        params={"periode_debut": "2024-06-01", "periode_fin": "2024-06-05"},
        headers=headers_auth,
    )
    assert r.status_code == 404
    assert r.json()["erreur"]["code"] == CodeErreur.RESSOURCE_LOCALITE_INCONNUE.value


def test_ti98_data_grandeur_invalide(client: TestClient, headers_auth: dict[str, str]) -> None:
    """grandeur hors enum -> 422."""
    r = client.get(
        f"/v1/horaire/{_LOCALITE_TEST}/poa",
        params={"periode_debut": "2024-06-01", "periode_fin": "2024-06-05"},
        headers=headers_auth,
    )
    assert r.status_code == 422


def test_ti99_data_plage_excessive_366_plus(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """plage > 366 jours -> ValidationError leve cote serveur.

    Comportement observe : FastAPI ne mappe pas systematiquement le
    ValidationError leve par un ``model_validator(mode="after")``
    Pydantic v2 dans ``Annotated[T, Depends()]`` vers un 422 standard.
    L'exception remonte comme ``ValidationError`` non geree, ce qui
    provoque un re-raise cote ``TestClient`` (option par defaut
    ``raise_server_exceptions=True``).

    Le test verifie que la requete est rejetee (exception levee
    contenant le message « plage maximale 366 jours »). Affinement
    possible ulterieur via un exception handler FastAPI dedie qui
    mapperait ``pydantic.ValidationError`` -> 422
    ``VALIDATION_VALEUR_INVALIDE`` enveloppee.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="366 jours"):
        client.get(
            f"/v1/horaire/{_LOCALITE_TEST}/{_GRANDEUR_TEST}",
            params={"periode_debut": "2023-01-01", "periode_fin": "2024-12-31"},
            headers=headers_auth,
        )


def test_ti100_data_plage_hors_disponibilite(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """plage futur (au-delà de la borne NRT) -> 400 PLAGE_TEMPORELLE_NON_DISPONIBLE."""
    # Periode future garantit la sortie de plage disponible (B1 statique
    # = aujourd'hui - 5 mois - 1 jour).
    r = client.get(
        f"/v1/horaire/{_LOCALITE_TEST}/{_GRANDEUR_TEST}",
        params={"periode_debut": "2026-04-01", "periode_fin": "2026-04-30"},
        headers=headers_auth,
    )
    assert r.status_code == 400
    payload = r.json()
    assert payload["erreur"]["code"] == CodeErreur.PLAGE_TEMPORELLE_NON_DISPONIBLE.value
    assert "plage_demandee" in payload["erreur"]["details"]
    assert "plage_disponible" in payload["erreur"]["details"]


def test_ti101_data_amont_indisponible_503(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """exception client externe -> 503 PASSE_PLAT_INDISPONIBLE."""
    from kuma_data_core.exceptions import NasaPowerTimeoutError

    with patch(
        "kuma_data_core.api.v1.horaire.fetch_hourly",
        side_effect=NasaPowerTimeoutError(url="http://test", timeout_seconds=30.0),
    ):
        r = client.get(
            f"/v1/horaire/{_LOCALITE_TEST}/{_GRANDEUR_TEST}",
            params={"periode_debut": "2024-06-01", "periode_fin": "2024-06-05"},
            headers=headers_auth,
        )
    assert r.status_code == 503
    assert r.json()["erreur"]["code"] == CodeErreur.PASSE_PLAT_INDISPONIBLE.value


# === Format CSV + grandeur Kt =============================================


def test_ti102_data_format_csv(client: TestClient, headers_auth: dict[str, str]) -> None:
    """format=csv -> 200 text/csv avec header attendu."""
    mock_response = _construire_payload_amont_mock(
        date(2024, 6, 1), date(2024, 6, 1), "ALLSKY_SFC_SW_DWN"
    )
    with patch("kuma_data_core.api.v1.horaire.fetch_hourly", return_value=mock_response):
        r = client.get(
            f"/v1/horaire/{_LOCALITE_TEST}/{_GRANDEUR_TEST}",
            params={
                "periode_debut": "2024-06-01",
                "periode_fin": "2024-06-01",
                "format": "csv",
            },
            headers=headers_auth,
        )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    body = r.text
    assert "instant,valeur,unite,statut_editorial" in body
    assert "passe_plat_non_valide" in body


def test_ti103_data_kt_nocturne_null(client: TestClient, headers_auth: dict[str, str]) -> None:
    """grandeur kt avec sentinelles nocturnes -> valeur null."""
    mock_response = _construire_payload_amont_mock(
        date(2024, 6, 1), date(2024, 6, 1), "ALLSKY_KT", sentinelles=True
    )
    with patch("kuma_data_core.api.v1.horaire.fetch_hourly", return_value=mock_response):
        r = client.get(
            f"/v1/horaire/{_LOCALITE_TEST}/kt",
            params={"periode_debut": "2024-06-01", "periode_fin": "2024-06-01"},
            headers=headers_auth,
        )
    assert r.status_code == 200
    payload = r.json()
    assert all(r_jour["valeur"] is None for r_jour in payload["resultats"])
    assert payload["resultats"][0]["unite"] == "sans dimension"


def test_ti104_data_unite_t2m_celsius(client: TestClient, headers_auth: dict[str, str]) -> None:
    """grandeur t2m -> unite °C cote Kuma."""
    mock_response = _construire_payload_amont_mock(date(2024, 6, 1), date(2024, 6, 1), "T2M")
    with patch("kuma_data_core.api.v1.horaire.fetch_hourly", return_value=mock_response):
        r = client.get(
            f"/v1/horaire/{_LOCALITE_TEST}/t2m",
            params={"periode_debut": "2024-06-01", "periode_fin": "2024-06-01"},
            headers=headers_auth,
        )
    assert r.status_code == 200
    payload = r.json()
    assert payload["resultats"][0]["unite"] == "°C"


# === Lever passe_plat : service du stocké validé =========================


def test_ti107_lever_stocke_valide_servi(client: TestClient, headers_auth: dict[str, str]) -> None:
    """plage couverte par le stocké validé -> statut valide_auto.

    Conakry GHI 2022-06 est dans la fenêtre stockée (2021-2023, QC) :
    l'endpoint sert la donnée validée au lieu de relayer la source amont.
    """
    r = client.get(
        f"/v1/horaire/{_LOCALITE_TEST}/{_GRANDEUR_TEST}",
        params={"periode_debut": "2022-06-01", "periode_fin": "2022-06-02"},
        headers=headers_auth,
    )
    assert r.status_code == 200
    payload = r.json()
    assert len(payload["resultats"]) > 0
    assert all(res["statut_editorial"] == "valide_auto" for res in payload["resultats"])


def test_ti108_lever_stocke_ne_relaie_pas_amont(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """quand le stocké couvre la plage, fetch_hourly n'est pas appelé."""
    with patch("kuma_data_core.api.v1.horaire.fetch_hourly") as mock_fetch:
        r = client.get(
            f"/v1/horaire/{_LOCALITE_TEST}/{_GRANDEUR_TEST}",
            params={"periode_debut": "2022-06-01", "periode_fin": "2022-06-02"},
            headers=headers_auth,
        )
    assert r.status_code == 200
    mock_fetch.assert_not_called()


def test_ti109_edition_figee_refuse_le_repli_sans_appel_amont(
    client: TestClient,
    headers_auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Profil édition figée (ADR-0003 D6) -> repli passe-plat refusé.

    Plage 2024 non couverte par le stocké : en profil figé, l'endpoint
    renvoie 400 PLAGE_TEMPORELLE_NON_DISPONIBLE au lieu de relayer NASA
    POWER, et fetch_hourly n'est jamais appelé (zéro dépendance
    sortante).
    """
    from kuma_data_core.core.config import get_settings

    monkeypatch.setattr(get_settings(), "edition_figee", True)
    with patch("kuma_data_core.api.v1.horaire.fetch_hourly") as mock_fetch:
        r = client.get(
            f"/v1/horaire/{_LOCALITE_TEST}/{_GRANDEUR_TEST}",
            params={"periode_debut": "2024-06-01", "periode_fin": "2024-06-05"},
            headers=headers_auth,
        )
    assert r.status_code == 400
    assert r.json()["erreur"]["code"] == CodeErreur.PLAGE_TEMPORELLE_NON_DISPONIBLE.value
    mock_fetch.assert_not_called()


def test_ti110_edition_figee_sert_toujours_le_stocke(
    client: TestClient,
    headers_auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le profil figé ne change rien au service du stocké."""
    from kuma_data_core.core.config import get_settings

    monkeypatch.setattr(get_settings(), "edition_figee", True)
    r = client.get(
        f"/v1/horaire/{_LOCALITE_TEST}/{_GRANDEUR_TEST}",
        params={"periode_debut": "2022-06-01", "periode_fin": "2022-06-02"},
        headers=headers_auth,
    )
    assert r.status_code == 200
    assert all(res["statut_editorial"] == "valide_auto" for res in r.json()["resultats"])


def test_ti111_serie_coquille_ignoree_le_stocke_terrain_est_servi(
    client: TestClient,
    headers_auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(kankan, ghi) : la coquille est écartée, le sol ESMAP est servi.

    Régression production 2026-07-20 : deux séries horaires actives
    coexistent pour ce couple - la série substrat 2001-2023 sans
    aucune mesure stockée (coquille) et la série sol terrain
    2021-2023 (17 520 mesures valide_auto). La sélection sans garde
    prenait la coquille et l'endpoint répondait 200 avec zéro
    résultat. Attendu : les mesures terrain sont servies, sans appel
    amont.
    """
    from kuma_data_core.core.config import get_settings

    monkeypatch.setattr(get_settings(), "edition_figee", True)
    with patch("kuma_data_core.api.v1.horaire.fetch_hourly") as mock_fetch:
        r = client.get(
            "/v1/horaire/kankan/ghi",
            params={"periode_debut": "2022-06-01", "periode_fin": "2022-06-02"},
            headers=headers_auth,
        )
    assert r.status_code == 200
    resultats = r.json()["resultats"]
    assert len(resultats) == 48
    assert all(res["statut_editorial"] == "valide_auto" for res in resultats)
    mock_fetch.assert_not_called()


def test_ti124_code_complet_sert_le_stocke(
    client: TestClient,
    headers_auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le code complet du referentiel (gin_kankan) est le chemin nominal.

    Genericite pays (residu 1) : toute localite du referentiel est
    adressable par son code complet, sans liste codee. L'alias court
    historique (kankan) reste couvert par ti111.
    """
    from kuma_data_core.core.config import get_settings

    monkeypatch.setattr(get_settings(), "edition_figee", True)
    r = client.get(
        "/v1/horaire/gin_kankan/ghi",
        params={"periode_debut": "2022-06-01", "periode_fin": "2022-06-02"},
        headers=headers_auth,
    )
    assert r.status_code == 200
    resultats = r.json()["resultats"]
    assert len(resultats) == 48
    assert all(res["statut_editorial"] == "valide_auto" for res in resultats)


def test_ti112_coquille_seule_en_figee_erreur_honnete(
    client: TestClient,
    headers_auth: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(kindia, ghi) : coquille seule -> 400 honnête, pas 200 vide.

    Kindia ne possède qu'une série horaire GHI sans mesures stockées
    (métadonnées 2001-2023). En profil figé, l'endpoint doit renvoyer
    PLAGE_TEMPORELLE_NON_DISPONIBLE plutôt que de laisser croire à
    une donnée servie en répondant 200 avec zéro résultat. Aucun
    appel amont.
    """
    from kuma_data_core.core.config import get_settings

    monkeypatch.setattr(get_settings(), "edition_figee", True)
    with patch("kuma_data_core.api.v1.horaire.fetch_hourly") as mock_fetch:
        r = client.get(
            "/v1/horaire/kindia/ghi",
            params={"periode_debut": "2022-06-01", "periode_fin": "2022-06-02"},
            headers=headers_auth,
        )
    assert r.status_code == 400
    assert r.json()["erreur"]["code"] == CodeErreur.PLAGE_TEMPORELLE_NON_DISPONIBLE.value
    mock_fetch.assert_not_called()


# === Endpoint disponibilite ===============================================


def test_ti105_disponibilite_succes(client: TestClient, headers_auth: dict[str, str]) -> None:
    """/disponibilite -> 200 + plage_disponible coherente."""
    r = client.get(
        f"/v1/horaire/{_LOCALITE_TEST}/{_GRANDEUR_TEST}/disponibilite",
        headers=headers_auth,
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["localite"] == _LOCALITE_TEST
    assert payload["grandeur"] == _GRANDEUR_TEST
    assert payload["plage_disponible"]["debut"] == "2001-01-01"
    assert payload["statut_editorial"] == "passe_plat_non_valide"


def test_ti106_disponibilite_sans_auth(client: TestClient) -> None:
    """/disponibilite sans auth -> 401."""
    r = client.get(f"/v1/horaire/{_LOCALITE_TEST}/{_GRANDEUR_TEST}/disponibilite")
    assert r.status_code == 401


# === Pré-test empirique 366 jours (marker dédié, exclu suite régulière) ===


@pytest.mark.empirique_nasa_power
def test_pre_test_empirique_366_jours_conakry() -> None:
    """Pré-test empirique : valide qu'une requete 366 jours x 6 parametres
    x 1 point amont n'est pas tronquee ni timeoutee.

    Test exclu de la suite reguliere via marker
    ``@pytest.mark.empirique_nasa_power``. À exécuter manuellement :

        uv run pytest tests/integration/api/test_horaire.py \\
            -m empirique_nasa_power -v --timeout=120

    Critere succes :
    - HTTP 200 OK
    - 52 600 valeurs (366 jours * 24 heures * 6 parametres)
    - Latence < 30 secondes
    - Pas de tronquage observe (toutes les cles YYYYMMDDHH presentes)

    Localite : Conakry-Kaloum (lat 9.5092, lon -13.7122).
    """
    import time

    from kuma_data_core.external.nasa_power import fetch_hourly

    parametres = [
        "ALLSKY_SFC_SW_DWN",
        "ALLSKY_SFC_SW_DNI",
        "ALLSKY_SFC_SW_DIFF",
        "T2M",
        "RH2M",
        "ALLSKY_KT",
    ]
    debut = date(2024, 1, 1)
    fin = date(2024, 12, 31)  # 366 jours bissextile

    instant_avant = time.monotonic()
    reponse = fetch_hourly(
        latitude=9.5092,
        longitude=-13.7122,
        parameters=parametres,
        start=debut,
        end=fin,
    )
    latence_secondes = time.monotonic() - instant_avant

    # Verifications
    assert latence_secondes < 30.0, (
        f"Latence {latence_secondes:.1f}s > 30s - STOP chat pour arbitrage Q6"
    )
    nb_valeurs_par_parametre = {
        param: len(reponse.properties.parameter.get(param, {})) for param in parametres
    }
    nb_heures_attendu = 366 * 24  # 8784
    for param, nb_valeurs in nb_valeurs_par_parametre.items():
        assert nb_valeurs == nb_heures_attendu, (
            f"Parametre {param} : {nb_valeurs} valeurs vs {nb_heures_attendu} attendues "
            "- tronquage suspecte, STOP chat pour arbitrage Q6"
        )

    print(
        f"\nPre-test empirique 366 jours : OK. "
        f"Latence {latence_secondes:.1f}s, "
        f"{sum(nb_valeurs_par_parametre.values())} valeurs total"
    )
