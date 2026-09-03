"""
core -- Le moteur partage de l'agent.
Ce package contient TOUTE la logique metier. Les deux points d'entree du
projet (cli.py et web.py) ne font que l'appeler : ils ne contiennent aucune
regle de decision. C'est ce qui permet de livrer les deux formats demandes
(script + console web) sans ecrire la logique deux fois.
"""
__version__ = "1.0.0"
