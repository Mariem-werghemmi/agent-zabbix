# Sécurité
Ce document décrit la posture de sécurité de l'agent : les garde-fous intégrés,
un modèle de menaces synthétique, et la marche à suivre pour signaler une
vulnérabilité.
---
## 1. Principe fondateur
> **Le LLM décide, le code garde le contrôle final.**
L'agent s'appuie sur un modèle de langage, non déterministe par nature. La
sécurité ne repose donc **jamais** sur les instructions données au modèle (le
prompt), qui restent des *suggestions* qu'il pourrait ignorer ou qu'une injection
pourrait détourner. Elle repose sur des **contrôles codés dans les outils**
eux-mêmes — des *barrières* que le modèle ne peut pas franchir, même s'il le
« voulait ».
---
## 2. Les trois garde-fous
### 2.1 Mode dry-run (simulation)
- **Quoi** : tant que `DRY_RUN=true`, l'agent *calcule* sa décision et la
journalise, mais **n'écrit rien** dans Zabbix (aucun acquittement, aucun
commentaire).
- **Pourquoi** : permet d'observer et de mesurer le comportement de l'agent sans
aucun risque pour la supervision. C'est le mode par défaut pendant toute la
phase de mise au point.
- **Où** : la vérification est faite dans les outils d'écriture
(`acknowledge_event`, `escalate_event`), pas dans le prompt.
### 2.2 Seuil de sévérité codé en dur
- **Quoi** : `MAX_AUTO_ACK_SEVERITY` fixe la sévérité maximale que l'agent peut
acquitter seul (par défaut : `Warning`). Au-delà, l'acquittement est **refusé
par le code**, ce qui force une escalade vers un humain.
- **Pourquoi** : une alerte grave ne doit jamais pouvoir être fermée
automatiquement, quelle que soit la décision du modèle.
- **Où** : contrôle dans `acknowledge_event`, avant tout appel à l'API Zabbix.
### 2.3 Escalade par défaut
- **Quoi** : toute anomalie — erreur d'appel au modèle, réponse mal formée,
limite d'étapes de raisonnement atteinte, cas non reconnu — conduit à une
**escalade**, jamais à un acquittement.
- **Pourquoi** : « dans le doute, on remonte à un humain ». Le coût d'une escalade
inutile est faible ; celui d'un incident masqué est élevé.
- **Où** : logique de repli du moteur (`core/agent.py`).
> Conséquence mesurée : **0 faux acquittement** sur l'échantillon de test — le
> profil de risque le plus sûr pour un agent de niveau 1.
Contrôles complémentaires :
- L'agent utilise **`action=6`** (acquitter + commenter) sur les événements ; il
ne **ferme jamais** un problème et ne modifie jamais une sévérité.
- Chaque décision est **journalisée** (hôte, problème, décision, raisonnement,
horodatage) pour audit.
---
## 3. Modèle de menaces (synthétique)
| Menace | Impact potentiel | Mitigation en place |
|---|---|---|
| **Injection de prompt / LLM détourné** | Le modèle tente une action dangereuse (acquitter une alerte critique). | Garde-
| **Fuite du jeton Zabbix** | Un attaquant agit sur Zabbix avec les droits de l'agent. | Jeton **à droits restreints** sur
| **Fuite de la clé API du LLM** | Consommation du quota / coûts, accès au service tiers. | Clé stockée dans `.env` (git-i
| **Fuite des identifiants SMTP** | Envoi d'e-mails frauduleux depuis le compte de notification. | Compte e-mail **dédié**
| **Exfiltration de données via le LLM cloud** | Les libellés d'alertes (noms d'hôtes, IP) transitent vers un tiers. | Com
| **Compromission de la VM de l'agent** | Accès au code et à `.env`. | Agent isolé sur une **VM séparée** de Zabbix ; il n
| **Secret committé par erreur** | Secret exposé publiquement (et à vie dans l'historique). | `.gitignore` strict ; `.env`
---
## 4. Bonnes pratiques de configuration
- Ne **jamais** committer `.env` ni aucun secret réel ; n'utiliser que
`.env.example` avec des valeurs factices.
- Utiliser un **jeton API Zabbix dédié à droits restreints**, pas un compte
administrateur.
- Garder `DRY_RUN=true` jusqu'à validation du comportement sur des alertes de
test.
- Faire tourner le service sous un **utilisateur système non privilégié**.
---
## 5. Gestion des secrets & scan
Avant tout commit :
```bash
# Vérifier qu'aucun secret ne traîne dans l'arbre de travail
grep -rEi "gsk_|api[_-]?key|password|secret|token" \
--exclude-dir=.git --exclude="*.example" --exclude="SECURITY.md" . || echo "OK"
# (optionnel mais recommandé) scan dédié
gitleaks detect --source . --redact
```
---
