"""
core/tools_schema.py -- Description des outils pour le LLM.
Le LLM ne lit pas le code Python : il ne connait que ces descriptions JSON.
Leur qualite determine donc DIRECTEMENT la qualite du tool-calling. Quand
l'agent choisit le mauvais outil ou remplit mal un parametre, c'est ici
qu'il faut corriger -- pas dans la boucle ReAct.
Regles de redaction appliquees ci-dessous :
- dire QUAND utiliser l'outil, pas seulement ce qu'il fait
- donner des exemples concrets de valeurs dans les descriptions
- garder peu d'outils (5) : un LLM se trompe d'autant plus qu'il a le choix
"""
from core import zabbix_tools
# ---------------------------------------------------------------------------
# Schemas au format "function calling" (standard OpenAI, compris par
# Groq, Gemini, Mistral et Ollama)
# ---------------------------------------------------------------------------
TOOLS = [
# --- OUTIL 1 ----------------------------------------------------------
{
"type": "function",
"function": {
"name": "get_active_problems",
"description": (
"Liste les alertes (problemes) actuellement actives dans Zabbix. "
"A utiliser pour voir la situation generale ou verifier si un hote "
"a plusieurs alertes simultanees (signe d'un probleme plus grave)."
),
"parameters": {
"type": "object",
"properties": {
"hostname": {
"type": "string",
"description": "Nom de l'hote a filtrer, ex. 'srv-web-02'. Omettre pour tout voir.",
},
"limit": {
"type": "integer",
"description": "Nombre maximum de problemes a renvoyer (defaut 20).",
},
},
"required": [],
},
},
},
# --- OUTIL 2 ----------------------------------------------------------
{
"type": "function",
"function": {
"name": "get_host_context",
"description": (
"Renvoie le contexte d'un hote : est-il EN MAINTENANCE, est-il "
"surveille, a quels groupes appartient-il, quelle est son IP. "
"A APPELER SYSTEMATIQUEMENT EN PREMIER : une alerte sur un hote en "
"maintenance est un faux positif qu'il faut acquitter sans hesiter."
),
"parameters": {
"type": "object",
"properties": {
"hostname": {
"type": "string",
"description": "Nom exact de l'hote, ex. 'srv-web-02'.",
}
},
"required": ["hostname"],
},
},
},
# --- OUTIL 3 ----------------------------------------------------------
{
"type": "function",
"function": {
"name": "get_metric_history",
"description": (
"Renvoie les dernieres valeurs mesurees d'une metrique, avec sa "
"moyenne, son minimum et son maximum. Sert a distinguer un pic "
"transitoire (deja retombe : on peut acquitter) d'un probleme "
"persistant (il faut escalader). "
"Cles utiles : 'cpu.util' pour le CPU, 'vfs.fs.dependent.size' pour le disque, "
"'proc.num' pour les processus, 'icmpping' pour la joignabilite."
),
"parameters": {
"type": "object",
"properties": {
"hostname": {
"type": "string",
"description": "Nom exact de l'hote.",
},
"key_search": {
"type": "string",
"description": (
"Fragment de la cle Zabbix a rechercher. "
"Exemples : 'cpu.util', 'vfs.fs.dependent.size', 'proc.num', 'icmpping'."
),
},
"limit": {
"type": "integer",
"description": "Nombre de points d'historique (defaut 10).",
},
},
"required": ["hostname", "key_search"],
},
},
},
# --- OUTIL 4 ----------------------------------------------------------
{
"type": "function",
"function": {
"name": "acknowledge_event",
"description": (
"ACQUITTE une alerte en y joignant une justification. "
"A n'utiliser QUE si le cas est connu, benin, et sans impact "
"utilisateur : hote en maintenance, pic transitoire deja retombe, "
"seuil legerement depasse sans consequence. "
"En cas de doute, ne pas utiliser cet outil : utiliser escalate_event."
),
"parameters": {
"type": "object",
"properties": {
"eventid": {
"type": "string",
"description": "Identifiant de l'evenement a acquitter.",
},
"message": {
"type": "string",
"description": (
"Justification en francais, visible par les equipes dans Zabbix. "
"Ex. : 'Pic CPU transitoire (max 82%, retombe a 15%), hote sain.'"
),
},
"severity": {
"type": "integer",
"description": "Severite de l'alerte (0 a 5), pour le controle de seuil.",
},
},
"required": ["eventid", "message"],
},
},
},
# --- OUTIL 5 ----------------------------------------------------------
{
"type": "function",
"function": {
"name": "escalate_event",
"description": (
"ESCALADE une alerte vers le niveau 2. L'alerte reste NON ACQUITTEE "
"et un message explicatif y est ajoute. "
"A utiliser des qu'il y a un doute, une severite elevee, un impact "
"utilisateur possible, ou un cas jamais rencontre. "
"Une escalade inutile coute peu ; une alerte acquittee a tort peut "
"masquer une panne reelle."
),
"parameters": {
"type": "object",
"properties": {
"eventid": {
"type": "string",
"description": "Identifiant de l'evenement a escalader.",
},
"message": {
"type": "string",
"description": (
"Raison de l'escalade, en francais, a destination du N2. "
"Ex. : 'Disque / a 95%, croissance continue depuis 2h.'"
),
},
"hostname": {
"type": "string",
"description": "Nom de l'hote concerne (pour la notification e-mail).",
},
"problem": {
"type": "string",
"description": "Intitule du probleme (pour la notification e-mail).",
},
},
"required": ["eventid", "message"],
},
},
},
]
# ---------------------------------------------------------------------------
# Table de correspondance nom -> fonction Python reelle.
#
# Le LLM renvoie un NOM d'outil ; c'est nous qui decidons a quelle fonction
# il correspond. Un nom absent de ce dictionnaire ne peut pas etre execute :
# c'est une protection supplementaire contre une hallucination du modele.
# ---------------------------------------------------------------------------
DISPATCH = {
"get_active_problems": zabbix_tools.get_active_problems,
"get_host_context": zabbix_tools.get_host_context,
"get_metric_history": zabbix_tools.get_metric_history,
"acknowledge_event": zabbix_tools.acknowledge_event,
"escalate_event": zabbix_tools.escalate_event,
}
# Outils qui ecrivent dans Zabbix : la boucle ReAct s'arrete des que l'un
# d'eux a ete appele avec succes (une decision par alerte, pas deux).
TERMINAL_TOOLS = {"acknowledge_event", "escalate_event"}
