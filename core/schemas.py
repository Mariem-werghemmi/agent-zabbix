from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

SEVERITY_LABELS = {
    0: "Non classifie",
    1: "Information",
    2: "Warning",
    3: "Average",
    4: "High",
    5: "Disaster",
}


class Action(str, Enum):
    ACKNOWLEDGE = "ACKNOWLEDGE"
    ESCALATE = "ESCALATE"


class AlertFamily(str, Enum):
    CPU = "CPU_ELEVE"
    DISK = "DISQUE_PLEIN"
    SERVICE = "SERVICE_ARRETE"
    HOST_DOWN = "HOST_INJOIGNABLE"
    UNKNOWN = "INCONNUE"


class Decision(BaseModel):
    action: Action = Field(
        description="ACKNOWLEDGE si cas connu et benin, ESCALATE sinon"
    )
    family: AlertFamily = Field(
        default=AlertFamily.UNKNOWN,
        description="Famille d'alerte identifiee",
    )
    reasoning: str = Field(
        min_length=20,
        description="Justification en francais",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Niveau de confiance entre 0 et 1",
    )
    message: str = Field(
        min_length=5,
        max_length=2000,
        description="Message a inscrire dans Zabbix",
    )


class AlertContext(BaseModel):
    eventid: str
    name: str
    severity: int = 0
    hostname: str = "inconnu"
    clock: int = 0

    @property
    def severity_label(self) -> str:
        return SEVERITY_LABELS.get(self.severity, "Inconnue")

    def to_prompt(self) -> str:
        horodatage = (
            datetime.fromtimestamp(self.clock).strftime("%Y-%m-%d %H:%M:%S")
            if self.clock
            else "inconnu"
        )
        return (
            f"Nouvelle alerte Zabbix a traiter :\n"
            f"- eventid : {self.eventid}\n"
            f"- Probleme : {self.name}\n"
            f"- Hote : {self.hostname}\n"
            f"- Severite : {self.severity} ({self.severity_label})\n"
            f"- Depuis : {horodatage}\n\n"
            f"IMPORTANT : Pour TOUS tes appels d'outils, utilise "
            f"OBLIGATOIREMENT hostname=\"{self.hostname}\". "
            f"N'utilise AUCUN autre nom d'hote.\n\n"
            f"Analyse cette alerte en utilisant tes outils, puis decide."
        )


class DecisionRecord(BaseModel):
    id: int | None = None
    eventid: str
    hostname: str
    problem_name: str
    severity: int
    action: str
    family: str
    reasoning: str
    confidence: float
    message: str
    dry_run: bool
    steps_used: int
    duration_ms: int
    llm_model: str
    created_at: str = ""

    @property
    def severity_label(self) -> str:
        return SEVERITY_LABELS.get(self.severity, "Inconnue")
