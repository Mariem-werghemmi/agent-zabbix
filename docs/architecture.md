# Architecture
## Vue d'ensemble
L'agent est déployé sur une **VM séparée** du serveur Zabbix. Il dialogue avec
Zabbix uniquement via l'API JSON-RPC, avec un jeton à droits restreints. Un
**moteur unique** (`core/`) est partagé par la ligne de commande, la console web
et l'outil d'évaluation.
```
VM 1 — Zabbix                              VM 2 — Agent IA
┌────────────────────┐              ┌────────────────────────────────┐
│ Serveur Zabbix 7.0  │ API JSON-RPC │ Moteur core/    (boucle ReAct) │
│ api_jsonrpc.php     │◀──────────────▶│ Pensée → Action → Observation│
│                     │ jeton restreint│ ├─ 5 outils (zabbix_utils)   │
└────────────────────┘                 │ ├─ garde-fous (dry-run,      │
                                       │ │ seuil, escalade défaut)    │
                                       │ └─ décision →SQLite (journal)│
                                       |                              │
                                       │ Interfaces : cli.py · web.py │
                                       │                · evaluate.py │
                                       │ LLM interchangeable (.env) ──┼──▶ Groq / local
                                       │ Notification e-mail (SMTP)   │
                                      └────────────────────────────────┘
                                       systemd : agent-watch · agent-web
```
## La boucle ReAct (cœur du système)
```
Pensée : que dois-je vérifier ?
Action : appeler un outil Zabbix
Observation : lire le résultat
↺ (répété jusqu'à la décision, nombre d'étapes borné)
Décision : acquitter OU escalader
```
## Les 5 outils
| Outil | Type | Rôle |
|---|---|---|
| `get_active_problems` | lecture | lister les alertes actives |
| `get_host_context` | lecture | vérifier la maintenance / le contexte d'un hôte |
| `get_metric_history` | lecture | consulter l'historique d'une métrique |
| `acknowledge_event` | écriture | acquitter (avec justification) |
| `escalate_event` | écriture | escalader vers le niveau 2 |
## Les 4 familles d'alertes
CPU élevé · disque plein · service arrêté · hôte injoignable.
> Remplacer ce schéma ASCII par une image (`docs/architecture.png`) si vous en
> réalisez une version graphique — le README pourra alors l'afficher directement.
