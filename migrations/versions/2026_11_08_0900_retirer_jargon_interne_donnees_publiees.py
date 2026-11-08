"""retirer_jargon_interne_donnees_publiees

Revision ID: 128
Revises: 127
Create Date: 2026-11-08 09:00:00.000000+00:00

Migration de coherence editoriale, sans DDL ni donnee mesuree. Suite de la
migration 127 (catalogue et ``grandeurs_referentiel``) pour les colonnes de
texte des autres tables publiees telles quelles (``TABLES_PUBLIEES`` du
manifeste de publication) : leurs textes portaient du vocabulaire de chantier
interne (dettes « D-n », vagues, lots, etapes, phases, codes d'etape « 1-1E »,
renvois de specs, de PR et de documents ``*.md`` du depot).

1. ``grandeurs_metier.commentaire_editorial`` (``degenerescence_pixel``, aussi
   servi par l'API comme note de degenerescence) : « (D-29 generalise) » est
   retire de 140 lignes ; la phrase dit deja la regle (« ne pas presenter
   comme des mesures independantes »). Transformation ``replace`` sur un
   fragment unique par ligne, gardee par le nombre de lignes et une empreinte
   md5 de l'ensemble des textes touches ; toutes versions confondues (le
   versioning fait partie de la donnee publiee).
2. ``localites.notes`` (67 localites) : mention de la densification
   prefectorale et renvois a sa spec retires ; codes de phase et etiquettes
   de suivi interne remplaces par leur contenu en clair.
3. ``sources.notes`` (14 sources) et ``sources.metadonnees`` (2 valeurs
   texte, cles et types inchanges) : idem.
4. ``referentiels_calage.provenance`` (3 lignes) : renvois vers une note
   ``*.md`` et un script du depot remplaces par leur contenu.

Corrections de fond au passage (enonces devenus faux) : ``ecmwf_era5`` ne
porte aucune serie Kuma (seule ERA5-Land, source distincte ``ecmwf_era5_land``
depuis la migration 068, est ingeree) ; ``ecmwf_era5_land`` couvre 34
localites et non les 6 villes pilotes ; ``esmap_wapp`` alimente une serie DNI
en plus de la serie GHI ; ``cams_radiation`` porte GHI, DNI et DHI ; la
communaute NASA POWER est fixee (RE, client d'ingestion).

Les textes generes par le code (``services/grandeurs/degenerescence_pixel``,
``db/seeds/localites_prefectures_seed_data``,
``db/seeds/referentiels_calage_101_seed_data``) ne sont pas modifies : les
migrations 085, 090 et 101 les importent, et changer leur sortie changerait
l'etat que ces migrations produisent sur une base neuve.

Correction en place (UPDATE sous trigger d'audit ``kuma_log_audit()``), sans
nouvelle version : seul le texte change ; ``valeur``, ``valide_du``,
``valide_au``, ``statut``, confiance et ``modifie_le`` ne sont pas touches
(precedent migrations 100, 125, 126 et 127).

Gardes : chaque ligne reecrite par fragments doit avoir l'empreinte md5 de
son texte de depart exact, chaque fragment doit y figurer une seule fois et
le texte d'arrivee doit avoir l'empreinte attendue. Le downgrade applique les
memes fragments en sens inverse avec les memes gardes et restaure les textes
d'origine a l'identique. Aucun reseau.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "128"
down_revision: str | Sequence[str] | None = "127"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Substitution : (fragment de depart exact, fragment d'arrivee).
Substitution = tuple[str, str]


# === 1. grandeurs_metier.commentaire_editorial =============================

DEGENERESCENCE: Substitution = (
    "mesures independantes (D-29 generalise).",
    "mesures independantes.",
)
DEGENERESCENCE_LIGNES = 140
# md5 de string_agg(texte, E'\n' ORDER BY texte COLLATE "C") des lignes touchees.
DEGENERESCENCE_EMPREINTES: tuple[str, str] = (
    "9cf2ec88f85c47c580898e8f3bc3568f",
    "ef0689e89c2adc510b8a3f69ec5e64d1",
)


# === 2. localites.notes ====================================================

SUBSTITUTIONS_LOCALITES: dict[str, Substitution] = {
    "densification": (
        " Densification prefectorale Etape 1, compile 2026-06-20.",
        " Compilation du 2026-06-20.",
    ),
    "commune_chef_lieu": (
        "point d'ingestion solaire uniforme (modelisation (a), spec Etape 1 Sec. 5.3).",
        "point d'ingestion solaire uniforme.",
    ),
    "prefecture": (
        "Coordonnees du chef-lieu (Sec. 5.3), identiques",
        "Coordonnees du chef-lieu, identiques",
    ),
    "conakry_perimetre": (
        "choix de modélisation pilote phase 1. La réforme du 18 janvier 2024 porte "
        "Conakry à 13 communes ; intégration prévue en phase 2.",
        "choix de modélisation initial. La réforme du 18 janvier 2024 porte Conakry "
        "à 13 communes ; les communes issues de cette réforme ne sont pas encore "
        "intégrées.",
    ),
    "kassa": (
        "Pour représentation post-2021, créer gin_conakry_kassa en phase 2.",
        "Pour une représentation post-2021, une localité distincte gin_conakry_kassa "
        "reste à créer.",
    ),
    "scission_2024": (
        "Pour représentation post-2024, créer 3 entités enfants en phase 2.",
        "Pour une représentation post-2024, 3 localités enfants restent à créer.",
    ),
    "anm_etiquette_labe": (
        "[v3 post-clôture phase 1-1D : intégration source ANM Guinée découverte hors "
        "mission de compilation, GF-7]. Wikidata Q1020384. Population",
        "Wikidata Q1020384. Population",
    ),
    "anm_etiquette_matoto": (
        "[v3 post-clôture phase 1-1D : intégration source ANM Guinée découverte hors "
        "mission de compilation, GF-7]. Périmètre des 5",
        "Périmètre des 5",
    ),
    "anm_consultation": (
        "ANM Guinée consulté le 2026-05-09 (post-clôture phase 1-1D, cf. tag début de note).",
        "ANM Guinée consulté le 2026-05-09.",
    ),
}

_DENSIF_COMMUNE = ("commune_chef_lieu", "densification")
_DENSIF_PREFECTURE = ("prefecture", "densification")

# code -> cles de SUBSTITUTIONS_LOCALITES appliquees, dans l'ordre.
LOCALITES: dict[str, tuple[str, ...]] = {
    "gin_labe": ("anm_etiquette_labe", "anm_consultation"),
    "gin_conakry_kaloum": ("conakry_perimetre", "kassa"),
    "gin_conakry_dixinn": ("conakry_perimetre",),
    "gin_conakry_matam": ("conakry_perimetre",),
    "gin_conakry_matoto": (
        "anm_etiquette_matoto",
        "conakry_perimetre",
        "scission_2024",
        "anm_consultation",
    ),
    "gin_conakry_ratoma": ("conakry_perimetre", "scission_2024"),
}
# Les 61 localites de la densification prefectorale (absentes de LOCALITES)
# recoivent _DENSIF_PREFECTURE (noeud ``*_prefecture``) ou _DENSIF_COMMUNE
# (commune chef-lieu). EMPREINTES_LOCALITES fixe la liste exacte des 67 codes.

# code -> (md5 du texte de depart, md5 du texte d'arrivee).
EMPREINTES_LOCALITES: dict[str, tuple[str, str]] = {
    "gin_beyla": ("54d1f098fb3f7f729944bf52d3ded7c5", "053b13fe6358dbe1b948518e00ba0acc"),
    "gin_beyla_prefecture": (
        "68290e8de5d961bd3b584d6326d4b021",
        "97c200835572f63c6fa85f48048ac944",
    ),
    "gin_boffa": ("53b0c4e46142affafeef37be7e7fb3c3", "aed0519445049109f9636cc6bb55f78c"),
    "gin_boffa_prefecture": (
        "15aa47695e551122ac5123299dd5fedc",
        "929ff656951046a996519ae5d9ee69f7",
    ),
    "gin_boke_centre": ("38bb997b391c2383066c27632cdaf6c9", "e070945cc4cd4225a9b2ed1b49e1ba2f"),
    "gin_boke_prefecture": ("be9d84c43bac6002735581371d330ed0", "544aa121ff276cbcdd097884932c5691"),
    "gin_conakry_dixinn": ("9413a9f8ea6baef2598f766ddc372001", "45f5047d32672862e3232f5f79c12028"),
    "gin_conakry_kaloum": ("31de59ecdfcd048241206735743098fc", "61a30f4f7419c5628a91a0fba93655e5"),
    "gin_conakry_matam": ("0bc0dcfef59f560e4de63e2e28288d3e", "eade2e2dbf5bcf0b4e3111d7f7bc9bf5"),
    "gin_conakry_matoto": ("dfa4e3bdd1cd914721f0e11bc6d5ea77", "299f3846d541951d7232adbd8daa554d"),
    "gin_conakry_ratoma": ("a76bdb2a8b97a3c051fabce36458c61a", "4006438739c4db2f95cd27fa1606447c"),
    "gin_coyah": ("1313518328396a171271c81aac647fc2", "36ed8ce75c113957874f86798140d845"),
    "gin_coyah_prefecture": (
        "47c2ca71bef4a76bf3d779f4093760d1",
        "82dadcb9d5ed191f29269012f56f86ae",
    ),
    "gin_dabola": ("f015e202d99d617508c95dc9439ff8e5", "227a2461761431395eaaec5f90463b51"),
    "gin_dabola_prefecture": (
        "09a83180ebe918d01d89398971ac53d5",
        "8c3550c780c24d6df9df73f896db1f42",
    ),
    "gin_dalaba": ("bb0da2d62aa8eb7eef0792a3642afe62", "8650f9eaa001961df20b9f89ddbb5138"),
    "gin_dalaba_prefecture": (
        "d87048224f656a789fe0b67e2d9a5827",
        "56de4fe3c92608bd4e55033f525bab1c",
    ),
    "gin_dinguiraye": ("41aafd5c363a2b5c7d50cc9581174942", "fdc739053306c8a75b254cd368b1aeaa"),
    "gin_dinguiraye_prefecture": (
        "843308c4d20d3d9eedb56b97b09e0248",
        "40512e47eb260cf36c17802e2a0d6eef",
    ),
    "gin_dubreka": ("e4868b62122f90938e41a2998c75778d", "5bdbe75716be5ed924c1b4f135eb4f02"),
    "gin_dubreka_prefecture": (
        "282bbc2d5aa73ff219de8c68988470b9",
        "9481b0d171fc0caee3a8c94ddc7fca20",
    ),
    "gin_faranah_centre": ("e2b533ed1d06f96d39b308395174fb95", "761e929f34cfcc5df28ee19203e166e7"),
    "gin_faranah_prefecture": (
        "ebc387d45ca303caa71d2af80407a0d5",
        "042c986fb03a80ad03b4de8c1f525341",
    ),
    "gin_forecariah": ("68ec8026b4c52563bf896620d8c50d4b", "cdbfad37561f330d4e6d6d1f35a91a81"),
    "gin_forecariah_prefecture": (
        "bda35a251a24fb310b3332e5318bc309",
        "3af4e8085a34b395e1a2120eba8aa393",
    ),
    "gin_fria": ("5982dd451094800c65da65c9e7f9320a", "20406b926c45bca84561f12a6d8b23d4"),
    "gin_fria_prefecture": ("6a25cfe5df644b5525c19476b4c8ec88", "bc67f2d846e0edcc754c93d4880faa04"),
    "gin_gaoual": ("1e3df3c0d48814e004b7f1e5ecc94ae9", "87b71dfa2383e59d0cc99aea4237dfb4"),
    "gin_gaoual_prefecture": (
        "fa9588ba4ca9529845e69754df5abe6a",
        "9c10f88d782a98122640c000b1aaf08b",
    ),
    "gin_gueckedou": ("c91081bd6b6ba13f31510bb5d596be06", "6ed95f1f48b22b8531012b4b22d18bd7"),
    "gin_gueckedou_prefecture": (
        "d7663e258f220e3833ddbcbdf1c078f2",
        "88d57519e9d41483929958badee00dfb",
    ),
    "gin_kankan_prefecture": (
        "79b5be9eeaa95a308728e14a2677939e",
        "ba4a60af29155d5923b94ac62fd3b163",
    ),
    "gin_kerouane": ("a63d5bea1f4f8c95e6caaf3a1856cefb", "bcda415152f4cd85be1fad0ec8599287"),
    "gin_kerouane_prefecture": (
        "0b91c03677e1bdb328bb4e19c1f5f4ef",
        "68dfb2672e2761330dd9137313c949bd",
    ),
    "gin_kindia_prefecture": (
        "de29eec5b3dc04890315301d4eb76d1a",
        "566a87970e743dca964ce9a0858815de",
    ),
    "gin_kissidougou": ("ec71b2d6d7d3c0623b08a0bd6f3787cd", "9ebef39a989bcaeca5b4879cc70b847f"),
    "gin_kissidougou_prefecture": (
        "002cd136b07aa88bfb27ee555b8d10a7",
        "308613594b3a896bebe3b12e076894bb",
    ),
    "gin_koubia": ("59cb0154d945cd39e0f659cb97aa4f90", "6f6bc487d5ae34849dd20f5ef1663ffb"),
    "gin_koubia_prefecture": (
        "5c7ce598e2e09bb2dc811e76655c48db",
        "04ef253fba462abe12dfddfc983882ea",
    ),
    "gin_koundara": ("9be253718a47105c044fdcf5bfcfe1a2", "91b6d3d2f6f2b9f9fefd69556dd4cc0c"),
    "gin_koundara_prefecture": (
        "9f5c37770d177e40ebbfb15182f9ab44",
        "c208fe79022e200cf03108322f2c74b4",
    ),
    "gin_kouroussa": ("c7936e6eabefaf55b892bdf39570d245", "26e52e410b6e02a37590986bc3d36bfa"),
    "gin_kouroussa_prefecture": (
        "3c89787d0d1349da8b349df8aef420cd",
        "82160cee0ebb751b28c45055ff392f03",
    ),
    "gin_labe": ("462d9f8d77d7715c4a9a0f74a0191ea9", "0740c002ae540e6299b8c81a2aa3e189"),
    "gin_labe_prefecture": ("5d71dbcaab9fd315ddf7ebf68d6c2f66", "61b680dcc46739b65cd01f71302c8d59"),
    "gin_lelouma": ("c4b14b98864a3d1eb9f83ffb7b7981ff", "1bdd29fea66f4e3d157559135359a008"),
    "gin_lelouma_prefecture": (
        "fc1f745a874b4401892d279e0106bb25",
        "abfc51ccd1d74170a7d87febfcc3b4cb",
    ),
    "gin_lola": ("601921b08606e40a1b4f46f9917777db", "efdab96d3aa02750fb45ea313f6ef494"),
    "gin_lola_prefecture": ("8485aac6c620d8eaa81a93682016f3b3", "aeacdde2078157c0a53e255df586829b"),
    "gin_macenta": ("f1f678a6c87159de05c7e5746188b8da", "6dfe5e5a2326362372fcad9436ded7a7"),
    "gin_macenta_prefecture": (
        "8412430d1aac3718352a56253e8ec0a2",
        "b3ab48b068ed0a5244ce99742a02a700",
    ),
    "gin_mali": ("761c209fcf58c27744434d4aee46ff11", "4711fcff67e5b49af349de47400e0cb5"),
    "gin_mali_prefecture": ("0a11227b27db2b931b56f4342c91764d", "04c49bcdc9e613dad924355d905fab7e"),
    "gin_mamou_prefecture": (
        "d08c7e7b5dfdafde55c3bfa19aa28a96",
        "fb0333a26a230a3f415a866e5efe37b8",
    ),
    "gin_mandiana": ("6a4c02c04722c64916a81eec33a5a7de", "63d7b0ecdbb519d750702eed264f86ff"),
    "gin_mandiana_prefecture": (
        "873d92b2d22ada648cebb99b26691521",
        "74984a8ae65490686c8967c65d9c389a",
    ),
    "gin_nzerekore_prefecture": (
        "2c91fec53a80304f949a7669d5dae018",
        "2917b0c5bd082416e1fbfeb91b85b449",
    ),
    "gin_pita": ("3e0393ad5d81777ebb2e042627475f81", "f0656cad4e5cb440d26bb39f8252abb4"),
    "gin_pita_prefecture": ("7e2a7f3121c84b5040fc5b6e9eb6f82c", "84fc0c34a4face6ef3651d590563d4b2"),
    "gin_siguiri": ("01d188d94d1092291ad1145644d9aa3f", "3954ee154cb92d1feb665eb73eabfcb7"),
    "gin_siguiri_prefecture": (
        "bf97b0b4a5cd88c2385f150e07bfb393",
        "0bc8ac97ce8f6d4d689e7da6c4d18d93",
    ),
    "gin_telimele": ("2f8d4d4c994bf3290deb44591380db4c", "7950a11129b01dd5c32f45c0e0737c05"),
    "gin_telimele_prefecture": (
        "734efb71d548883c5a8747a3d1bdbc4d",
        "a0a2adccf3e6d009514a2a852d0fac68",
    ),
    "gin_tougue": ("dab78ede218c4099c42e00d414222e3e", "ee852c66ecf8449bb9012a85f44d0cb9"),
    "gin_tougue_prefecture": (
        "48287f1a1a8bae1280aa954b3e68a17e",
        "4a05ccbfd36bdeba29f729fdfd295f6a",
    ),
    "gin_yomou": ("0a9dd16e22d6e6dc11344aedb779e0e2", "c928883bf6fa5e32dcd1507b73dcba13"),
    "gin_yomou_prefecture": (
        "a316047c789a3e26dc0fbc94d9aa5f21",
        "f29ce9f78cc6ef264a7006be8b1d20a4",
    ),
}


# === 3. sources.notes et sources.metadonnees ===============================

_HYDRO = "à l'activation du pipeline hydro"

NOTES_SOURCES: dict[str, tuple[Substitution, ...]] = {
    "anm_guinee_stations": (
        (
            "ont été recensées en mission 1-1D (mai 2026) lors d'une trouvaille "
            "post-clôture (cf. spec 1-1D, ANM 2 concordances actées : Labé station "
            "61809, Matoto station 61832 ;",
            "ont été recensées en mai 2026 (2 concordances actées avec les localités "
            "Kuma : Labé station 61809, Matoto station 61832 ;",
        ),
        (
            "Convention applicative phase 1-2b : exposer la traçabilité",
            "Convention applicative : exposer la traçabilité",
        ),
    ),
    "cams_radiation": (
        (
            "Vague 4 Lot B : DNI all-sky aérosol-corrigé (BNI), 3ᵉ référence d'écart "
            "inter-source (enjeu Harmattan).",
            "Usage Kuma : GHI, DNI et DHI journaliers et mensuels ; le DNI all-sky "
            "aérosol-corrigé (BNI) sert de 3ᵉ référence d'écart inter-source, après "
            "NASA POWER et SARAH-3 (enjeu Harmattan).",
        ),
    ),
    "ecmwf_era5": (
        (
            "Compatible solaire + climat (opérationnel phase 1) ; paramètres hydro "
            "(precipitation, évapotranspiration, runoff via ERA5-Land) conçus pour "
            "cross-check β2 mais non activés en phase 1 (cf. CdC § 4.1).",
            "Compatible solaire + climat ; paramètres hydro (precipitation, "
            "évapotranspiration, runoff via ERA5-Land) conçus pour cross-check β2 mais "
            "non activés (cf. CdC § 4.1). Aucune série Kuma n'est ingérée depuis cette "
            "source : les séries de réanalyse ECMWF de Kuma proviennent d'ERA5-Land "
            "(source `ecmwf_era5_land`).",
        ),
        (
            "single levels (DOI retenu, dataset pivot Kuma phase 1)",
            "single levels (DOI retenu, dataset pivot de la fiche)",
        ),
        (
            "Pour 1-1E, fiche pivot = single levels",
            "Fiche pivot = single levels",
        ),
        (
            ": non seedée dans la présente fiche. À acter potentiellement comme source "
            "distincte `ecmwf_era5_land` en future passe (passe complémentaire 1-1E ou "
            "phase 2+) pour appui spécifique sur le vecteur hydro β2 (DOI ERA5-Land "
            "monthly : 10.24381/cds.68d2bb30 ; cf. Muñoz Sabater 2019). Décision "
            "technique à acter (DT-X potentielle) si besoin avéré phase 2+. En 1-1E, "
            "périmètre source = ERA5 atmospheric reanalysis uniquement.",
            ": non couverte par la présente fiche ; elle fait l'objet de la source "
            "distincte `ecmwf_era5_land` (DOI ERA5-Land monthly : 10.24381/cds.68d2bb30 "
            "; cf. Muñoz Sabater 2019). Périmètre de la présente fiche = ERA5 "
            "atmospheric reanalysis uniquement.",
        ),
        (
            "À intégrer en convention applicative phase 1-2b pour",
            "À intégrer en convention applicative pour",
        ),
        (
            "il est multi-vecteurs et opérationnel phase 1 pour solaire + climat). "
            "L'usage hydro d'ERA5 est cependant conçu pour cross-check référentiel "
            "sans activation phase 1.",
            "il est multi-vecteurs, solaire + climat). L'usage hydro d'ERA5 est "
            "cependant conçu pour cross-check référentiel, sans activation.",
        ),
    ),
    "ecmwf_era5_land": (
        (
            "Vague 4 Lot A : co-localisation (D-29) et altitude (D-24) sur les 6 villes pilotes.",
            "Usage Kuma : pallier deux limites de NASA POWER, la co-localisation (des "
            "localités voisines partagent une même cellule CERES 1°, comme Kindia et "
            "Mamou, qu'ERA5-Land sépare géométriquement) et l'altitude (la grille "
            "MERRA-2 lisse le relief du Fouta-Djalon et sous-estime l'écart de "
            "température entre Labé et Conakry).",
        ),
    ),
    "esmap_wapp": (
        (
            "Source en appui de la couche confiance A (mesure sol) : terrain-lite GHI "
            "Lot A, premiere grandeur Kuma en confiance A via la regle R3.",
            "Source en appui de la couche confiance A (mesure sol) : series horaires "
            "terrain-lite GHI et DNI de Kankan (2021-2023), en confiance A via la "
            "regle R3 ; la serie GHI a ete la premiere grandeur Kuma en confiance A.",
        ),
    ),
    "iec_60041_1991": (
        (
            "Source hydro structurelle 3/4 du périmètre β2 phase 1 (les 3 autres",
            "Source hydro structurelle 3/4 du périmètre β2 (les 3 autres",
        ),
        (
            "À surveiller en passe d'activation phase 2+.",
            f"À surveiller {_HYDRO}.",
        ),
        (
            "(hors scope direct 1-1E, à mentionner pour traçabilité)",
            "(hors scope direct de la présente fiche, à mentionner pour traçabilité)",
        ),
        (
            "Si Kuma phase 2+ étend les calculs hydro",
            "Si Kuma étend ultérieurement les calculs hydro",
        ),
        (
            "Pertinence Kuma - convention applicative phase 2+ : norme directement",
            f"Pertinence Kuma - convention applicative {_HYDRO} : norme directement",
        ),
        (
            "Convention applicative à acter en spec préparatoire phase 2+. Accès",
            "Convention applicative à acter avant l'activation du pipeline hydro. Accès",
        ),
    ),
    "iec_61724_1_2021": (
        (
            "Norme opérationnelle phase 1 pour le vecteur solaire.",
            "Norme opérationnelle pour le vecteur solaire.",
        ),
        (
            "Convention applicative phase 1-2b : application des conventions",
            "Convention applicative : application des conventions",
        ),
        (
            "(norme solaire opérationnelle phase 1, hors liste",
            "(norme solaire opérationnelle, hors liste",
        ),
    ),
    "kuma_calculs": (
        (
            "(HEP en 1-5 ; futures grandeurs calculees Kuma en 1-6+). Auto-evaluation "
            "fiabilite='haute' coherente avec la doctrine editoriale phase 1 (Kuma "
            "engage son autorite editoriale sur la correction du calcul, cf. cadrage "
            "phase 1 Principe 1).",
            "(HEP et les autres grandeurs calculees par Kuma). Auto-evaluation "
            "fiabilite='haute' coherente avec la doctrine editoriale de Kuma (Kuma "
            "engage son autorite editoriale sur la correction du calcul).",
        ),
    ),
    "nasa_power": (
        (
            "valeur effective pour la communauté Kuma phase 1 = RE (Renewable Energy, "
            "focus solaire).",
            "valeur effective pour la communauté RE (Renewable Energy, focus solaire), "
            "retenue par Kuma pour ses requêtes NASA POWER.",
        ),
        (
            "SB (Sustainable Buildings). Convention de communauté Kuma à acter en spec "
            "préparatoire 1-2a. Méthodologie",
            "SB (Sustainable Buildings). Méthodologie",
        ),
        (
            "Cette exigence se traduira en convention applicative phase 1-2b pour",
            "Cette exigence est à traduire en convention applicative pour",
        ),
        (
            "(source primaire phase 1 du substrat physique guinéen, opérationnelle "
            "phase 1 pour solaire + climat,",
            "(source primaire du substrat physique guinéen, opérationnelle pour solaire + climat,",
        ),
    ),
    "sarah3_monthly": (
        (
            "Retenue en 1-7a comme source de reference inter-source pour "
            "ecart_relatif_referentiel (cf. note methodologique amont PR #53).",
            "Retenue comme source de reference inter-source pour "
            "ecart_relatif_referentiel (ecart mensuel du GHI entre NASA POWER et "
            "SARAH-3).",
        ),
    ),
    "wmo_168_2008": (
        (
            "Méta-norme métrologique hydrologique pour la phase 1 β2.",
            "Méta-norme métrologique hydrologique du périmètre β2.",
        ),
        (
            "Source hydro structurelle 4/4 et dernière du périmètre β2 phase 1.",
            "Source hydro structurelle 4/4 et dernière du périmètre β2.",
        ),
        (
            "le plus pertinent pour Kuma phase 1 (mesures hydrométriques",
            "le plus pertinent pour Kuma (mesures hydrométriques",
        ),
        (
            "Pertinence Kuma - convention applicative phase 2+ : norme méthodologique",
            f"Pertinence Kuma - convention applicative {_HYDRO} : norme méthodologique",
        ),
        (
            "Si Kuma calcule des grandeurs métier hydro phase 2+ (débit",
            "Si Kuma calcule ultérieurement des grandeurs métier hydro (débit",
        ),
        (
            "Convention applicative à acter en spec préparatoire phase 2+. GF-1",
            "Convention applicative à acter avant l'activation du pipeline hydro. GF-1",
        ),
        (
            "GF-4 fortement applicable au moment d'activation phase 2+ :",
            f"GF-4 fortement applicable {_HYDRO} :",
        ),
        (
            "(hors scope direct 1-1E) : Technical",
            "(hors scope direct de la présente fiche) : Technical",
        ),
        (
            "Si Kuma phase 2+ étend les pratiques",
            "Si Kuma étend ultérieurement les pratiques",
        ),
    ),
    "wmo_8_2024": (
        (
            "Méta-norme métrologique météo opérationnelle phase 1 (vecteur",
            "Méta-norme métrologique météo opérationnelle (vecteur",
        ),
        (
            "C'est le volume pertinent pour Kuma phase 1 (mesures météo de surface).",
            "C'est le volume pertinent pour Kuma (mesures météo de surface).",
        ),
        (
            "Convention applicative phase 1-2b : la citation canonique",
            "Convention applicative : la citation canonique",
        ),
        (
            "(méta-norme météo opérationnelle phase 1, hors liste",
            "(méta-norme météo opérationnelle, hors liste",
        ),
    ),
    "wmo_grdc": (
        (
            "rôle β2 phase 1 = référentiel uniquement, validation effective phase 2+. "
            "Source hydro structurelle 1/4 du périmètre β2 phase 1 (les 3 autres",
            f"rôle β2 = référentiel uniquement, validation effective {_HYDRO}. "
            "Source hydro structurelle 1/4 du périmètre β2 (les 3 autres",
        ),
        (
            "Cette exigence se traduira en convention applicative phase 2+ pour",
            "Cette exigence est à traduire en convention applicative pour",
        ),
        (
            "au moment de l'activation phase 2+ (le statut",
            "au moment de l'activation du pipeline hydro (le statut",
        ),
    ),
    "wwf_hydrosheds": (
        (
            "rôle β2 phase 1 = référentiel uniquement, validation effective phase 2+. "
            "Source hydro structurelle 2/4 du périmètre β2 phase 1 (les 3 autres",
            f"rôle β2 = référentiel uniquement, validation effective {_HYDRO}. "
            "Source hydro structurelle 2/4 du périmètre β2 (les 3 autres",
        ),
        (
            "Hors scope phase 1 mais pertinent pour Kuma futur si extension "
            "agro-écologie / plaines inondables / mangroves côtières guinéennes "
            "(sous-mission potentielle phase 2+, à acter si besoin avéré).",
            "Hors scope actuel mais pertinent pour Kuma futur si extension "
            "agro-écologie / plaines inondables / mangroves côtières guinéennes (à "
            "acter si besoin avéré).",
        ),
        (
            "v1.1 (version courante effective phase 1) -",
            "v1.1 (version courante effective) -",
        ),
        (
            "Pour Kuma phase 1, v1.1 reste pleinement opérationnel",
            "Pour Kuma, v1.1 reste pleinement opérationnel",
        ),
        (
            "Convention applicative phase 2+ : exposer la traçabilité",
            f"Convention applicative {_HYDRO} : exposer la traçabilité",
        ),
        (
            "Différé cohérent avec le statut β2 du vecteur hydro phase 1.",
            "Différé cohérent avec le statut β2 du vecteur hydro.",
        ),
        (
            "Cohérence à acter en passe d'ingestion phase 2+.",
            "Cohérence à acter lors de l'ingestion hydro.",
        ),
    ),
}

# code -> (md5 du texte de depart, md5 du texte d'arrivee).
EMPREINTES_NOTES_SOURCES: dict[str, tuple[str, str]] = {
    "anm_guinee_stations": ("43bf83c170e05254c4c1bd576cb167f7", "19c4989c957b488ac27c66c1c032626d"),
    "cams_radiation": ("1cd1f760878596741834e4cc1c84a737", "d18bb43b9081c7112b4e2d9ce69200e8"),
    "ecmwf_era5": ("a03133b86a2fab96cc3e9ad930321a3e", "84c5c355fdfe49c34c62f099dd214182"),
    "ecmwf_era5_land": ("e6a7f2d039b4382b913a9521f6de6468", "3d76e4eae700821805e770d1f84fa4f5"),
    "esmap_wapp": ("a4747adc7aec6b570316c0d0e9036089", "e11d13527dcf8b85bd55ce4cf8221c0e"),
    "iec_60041_1991": ("8b22204dcd86b9816579a7e7f158df00", "2196d6e22f3d4943988554384505df6a"),
    "iec_61724_1_2021": ("3525b6f12f3b0309e12a8d7f8a797021", "2a5944b86e10a0673bbc447ac60f7252"),
    "kuma_calculs": ("42638e27f61015a32417ac8692880a8f", "815f11aee8c58a3128e3637a61e2d3d4"),
    "nasa_power": ("c83e87eb4f35358107fd7efb2b976538", "b8d83a7e23a9c75b2d25715ee26a0fc5"),
    "sarah3_monthly": ("66be8fe3325fa763e9ce85c4c97bca3a", "f551547fe1d7a41861221873dab6a2d4"),
    "wmo_168_2008": ("b7b206fab935b8a0928dcb573b2914a2", "286533e4955df665990634e93809e8f5"),
    "wmo_8_2024": ("cc10fca7876217101edb7cc3cbf6d638", "e7fd466c68e4a2d24e5b01d630b056c9"),
    "wmo_grdc": ("72ea8f545a19631b84d674ce8dcf67cb", "6e993f94235e791e6c0c50cfd2f7f902"),
    "wwf_hydrosheds": ("3882428a8c0795d9359497a681e97d18", "29018d52e24063552be66ea689d716b6"),
}

# (code source, cle de premier niveau) -> (valeur texte de depart, d'arrivee).
METADONNEES_SOURCES: dict[tuple[str, str], tuple[str, str]] = {
    ("esmap_wapp", "grandeur_ingeree"): (
        "GHI (agrege horaire, terrain-lite Lot A)",
        "GHI et DNI (agreges horaires, terrain-lite)",
    ),
    ("iec_60041_1991", "edition_millesimee"): (
        "3.0 (1991-11-30) avec Corrigendum 1 (mars 1996) ; Stability date 2025 - date "
        "de revue planifiée par l'IEC, pas date de remplacement ; norme courante en "
        "vigueur à mai 2026 [À reverifier en passe 2 phase 2+ si une nouvelle édition "
        "a été publiée]",
        "3.0 (1991-11-30) avec Corrigendum 1 (mars 1996) ; Stability date 2025 - date "
        "de revue planifiée par l'IEC, pas date de remplacement ; norme courante en "
        "vigueur à mai 2026 [À reverifier si une nouvelle édition a été publiée]",
    ),
}


# === 4. referentiels_calage.provenance =====================================

CALAGE_CODE = "gin_kankan_ghi_calage_saisonnier"
CALAGE_LIGNES = 3
CALAGE_PROVENANCE: Substitution = (
    " Note docs/methodologie/calage-ghi-kankan-terrain-lite.md, script reproductible "
    "scripts/analyse_calage_ghi_kankan.py, biais saisonniers du recalcul mensuel de "
    "l'etude Tokounou (2026-07-17).",
    " Biais saisonniers du recalcul mensuel de l'etude Tokounou (2026-07-17) ; "
    "methode et script d'analyse reproductibles documentes par Kuma.",
)


# === Helpers ===============================================================


def _md5(texte: str) -> str:
    return hashlib.md5(texte.encode("utf-8")).hexdigest()


def _echec(message: str) -> RuntimeError:
    return RuntimeError(f"Migration 128 : {message} Abandon sans ecriture partielle.")


def _reecrire(
    texte: str, substitutions: Sequence[Substitution], *, sens: int, contexte: str
) -> str:
    """Applique les substitutions (sens 1) ou leur inverse en ordre inverse (sens 0).

    Chaque fragment de depart doit figurer exactement une fois avant son
    remplacement, et son fragment d'arrivee exactement une fois apres : la
    transformation est alors inversible a l'identique.
    """
    etapes = list(substitutions) if sens == 1 else [(b, a) for a, b in reversed(substitutions)]
    for depart, arrivee in etapes:
        if texte.count(depart) != 1:
            raise _echec(
                f"{contexte} : fragment {depart[:60]!r} attendu une fois, "
                f"trouve {texte.count(depart)} fois."
            )
        texte = texte.replace(depart, arrivee)
        if texte.count(arrivee) != 1:
            raise _echec(f"{contexte} : fragment {arrivee[:60]!r} non unique apres remplacement.")
    return texte


def _reecrire_ligne(
    *,
    table: str,
    colonne: str,
    code: str,
    substitutions: Sequence[Substitution],
    empreintes: tuple[str, str],
    sens: int,
) -> None:
    """Reecrit le texte d'une ligne (cle naturelle ``code``) sous gardes md5."""
    md5_depart, md5_arrivee = empreintes if sens == 1 else (empreintes[1], empreintes[0])
    contexte = f"{table}.{colonne} de {code!r}"
    bind = op.get_bind()
    lignes = bind.execute(
        sa.text(f"SELECT {colonne} FROM {table} WHERE code = :code"), {"code": code}
    ).all()
    if len(lignes) != 1 or lignes[0][0] is None:
        raise _echec(f"{contexte} : 1 ligne non nulle attendue, {len(lignes)} trouvee(s).")
    texte = str(lignes[0][0])
    if _md5(texte) != md5_depart:
        raise _echec(f"{contexte} : texte de depart different de l'etat attendu.")
    nouveau = _reecrire(texte, substitutions, sens=sens, contexte=contexte)
    if _md5(nouveau) != md5_arrivee:
        raise _echec(f"{contexte} : texte d'arrivee different de l'etat attendu.")
    resultat = bind.execute(
        sa.text(
            f"UPDATE {table} SET {colonne} = :nouveau "
            f"WHERE code = :code AND md5({colonne}) = :md5_depart"
        ),
        {"nouveau": nouveau, "code": code, "md5_depart": md5_depart},
    )
    if resultat.rowcount != 1:
        raise _echec(f"{contexte} : {resultat.rowcount} ligne(s) mise(s) a jour au lieu de 1.")


def _empreinte_degenerescence(fragment: str) -> tuple[int, str | None]:
    """(nombre, md5 agrege) des commentaires degenerescence_pixel contenant ``fragment``."""
    ligne = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT count(*) AS n,
                       md5(string_agg(commentaire_editorial, E'\\n'
                                      ORDER BY commentaire_editorial COLLATE "C")) AS h
                FROM grandeurs_metier
                WHERE grandeur_code = 'degenerescence_pixel'
                  AND strpos(commentaire_editorial, :f) > 0
                """
            ),
            {"f": fragment},
        )
        .one()
    )
    return int(ligne.n), ligne.h


def _degenerescence(*, sens: int) -> None:
    depart, arrivee = DEGENERESCENCE if sens == 1 else DEGENERESCENCE[::-1]
    md5_depart, md5_arrivee = (
        DEGENERESCENCE_EMPREINTES if sens == 1 else DEGENERESCENCE_EMPREINTES[::-1]
    )
    bind = op.get_bind()
    n, h = _empreinte_degenerescence(depart)
    if (n, h) != (DEGENERESCENCE_LIGNES, md5_depart):
        raise _echec(
            f"commentaires degenerescence_pixel : {DEGENERESCENCE_LIGNES} lignes d'etat "
            f"connu attendues, {n} trouvee(s) (empreinte {h})."
        )
    if _empreinte_degenerescence(arrivee)[0] != 0:
        raise _echec("commentaires degenerescence_pixel : etat d'arrivee deja present.")
    multiples = bind.execute(
        sa.text(
            """
            SELECT count(*) FROM grandeurs_metier
            WHERE grandeur_code = 'degenerescence_pixel'
              AND strpos(commentaire_editorial, :f) > 0
              AND length(commentaire_editorial) - length(replace(commentaire_editorial, :f, ''))
                  <> length(:f)
            """
        ),
        {"f": depart},
    ).scalar_one()
    if multiples:
        raise _echec(f"{multiples} commentaire(s) portent le fragment plusieurs fois.")
    resultat = bind.execute(
        sa.text(
            """
            UPDATE grandeurs_metier
            SET commentaire_editorial = replace(commentaire_editorial, :depart, :arrivee)
            WHERE grandeur_code = 'degenerescence_pixel'
              AND strpos(commentaire_editorial, :depart) > 0
            """
        ),
        {"depart": depart, "arrivee": arrivee},
    )
    if resultat.rowcount != DEGENERESCENCE_LIGNES:
        raise _echec(f"{resultat.rowcount} commentaire(s) degenerescence_pixel mis a jour.")
    if _empreinte_degenerescence(arrivee) != (DEGENERESCENCE_LIGNES, md5_arrivee):
        raise _echec("commentaires degenerescence_pixel : etat d'arrivee inattendu.")


def _substitutions_localite(code: str) -> tuple[Substitution, ...]:
    if code in LOCALITES:
        cles = LOCALITES[code]
    elif code.endswith("_prefecture"):
        cles = _DENSIF_PREFECTURE
    else:
        cles = _DENSIF_COMMUNE
    return tuple(SUBSTITUTIONS_LOCALITES[c] for c in cles)


def _metadonnee(*, code: str, cle: str, attendue: str, nouvelle: str) -> None:
    resultat = op.get_bind().execute(
        sa.text(
            """
            UPDATE sources
            SET metadonnees = jsonb_set(
                metadonnees, ARRAY[CAST(:cle AS text)], to_jsonb(CAST(:nouvelle AS text))
            )
            WHERE code = :code
              AND jsonb_typeof(metadonnees -> :cle) = 'string'
              AND metadonnees ->> :cle = :attendue
            """
        ),
        {"code": code, "cle": cle, "attendue": attendue, "nouvelle": nouvelle},
    )
    if resultat.rowcount != 1:
        raise _echec(
            f"metadonnees {cle!r} de {code!r} attendue dans son etat de depart exact, "
            f"{resultat.rowcount} ligne(s) mise(s) a jour au lieu de 1."
        )


def _calage(*, sens: int) -> None:
    depart, arrivee = CALAGE_PROVENANCE if sens == 1 else CALAGE_PROVENANCE[::-1]
    bind = op.get_bind()
    textes = (
        bind.execute(
            sa.text("SELECT provenance FROM referentiels_calage WHERE code = :code"),
            {"code": CALAGE_CODE},
        )
        .scalars()
        .all()
    )
    if len(textes) != CALAGE_LIGNES or any(t.count(depart) != 1 for t in textes):
        raise _echec(
            f"provenance de {CALAGE_CODE!r} : {CALAGE_LIGNES} lignes portant le fragment "
            "de depart une fois attendues."
        )
    resultat = bind.execute(
        sa.text(
            """
            UPDATE referentiels_calage
            SET provenance = replace(provenance, :depart, :arrivee)
            WHERE code = :code AND strpos(provenance, :depart) > 0
            """
        ),
        {"code": CALAGE_CODE, "depart": depart, "arrivee": arrivee},
    )
    if resultat.rowcount != CALAGE_LIGNES:
        raise _echec(
            f"provenance de {CALAGE_CODE!r} : {resultat.rowcount} ligne(s) mise(s) a jour."
        )


def _appliquer(*, sens: int) -> None:
    """``sens`` = 1 : (depart -> arrivee) ; ``sens`` = 0 : (arrivee -> depart)."""
    _degenerescence(sens=sens)

    for code in sorted(EMPREINTES_LOCALITES):
        _reecrire_ligne(
            table="localites",
            colonne="notes",
            code=code,
            substitutions=_substitutions_localite(code),
            empreintes=EMPREINTES_LOCALITES[code],
            sens=sens,
        )

    for code in sorted(NOTES_SOURCES):
        _reecrire_ligne(
            table="sources",
            colonne="notes",
            code=code,
            substitutions=NOTES_SOURCES[code],
            empreintes=EMPREINTES_NOTES_SOURCES[code],
            sens=sens,
        )

    for (code, cle), valeurs in sorted(METADONNEES_SOURCES.items()):
        attendue, nouvelle = valeurs if sens == 1 else valeurs[::-1]
        _metadonnee(code=code, cle=cle, attendue=attendue, nouvelle=nouvelle)

    _calage(sens=sens)


def upgrade() -> None:
    _appliquer(sens=1)


def downgrade() -> None:
    _appliquer(sens=0)
