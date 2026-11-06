"""Reglas de negocio de VetCare 24 (aplicación del PIA, Unidad 5).

Reglas implementadas:
  1. Bloqueo farmacológico por alergias (US-11)
  2. Interrupción de agenda por urgencias (US-06)
  3. Prevención de expedientes duplicados (US-13)

Ejercicio separado con adaptador simulado:
  4. Recordatorio de vacuna 3 días antes del vencimiento (notificador externo)
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import Boolean, String, create_engine, or_, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# --------------------------------------------------------------------------
# Persistencia (SQLAlchemy)
# --------------------------------------------------------------------------
class VetBase(DeclarativeBase):
    pass


class RecetaRow(VetBase):
    __tablename__ = "recetas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mascota_id: Mapped[int]
    medicamento: Mapped[str] = mapped_column(String)
    con_alerta: Mapped[bool] = mapped_column(Boolean, default=False)
    autorizada_por: Mapped[str | None] = mapped_column(String, nullable=True)


class PropietarioRow(VetBase):
    __tablename__ = "propietarios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String)
    telefono: Mapped[str] = mapped_column(String, default="")
    correo: Mapped[str | None] = mapped_column(String, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


def make_vet_engine(url="sqlite+pysqlite:///:memory:"):
    engine = create_engine(url)
    VetBase.metadata.create_all(engine)
    return engine


def _normalizar(texto):
    return texto.strip().casefold()


# --------------------------------------------------------------------------
# Regla 1: Bloqueo farmacológico por alergias (US-11)
# --------------------------------------------------------------------------
class AlergiaDetectada(Exception):
    pass


@dataclass
class Mascota:
    id: int
    nombre: str
    alergias: set = field(default_factory=set)


@dataclass(frozen=True)
class Medicamento:
    nombre: str
    sustancias: frozenset


class RecetaService:
    def __init__(self, session):
        self.session = session

    def prescribir(
        self, mascota, medicamento, confirmar_conscientemente=False, veterinario=None
    ):
        alergias = {_normalizar(a) for a in mascota.alergias}
        sustancias = {_normalizar(s) for s in medicamento.sustancias}
        conflicto = alergias & sustancias
        autorizada_por = None

        if conflicto:
            if not confirmar_conscientemente:
                raise AlergiaDetectada(
                    f"{mascota.nombre} es alérgica a {', '.join(sorted(conflicto))}. "
                    f"No se puede guardar la receta de {medicamento.nombre} "
                    "sin la confirmación del veterinario"
                )
            if not veterinario:
                raise ValueError(
                    "Para confirmar la receta debe indicarse el veterinario "
                    "que la autoriza"
                )
            autorizada_por = veterinario

        receta = RecetaRow(
            mascota_id=mascota.id,
            medicamento=medicamento.nombre,
            con_alerta=bool(conflicto),
            autorizada_por=autorizada_por,
        )
        self.session.add(receta)
        self.session.flush()
        return receta


# --------------------------------------------------------------------------
# Regla 2: Interrupción de agenda por urgencias (US-06)
# --------------------------------------------------------------------------
class UrgenciaIncompleta(Exception):
    pass


class AgendaExcedeCierre(Exception):
    pass


@dataclass
class Cita:
    id: int
    mascota_id: int
    inicio: datetime
    fin: datetime
    estado: str = "PROGRAMADA"


@dataclass
class Urgencia:
    mascota_id: int
    motivo: str
    llegada: datetime


class Agenda:
    def __init__(self, citas, hora_cierre, desplazamiento=timedelta(minutes=20)):
        self.citas = citas
        self.hora_cierre = hora_cierre
        self.desplazamiento = desplazamiento

    def registrar_urgencia(self, mascota_id, motivo, ahora):
        faltantes = []
        if not mascota_id:
            faltantes.append("el identificador de la mascota")
        if not (motivo or "").strip():
            faltantes.append("el motivo de consulta")
        if faltantes:
            raise UrgenciaIncompleta(
                "No se puede activar el modo Urgencia: falta "
                + " y ".join(faltantes)
            )

        en_curso = [c for c in self.citas if c.inicio <= ahora < c.fin]
        por_mover = [c for c in self.citas if c.inicio > ahora]

        if por_mover:
            ultimo_fin = max(c.fin for c in por_mover) + self.desplazamiento
            if ultimo_fin > self.hora_cierre:
                raise AgendaExcedeCierre(
                    "No se puede recorrer la agenda: la última cita terminaría "
                    f"a las {ultimo_fin:%H:%M}, después del cierre de la clínica "
                    f"({self.hora_cierre:%H:%M})"
                )

        for cita in en_curso:
            cita.estado = "PAUSADA"
        for cita in por_mover:
            cita.inicio += self.desplazamiento
            cita.fin += self.desplazamiento
        return Urgencia(mascota_id=mascota_id, motivo=motivo.strip(), llegada=ahora)


# --------------------------------------------------------------------------
# Regla 3: Prevención de expedientes duplicados (US-13)
# --------------------------------------------------------------------------
class PosibleDuplicado(Exception):
    pass


def _solo_digitos(texto):
    return "".join(ch for ch in (texto or "") if ch.isdigit())


class ExpedienteService:
    def __init__(self, session):
        self.session = session

    def _buscar_activo(self, telefono, correo):
        condiciones = []
        if telefono:
            condiciones.append(PropietarioRow.telefono == telefono)
        if correo:
            condiciones.append(PropietarioRow.correo == correo)
        if not condiciones:
            return None
        consulta = select(PropietarioRow).where(
            PropietarioRow.activo.is_(True), or_(*condiciones)
        )
        return self.session.scalars(consulta).first()

    def registrar_propietario(
        self, nombre, telefono="", correo=None, confirmar_distinta_persona=False
    ):
        telefono = _solo_digitos(telefono)
        correo = _normalizar(correo) if correo else None

        existente = self._buscar_activo(telefono, correo)
        if existente and not confirmar_distinta_persona:
            raise PosibleDuplicado(
                "Ya existe un expediente activo con ese teléfono o correo: "
                f"{existente.nombre} (expediente {existente.id}). "
                "Revise si es la misma persona antes de crear uno nuevo"
            )

        propietario = PropietarioRow(
            nombre=nombre.strip(), telefono=telefono, correo=correo, activo=True
        )
        self.session.add(propietario)
        self.session.flush()
        return propietario


# --------------------------------------------------------------------------
# Ejercicio separado: recordatorio de vacuna con adaptador simulado
# --------------------------------------------------------------------------
class RecordatorioService:
    """El notificador (SMS, WhatsApp o correo) es un servicio externo: se
    recibe como colaborador para poder sustituirlo por un Mock en las pruebas."""

    def __init__(self, notificador, dias_aviso=3):
        self.notificador = notificador
        self.dias_aviso = dias_aviso

    def enviar_recordatorio_vacuna(
        self, telefono, mascota, fecha_refuerzo: date, hoy: date, ya_aplicada=False
    ):
        if ya_aplicada:
            return False
        if (fecha_refuerzo - hoy).days > self.dias_aviso:
            return False
        self.notificador.enviar(
            telefono,
            f"Recordatorio: el refuerzo de vacuna de {mascota} vence el "
            f"{fecha_refuerzo:%d/%m/%Y}. Agende su cita en VetCare 24",
        )
        return True
