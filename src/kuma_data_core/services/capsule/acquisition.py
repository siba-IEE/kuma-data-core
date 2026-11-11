"""Acquisition des entrées de la ressource depuis la base du Core.

Implémentation concrète de ``SourceCapsule`` (le protocole de ``construire``).
Lit trois choses au point :

- la résolution (lat, lon) → la localité dont la climatologie représente le
  point, et son code de climatologie (même règle que ``/v1/localites/resolution``) ;
- la climatologie mensuelle : moyenne par mois calendaire sur 1991-2020 des
  mesures mensuelles de cette série (12 valeurs, kWh/m²/j = HEP) ;
- la séquence horaire satellite : la série GHI horaire NASA de la localité,
  le brut au point, mois et heures comptés dans le fuseau de la localité.

Rien de calé ici : la séquence et la climatologie sortent brutes, le moteur cale
via le champ ``calage``, présent en ligne seulement. Aucun appel à kuma-calage
dans ce module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.editorial.selection import lignes_en_vigueur, lignes_en_vigueur_validees
from kuma_data_core.lecture.localites import lister_candidates_resolution
from kuma_data_core.services.capsule.construire import EntreesRessource
from kuma_data_core.services.resolution import MESSAGE_POINT_HORS_ZONE, resoudre


class PointHorsReferentielError(ValueError):
    """Le point ne se résout sur aucune localité, ou la localité n'a pas le brut."""


@dataclass(frozen=True)
class SourceCore:
    """Source d'acquisition adossée à une session du Core.

    ``annee_min`` / ``annee_max`` fenêtrent la séquence horaire (années
    locales, bornes incluses). ``None`` prend toute la profondeur stockée :
    honnête mais lourd (25 ans ~ 219 000 points). L'appelant fixe le compromis.
    """

    session: Session
    annee_min: int | None = None
    annee_max: int | None = None

    def acquerir(self, latitude_deg: float, longitude_deg: float) -> EntreesRessource:
        localite = self._resoudre(latitude_deg, longitude_deg)
        climatologie, provenance_clim = self._climatologie_hep(localite["localite_id"])
        sequence, periode, provenance_seq = self._sequence_horaire(localite["localite_id"])
        temperatures, provenance_temp = self._extremes_temperature(localite["localite_id"])

        metadonnees = {
            "identite": {
                "nom": localite["nom"],
                "latitudeDeg": latitude_deg,
                "longitudeDeg": longitude_deg,
            },
            "edition": {
                "id": f"capsule-{localite['localite_code']}",
                "revisionSource": provenance_seq["code"],
            },
            # Les quatre séries que le moteur exige à l'en-tête : la climatologie
            # au point vient du mensuel de la cellule, la climatologie source et
            # les deux séquences viennent de l'horaire (la source est dérivée de
            # la séquence ; le contraignant est ici le type). La résolution est
            # ajoutée pour l'audit.
            "provenance": {
                "climatologieAuPoint": provenance_clim,
                "climatologieSource": provenance_seq,
                "sequenceType": provenance_seq,
                "sequenceContraignant": provenance_seq,
                "resolution": {
                    "localite": localite["localite_code"],
                    "serieReference": localite["serie_climatologie"],
                    "distanceKm": localite["distance_km"],
                    "memeCellule": localite["meme_cellule"],
                },
                # Présent seulement quand les extrêmes sont servis : une série
                # embarquée cite sa provenance ; absente, pas de clé vide.
                **(
                    {"temperaturesConception": provenance_temp}
                    if provenance_temp is not None
                    else {}
                ),
            },
        }
        return EntreesRessource(
            metadonnees=metadonnees,
            periode=periode,
            domaine_validite=periode,
            climatologie_hep=climatologie,
            sequence=sequence,
            temperatures_conception=temperatures,
        )

    def _resoudre(self, lat: float, lon: float) -> dict[str, Any]:
        """Résout le point vers la localité dont la climatologie GHI le représente."""
        candidates = lister_candidates_resolution(self.session, "ghi")
        if not candidates:
            raise PointHorsReferentielError("aucun point d'ingestion de climatologie GHI")
        resolution = resoudre(lat, lon, candidates)
        if resolution is None:
            raise PointHorsReferentielError(MESSAGE_POINT_HORS_ZONE)
        retenue = resolution.candidate
        return {
            "localite_id": retenue.localite_id,
            "localite_code": retenue.code,
            "nom": retenue.nom,
            "serie_climatologie": retenue.serie_code,
            "distance_km": round(resolution.distance_km, 1),
            "meme_cellule": resolution.meme_cellule,
        }

    def _climatologie_hep(self, localite_id: int) -> tuple[list[float], dict[str, Any]]:
        """Les 12 HEP mensuelles, moyenne par mois sur la mensuelle la plus profonde.

        L'horaire NASA ne démarre qu'en 2001, mais l'énergie mensuelle remonte à
        1984 : on prend la série mensuelle NASA de plus grande profondeur de la
        localité. La résolution reste, elle, sur la climatologie de référence
        1991-2020 (identification de la cellule).
        """
        meta = self.session.execute(
            text(
                """
                SELECT sm.code, sm.libelle, sm.methode_collecte,
                       sm.periode_debut, sm.periode_fin, s.code AS source_code, s.titre
                FROM series_metadonnees sm
                LEFT JOIN sources s ON s.id = sm.source_id
                WHERE sm.localite_id = :loc AND sm.grandeur_code = 'ghi'
                  AND sm.granularite = 'mensuel' AND sm.actif AND s.code = 'nasa_power'
                ORDER BY sm.periode_debut ASC, (sm.periode_fin - sm.periode_debut) DESC
                LIMIT 1
                """
            ),
            {"loc": localite_id},
        ).first()
        if meta is None:
            raise PointHorsReferentielError(
                f"pas de climatologie mensuelle NASA pour la localité {localite_id}"
            )
        rows = self.session.execute(
            text(
                f"""
                SELECT m.mois, avg(m.valeur) AS hep
                FROM mesures_ressource_mensuelles m
                JOIN series_metadonnees sm ON sm.id = m.serie_id
                WHERE sm.code = :code AND {lignes_en_vigueur("m")}
                GROUP BY m.mois ORDER BY m.mois
                """
            ),
            {"code": meta.code},
        ).all()
        if len(rows) != 12:
            raise PointHorsReferentielError(
                f"climatologie {meta.code} incomplète : {len(rows)} mois sur 12"
            )
        provenance = {
            "code": meta.code,
            "libelle": meta.libelle,
            "methode": meta.methode_collecte,
            "source": meta.source_code,
            "sourceTitre": meta.titre,
            "periode": {
                "debut": meta.periode_debut.strftime("%Y-%m"),
                "fin": meta.periode_fin.strftime("%Y-%m"),
            },
        }
        return [float(r.hep) for r in rows], provenance

    def _extremes_temperature(
        self, localite_id: int
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Records de température au point, sur les séries ``t2m_min`` / ``t2m_max``.

        Le plus froid des minima journaliers et le plus chaud des maxima, bruts
        NASA et hors calage : le calage corrige l'irradiance, pas la température.
        Rend ``(None, None)`` si les séries sont absentes : la capsule omet alors
        le bloc et le dimensionnement des strings retombe sur une saisie manuelle.
        """
        row = self.session.execute(
            text(
                f"""
                SELECT
                    min(m.valeur) FILTER (WHERE sm.grandeur_code = 't2m_min') AS froid,
                    max(m.valeur) FILTER (WHERE sm.grandeur_code = 't2m_max') AS chaud,
                    min(sm.periode_debut) AS debut,
                    max(sm.periode_fin) AS fin,
                    min(s.code) AS source_code
                FROM mesures_ressource m
                JOIN series_metadonnees sm ON sm.id = m.serie_id
                LEFT JOIN sources s ON s.id = sm.source_id
                WHERE sm.localite_id = :loc
                  AND sm.grandeur_code IN ('t2m_min', 't2m_max')
                  AND sm.granularite = 'journalier' AND sm.actif
                  AND {lignes_en_vigueur("m")}
                """
            ),
            {"loc": localite_id},
        ).first()
        if row is None or row.froid is None or row.chaud is None:
            return None, None

        fenetre = {
            "debut": row.debut.strftime("%Y-%m"),
            "fin": row.fin.strftime("%Y-%m"),
        }
        temperatures = {
            "froidC": round(float(row.froid), 2),
            "chaudC": round(float(row.chaud), 2),
            "fenetre": fenetre,
        }
        provenance = {
            "froid": "t2m_min",
            "chaud": "t2m_max",
            "source": row.source_code,
            "agregat": "record",
            "periode": fenetre,
        }
        return temperatures, provenance

    def _sequence_horaire(
        self, localite_id: int
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Séquence GHI horaire satellite de la localité : (séquence, période, provenance).

        Mois, heures et années de la fenêtre sont ceux du fuseau de la localité
        (``localites.fuseau_horaire``, UTC si elle n'en a pas).
        """
        meta = self.session.execute(
            text(
                """
                SELECT sm.code, sm.libelle, sm.methode_collecte,
                       sm.periode_debut, sm.periode_fin, s.code AS source_code, s.titre,
                       COALESCE(l.fuseau_horaire, 'UTC') AS fuseau
                FROM series_metadonnees sm
                JOIN localites l ON l.id = sm.localite_id
                LEFT JOIN sources s ON s.id = sm.source_id
                WHERE sm.localite_id = :loc AND sm.grandeur_code = 'ghi'
                  AND sm.granularite = 'horaire' AND sm.actif
                  AND sm.methode_collecte = 'modele_satellitaire'
                ORDER BY sm.periode_fin DESC
                LIMIT 1
                """
            ),
            {"loc": localite_id},
        ).first()
        if meta is None:
            raise PointHorsReferentielError(
                f"pas de série GHI horaire satellite pour la localité {localite_id}"
            )

        clauses = ["sm.code = :code", lignes_en_vigueur_validees("mh")]
        params: dict[str, object] = {"code": meta.code, "fuseau": meta.fuseau}
        if self.annee_min is not None:
            clauses.append("extract(year from mh.instant_mesure at time zone :fuseau) >= :amin")
            params["amin"] = self.annee_min
        if self.annee_max is not None:
            clauses.append("extract(year from mh.instant_mesure at time zone :fuseau) <= :amax")
            params["amax"] = self.annee_max
        where = " AND ".join(clauses)

        rows = self.session.execute(
            text(
                f"""
                SELECT extract(month from mh.instant_mesure at time zone :fuseau)::int AS mois,
                       extract(hour from mh.instant_mesure at time zone :fuseau)::int AS heure,
                       mh.valeur
                FROM mesures_ressource_horaires mh
                JOIN series_metadonnees sm ON sm.id = mh.serie_id
                WHERE {where}
                ORDER BY mh.instant_mesure
                """
            ),
            params,
        ).all()
        if not rows:
            raise PointHorsReferentielError(f"série {meta.code} sans point horaire validé")

        sequence = {
            "mois": [int(r.mois) for r in rows],
            "heures": [int(r.heure) for r in rows],
            "ghi": [float(r.valeur) for r in rows],
        }
        # La période reflète la fenêtre réellement servie, pas la série entière.
        debut = (
            f"{self.annee_min}-01"
            if self.annee_min is not None
            else meta.periode_debut.strftime("%Y-%m")
        )
        fin = (
            f"{self.annee_max}-12"
            if self.annee_max is not None
            else meta.periode_fin.strftime("%Y-%m")
        )
        periode = {"debut": debut, "fin": fin}
        provenance = {
            "code": meta.code,
            "libelle": meta.libelle,
            "methode": meta.methode_collecte,
            "source": meta.source_code,
            "sourceTitre": meta.titre,
            "periode": periode,
        }
        return sequence, periode, provenance
