"""Respuestas de los paquetes para radicar (API §19). El detalle de los documentos sale
del manifiesto interno, que es solo para uso interno: nunca la clave del objeto."""

from rest_framework import serializers

from apps.crm.serializers import UserRefSerializer
from apps.documents.models import DocumentPackageJob, PackageJobStatus


class CodeNameSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class PackageHolderSerializer(serializers.Serializer):
    scope = serializers.CharField(help_text="`APPLICATION` o `PARTICIPANT`.")
    participant_id = serializers.UUIDField(allow_null=True)
    role = serializers.CharField(allow_null=True)
    role_name = serializers.CharField(allow_null=True)
    full_name = serializers.CharField(allow_null=True)
    folder = serializers.CharField(help_text="Carpeta dentro del ZIP.")


class PackageFileSerializer(serializers.Serializer):
    path = serializers.CharField(help_text="Ruta dentro del ZIP.")
    document_file_id = serializers.UUIDField()
    version_number = serializers.IntegerField()
    client_filename = serializers.CharField()
    mime_type = serializers.CharField()
    size_bytes = serializers.IntegerField()
    sha256 = serializers.CharField()


class PackageDocumentSerializer(serializers.Serializer):
    slot_id = serializers.UUIDField()
    document_type = CodeNameSerializer()
    # Choca con `Field.label` de los stubs de DRF (mismo `type: ignore` que
    # `CatalogItemRefSerializer`): el campo de la API se llama así.
    label = serializers.CharField()  # type: ignore[assignment]
    holder = PackageHolderSerializer()
    status = serializers.CharField(help_text="`APPROVED` o `WAIVED` (sin archivo).")
    document_date = serializers.DateField(allow_null=True)
    expires_at = serializers.DateField(allow_null=True)
    file = PackageFileSerializer(allow_null=True)
    waiver_reason = CodeNameSerializer(allow_null=True)


class PackageOutputSerializer(serializers.Serializer):
    filename = serializers.CharField(source="original_filename")
    size_bytes = serializers.IntegerField()
    sha256 = serializers.CharField()


class DocumentPackageJobSerializer(serializers.ModelSerializer):
    application_id = serializers.UUIDField(read_only=True)
    status = serializers.ChoiceField(
        source="effective_status",
        choices=PackageJobStatus.choices,
        read_only=True,
        help_text="`EXPIRED` en cuanto pasa `expires_at`, aunque el comando no haya corrido.",
    )
    requested_by = UserRefSerializer(read_only=True)
    fingerprint = serializers.CharField(
        source="manifest.fingerprint",
        read_only=True,
        help_text="Huella documental al pedir el paquete.",
    )
    output = PackageOutputSerializer(
        source="output_file_object",
        read_only=True,
        allow_null=True,
        help_text="El ZIP, cuando el paquete terminó.",
    )
    documents = PackageDocumentSerializer(source="manifest.documents", many=True, read_only=True)

    class Meta:
        model = DocumentPackageJob
        fields = [
            "id",
            "application_id",
            "application_version",
            "status",
            "error_code",
            "fingerprint",
            "requested_by",
            "created_at",
            "started_at",
            "completed_at",
            "expires_at",
            "output",
            "documents",
        ]
        read_only_fields = fields
