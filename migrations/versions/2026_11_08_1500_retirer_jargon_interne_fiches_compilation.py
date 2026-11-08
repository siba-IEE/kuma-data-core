"""retirer_jargon_interne_fiches_compilation

Revision ID: 129
Revises: 128
Create Date: 2026-11-08 15:00:00.000000+00:00

Migration de coherence editoriale, sans DDL ni donnee mesuree. Suite des
migrations 127 et 128 : le motif ``JARGON_INTERNE`` (``tests/_jargon.py``) est
etendu au vocabulaire des fiches de compilation des sources et des localites,
et les textes publies qui le portaient sont reecrits en clair.

1. ``localites.notes`` (76 localites) : renvois au cahier des charges de la
   compilation (« CdC § 5.3 », « § 4.6 / E.15 », « § 4.8.2 », « Annexe B »,
   « v3.3 § 4.5 / § 4.7 ») remplaces par la regle qu'ils designent ; code de
   decision « (D7) » retire (la phrase dit deja la regle : demographie nulle,
   a sourcer de facon homogene) ; « verifiee par superviseur » et
   « migration 011 » remplaces par leur contenu ; etiquettes de suivi
   « [v2 corrigee post-audit ...] » retirees (Matam : historique de processus
   seul) ou reecrites en clair (Mamou : le fait sur le chiffre 93 304 est garde).
2. ``sources.notes`` (9 sources) : codes de decisions techniques (« DT-1 » ordre
   de tutelle des codes de source, « DT-7 » edition millesimee en metadonnees,
   « DT-8 » mention hydro structurelle normee, « DT-9 » ISBN natif IEC,
   « DT-X potentielle »), de garde-fous (« GF-1 » restriction d'acces a la source
   primaire, « GF-4 » veille d'edition), statut « β2 » du vecteur hydro (schema
   de validation concu, population differee), cahier des charges « CdC » et
   passes de compilation remplaces par leur contenu.
3. ``sources.metadonnees`` (3 valeurs texte de 2 sources, cles et types
   inchanges) : « en passe 2 » retire de « a confirmer en passe 2 ».
4. ``series_metadonnees.methode_collecte_doc`` et ``url_documentation`` (198
   lignes, colonnes publiees non masquees) : chemins du depot
   ``docs/methodologie/grandeurs/*.md`` remplaces par le lien du document dans
   le depot public (``https://github.com/siba-IEE/kuma-data-core``, AGPL). Le
   chemin ``rang_referentiel_temporel.md`` ne designait aucun fichier : la
   methode de cette grandeur est documentee dans
   ``docs/methodologie/referentiels-comparatifs-phase-1.md``, vise a la place.

Correction en place (UPDATE sous trigger d'audit ``kuma_log_audit()``), sans
nouvelle version : seul le texte change ; aucune autre colonne, ``modifie_le``
compris, n'est touchee (precedent migrations 100, 125 a 128).

Gardes : chaque ligne reecrite par fragments doit avoir l'empreinte md5 de son
texte de depart exact, chaque fragment doit y figurer une seule fois et le
texte d'arrivee doit avoir l'empreinte attendue ; chaque valeur de
``metadonnees`` et chaque chemin de ``series_metadonnees`` est attendu dans son
etat de depart exact, en nombre de lignes exact. Le downgrade applique les
memes transformations en sens inverse avec les memes gardes et restaure les
textes d'origine a l'identique. Aucun reseau.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "129"
down_revision: str | Sequence[str] | None = "128"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Substitution : (fragment de depart exact, fragment d'arrivee).
Substitution = tuple[str, str]


# === 1. localites.notes ====================================================

_D7: Substitution = ("Demographie NULL (D7) :", "Demographie NULL :")
_SUPERVISEUR: Substitution = (
    "verifiee par superviseur 2026-06-20)",
    "verifiee en relecture le 2026-06-20)",
)
_MIGRATION_011: Substitution = (
    "Chef-lieu deja ingere (migration 011, Wikidata",
    "Chef-lieu deja ingere (commune existante, Wikidata",
)
# Region : coordonnees du chef-lieu, pas du centroid (convention de la compilation).
_CDC_REGION: Substitution = (
    " - CdC § 5.3. Identiques",
    ", pas du centroid régional (convention Kuma). Identiques",
)
# Commune chef-lieu de region : la region porte les coordonnees de la commune.
_CDC_COMMUNE: Substitution = (
    "(CdC § 5.3).",
    "(la région porte les coordonnées de son chef-lieu).",
)
_CDC_BRUT: Substitution = (
    "NON retenu (CdC § 4.8.2).",
    "NON retenu (règle Kuma : RGPH-3 brut strict).",
)

# code -> substitutions appliquees, dans l'ordre. Les 61 localites de la
# densification prefectorale absentes de cette table recoivent (_D7,) seul ;
# EMPREINTES_LOCALITES fixe la liste exacte des codes reecrits.
LOCALITES: dict[str, tuple[Substitution, ...]] = {
    "gin_boke": ((" - convention CdC § 5.3.", " (convention Kuma)."),),
    "gin_conakry": (
        (
            "pas de ville chef-lieu distincte, CdC § 4.6 / E.15)",
            "pas de ville chef-lieu distincte)",
        ),
    ),
    "gin_conakry_kaloum": (
        (
            "Coordonnées identiques à gin_conakry (CdC § 4.6 / E.15).",
            "Coordonnées identiques à gin_conakry (la région-ville porte les coordonnées "
            "du centre administratif Kaloum).",
        ),
    ),
    "gin_conakry_matam": (
        ("(CdC § 4.8.2 RGPH-3 brut strict)", "(règle Kuma : RGPH-3 brut strict)"),
        (
            "Altitude 27 m (Mapcarta). [v2 corrigée post-audit superviseur : ajout mention "
            "modélisation pilote § 2.1 manquante du CSV v1 - leçon GF-6]. Source",
            "Altitude 27 m (Mapcarta). Source",
        ),
    ),
    "gin_faranah": (
        ("pas du centroid régional - CdC § 5.3.", "pas du centroid régional (convention Kuma)."),
    ),
    "gin_forecariah": (_SUPERVISEUR, _D7),
    "gin_forecariah_prefecture": (_SUPERVISEUR, _D7),
    "gin_kankan": (
        (
            "198 717 (CdC v3.3 § 4.5, valeur non corroborée",
            "198 717 (valeur du cahier des charges de la compilation, non corroborée",
        ),
        _CDC_COMMUNE,
        _CDC_BRUT,
        (
            "Altitude 381 m (CdC Annexe B + Kankan Airport 376 m)",
            "Altitude 381 m (cahier des charges de la compilation ; Kankan Airport 376 m)",
        ),
    ),
    "gin_kankan_prefecture": (_MIGRATION_011, _D7),
    "gin_kankan_region": (_CDC_REGION,),
    "gin_kindia": (_CDC_COMMUNE,),
    "gin_kindia_prefecture": (_MIGRATION_011, _D7),
    "gin_kindia_region": (_CDC_REGION,),
    "gin_labe": (
        _CDC_COMMUNE,
        (
            "Britannica 1 050 m, CdC v3.3 § 4.7 1 025 m)",
            "Britannica 1 050 m, cahier des charges de la compilation 1 025 m)",
        ),
    ),
    "gin_labe_prefecture": (_MIGRATION_011, _D7),
    "gin_labe_region": (_CDC_REGION,),
    "gin_lelouma": (_SUPERVISEUR, _D7),
    "gin_lelouma_prefecture": (_SUPERVISEUR, _D7),
    "gin_mamou": (
        (
            "[v2 corrigée post-audit : v1 retenait 93 304 = projection RGPH-3 à 2017 publiée "
            "dans Annuaire stat INS-Guinée 2016 (nov 2017), confondue avec brut à cause du "
            "breakdown homme/femme].",
            "Le chiffre 93 304 est une projection RGPH-3 à 2017 publiée dans l'Annuaire stat "
            "INS-Guinée 2016 (nov 2017), à ne pas confondre avec le brut malgré sa ventilation "
            "homme/femme ; une version antérieure de cette fiche l'avait retenu par erreur.",
        ),
        _CDC_COMMUNE,
    ),
    "gin_mamou_prefecture": (_MIGRATION_011, _D7),
    "gin_mamou_region": (_CDC_REGION,),
    "gin_nzerekore": (_CDC_COMMUNE,),
    "gin_nzerekore_prefecture": (_MIGRATION_011, _D7),
    "gin_nzerekore_region": (_CDC_REGION,),
}

# code -> (md5 du texte de depart, md5 du texte d'arrivee).
EMPREINTES_LOCALITES: dict[str, tuple[str, str]] = {
    "gin_beyla": ("053b13fe6358dbe1b948518e00ba0acc", "b2c686143f878a4a5a663d632fcb9f6b"),
    "gin_beyla_prefecture": (
        "97c200835572f63c6fa85f48048ac944",
        "c515a8b3c70bba9e3bb8ce702c0cb3b1",
    ),
    "gin_boffa": ("aed0519445049109f9636cc6bb55f78c", "ab02ba67d711ab9edcd92a1070c9cdcd"),
    "gin_boffa_prefecture": (
        "929ff656951046a996519ae5d9ee69f7",
        "1b00cf59d3a83074067045d83c781d52",
    ),
    "gin_boke": ("b8f9ccc2ede88ffa2f793199767e94d5", "a511268295024d5fff216c3a9b05e54f"),
    "gin_boke_centre": ("e070945cc4cd4225a9b2ed1b49e1ba2f", "ffd72ba4a314a2eedc1422a01947b260"),
    "gin_boke_prefecture": (
        "544aa121ff276cbcdd097884932c5691",
        "36737f4b6946421df6edf5dfa82dd274",
    ),
    "gin_conakry": ("82bf38ff1edbf25f0773cbd6324d306d", "b3ffbe23e6cb34b2f8e2e2367d5733b8"),
    "gin_conakry_kaloum": ("61a30f4f7419c5628a91a0fba93655e5", "0836c22cdddede4edf2230ee848a9d4a"),
    "gin_conakry_matam": ("eade2e2dbf5bcf0b4e3111d7f7bc9bf5", "16cda5228c360f429f09450f459cf46c"),
    "gin_coyah": ("36ed8ce75c113957874f86798140d845", "4b2ae3d90d594e5e9d9d8d92e1744d85"),
    "gin_coyah_prefecture": (
        "82dadcb9d5ed191f29269012f56f86ae",
        "4112b15743ffa765e27a6a2528a58690",
    ),
    "gin_dabola": ("227a2461761431395eaaec5f90463b51", "fc4cd61e0d173e75bf6833669f773e2e"),
    "gin_dabola_prefecture": (
        "8c3550c780c24d6df9df73f896db1f42",
        "26c1c7960c12344a268aab3e26d72f72",
    ),
    "gin_dalaba": ("8650f9eaa001961df20b9f89ddbb5138", "06e0889e86c4f414b7c6ffd95efdeea2"),
    "gin_dalaba_prefecture": (
        "56de4fe3c92608bd4e55033f525bab1c",
        "b72a110b0734663ad4ee0796a9fe6320",
    ),
    "gin_dinguiraye": ("fdc739053306c8a75b254cd368b1aeaa", "35e43f8dde59935640647c2b4f16cbb9"),
    "gin_dinguiraye_prefecture": (
        "40512e47eb260cf36c17802e2a0d6eef",
        "c03d2d87aeb914eceab64cd39b69225e",
    ),
    "gin_dubreka": ("5bdbe75716be5ed924c1b4f135eb4f02", "00671742e0b9e3992b5e1dca4344cdae"),
    "gin_dubreka_prefecture": (
        "9481b0d171fc0caee3a8c94ddc7fca20",
        "58fc5f27b39eb50fd766da990b940098",
    ),
    "gin_faranah": ("d22ab1a570931f2e711dc04c7229dbaf", "6f6f3a74f2dc4133c68aab554955fef3"),
    "gin_faranah_centre": ("761e929f34cfcc5df28ee19203e166e7", "b7d6226989469e23ae42ad650534b194"),
    "gin_faranah_prefecture": (
        "042c986fb03a80ad03b4de8c1f525341",
        "2e95dc333d4c13529085490775277da1",
    ),
    "gin_forecariah": ("cdbfad37561f330d4e6d6d1f35a91a81", "1b19b926d7145cdb8e251fdce0bea620"),
    "gin_forecariah_prefecture": (
        "3af4e8085a34b395e1a2120eba8aa393",
        "b58c1b484d31900186e5ff31f33eb73a",
    ),
    "gin_fria": ("20406b926c45bca84561f12a6d8b23d4", "d8ffe88670308bef3fbe52973d7e204b"),
    "gin_fria_prefecture": (
        "bc67f2d846e0edcc754c93d4880faa04",
        "077adc9b315d25926d7d3926ad8970b9",
    ),
    "gin_gaoual": ("87b71dfa2383e59d0cc99aea4237dfb4", "e4160a512fac664e7913697bb9146563"),
    "gin_gaoual_prefecture": (
        "9c10f88d782a98122640c000b1aaf08b",
        "c84c4f747e492f2b653c370931214f93",
    ),
    "gin_gueckedou": ("6ed95f1f48b22b8531012b4b22d18bd7", "fbda44693cde4f682334d1d9c7fbe23b"),
    "gin_gueckedou_prefecture": (
        "88d57519e9d41483929958badee00dfb",
        "96a7ad01e7bf530bf52917875644ab57",
    ),
    "gin_kankan": ("15cb34d17d8cc82a07f7ea49fa0ebb4a", "1f6978ecc652b54355c6040f3cb0afc1"),
    "gin_kankan_prefecture": (
        "ba4a60af29155d5923b94ac62fd3b163",
        "1084932420b9ff84d2e58bfe4a21dcc9",
    ),
    "gin_kankan_region": ("1ffad3f56e203780ecb30f7c76301d82", "9ab0e5bdd39217b3911923d4371314d1"),
    "gin_kerouane": ("bcda415152f4cd85be1fad0ec8599287", "11560b9c75b63985d2ed4014b84e7fb5"),
    "gin_kerouane_prefecture": (
        "68dfb2672e2761330dd9137313c949bd",
        "7dac1f69038a85ad8b3cecf31c44327c",
    ),
    "gin_kindia": ("877dd534d05409971e5fc55b471a4df8", "178b5dc155c6cd7dfc770d8b65ee5d94"),
    "gin_kindia_prefecture": (
        "566a87970e743dca964ce9a0858815de",
        "5fc2bdd7282e77edad11265f497f4acd",
    ),
    "gin_kindia_region": ("dbeb1aea1a02c74fc8b67aaece5c2217", "32416579530e597422da864f58685c81"),
    "gin_kissidougou": ("9ebef39a989bcaeca5b4879cc70b847f", "644f9840183347dd50539c2b43805c69"),
    "gin_kissidougou_prefecture": (
        "308613594b3a896bebe3b12e076894bb",
        "4be3c6166dbad667231b689c16204273",
    ),
    "gin_koubia": ("6f6bc487d5ae34849dd20f5ef1663ffb", "80a91513ad0f63667fd6a600055b2314"),
    "gin_koubia_prefecture": (
        "04ef253fba462abe12dfddfc983882ea",
        "cab8e8e7f9fd3f69b9a2f83b84a65f77",
    ),
    "gin_koundara": ("91b6d3d2f6f2b9f9fefd69556dd4cc0c", "8160decc81a9ba3127e4ebafc9fb43b1"),
    "gin_koundara_prefecture": (
        "c208fe79022e200cf03108322f2c74b4",
        "97f93a2f46d471f03238244eff6f9922",
    ),
    "gin_kouroussa": ("26e52e410b6e02a37590986bc3d36bfa", "05d91a4d53fa270495e6f0f7cffc2f38"),
    "gin_kouroussa_prefecture": (
        "82160cee0ebb751b28c45055ff392f03",
        "6ae6cdf78fd7cf99e9f4065cdb3d9a6b",
    ),
    "gin_labe": ("0740c002ae540e6299b8c81a2aa3e189", "047d1c0e343b0cebce7440f1d1395034"),
    "gin_labe_prefecture": (
        "61b680dcc46739b65cd01f71302c8d59",
        "24386fd032a4687921a4881ef2fbbbf7",
    ),
    "gin_labe_region": ("f8abcac49424ab62d4a7ca9f209e2fef", "55b70006e14df687c4ddb3fb20a015ca"),
    "gin_lelouma": ("1bdd29fea66f4e3d157559135359a008", "fc196d8550ea2d8c792962c42ad34b37"),
    "gin_lelouma_prefecture": (
        "abfc51ccd1d74170a7d87febfcc3b4cb",
        "8a6bea317fd0bf87f430d9794b1459c2",
    ),
    "gin_lola": ("efdab96d3aa02750fb45ea313f6ef494", "0ec783dc9d3bad4138b53a91f741c010"),
    "gin_lola_prefecture": (
        "aeacdde2078157c0a53e255df586829b",
        "e10af2045c14d10467393985b3c7418e",
    ),
    "gin_macenta": ("6dfe5e5a2326362372fcad9436ded7a7", "a5caea402ebbc09b22d6d61412fd7191"),
    "gin_macenta_prefecture": (
        "b3ab48b068ed0a5244ce99742a02a700",
        "f1cb2ea954c3d17d40e76dab08c7b7c3",
    ),
    "gin_mali": ("4711fcff67e5b49af349de47400e0cb5", "5e82f51de1f19adf95dce00ecb8946b9"),
    "gin_mali_prefecture": (
        "04c49bcdc9e613dad924355d905fab7e",
        "4dc0acd721ca3e20e70c8628a09b6586",
    ),
    "gin_mamou": ("6b52538589a04117ecd8cef7ceade5d3", "3ace641d406c38f3cd46cff847737941"),
    "gin_mamou_prefecture": (
        "fb0333a26a230a3f415a866e5efe37b8",
        "e1510396c62c3dbaa76e342fb7f5c2e4",
    ),
    "gin_mamou_region": ("d4fcecf666f35dc4bc23476b83e07609", "dbb1406cae598b2e3f0483fd41457245"),
    "gin_mandiana": ("63d7b0ecdbb519d750702eed264f86ff", "1efa28bfa85a8d93e86ca32d052cc328"),
    "gin_mandiana_prefecture": (
        "74984a8ae65490686c8967c65d9c389a",
        "72f67c640d07826cfa5ddaa941041295",
    ),
    "gin_nzerekore": ("11a019ed1f432193d602942ef378cfb4", "b5fb663394b45c5de170e2fdcd39c7a1"),
    "gin_nzerekore_prefecture": (
        "2917b0c5bd082416e1fbfeb91b85b449",
        "e6068f36121f00ab33b2a47cd61f1d11",
    ),
    "gin_nzerekore_region": (
        "efd5ac7df1fb3604261aa1543375a773",
        "fda5b97ef5c5a6b152c8c3fccba7ffeb",
    ),
    "gin_pita": ("f0656cad4e5cb440d26bb39f8252abb4", "be74f8af265d8519b9f6ad363608ace4"),
    "gin_pita_prefecture": (
        "84fc0c34a4face6ef3651d590563d4b2",
        "ee590f77a9baf3f60990676e854de7db",
    ),
    "gin_siguiri": ("3954ee154cb92d1feb665eb73eabfcb7", "98fed6868c919653f097ce9f5488a13f"),
    "gin_siguiri_prefecture": (
        "0bc8ac97ce8f6d4d689e7da6c4d18d93",
        "5ebaa2534e1b81e41da0f8c52a9d682b",
    ),
    "gin_telimele": ("7950a11129b01dd5c32f45c0e0737c05", "42eb576b29c94d624350c1e10dda8680"),
    "gin_telimele_prefecture": (
        "a0a2adccf3e6d009514a2a852d0fac68",
        "fe7fec05404fa93b3170a30896aa40aa",
    ),
    "gin_tougue": ("ee852c66ecf8449bb9012a85f44d0cb9", "176fad3af52655a12dabe7353f2c8ae1"),
    "gin_tougue_prefecture": (
        "4a05ccbfd36bdeba29f729fdfd295f6a",
        "6916fef5b1e59a39edb7fa6b10e7091b",
    ),
    "gin_yomou": ("c928883bf6fa5e32dcd1507b73dcba13", "3f35e7b221b8ec1c137e762b31692a9b"),
    "gin_yomou_prefecture": (
        "f29ce9f78cc6ef264a7006be8b1d20a4",
        "6ab4093a4e944fd7b891d0d1fe9a23b1",
    ),
}


# === 2. sources.notes ======================================================

# DT-1 (docs/methodologie/conventions-transverses.md, « Ordre de tutelle dans
# le code des sources ») : tutelle internationale si elle existe, sinon
# producteur scientifique ou administratif national.
_DT1: Substitution = ("Convention de code DT-1 :", "Convention de code (ordre de tutelle) :")
_DT1_ORDRE: Substitution = (
    "l'ordre DT-1 : tutelle internationale",
    "l'ordre de tutelle des codes Kuma : tutelle internationale",
)
# DT-8 : la mention normee « Source de reference structurelle (hydrologie) »
# (constante _MENTION_BETA2_NORMEE du seed des sources) propre aux 4 sources hydro.
_DT8: Substitution = (
    "Pas de mention β2 normée DT-8 (",
    "Pas de mention hydro structurelle normée (",
)
_BETA2_ROLE: Substitution = (
    "rôle β2 = référentiel uniquement",
    "rôle hydro = référentiel uniquement",
)


def _perimetre(rang: str) -> Substitution:
    return (
        f"Source hydro structurelle {rang} du périmètre β2",
        f"Source hydro structurelle {rang} du périmètre hydro structurel",
    )


NOTES_SOURCES: dict[str, tuple[Substitution, ...]] = {
    "anm_guinee_stations": (
        _DT1,
        (
            "distinction conforme au principe DT-1 qui privilégie",
            "distinction conforme à l'ordre de tutelle des codes, qui privilégie",
        ),
        (
            "GF-1 fortement applicable : pas d'API publique",
            "Accès à la source primaire fortement restreint : pas d'API publique",
        ),
        ("À évaluer en passe de contact officiel.", "À évaluer lors du contact officiel."),
        (
            "Dettes éditoriales projet (à résoudre",
            "Points éditoriaux ouverts (à résoudre",
        ),
        _DT8,
        (
            "si une mission hydro β2 future nécessite",
            "si une mission hydro future nécessite",
        ),
        ("à acter en future passe.", "à acter le moment venu."),
    ),
    "ecmwf_era5": (
        (
            "conçus pour cross-check β2 mais non activés (cf. CdC § 4.1).",
            "conçus pour un cross-check hydro mais non activés (le pipeline hydro n'est pas "
            "encore actif).",
        ),
        _DT1,
        _DT1_ORDRE,
        _DT8,
    ),
    "iec_60041_1991": (
        _perimetre("3/4"),
        ("(datation à confirmer en passe 2)", "(datation à confirmer)"),
        _DT1,
        ("hors périmètre source IEC cf. DT-9 du CdC v2.2)", "hors périmètre source IEC)"),
        (
            "ces normes pourraient mériter des fiches dédiées (DT-X potentielle).",
            "ces normes pourraient mériter des fiches dédiées.",
        ),
        (
            "GF-1 fortement applicable : texte intégral payant",
            "Accès à la source primaire fortement restreint : texte intégral payant",
        ),
    ),
    "iec_61724_1_2021": (
        _DT1,
        (
            "Convention transverse normes éditées initialisée par cette fiche (1ère "
            "occurrence), confirmée sur les 3 normes éditées suivantes de la passe",
            "Même convention appliquée aux 3 autres normes éditées",
        ),
        (
            "Cohérent avec DT-7 où metadonnees->>'edition_millesimee' peut",
            "Cohérent avec la convention Kuma selon laquelle metadonnees->>'edition_millesimee' "
            "peut",
        ),
        (
            "sortent du périmètre source IEC (cf. DT-9 du CdC v2.2).",
            "sortent du périmètre source IEC.",
        ),
        (
            "GF-1 applicable : source primaire (texte intégral) inatteignable sans achat",
            "Accès à la source primaire restreint : texte intégral inatteignable sans achat",
        ),
        _DT8,
    ),
    "nasa_power": (_DT1, _DT8),
    "wmo_168_2008": (
        (
            "Méta-norme métrologique hydrologique du périmètre β2.",
            "Méta-norme métrologique hydrologique du périmètre hydro structurel.",
        ),
        _perimetre("4/4 et dernière"),
        (
            "gestion ressources en eau (DT-X potentielle).",
            "gestion ressources en eau.",
        ),
        _DT1,
        (
            "Pattern parfaitement stable sur toute la passe :",
            "Pattern stable sur l'ensemble des sources compilées :",
        ),
        (
            "GF-1 non applicable (accès libre direct via library.wmo.int).",
            "Aucune restriction d'accès à la source primaire (accès libre direct via "
            "library.wmo.int).",
        ),
        (
            "GF-4 fortement applicable à l'activation du pipeline hydro : surveiller la "
            "publication de la 7ème édition (drift CdC futur potentiel similaire à `wmo_8_2024`).",
            "Veille d'édition fortement recommandée à l'activation du pipeline hydro : "
            "surveiller la publication de la 7ème édition (le code millésimé changerait alors, "
            "comme pour `wmo_8_2024`).",
        ),
        (
            "ces manuels pourraient mériter des fiches dédiées (DT-X potentielle).",
            "ces manuels pourraient mériter des fiches dédiées.",
        ),
    ),
    "wmo_8_2024": (
        (
            "créer une fiche dédiée avec ses identifiants propres (DT-X potentielle).",
            "créer une fiche dédiée avec ses identifiants propres.",
        ),
        _DT1,
        ("Aucun GF-1 applicable.", "Aucune restriction d'accès à la source primaire."),
        (
            "première source structurelle de la passe disposant",
            "première source structurelle compilée par Kuma (mai 2026) disposant",
        ),
        (
            "Drift par rapport au CdC § 2.2 : le CdC énumère le code `wmo_8_2023` (provisoire "
            "à la date de cadrage initial mai 2026). L'édition publiée effective est 2024. Code "
            "corrigé en `wmo_8_2024` dans la présente fiche. Amendement CdC § 2.2 acté en passe "
            "consolidation post-compilation. Aucun impact doctrinal - seul le millésime du code "
            "change, l'identité de la source et son rôle dans la cartographie § 4.2 sont "
            "inchangés.",
            "Le code prévu au départ, `wmo_8_2023` (provisoire en mai 2026), a été corrigé en "
            "`wmo_8_2024` : l'édition publiée effective est 2024. Seul le millésime du code "
            "change ; l'identité de la source et son rôle sont inchangés.",
        ),
        _DT8,
    ),
    "wmo_grdc": (
        _BETA2_ROLE,
        _perimetre("1/4"),
        _DT1,
        _DT1_ORDRE,
        (
            "GF-1 modéré : pas de paywall financier",
            "Accès à la source primaire modérément restreint : pas de paywall financier",
        ),
        (
            "GF-4 non applicable : pas de millésime éditorial",
            "Pas de veille d'édition nécessaire : pas de millésime éditorial",
        ),
    ),
    "wwf_hydrosheds": (
        _BETA2_ROLE,
        _perimetre("2/4"),
        (
            "un amendement de fiche en passe ultérieure si",
            "un amendement de fiche si",
        ),
        _DT1,
        ("au sens strict de DT-1)", "au sens strict de l'ordre de tutelle des codes)"),
        ("[DOI à confirmer en passe 2]", "[DOI à confirmer]"),
        (
            "Différé cohérent avec le statut β2 du vecteur hydro.",
            "Différé cohérent avec le statut du vecteur hydro (schéma de validation conçu, "
            "population différée).",
        ),
        (
            "GF-1 non applicable (accès libre direct via portail). GF-4 non applicable au code",
            "Aucune restriction d'accès à la source primaire (accès libre direct via portail). "
            "Veille d'édition sans objet pour le code",
        ),
        ("(v1.1 actuel à confirmer en passe 2)", "(v1.1 actuel à confirmer)"),
    ),
}

# code -> (md5 du texte de depart, md5 du texte d'arrivee).
EMPREINTES_NOTES_SOURCES: dict[str, tuple[str, str]] = {
    "anm_guinee_stations": (
        "19c4989c957b488ac27c66c1c032626d",
        "bb1b1b4c04ba7e3d393e12d6210dc323",
    ),
    "ecmwf_era5": ("84c5c355fdfe49c34c62f099dd214182", "963399b886939faef505fc2e0f1bcc08"),
    "iec_60041_1991": ("2196d6e22f3d4943988554384505df6a", "616e273f8b8b940532a1b6fda39aa2ac"),
    "iec_61724_1_2021": ("2a5944b86e10a0673bbc447ac60f7252", "1e05599babfaa04c1c02c16fa653cc64"),
    "nasa_power": ("b8d83a7e23a9c75b2d25715ee26a0fc5", "eb068bf16381d603875c1f97ded6f78e"),
    "wmo_168_2008": ("286533e4955df665990634e93809e8f5", "3a208f7fdff23cd8e9ae1220882ddd5c"),
    "wmo_8_2024": ("e7fd466c68e4a2d24e5b01d630b056c9", "bac75a1bfa7de69408d1aee3f21d50d7"),
    "wmo_grdc": ("6e993f94235e791e6c0c50cfd2f7f902", "d0cf25e50f408d6de133925c5ff656a5"),
    "wwf_hydrosheds": ("29018d52e24063552be66ea689d716b6", "d9f2aa20e34b67e600b544d310829b17"),
}


# === 3. sources.metadonnees ================================================

# (code source, cle de premier niveau) -> (valeur texte de depart, d'arrivee).
METADONNEES_SOURCES: dict[tuple[str, str], tuple[str, str]] = {
    ("wmo_8_2024", "edition_millesimee"): (
        "2024 edition (digital, 601 pages - chiffre attribué au Volume I, à reconfirmer en "
        "passe 2 ; 5 volumes depuis 2018, scope fiche = Volume I)",
        "2024 edition (digital, 601 pages - chiffre attribué au Volume I, à reconfirmer ; 5 "
        "volumes depuis 2018, scope fiche = Volume I)",
    ),
    ("wmo_grdc", "couverture_temporelle_debut"): (
        "1807 (la plus ancienne série en service est dans le bassin de la mer Baltique, selon "
        "paper BALTEX dataset Frontiers 2025 ; pays exact à confirmer en passe 2) ; couverture "
        "Guinée à confirmer en passe 2 (cf. notes)",
        "1807 (la plus ancienne série en service est dans le bassin de la mer Baltique, selon "
        "paper BALTEX dataset Frontiers 2025 ; pays exact à confirmer) ; couverture Guinée à "
        "confirmer (cf. notes)",
    ),
    ("wmo_grdc", "granularite_spatiale"): (
        "ponctuelle (gauging stations) ; > 11 000 stations à décembre 2025 (10 836 en janvier "
        "2025, croissance soutenue avec 1772 stations mises à jour en 2024) ; 43 pays ont "
        "contribué en 2025, 44 en 2024 selon GRDC reviews ; durée moyenne par station 40 ans "
        "selon historique GRDC ; en Guinée stations attendues sur Niger, Sénégal, Gambie, "
        "Konkouré. Détails complémentaires (nombre cumulé exact de pays contributeurs, durée "
        "moyenne précise, stations Guinée) à confirmer en passe 2 via database statistics "
        "GRDC ; cf. notes.",
        "ponctuelle (gauging stations) ; > 11 000 stations à décembre 2025 (10 836 en janvier "
        "2025, croissance soutenue avec 1772 stations mises à jour en 2024) ; 43 pays ont "
        "contribué en 2025, 44 en 2024 selon GRDC reviews ; durée moyenne par station 40 ans "
        "selon historique GRDC ; en Guinée stations attendues sur Niger, Sénégal, Gambie, "
        "Konkouré. Détails complémentaires (nombre cumulé exact de pays contributeurs, durée "
        "moyenne précise, stations Guinée) à confirmer via database statistics GRDC ; cf. "
        "notes.",
    ),
}


# === 4. series_metadonnees.methode_collecte_doc / url_documentation ========

_DEPOT_PUBLIC = "https://github.com/siba-IEE/kuma-data-core/blob/main/"

# chemin du depot -> (lien du depot public, nombre de lignes portant le chemin
# dans les deux colonnes a la fois).
DOCUMENTATION_SERIES: dict[str, tuple[str, int]] = {
    "docs/methodologie/grandeurs/fraction_diffuse.md": (
        _DEPOT_PUBLIC + "docs/methodologie/grandeurs/fraction_diffuse.md",
        34,
    ),
    "docs/methodologie/grandeurs/hep.md": (
        _DEPOT_PUBLIC + "docs/methodologie/grandeurs/hep.md",
        34,
    ),
    "docs/methodologie/grandeurs/humidex.md": (
        _DEPOT_PUBLIC + "docs/methodologie/grandeurs/humidex.md",
        34,
    ),
    "docs/methodologie/grandeurs/productible_specifique_theorique.md": (
        _DEPOT_PUBLIC + "docs/methodologie/grandeurs/productible_specifique_theorique.md",
        34,
    ),
    # Aucun fichier a ce chemin : la methode est dans la note des referentiels comparatifs.
    "docs/methodologie/grandeurs/rang_referentiel_temporel.md": (
        _DEPOT_PUBLIC + "docs/methodologie/referentiels-comparatifs-phase-1.md",
        28,
    ),
    "docs/methodologie/grandeurs/variabilite_journaliere.md": (
        _DEPOT_PUBLIC + "docs/methodologie/grandeurs/variabilite_journaliere.md",
        34,
    ),
}


# === Helpers ===============================================================


def _md5(texte: str) -> str:
    return hashlib.md5(texte.encode("utf-8")).hexdigest()


def _echec(message: str) -> RuntimeError:
    return RuntimeError(f"Migration 129 : {message} Abandon sans ecriture partielle.")


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


def _substitutions_localite(code: str) -> tuple[Substitution, ...]:
    return LOCALITES.get(code, (_D7,))


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


def _documentation(*, depart: str, arrivee: str, lignes: int) -> None:
    """Remplace ``depart`` par ``arrivee`` dans les deux colonnes de documentation."""
    bind = op.get_bind()
    n_depart, n_partiel, n_arrivee = bind.execute(
        sa.text(
            """
            SELECT
              count(*) FILTER (WHERE methode_collecte_doc = :d AND url_documentation = :d),
              count(*) FILTER (WHERE (methode_collecte_doc = :d) <> (url_documentation = :d)),
              count(*) FILTER (WHERE methode_collecte_doc = :a OR url_documentation = :a)
            FROM series_metadonnees
            """
        ),
        {"d": depart, "a": arrivee},
    ).one()
    if (n_depart, n_partiel, n_arrivee) != (lignes, 0, 0):
        raise _echec(
            f"series_metadonnees {depart!r} : {lignes} lignes portant ce texte dans les deux "
            f"colonnes et aucune portant {arrivee!r} attendues ; trouve {n_depart} (dont "
            f"{n_partiel} partielles) et {n_arrivee}."
        )
    resultat = bind.execute(
        sa.text(
            """
            UPDATE series_metadonnees
            SET methode_collecte_doc = :a, url_documentation = :a
            WHERE methode_collecte_doc = :d AND url_documentation = :d
            """
        ),
        {"d": depart, "a": arrivee},
    )
    if resultat.rowcount != lignes:
        raise _echec(
            f"series_metadonnees {depart!r} : {resultat.rowcount} ligne(s) mise(s) a jour."
        )


def _appliquer(*, sens: int) -> None:
    """``sens`` = 1 : (depart -> arrivee) ; ``sens`` = 0 : (arrivee -> depart)."""
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

    for chemin, (lien, lignes) in sorted(DOCUMENTATION_SERIES.items()):
        depart, arrivee = (chemin, lien) if sens == 1 else (lien, chemin)
        _documentation(depart=depart, arrivee=arrivee, lignes=lignes)


def upgrade() -> None:
    _appliquer(sens=1)


def downgrade() -> None:
    _appliquer(sens=0)
