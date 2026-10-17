"""Contratos e implementaciones en memoria de los repositorios."""

from abc import ABC, abstractmethod
from datetime import date, datetime

from modelos import CitaMedica, RegistroAuditoria, RegistroListaEspera, Sede, Usuario


class IUsuarioRepository(ABC):
    """Define las operaciones de almacenamiento de usuarios."""
    @abstractmethod
    def guardar(self, usuario: Usuario) -> bool: """Guarda un usuario y retorna el resultado."""
    @abstractmethod
    def buscar_por_id(self, identificador: str) -> Usuario | None: """Busca un usuario por su identificador."""
    @abstractmethod
    def buscar_por_correo(self, correo: str) -> Usuario | None: """Busca un usuario por correo."""
    @abstractmethod
    def buscar_por_documento(self, numero_documento: str) -> Usuario | None: """Busca un usuario por documento."""
    @abstractmethod
    def buscar_por_documento_o_nombre(self, termino: str) -> list[Usuario]: """Busca por documento o nombres."""
    @abstractmethod
    def obtener_activos(self) -> list[Usuario]: """Obtiene los usuarios activos."""
    @abstractmethod
    def obtener_todos(self) -> list[Usuario]: """Obtiene todos los usuarios sin filtrar por estado."""
    @abstractmethod
    def existe_documento_o_correo(self, documento: str, correo: str) -> bool: """Comprueba duplicidad de documento o correo."""


class ICitaRepository(ABC):
    """Define las operaciones de almacenamiento de citas."""
    @abstractmethod
    def guardar(self, cita: CitaMedica) -> bool: """Guarda una cita y retorna el resultado."""
    @abstractmethod
    def buscar_por_id(self, identificador: str) -> CitaMedica | None: """Busca una cita por identificador."""
    @abstractmethod
    def obtener_por_paciente(self, id_paciente: str) -> list[CitaMedica]: """Obtiene las citas de un paciente."""
    @abstractmethod
    def obtener_por_medico_y_fecha(self, id_medico: str, fecha: date) -> list[CitaMedica]: """Obtiene citas de médico por fecha."""
    @abstractmethod
    def obtener_por_sede_medico_fecha(self, id_sede: str, id_medico: str, fecha: date) -> list[CitaMedica]: """Obtiene citas por sede, médico y fecha."""
    @abstractmethod
    def existe_cita_en_horario(self, id_medico: str, fecha_hora: datetime) -> bool: """Comprueba una cita de médico en horario."""
    @abstractmethod
    def existe_cita_paciente_en_horario(self, id_paciente: str, fecha_hora: datetime) -> bool: """Comprueba una cita de paciente en horario."""
    @abstractmethod
    def contar_citas_medico_en_fecha(self, id_medico: str, fecha: date) -> int: """Cuenta citas de médico por fecha."""
    @abstractmethod
    def obtener_todas(self) -> list[CitaMedica]: """Obtiene todas las citas registradas."""
    @abstractmethod
    def obtener_futuras_por_medico(self, id_medico: str) -> list[CitaMedica]: """Obtiene citas futuras vigentes de un médico."""


class ISedeRepository(ABC):
    """Define las operaciones de almacenamiento de sedes."""
    @abstractmethod
    def guardar(self, sede: Sede) -> bool: """Guarda o actualiza una sede."""
    @abstractmethod
    def buscar_por_id(self, identificador: str) -> Sede | None: """Busca una sede por identificador."""
    @abstractmethod
    def buscar_por_nombre(self, nombre: str) -> Sede | None: """Busca una sede por su nombre."""
    @abstractmethod
    def obtener_todas(self) -> list[Sede]: """Obtiene todas las sedes registradas."""


class IListaEsperaRepository(ABC):
    """Define las operaciones de almacenamiento de la lista de espera."""
    @abstractmethod
    def guardar(self, registro: RegistroListaEspera) -> bool: """Guarda una solicitud en espera."""
    @abstractmethod
    def buscar_por_id(self, identificador: str) -> RegistroListaEspera | None: """Busca una solicitud por identificador."""
    @abstractmethod
    def eliminar(self, identificador: str) -> bool: """Elimina una solicitud de la lista de espera."""
    @abstractmethod
    def obtener_todas(self) -> list[RegistroListaEspera]: """Obtiene todas las solicitudes vigentes."""


class IAuditoriaRepository(ABC):
    """Define las operaciones de almacenamiento de la bitácora de auditoría."""
    @abstractmethod
    def registrar(self, registro: RegistroAuditoria) -> bool: """Agrega un evento a la bitácora."""
    @abstractmethod
    def obtener_por_rango(self, fecha_inicio: date, fecha_fin: date, id_sede: str = "") -> list[RegistroAuditoria]: """Obtiene eventos de un rango de fechas."""


class UsuarioRepositoryMemory(IUsuarioRepository):
    """Almacena usuarios en memoria usando un diccionario."""
    def __init__(self) -> None:
        """Inicializa el almacenamiento vacío."""
        self._usuarios: dict[str, Usuario] = {}

    def guardar(self, usuario: Usuario) -> bool:
        """Guarda o actualiza un usuario.

        Parámetros:
            usuario: Usuario a almacenar.
        Retorna:
            Verdadero al guardar.
        """
        self._usuarios[usuario.id] = usuario
        return True

    def buscar_por_id(self, identificador: str) -> Usuario | None:
        """Busca un usuario por identificador.

        Parámetros:
            identificador: UUID del usuario.
        Retorna:
            Usuario encontrado o ninguno.
        """
        return self._usuarios.get(identificador)

    def buscar_por_correo(self, correo: str) -> Usuario | None:
        """Busca un usuario ignorando mayúsculas en correo."""
        return next((u for u in self._usuarios.values() if u.correo.lower() == correo.lower()), None)

    def buscar_por_documento(self, numero_documento: str) -> Usuario | None:
        """Busca un usuario por número de documento."""
        return next((u for u in self._usuarios.values() if u.numero_documento == numero_documento), None)

    def buscar_por_documento_o_nombre(self, termino: str) -> list[Usuario]:
        """Busca coincidencias insensibles a mayúsculas.

        Parámetros:
            termino: Texto de documento o nombres.
        Retorna:
            Usuarios coincidentes.
        """
        texto = termino.lower()
        return [u for u in self._usuarios.values() if texto in u.numero_documento.lower() or texto in u.nombres.lower()]

    def obtener_activos(self) -> list[Usuario]:
        """Retorna todos los usuarios activos."""
        from enums import EstadoUsuario
        return [u for u in self._usuarios.values() if u.estado == EstadoUsuario.ACTIVO]

    def obtener_todos(self) -> list[Usuario]:
        """Retorna todos los usuarios registrados, sin filtrar por estado."""
        return list(self._usuarios.values())

    def existe_documento_o_correo(self, documento: str, correo: str) -> bool:
        """Indica si el documento o el correo ya están registrados."""
        return any(u.numero_documento == documento or u.correo.lower() == correo.lower() for u in self._usuarios.values())


class CitaRepositoryMemory(ICitaRepository):
    """Almacena citas en memoria usando un diccionario."""
    def __init__(self) -> None:
        """Inicializa el almacenamiento vacío."""
        self._citas: dict[str, CitaMedica] = {}

    def guardar(self, cita: CitaMedica) -> bool:
        """Guarda o actualiza una cita."""
        self._citas[cita.id] = cita
        return True

    def buscar_por_id(self, identificador: str) -> CitaMedica | None:
        """Busca una cita por identificador."""
        return self._citas.get(identificador)

    def obtener_por_paciente(self, id_paciente: str) -> list[CitaMedica]:
        """Obtiene las citas pertenecientes a un paciente."""
        return [c for c in self._citas.values() if c.id_paciente == id_paciente]

    def obtener_por_medico_y_fecha(self, id_medico: str, fecha: date) -> list[CitaMedica]:
        """Obtiene citas de un médico en una fecha."""
        return [c for c in self._citas.values() if c.id_medico == id_medico and c.fecha_hora.date() == fecha]

    def obtener_por_sede_medico_fecha(self, id_sede: str, id_medico: str, fecha: date) -> list[CitaMedica]:
        """Obtiene citas filtradas por sede, médico y fecha."""
        return [c for c in self._citas.values() if c.id_sede == id_sede and c.id_medico == id_medico and c.fecha_hora.date() == fecha]

    def existe_cita_en_horario(self, id_medico: str, fecha_hora: datetime) -> bool:
        """Indica si un médico tiene una cita no cancelada a esa hora."""
        from enums import EstadoCita
        return any(c.id_medico == id_medico and c.fecha_hora == fecha_hora and c.estado_cita != EstadoCita.CANCELADA for c in self._citas.values())

    def existe_cita_paciente_en_horario(self, id_paciente: str, fecha_hora: datetime) -> bool:
        """Indica si un paciente tiene una cita no cancelada a esa hora."""
        from enums import EstadoCita
        return any(c.id_paciente == id_paciente and c.fecha_hora == fecha_hora and c.estado_cita != EstadoCita.CANCELADA for c in self._citas.values())

    def contar_citas_medico_en_fecha(self, id_medico: str, fecha: date) -> int:
        """Cuenta las citas no canceladas de un médico durante una fecha."""
        from enums import EstadoCita
        return sum(c.id_medico == id_medico and c.fecha_hora.date() == fecha and c.estado_cita != EstadoCita.CANCELADA for c in self._citas.values())

    def obtener_todas(self) -> list[CitaMedica]:
        """Obtiene todas las citas almacenadas."""
        return list(self._citas.values())

    def obtener_futuras_por_medico(self, id_medico: str) -> list[CitaMedica]:
        """Obtiene las citas futuras programadas o confirmadas de un médico."""
        from enums import EstadoCita
        ahora = datetime.now()
        return [c for c in self._citas.values() if c.id_medico == id_medico and c.fecha_hora > ahora and c.estado_cita in (EstadoCita.PROGRAMADA, EstadoCita.CONFIRMADA)]


class SedeRepositoryMemory(ISedeRepository):
    """Almacena sedes en memoria conservando el orden de creación."""
    def __init__(self) -> None:
        """Inicializa el almacenamiento vacío."""
        self._sedes: dict[str, Sede] = {}

    def guardar(self, sede: Sede) -> bool:
        """Guarda o actualiza una sede."""
        self._sedes[sede.id] = sede
        return True

    def buscar_por_id(self, identificador: str) -> Sede | None:
        """Busca una sede por identificador."""
        return self._sedes.get(identificador)

    def buscar_por_nombre(self, nombre: str) -> Sede | None:
        """Busca una sede por nombre ignorando mayúsculas."""
        return next((s for s in self._sedes.values() if s.nombre.lower() == nombre.strip().lower()), None)

    def obtener_todas(self) -> list[Sede]:
        """Obtiene todas las sedes registradas."""
        return list(self._sedes.values())


class AuditoriaRepositoryMemory(IAuditoriaRepository):
    """Almacena la bitácora de auditoría en memoria."""
    def __init__(self) -> None:
        """Inicializa la bitácora vacía."""
        self._registros: list[RegistroAuditoria] = []

    def registrar(self, registro: RegistroAuditoria) -> bool:
        """Agrega un evento a la bitácora."""
        self._registros.append(registro)
        return True

    def obtener_por_rango(self, fecha_inicio: date, fecha_fin: date, id_sede: str = "") -> list[RegistroAuditoria]:
        """Obtiene los eventos de un rango, opcionalmente filtrados por sede.

        Parámetros:
            fecha_inicio: Inicio inclusivo del rango.
            fecha_fin: Fin inclusivo del rango.
            id_sede: Sede a filtrar; vacío consulta todas.
        Retorna:
            Eventos ordenados del más reciente al más antiguo.
        """
        seleccion = [r for r in self._registros if fecha_inicio <= r.fecha_hora.date() <= fecha_fin and (not id_sede or r.id_sede == id_sede)]
        return sorted(seleccion, key=lambda registro: registro.fecha_hora, reverse=True)


class ListaEsperaRepositoryMemory(IListaEsperaRepository):
    """Almacena la lista de espera en memoria conservando el orden de llegada."""
    def __init__(self) -> None:
        """Inicializa el almacenamiento vacío."""
        self._registros: dict[str, RegistroListaEspera] = {}

    def guardar(self, registro: RegistroListaEspera) -> bool:
        """Guarda una solicitud en espera."""
        self._registros[registro.id] = registro
        return True

    def buscar_por_id(self, identificador: str) -> RegistroListaEspera | None:
        """Busca una solicitud por identificador."""
        return self._registros.get(identificador)

    def eliminar(self, identificador: str) -> bool:
        """Elimina una solicitud de la lista de espera."""
        return self._registros.pop(identificador, None) is not None

    def obtener_todas(self) -> list[RegistroListaEspera]:
        """Obtiene todas las solicitudes vigentes, en el orden en que se registraron."""
        return sorted(self._registros.values(), key=lambda registro: registro.fecha_solicitud)
