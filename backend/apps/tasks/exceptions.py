from rest_framework import status

from config.exceptions import ApiError


class TaskNotPending(ApiError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "TASK_NOT_PENDING"
    default_detail = "La tarea ya está completada o cancelada: no se puede cambiar."
