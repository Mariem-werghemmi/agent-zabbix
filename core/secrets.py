"""
core/secrets.py -- Chargement des secrets depuis Vault (mode dev) ou l'env.

Backend selectionne par la variable SECRETS_BACKEND :
  env (defaut)  -> comportement d'origine : les secrets viennent de .env
  vault         -> les secrets sont lus dans HashiCorp Vault (mode dev/local)

ADDITIF & RETRO-COMPATIBLE : sans SECRETS_BACKEND=vault, cette fonction ne fait
rien et l'application se comporte exactement comme avant. Vault n'est donc une
dependance QUE si on choisit ce backend.

Principe : on lit les secrets dans Vault et on les injecte dans l'environnement
AVANT que Pydantic ne lise la configuration (config.py). Ainsi, aucun autre
fichier n'a besoin d'etre modifie.
"""
import logging
import os

logger = logging.getLogger(__name__)


def load_secrets_into_env() -> dict:
    """Charge les secrets selon SECRETS_BACKEND et les injecte dans os.environ.

    Retourne le dict des secrets charges (vide si backend != vault).
    """
    backend = os.environ.get("SECRETS_BACKEND", "env").strip().lower()
    if backend != "vault":
        return {}  # backend "env" : rien a faire, .env est lu par Pydantic

    try:
        import hvac  # dependance optionnelle : pip install hvac
    except ImportError:
        logger.error("SECRETS_BACKEND=vault mais le paquet 'hvac' n'est pas installe.")
        raise

    addr = os.environ.get("VAULT_ADDR", "http://127.0.0.1:8200")
    token = os.environ.get("VAULT_TOKEN", "root")
    path = os.environ.get("VAULT_SECRET_PATH", "agent-zabbix")

    client = hvac.Client(url=addr, token=token)
    if not client.is_authenticated():
        raise RuntimeError(f"Authentification Vault echouee sur {addr}")

    read = client.secrets.kv.v2.read_secret_version(path=path, mount_point="secret")
    data = read["data"]["data"]

    # On n'ECRASE pas une variable deja definie dans l'environnement : setdefault.
    for key, value in data.items():
        os.environ.setdefault(key, str(value))

    logger.info("Secrets charges depuis Vault (%d cles) : %s", len(data), addr)
    return data
