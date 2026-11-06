"""Pruebas de las reglas de negocio de VetCare 24 (PIA).

Cada prueba lleva en su nombre el ID del caso de la matriz
docs/matriz_casos_vetcare.csv (CP-01 ... CP-12).
"""

import csv
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.vetcare import (
    Agenda,
    AgendaExcedeCierre,
    AlergiaDetectada,
    Cita,
    ExpedienteService,
    Mascota,
    Medicamento,
    PosibleDuplicado,
    PropietarioRow,
    RecetaRow,
    RecetaService,
    RecordatorioService,
    UrgenciaIncompleta,
    make_vet_engine,
)


@pytest.fixture
def session():
    engine = make_vet_engine()
    with Session(engine) as s:
        yield s
    engine.dispose()


# ---------------------------------------------------------------------------
# Regla 1: Bloqueo farmacológico por alergias (US-11)
# ---------------------------------------------------------------------------
def test_cp01_receta_sin_alergia_se_guarda(session):
    # Arrange
    luna = Mascota(1, "Luna", {"penicilina"})
    meloxicam = Medicamento("Meloxicam", frozenset({"meloxicam"}))
    # Act
    receta = RecetaService(session).prescribir(luna, meloxicam)
    # Assert
    assert receta.con_alerta is False
    assert receta.autorizada_por is None
    assert session.scalar(select(func.count()).select_from(RecetaRow)) == 1


def test_cp02_receta_con_alergia_se_bloquea(session):
    luna = Mascota(1, "Luna", {"Penicilina"})
    penicilina = Medicamento("Penicilina G", frozenset({"penicilina"}))

    with pytest.raises(AlergiaDetectada, match="alérgica a penicilina"):
        RecetaService(session).prescribir(luna, penicilina)

    assert session.scalar(select(func.count()).select_from(RecetaRow)) == 0


def test_cp03_alergia_confirmada_deja_constancia(session):
    luna = Mascota(1, "Luna", {"penicilina"})
    penicilina = Medicamento("Penicilina G", frozenset({"penicilina"}))

    receta = RecetaService(session).prescribir(
        luna, penicilina, confirmar_conscientemente=True, veterinario="Dra. Ruiz"
    )

    assert receta.con_alerta is True
    assert receta.autorizada_por == "Dra. Ruiz"
    guardada = session.scalar(select(RecetaRow))
    assert guardada.autorizada_por == "Dra. Ruiz"


def test_cp03b_confirmar_sin_veterinario_se_rechaza(session):
    luna = Mascota(1, "Luna", {"penicilina"})
    penicilina = Medicamento("Penicilina G", frozenset({"penicilina"}))

    with pytest.raises(ValueError, match="veterinario que la autoriza"):
        RecetaService(session).prescribir(
            luna, penicilina, confirmar_conscientemente=True
        )

    assert session.scalar(select(func.count()).select_from(RecetaRow)) == 0


# ---------------------------------------------------------------------------
# Regla 2: Interrupción de agenda por urgencias (US-06)
# ---------------------------------------------------------------------------
CIERRE = datetime(2026, 11, 6, 20, 0)
AHORA = datetime(2026, 11, 6, 10, 10)


def _agenda(fin_ultima=datetime(2026, 11, 6, 11, 30)):
    citas = [
        Cita(1, 101, datetime(2026, 11, 6, 10, 0), datetime(2026, 11, 6, 10, 30)),
        Cita(2, 102, datetime(2026, 11, 6, 10, 30), datetime(2026, 11, 6, 11, 0)),
        Cita(3, 103, datetime(2026, 11, 6, 11, 0), fin_ultima),
    ]
    return Agenda(citas, CIERRE)


def test_cp04_urgencia_pausa_turno_y_recorre_agenda():
    agenda = _agenda()

    urgencia = agenda.registrar_urgencia(500, "Atropellamiento", AHORA)

    assert urgencia.motivo == "Atropellamiento"
    assert agenda.citas[0].estado == "PAUSADA"
    assert agenda.citas[1].inicio == datetime(2026, 11, 6, 10, 50)
    assert agenda.citas[2].fin == datetime(2026, 11, 6, 11, 50)


@pytest.mark.parametrize(
    ("mascota_id", "motivo", "falta"),
    [
        (None, "Convulsiones", "el identificador de la mascota"),
        (500, "   ", "el motivo de consulta"),
    ],
    ids=["sin_mascota", "sin_motivo"],
)
def test_cp05_urgencia_sin_datos_criticos_se_bloquea(mascota_id, motivo, falta):
    agenda = _agenda()
    inicio_original = agenda.citas[1].inicio

    with pytest.raises(UrgenciaIncompleta, match=falta):
        agenda.registrar_urgencia(mascota_id, motivo, AHORA)

    assert agenda.citas[0].estado == "PROGRAMADA"
    assert agenda.citas[1].inicio == inicio_original


def test_cp06_ultima_cita_termina_exactamente_al_cierre():
    # La última cita termina a las 19:40; con +20 min termina a las 20:00.
    agenda = _agenda(fin_ultima=datetime(2026, 11, 6, 19, 40))

    agenda.registrar_urgencia(500, "Intoxicación", AHORA)

    assert agenda.citas[2].fin == CIERRE


def test_cp06b_un_minuto_despues_del_cierre_se_rechaza():
    # Termina a las 19:41; con +20 min terminaría a las 20:01.
    agenda = _agenda(fin_ultima=datetime(2026, 11, 6, 19, 41))
    fin_original = agenda.citas[2].fin

    with pytest.raises(AgendaExcedeCierre, match="20:01"):
        agenda.registrar_urgencia(500, "Intoxicación", AHORA)

    assert agenda.citas[2].fin == fin_original
    assert agenda.citas[0].estado == "PROGRAMADA"


def test_urgencia_sin_citas_pendientes_no_mueve_nada():
    agenda = Agenda([], CIERRE, desplazamiento=timedelta(minutes=15))

    urgencia = agenda.registrar_urgencia(500, "Fractura", AHORA)

    assert urgencia.llegada == AHORA
    assert agenda.citas == []


# ---------------------------------------------------------------------------
# Regla 3: Prevención de expedientes duplicados (US-13)
# ---------------------------------------------------------------------------
def test_cp07_propietario_nuevo_crea_expediente(session):
    servicio = ExpedienteService(session)

    nuevo = servicio.registrar_propietario(
        "Ana Torres", "81 1234 5678", "Ana@Correo.com"
    )

    assert nuevo.id is not None
    assert nuevo.telefono == "8112345678"
    assert nuevo.correo == "ana@correo.com"


@pytest.mark.parametrize(
    ("telefono", "correo"),
    [("(81) 1234-5678", None), ("55 0000 0000", "ANA@correo.com")],
    ids=["mismo_telefono", "mismo_correo"],
)
def test_cp08_duplicado_se_detiene(session, telefono, correo):
    servicio = ExpedienteService(session)
    servicio.registrar_propietario("Ana Torres", "8112345678", "ana@correo.com")

    with pytest.raises(PosibleDuplicado, match="Ya existe un expediente activo"):
        servicio.registrar_propietario("Ana T.", telefono, correo)

    total = session.scalar(select(func.count()).select_from(PropietarioRow))
    assert total == 1


def test_cp09_familiares_confirmados_crean_expediente_independiente(session):
    servicio = ExpedienteService(session)
    madre = servicio.registrar_propietario("Rosa Gómez", "8112345678")

    hijo = servicio.registrar_propietario(
        "Luis Gómez", "8112345678", confirmar_distinta_persona=True
    )

    assert hijo.id != madre.id
    total = session.scalar(select(func.count()).select_from(PropietarioRow))
    assert total == 2


def test_cp11_perfil_inactivo_no_bloquea_el_registro(session):
    servicio = ExpedienteService(session)
    antiguo = servicio.registrar_propietario("Pedro Ruiz", "8199999999")
    antiguo.activo = False
    session.flush()

    nuevo = servicio.registrar_propietario("Pedro Ruiz Jr.", "8199999999")

    assert nuevo.id != antiguo.id


def test_registro_sin_telefono_ni_correo_no_se_considera_duplicado(session):
    servicio = ExpedienteService(session)
    primero = servicio.registrar_propietario("Sin Contacto Uno")

    segundo = servicio.registrar_propietario("Sin Contacto Dos")

    assert segundo.id != primero.id


# ---------------------------------------------------------------------------
# Persistencia: los datos sobreviven entre sesiones y rollback los descarta
# ---------------------------------------------------------------------------
def test_cp10_persistencia_entre_sesiones(tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'vetcare.db'}"
    engine = make_vet_engine(url)

    with Session(engine) as primera:
        ExpedienteService(primera).registrar_propietario("Ana Torres", "8112345678")
        primera.commit()

    with Session(engine) as segunda:
        guardado = segunda.scalar(select(PropietarioRow))
        assert guardado.nombre == "Ana Torres"
        assert guardado.telefono == "8112345678"
    engine.dispose()


def test_cp10b_rollback_descarta_el_expediente(tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'vetcare.db'}"
    engine = make_vet_engine(url)

    with Session(engine) as primera:
        ExpedienteService(primera).registrar_propietario("Ana Torres", "8112345678")
        primera.rollback()

    with Session(engine) as segunda:
        total = segunda.scalar(select(func.count()).select_from(PropietarioRow))
        assert total == 0
    engine.dispose()


# ---------------------------------------------------------------------------
# Ejercicio separado: recordatorio de vacuna con adaptador simulado (Mock)
# ---------------------------------------------------------------------------
def test_cp12_recordatorio_se_envia_al_notificador_simulado():
    notificador = Mock()
    servicio = RecordatorioService(notificador)

    enviado = servicio.enviar_recordatorio_vacuna(
        "8112345678", "Luna", date(2026, 11, 8), hoy=date(2026, 11, 5)
    )

    assert enviado is True
    notificador.enviar.assert_called_once()
    telefono, mensaje = notificador.enviar.call_args.args
    assert telefono == "8112345678"
    assert "Luna" in mensaje
    assert "08/11/2026" in mensaje


def test_cp12b_vacuna_ya_aplicada_no_envia_notificacion():
    notificador = Mock()
    servicio = RecordatorioService(notificador)

    enviado = servicio.enviar_recordatorio_vacuna(
        "8112345678",
        "Luna",
        date(2026, 11, 10),
        hoy=date(2026, 11, 5),
        ya_aplicada=True,
    )

    assert enviado is False
    notificador.enviar.assert_not_called()


def test_cp12c_a_cuatro_dias_aun_no_se_envia():
    notificador = Mock()
    servicio = RecordatorioService(notificador)

    enviado = servicio.enviar_recordatorio_vacuna(
        "8112345678", "Luna", date(2026, 11, 9), hoy=date(2026, 11, 5)
    )

    assert enviado is False
    notificador.enviar.assert_not_called()


# ---------------------------------------------------------------------------
# La matriz CSV está ligada a las pruebas reales
# ---------------------------------------------------------------------------
def test_matriz_csv_tiene_al_menos_nueve_casos_y_sus_pruebas_existen():
    ruta = Path(__file__).resolve().parent.parent / "docs" / "matriz_casos_vetcare.csv"
    with open(ruta, newline="", encoding="utf-8-sig") as archivo:
        filas = list(csv.DictReader(archivo))

    assert len(filas) >= 9
    for fila in filas:
        assert fila["Prueba"] in globals(), f"No existe la prueba {fila['Prueba']}"
