"""SQL de lecture de la base, servi aux routes de l'API.

La couche ignore HTTP et les schémas de réponse : une lecture qui ne trouve
rien rend ``None`` ou une liste vide, et l'appelant décide de la suite.
"""
