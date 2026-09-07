#!/usr/bin/env python3
"""
evaluate.py -- Mesure du critere de reussite du stage.

Le critere valide avec l'encadrant est :
    "Sur N alertes de test, l'agent produit une decision correcte et justifiee
     dans X % des cas, visible dans la console web et tracee en base."

Cet outil fournit le X %. Il compare, une par une, chaque decision prise par
l'agent (table 'decisions') a ce qu'un operateur humain de niveau 1 aurait
fait. Ton jugement d'humain est enregistre dans une table 'evaluations'
separee : on ne modifie jamais les decisions d'origine.

Usage :
    python3 evaluate.py --annotate              # annoter les decisions non evaluees
    python3 evaluate.py --stats                 # afficher le taux de reussite
    python3 evaluate.py --export                # exporter en CSV pour le rapport
    python3 evaluate.py --stats --family CPU_ELEVE   # filtrer par famille

Methodologie (a expliquer en soutenance) :
1. On genere des alertes de test variees (cf. guide, Partie 1).
2. L'agent les traite -> une ligne par decision dans 'decisions'.
3. Ici, pour chaque decision, l'humain indique l'action ATTENDUE.
4. correct = (action de l'agent == action attendue).
5. Le taux de reussite = nb correct / nb evalue, global et par famille.
"""

import argparse
import csv
import sqlite3
import sys
from datetime import datetime

from config import settings

# ---------------------------------------------------------------------------
# Table d'evaluation. Volontairement geree ici (et pas dans core/database.py)
# pour garder le moteur intact : l'evaluation est un outil d'analyse, pas une
# partie de l'agent.
# ---------------------------------------------------------------------------
EVAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id      INTEGER NOT NULL UNIQUE,
    agent_action     TEXT    NOT NULL,
    expected_action  TEXT    NOT NULL,
    correct          INTEGER NOT NULL,
    note             TEXT    DEFAULT '',
    evaluated_at     TEXT    NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES decisions(id)
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_file, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(EVAL_SCHEMA)
    return conn


# ===========================================================================
# ANNOTATION
# ===========================================================================
def annotate() -> None:
    """Parcourt les decisions non encore evaluees et demande le verdict humain."""
    conn = connect()

    pending = conn.execute(
        """
        SELECT d.*
        FROM decisions d
        LEFT JOIN evaluations e ON e.decision_id = d.id
        WHERE e.id IS NULL
        ORDER BY d.id ASC
        """
    ).fetchall()

    if not pending:
        print("Aucune decision en attente d'evaluation. Tout est deja annote.")
        conn.close()
        return

    print(f"\n{len(pending)} decision(s) a evaluer.")
    print("Pour chacune : indique ce qu'un operateur N1 aurait fait.")
    print("  [a] acquitter   [e] escalader   [s] passer   [q] quitter\n")

    evaluees = 0
    for d in pending:
        print("=" * 68)
        print(f"Decision #{d['id']} | event {d['eventid']} | {d['created_at']}")
        print(f"  Hote      : {d['hostname']}")
        print(f"  Probleme  : {d['problem_name']}")
        print(f"  Severite  : {d['severity']}")
        print(f"  Famille   : {d['family']}")
        print(f"  --> Agent : {d['action']} (confiance {d['confidence']:.0%})")
        print(f"      Raison : {d['reasoning']}")
        print("-" * 68)

        reponse = ""
        while reponse not in ("a", "e", "s", "q"):
            reponse = input("Qu'aurait fait le N1 ? [a/e/s/q] ").strip().lower()

        if reponse == "q":
            break
        if reponse == "s":
            continue

        expected = "ACKNOWLEDGE" if reponse == "a" else "ESCALATE"
        correct = 1 if expected == d["action"] else 0
        note = input("Note (facultatif) : ").strip()

        conn.execute(
            """
            INSERT INTO evaluations
                (decision_id, agent_action, expected_action, correct, note, evaluated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (d["id"], d["action"], expected, correct, note,
             datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        evaluees += 1

        verdict = "CORRECT" if correct else "INCORRECT"
        print(f"  -> Enregistre : agent={d['action']} / attendu={expected} [{verdict}]\n")

    conn.close()
    print(f"\n{evaluees} decision(s) evaluee(s) lors de cette session.")


# ===========================================================================
# STATISTIQUES
# ===========================================================================
def stats(family: str | None = None) -> None:
    """Affiche le taux de reussite global, par famille, et la matrice de confusion."""
    conn = connect()

    filtre = "WHERE d.family = ?" if family else ""
    args = (family,) if family else ()

    # --- Taux global ------------------------------------------------------
    # Filtre construit en interne (2 valeurs fixes possibles), jamais depuis une
    # entree utilisateur brute. Valeurs reelles passees via args (requete parametree).
    query = f"SELECT COUNT(*) AS n, COALESCE(SUM(e.correct), 0) AS ok FROM evaluations e JOIN decisions d ON d.id = e.decision_id {filtre}"  # nosec B608
    row = conn.execute(query, args).fetchone()
    total, ok = row["n"], row["ok"]
    if total == 0:
        print("Aucune decision evaluee pour ce filtre. Lance d'abord --annotate.")
        conn.close()
        return

    taux = 100 * ok / total
    titre = f" (famille {family})" if family else ""
    print("=" * 60)
    print(f" CRITERE DE REUSSITE{titre}")
    print("=" * 60)
    print(f" Decisions evaluees   : {total}")
    print(f" Decisions correctes  : {ok}")
    print(f" TAUX DE REUSSITE     : {taux:.1f} %")
    print("=" * 60)

    # --- Detail par famille ----------------------------------------------
    print("\n Detail par famille :")
    rows = conn.execute(
        """
        SELECT d.family AS famille,
               COUNT(*) AS n,
               COALESCE(SUM(e.correct), 0) AS ok
        FROM evaluations e
        JOIN decisions d ON d.id = e.decision_id
        GROUP BY d.family
        ORDER BY d.family
        """
    ).fetchall()
    for r in rows:
        pct = 100 * r["ok"] / r["n"] if r["n"] else 0
        print(f"   {r['famille']:<18} {r['ok']:>3}/{r['n']:<3}  ({pct:.0f} %)")

    # --- Matrice de confusion --------------------------------------------
    # Montre OU l'agent se trompe : a-t-il tendance a trop acquitter
    # (dangereux) ou trop escalader (juste couteux en temps) ?
    print("\n Matrice de confusion (agent x attendu) :")
    print(f"   {'':<22}{'attendu ACK':<14}{'attendu ESC':<14}")
    for agent_act in ("ACKNOWLEDGE", "ESCALATE"):
        ligne = f"   agent {agent_act:<16}"
        for exp_act in ("ACKNOWLEDGE", "ESCALATE"):
            c = conn.execute(
                """
                SELECT COUNT(*) AS n FROM evaluations
                WHERE agent_action = ? AND expected_action = ?
                """,
                (agent_act, exp_act),
            ).fetchone()["n"]
            ligne += f"{c:<14}"
        print(ligne)

    # --- Erreurs les plus graves : faux acquittements ---------------------
    faux_ack = conn.execute(
        """
        SELECT d.hostname, d.problem_name, e.note
        FROM evaluations e
        JOIN decisions d ON d.id = e.decision_id
        WHERE e.agent_action = 'ACKNOWLEDGE' AND e.expected_action = 'ESCALATE'
        """
    ).fetchall()

    if faux_ack:
        print("\n /!\\ FAUX ACQUITTEMENTS (l'agent a acquitte ce qu'il fallait escalader) :")
        for r in faux_ack:
            print(f"   - {r['hostname']} : {r['problem_name']}  {('('+r['note']+')') if r['note'] else ''}")
        print("   Ce sont les erreurs les plus graves : a corriger en priorite dans le prompt.")

    conn.close()


# ===========================================================================
# EXPORT
# ===========================================================================
def export(chemin: str = "data/evaluation.csv") -> None:
    """Exporte le detail des evaluations en CSV pour le rapport."""
    conn = connect()

    rows = conn.execute(
        """
        SELECT d.id, d.created_at, d.hostname, d.problem_name, d.family,
               d.severity, e.agent_action, e.expected_action, e.correct, e.note
        FROM evaluations e
        JOIN decisions d ON d.id = e.decision_id
        ORDER BY d.id
        """
    ).fetchall()
    conn.close()

    if not rows:
        print("Rien a exporter.")
        return

    with open(chemin, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([k for k in rows[0].keys()])
        for r in rows:
            writer.writerow([r[k] for k in r.keys()])

    print(f"Export ecrit : {chemin}  ({len(rows)} lignes)")


# ===========================================================================
def main() -> int:
    p = argparse.ArgumentParser(description="Mesure du critere de reussite de l'agent")
    p.add_argument("--annotate", action="store_true", help="annoter les decisions non evaluees")
    p.add_argument("--stats", action="store_true", help="afficher le taux de reussite")
    p.add_argument("--export", action="store_true", help="exporter en CSV")
    p.add_argument("--family", type=str, help="filtrer les stats sur une famille")
    args = p.parse_args()

    if not any((args.annotate, args.stats, args.export)):
        p.print_help()
        return 1

    if args.annotate:
        annotate()
    if args.stats:
        stats(args.family)
    if args.export:
        export()

    return 0


if __name__ == "__main__":
    sys.exit(main())
