"""
config.py -- Lecture centralisee de la configuration.
"""
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()   # charge .env dans os.environ, AVANT tout le reste
from pydantic_settings import BaseSettings, SettingsConfigDict
from core.secrets import load_secrets_into_env
load_secrets_into_env()  # avant la lecture Pydantic
BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Configuration de l'application, chargee depuis .env."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = "REMPLACER"
    llm_model: str = "llama-3.3-70b-versatile"
    llm_temperature: float = 0.0
    llm_max_steps: int = 8
    llm_timeout: int = 120

    zabbix_url: str = "http://localhost/zabbix/api_jsonrpc.php"
    zabbix_token: str = "REMPLACER"
    zabbix_verify_ssl: bool = False

    dry_run: bool = True
    max_auto_ack_severity: int = 2

    notify_email_enabled: bool = False
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "agent-zabbix@localhost"
    smtp_to: str = ""

    poll_interval: int = 60
    db_path: str = "data/agent.db"
    log_path: str = "data/agent.log"
    # Ecoute volontairement sur toutes les interfaces : acces prevu via docker-compose.
    web_host: str = "0.0.0.0"  # nosec B104
    web_port: int = 8000

    @property
    def db_file(self) -> Path:
        p = BASE_DIR / self.db_path
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def log_file(self) -> Path:
        p = BASE_DIR / self.log_path
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def mode_label(self) -> str:
        return "DRY-RUN (simulation)" if self.dry_run else "AUTONOME (actions reelles)"


settings = Settings()
