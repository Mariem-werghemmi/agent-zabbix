# Agent IA de supervision Zabbix — Niveau 1
> Un agent d'intelligence artificielle qui **trie, diagnostique et traite
> automatiquement** les alertes routinières de supervision Zabbix, pour soulager
> les opérateurs de niveau 1 — sans jamais masquer un incident réel.
![CI](https://github.com/Mariem-werghemmi/agent-zabbix/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![Zabbix](https://img.shields.io/badge/Zabbix-7.0-red)
![LLM](https://img.shields.io/badge/LLM-Groq%20%2F%20Llama%203.3-0E6E6C)
![License](https://img.shields.io/badge/License-MIT-green)
![Security](https://img.shields.io/badge/Security-Trivy%20%7C%20Bandit%20%7C%20Gitleaks-0E6E6C)
Projet réalisé lors d'un stage chez **Next Step IT**. L'agent réduit le *bruit
d'alertes* (« alert fatigue ») en prenant en charge les cas connus, tout en
escaladant vers un humain toute situation incertaine.
---
## 🎯 Résultats
| Indicateur | Valeur |
|---|---|
| **Taux de décisions correctes** | **90,9 %** |
| **Faux acquittements** (erreur dangereuse) | **0** |
| Familles d'alertes couvertes | 4 (CPU, disque, service, hôte injoignable) |
| Outils Zabbix exposés à l'agent | 5 |
| Temps de traitement moyen | ≈ 2–4 s / décision (cloud) |
> Le chiffre clé n'est pas le taux, mais le **zéro faux acquittement** : l'agent
> n'a jamais fermé les yeux sur un vrai problème. Sa seule erreur mesurée était
> une *fausse escalade* (sans danger), diagnostiquée puis corrigée par ajustement
> du prompt (confusion entre la dernière valeur d'une métrique et sa moyenne).
---
## 🏗️ Architecture
```
VM 1 — Zabbix                             VM 2 — Agent IA
┌────────────────────┐               ┌────────────────────────────────┐
│ Serveur Zabbix      │ API JSON-RPC │ Moteur core/     (boucle ReAct) │
|
│ (7.0)               │◀──────────────▶│ Pensée → Action → Observation │
│ api_jsonrpc.php     │ jeton restreint│ ├─ 5 outils (zabbix_utils)    │
└────────────────────┘                 │ ├─ garde-fous (dry-run,       │
                                       | │     seuil, escalade défaut) │
                                       │ └─ décision → SQLite (journal)│
                                       │                               │
                                       │ cli.py · web.py · evaluate.py │
                                       │ LLM interchangeable (.env) ───┼──▶ Groq
                                       │ notification e-mail (SMTP)    │ (ou local)
                                       └────────────────────────────────┘
                                     services systemd : agent-watch, agent-web
```
Un **agent unique** met en œuvre une boucle de raisonnement **ReAct**
(*Reason + Act*) codée à la main — aucun framework — pour garder le raisonnement
totalement transparent et explicable. Le modèle de langage est **interchangeable
par simple configuration** (`.env`).
---
## 🔒 Pourquoi c'est sécurisé
La confiance ne repose pas sur le « bon vouloir » du modèle, mais sur des
**garde-fous codés dans les outils**, indépendants du prompt — le LLM ne peut
donc pas les contourner :
- **Mode dry-run** — l'agent *propose* ses actions sans jamais écrire dans Zabbix
tant que la confiance n'est pas validée.
- **Seuil de sévérité codé en dur** — au-delà de « Warning », l'acquittement
automatique est *refusé par le code*, ce qui force l'escalade.
- **Escalade par défaut** — toute anomalie (erreur, doute, cas inconnu) mène à
une escalade, jamais à un acquittement.
Détails complets et modèle de menaces : voir [SECURITY.md](SECURITY.md).
---
## 🧰 Stack technique
| Rôle | Choix |
|---|---|
| Langage | Python 3.12 |
| Modèle de langage | Groq / Llama 3.3 70B (interchangeable via `.env`) |
| Accès Zabbix | `zabbix_utils` (API JSON-RPC, Zabbix 7.0) |
| Validation des données | Pydantic v2 |
| Console web | FastAPI + Jinja2 |
| Traçabilité | SQLite |
| Notifications | SMTP (e-mail) |
| Déploiement | services systemd (`agent-watch`, `agent-web`) |
---
## 🚀 Démarrage rapide
```bash
# 1. Cloner et installer
git clone https://github.com/<votre-utilisateur>/agent-zabbix.git
cd agent-zabbix
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# 2. Configurer (copier le modèle puis remplir 3 valeurs)
cp .env.example .env
# -> LLM_API_KEY, ZABBIX_URL, ZABBIX_TOKEN
# 3. Vérifier les connexions (Zabbix + LLM)
python3 cli.py --check
# 4. Traiter les alertes une fois, en mode simulation (dry-run)
python3 cli.py --once --verbose
# 5. Lancer la console web
python3 web.py # http://<IP>:8000
```
Modes principaux : `--check` (diagnostic), `--once` (traitement ponctuel),
`--watch` (surveillance continue), `--eventid <ID>` (un événement précis).
Mesure du taux de réussite : `python3 evaluate.py --stats`.
---
## 📁 Structure du dépôt
```
agent-zabbix/
├── core/ # moteur ReAct, 5 outils Zabbix, schémas, base, notifier
├── cli.py # interface en ligne de commande
├── web.py # console web (FastAPI)
├── evaluate.py # mesure du taux de réussite (matrice de confusion)
├── templates/ # tableau de bord web
├── static/ # feuille de style
├── deploy/ # services systemd + scripts d'intégration
├── docs/ # schéma d'architecture & documentation
├── .env.example # modèle de configuration (jamais de secret réel)
├── SECURITY.md # garde-fous & modèle de menaces
└── requirements.txt
```
---

## 🐳 Conteneurisation & CI/CD

L'agent et la console sont conteneurisés (Docker multi-stage, utilisateurs non-root, healthchecks) et orchestrés via `docker-compose`. Le serveur Zabbix reste externe (autre VM), sa configuration vient du `.env`.

```bash
cp .env.example .env   # remplir
docker compose up -d --build
docker compose ps      # les 2 services "healthy"
```

Un pipeline GitHub Actions (`.github/workflows/ci.yml`) exécute à chaque push :
secrets (Gitleaks) → SAST (Bandit) → SCA (pip-audit) → tests (pytest) → build → scan d'image (Trivy).

**Gestion des secrets** : backend Vault optionnel (`SECRETS_BACKEND=vault`), rétro-compatible avec `.env` par défaut.

**Tests** : 7 tests ciblés sur les garde-fous, dont la résistance à l'injection de prompt (`tests/test_prompt_injection.py`) — la preuve que le code, pas le prompt, garde le contrôle final.
---
## ⚠️ Limites honnêtes
- **Périmètre niveau 1 uniquement** : l'agent ne réalise aucun diagnostic
approfondi ni corrélation d'incidents (niveaux 2/3).
- **Aucune action sur les systèmes** : il agit *dans* Zabbix (acquitter /
commenter / escalader), jamais sur les serveurs supervisés.
- **Échantillon de mesure encore modeste** : le taux de 90,9 % valide la démarche
mais gagnerait à être confirmé sur un échantillon plus large.
- **Dépendance au cloud** si le LLM distant (Groq) est utilisé : l'architecture
est prévue pour basculer vers un modèle **local** (aucune donnée sortante) via
une seule variable de configuration.
---
## 📄 Licence
Distribué sous licence [MIT](LICENSE).
