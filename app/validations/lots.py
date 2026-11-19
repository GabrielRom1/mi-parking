def validate_edit_payload(payload):
    """Validate and normalize the JSON payload for editing an existing lot."""
    if not isinstance(payload, dict):
        return None, {"form": "El cuerpo de la solicitud debe ser un objeto JSON."}

    name = payload.get("name")
    location = payload.get("location")
    if not isinstance(name, str) or not name.strip():
        return None, {"name": "Introduce el nombre del lote."}
    if len(name.strip()) > 100:
        return None, {"name": "Usa 100 caracteres o menos."}
    if not isinstance(location, str) or not location.strip():
        return None, {"location": "Introduce la ubicación."}
    if len(location.strip()) > 255:
        return None, {"location": "Usa 255 caracteres o menos."}
    if not isinstance(payload.get("is_paid"), bool):
        return None, {"is_paid": "Indica si el lote es pago."}

    floors = payload.get("floors")
    if not isinstance(floors, list):
        return None, {"floors": "La lista de pisos no es válida."}

    normalized_floors = []
    for index, floor in enumerate(floors):
        prefix = f"floors-{index}-"
        if not isinstance(floor, dict):
            return None, {prefix + "capacity": "Los datos del piso no son válidos."}

        floor_id = floor.get("id")
        if floor_id is not None and (
            isinstance(floor_id, bool)
            or not isinstance(floor_id, int)
            or floor_id < 1
        ):
            return None, {prefix + "id": "El identificador del piso no es válido."}

        capacity = floor.get("capacity")
        accessible_capacity = floor.get("accessible_capacity")
        if (
            isinstance(capacity, bool)
            or not isinstance(capacity, int)
            or capacity < 0
        ):
            return None, {prefix + "capacity": "Introduce 0 o más."}
        if (
            isinstance(accessible_capacity, bool)
            or not isinstance(accessible_capacity, int)
            or accessible_capacity < 0
        ):
            return None, {prefix + "accessible_capacity": "Introduce 0 o más."}
        if accessible_capacity > capacity:
            return None, {
                prefix
                + "accessible_capacity": (
                    f"No puede exceder la capacidad del piso ({capacity})."
                )
            }

        role_id = floor.get("role_id")
        if role_id == "":
            role_id = None
        if role_id is not None and (
            isinstance(role_id, bool)
            or not isinstance(role_id, int)
            or role_id < 1
        ):
            return None, {prefix + "role_id": "Selecciona un rol válido."}

        normalized_floors.append(
            {
                "id": floor_id,
                "capacity": capacity,
                "accessible_capacity": accessible_capacity,
                "role_id": role_id,
            }
        )

    return {
        "name": name.strip(),
        "location": location.strip(),
        "is_paid": payload["is_paid"],
        "floors": normalized_floors,
    }, None
