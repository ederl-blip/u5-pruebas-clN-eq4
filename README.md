# Unidad 5 CLN: Integración, pruebas y calidad

Actividad 5 de **Componentes de lógica de negocio** (FIME, UANL), Equipo 4.

Proyecto en Python que practica pruebas unitarias, pruebas de integración con
SQLAlchemy, un Mock de pasarela de pago, autorización por reglas de negocio,
cobertura de pruebas y un pipeline de integración continua (GitHub Actions).
Incluye la aplicación del método a tres reglas del PIA **VetCare 24**.

## Requisitos

- Windows con PowerShell (los comandos son equivalentes en otros sistemas)
- Python 3.11 (probado con 3.11.9)
- Dependencias en `requirements.txt`: pytest, pytest-cov, Ruff y SQLAlchemy

## Instalación

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si PowerShell bloquea la activación del entorno virtual:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

Cuando el entorno está activo, el prompt muestra `(.venv)` al inicio.

## Comandos

| Qué hacer | Comando |
|---|---|
| Ejecutar todas las pruebas | `python -m pytest -v` |
| Ejecutar un archivo | `python -m pytest tests/test_vetcare.py -v` |
| Ejecutar una prueba | `python -m pytest tests/test_order.py::test_cannot_confirm_twice -v` |
| Revisar estilo | `python -m ruff check src tests` |
| Cobertura con reporte HTML | `python -m pytest -v --cov=src --cov-report=term-missing --cov-report=html --cov-fail-under=80` |
| Abrir el reporte HTML (Windows) | `start htmlcov\index.html` |

Resultado esperado: **43 pruebas aprobadas** y cobertura total de **100 %**
(el umbral exigido es 80 %).

## Estructura

```
src/
  domain.py        Pedido (Order): descuento VIP, total válido, deuda, doble confirmación
  application.py   OrderService: cobro mediante una pasarela de pago (puerto)
  repository.py    Repositorio de pedidos con SQLAlchemy (commit y rollback)
  security.py      Política de permisos para cancelar un pedido
  vetcare.py       Reglas del PIA VetCare 24 (alergias, urgencias, duplicados)
tests/
  test_order.py        Unitarias del dominio (incluye el caso TDD)
  test_security.py     Unitarias de la política de permisos
  test_repository.py   Integración con SQLite en memoria
  test_service.py      Servicio de pago con Mock de la pasarela
  test_vetcare.py      Reglas de VetCare 24, persistencia y Mock del notificador
docs/
  matriz_casos_vetcare.csv   Matriz de casos de prueba del PIA
.github/workflows/ci.yml     Pipeline de integración continua
```

## Arquitectura

El código separa responsabilidades en capas, de modo que cada regla se pueda
probar sin depender de lo demás:

- **Dominio** (`domain.py`, `security.py`): reglas de negocio puras, sin base de
  datos ni red. Se prueban con pruebas unitarias rápidas.
- **Aplicación** (`application.py`): orquesta el caso de uso y recibe la
  pasarela de pago como colaborador. En las pruebas se sustituye por un `Mock`,
  por lo que nunca se hace un cargo real.
- **Persistencia** (`repository.py`): guarda con SQLAlchemy. Las pruebas usan
  SQLite en memoria o en un archivo temporal para comprobar commit y rollback.
- **VetCare 24** (`vetcare.py`): entidades, servicios y persistencia de las
  reglas del PIA. El aviso de recordatorio de vacuna recibe el notificador
  externo como colaborador, por lo que se prueba con un Mock.

## Pruebas de VetCare 24 (PIA)

| Regla | Éxito | Error | Límite |
|---|---|---|---|
| US-11 Bloqueo farmacológico por alergias | CP-01 | CP-02 | CP-03 |
| US-06 Interrupción de agenda por urgencias | CP-04 | CP-05 | CP-06 |
| US-13 Prevención de expedientes duplicados | CP-07 | CP-08 | CP-09 |

Más casos derivados: persistencia entre sesiones y rollback (CP-10), perfil
inactivo (CP-11) y recordatorio de vacuna con Mock (CP-12). La matriz completa
está en `docs/matriz_casos_vetcare.csv`; cada prueba lleva en su nombre el ID
del caso.

## Integración continua

El workflow **CI Business Logic** (`.github/workflows/ci.yml`) se ejecuta en
cada push: instala dependencias, revisa el estilo con Ruff, ejecuta las pruebas
con cobertura mínima de 80 % (`python -m pytest`) y compila `src/`. Si un paso
falla, los siguientes se omiten.

Nota: que el pipeline marque rojo no bloquea por sí solo la integración de un
cambio. Para impedir el merge hay que configurar branch protection en GitHub.

## Limitaciones conocidas

- En `OrderService.checkout()` el pedido se confirma antes de cobrar. Si la
  pasarela rechaza el pago, el pedido queda en estado `CONFIRMED`. Una prueba
  documenta este comportamiento y la propuesta de mejora es cobrar primero y
  confirmar después.
- La cobertura mide qué líneas se ejecutan, no si todos los escenarios están
  probados. Faltan casos como una pasarela que falle con una excepción.

## Uso de IA

Se usó un asistente de IA (Claude) como apoyo para la guía del laboratorio, los
borradores del código y de las pruebas de VetCare 24 y la redacción. Todo se
verificó ejecutando las pruebas, Ruff, la cobertura y el pipeline, y las reglas
se validaron contra la documentación del equipo.
