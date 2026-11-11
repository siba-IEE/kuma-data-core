"""Émetteur de capsule (fichier Kuma) : la ressource que consomme le moteur mini-réseau.

Un seul assembleur pour deux fonctionnements : la capsule hors-ligne est
brute (sans calage), la ressource en ligne embarque les facteurs de calage.
L'assemblage (``arithmetique``, ``assembleur``, ``fichier_kuma``) est séparé
de l'accès aux données (``acquisition``, ``client_calage``).
"""
