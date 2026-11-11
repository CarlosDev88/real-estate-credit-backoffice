"""Paquete para radicar: pedido, nombres, manifiestos y worker (decisiones 14, 15 y 36 a
42)."""

import hashlib
import io
import json
import threading
import uuid
import zipfile
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any, BinaryIO

import pytest
from botocore.exceptions import ReadTimeoutError
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.applications.exceptions import ApplicationClosed, ApplicationNotReady
from apps.applications.models import (
    ApplicationParticipant,
    BankRuleEvaluation,
    CreditApplication,
)
from apps.catalogs.workflow import ApplicationStatus
from apps.crm.models import Client
from apps.documents import packages, tasks
from apps.documents.exceptions import StorageUnavailable
from apps.documents.fingerprint import dossier_fingerprint
from apps.documents.models import (
    ApplicationDocumentSlot,
    DocumentPackageJob,
    DocumentType,
    FileObject,
    PackageJobStatus,
    ScanStatus,
    SlotStatus,
)
from apps.documents.packages import (
    CHECKSUM_MISMATCH,
    STORAGE_UNAVAILABLE,
    ZIP,
    build_package,
    participant_folder,
    request_package,
    safe_name,
)
from apps.documents.storage import MemoryStorage, get_storage
from apps.identity.models import User
from config import celery_app
from tests.applications.buyer_access.conftest import set_status
from tests.applications.conftest import seeded_product
from tests.applications.dossier.conftest import (
    ApproveStored,
    PackageDossier,
    SlotFactory,
)

pytestmark = pytest.mark.django_db

EXPECTED_PATHS = [
    "00_SOLICITUD/Documento_de_propiedad_o_soporte_equivalente.pdf",
    "01_TITULAR_Laura_Gomez/Copia_del_documento_de_identidad.pdf",
    "01_TITULAR_Laura_Gomez/Desprendible_o_comprobante_de_nomina_1_de_2.pdf",
    "01_TITULAR_Laura_Gomez/Desprendible_o_comprobante_de_nomina_2_de_2.png",
    "02_COSOLICITANTE_Andres_Moreno/Copia_del_documento_de_identidad.jpg",
]


def memory() -> MemoryStorage:
    storage = get_storage()
    assert isinstance(storage, MemoryStorage)
    return storage


def package_keys() -> list[str]:
    return [key for key in memory().objects if key.startswith("packages/")]


def reload(job: DocumentPackageJob) -> DocumentPackageJob:
    return DocumentPackageJob.objects.select_related("output_file_object").get(pk=job.pk)


def output_key(job: DocumentPackageJob) -> str:
    output = reload(job).output_file_object
    assert output is not None
    return output.object_key


def zip_of(job: DocumentPackageJob) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(memory().objects[output_key(job)][0]))


def doc_type(code: str) -> DocumentType:
    return DocumentType.objects.get(code=code)


def custom_type(code: str, name: str) -> DocumentType:
    return DocumentType.objects.create(
        code=code,
        name=name,
        allowed_mime_types=["application/pdf"],
        max_size_bytes=1024 * 1024,
    )


@pytest.fixture
def requested(package_dossier: PackageDossier, advisor_user: User) -> DocumentPackageJob:
    return request_package(advisor_user, package_dossier.application).job


@pytest.fixture
def eager_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin propagar, ``apply`` reintenta la tarea como lo haría un worker."""
    monkeypatch.setitem(celery_app.conf, "CELERY_TASK_EAGER_PROPAGATES", False)


# --- Nombres (decisión 38) ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Desprendible de nómina 2 de 3", "Desprendible_de_nomina_2_de_3"),
        ("Año gravable — Señor Núñez", "Ano_gravable_Senor_Nunez"),
        ("  Carta/laboral: (firmada)  ", "Carta_laboral_firmada"),
        ("Ünïcödé ÇÀ", "Unicode_CA"),
        ("¿¡!?", "documento"),
        ("x" * 80, "x" * 60),
        ("a" * 59 + " b", "a" * 59),
    ],
)
def test_safe_name(text: str, expected: str) -> None:
    assert safe_name(text) == expected
    assert len(safe_name(text)) <= packages.MAX_NAME_LENGTH


@pytest.mark.parametrize(
    ("role", "first_names", "last_names", "expected"),
    [
        ("PRIMARY", "Laura", "Gómez Vélez", "01_TITULAR_Laura_Gomez"),
        ("CO_APPLICANT", "Andrés Felipe", "Moreno", "01_COSOLICITANTE_Andres_Moreno"),
        ("SOLIDARY_DEBTOR", "Ana María", "Núñez Ruiz", "01_DEUDOR_SOLIDARIO_Ana_Nunez"),
    ],
)
def test_participant_folders_use_the_role_and_first_name_and_surname(
    application: CreditApplication,
    make_client: Callable[..., Client],
    role: str,
    first_names: str,
    last_names: str,
    expected: str,
) -> None:
    participant = ApplicationParticipant(
        application=application,
        client=make_client(document_number="99", first_names=first_names, last_names=last_names),
        role=role,
    )

    assert participant_folder(1, participant) == expected


def test_a_long_participant_folder_is_cut_to_60(
    application: CreditApplication, make_client: Callable[..., Client]
) -> None:
    participant = ApplicationParticipant(
        application=application,
        client=make_client(document_number="99", first_names="M" * 40, last_names="R" * 40),
        role="SOLIDARY_DEBTOR",
    )

    folder = participant_folder(12, participant)

    assert folder.startswith("12_DEUDOR_SOLIDARIO_MMM")
    assert len(folder) == 60


def test_colliding_and_long_names_get_a_suffix(
    application: CreditApplication,
    advisor_user: User,
    make_slot: SlotFactory,
    approve_stored: ApproveStored,
) -> None:
    long_name = "Certificado de existencia y representación legal de la empresa empleadora"
    names = ("Carta laboral", "Carta, laboral!", "CARTA LABORAL", long_name, long_name + "s")
    for letter, name in zip("ABCDE", names, strict=True):
        approve_stored(make_slot(document_type=custom_type(f"CUSTOM_{letter}", name)))

    job = request_package(advisor_user, application).job

    assert job.manifest is not None
    paths = sorted(entry["file"]["path"] for entry in job.manifest["documents"])
    stem = "Certificado_de_existencia_y_representacion_legal_de_la_empre"
    assert paths == [
        "01_TITULAR_Laura_Gomez/CARTA_LABORAL_3.pdf",
        "01_TITULAR_Laura_Gomez/Carta_laboral.pdf",
        "01_TITULAR_Laura_Gomez/Carta_laboral_2.pdf",
        f"01_TITULAR_Laura_Gomez/{stem[:58]}_2.pdf",
        f"01_TITULAR_Laura_Gomez/{stem}.pdf",
    ]


# --- Pedido -----------------------------------------------------------------------------


def test_the_request_fixes_the_content_in_the_internal_manifest(
    package_dossier: PackageDossier, advisor_user: User
) -> None:
    application = package_dossier.application

    result = request_package(advisor_user, application)

    job = result.job
    assert result.created is True
    assert job.status == PackageJobStatus.PENDING
    assert job.requested_by == advisor_user
    assert job.application_version == application.version
    manifest = job.manifest
    assert manifest is not None
    assert manifest["fingerprint"] == dossier_fingerprint(application)
    assert manifest["application"] == {"id": str(application.pk), "code": application.code}
    documents = manifest["documents"]
    assert [entry["file"]["path"] for entry in documents if entry["file"]] == EXPECTED_PATHS
    assert [entry["slot_id"] for entry in documents] == [
        str(slot.pk)
        for slot in (
            package_dossier.ownership,
            package_dossier.employment,
            package_dossier.identity,
            package_dossier.payroll_1,
            package_dossier.payroll_2,
            package_dossier.co_identity,
        )
    ]
    waived = documents[1]
    assert waived["status"] == SlotStatus.WAIVED
    assert waived["file"] is None
    assert waived["waiver_reason"] == {"code": "OTHER", "name": "Otro"}
    assert waived["holder"]["folder"] == "01_TITULAR_Laura_Gomez"
    identity = documents[2]
    version = package_dossier.identity.current_file
    assert version is not None
    assert identity["file"] == {
        "path": EXPECTED_PATHS[1],
        "document_file_id": str(version.pk),
        "file_object_id": str(version.file_object_id),
        "version_number": 1,
        "client_filename": "cédula Laura.pdf",
        "mime_type": "application/pdf",
        "size_bytes": len(package_dossier.contents["identity"]),
        "sha256": hashlib.sha256(package_dossier.contents["identity"]).hexdigest(),
    }
    assert identity["holder"] == {
        "scope": "PARTICIPANT",
        "participant_id": str(version.slot.participant_id),
        "role": "PRIMARY",
        "role_name": "Titular",
        "full_name": "Laura Gómez Vélez",
        "folder": "01_TITULAR_Laura_Gomez",
    }
    assert documents[0]["holder"]["scope"] == "APPLICATION"
    assert documents[3]["document_date"] == "2026-10-30"


def test_the_request_only_checks_documents_and_saves_no_evaluation(
    package_dossier: PackageDossier, advisor_user: User
) -> None:
    """Decisión 36: con un producto que la guarda evaluaría, el paquete no lo hace."""
    application = package_dossier.application
    CreditApplication.objects.filter(pk=application.pk).update(bank_product=seeded_product())

    result = request_package(advisor_user, application)

    assert result.created is True
    assert not BankRuleEvaluation.objects.filter(application=application).exists()


def test_pending_or_expired_documents_block_the_request(
    package_dossier: PackageDossier,
    advisor_user: User,
    make_slot: SlotFactory,
    approve_stored: ApproveStored,
) -> None:
    pending = make_slot(document_type=doc_type("INCOME_TAX_RETURN"))
    expired = make_slot(document_type=doc_type("INCOME_RETENTION_CERTIFICATE"))
    approve_stored(
        expired,
        document_date=timezone.localdate() - timedelta(days=40),
        expires_at=timezone.localdate(),
    )

    with pytest.raises(ApplicationNotReady) as error:
        request_package(advisor_user, package_dossier.application)

    details = error.value.details
    assert [(d["code"], d["resource_id"]) for d in details] == [
        ("DOCUMENT_EXPIRED", str(expired.pk)),
        ("DOCUMENT_PENDING", str(pending.pk)),
    ]
    assert not DocumentPackageJob.objects.exists()


def test_a_dossier_without_required_documents_cannot_be_packaged(
    application: CreditApplication, advisor_user: User
) -> None:
    with pytest.raises(ApplicationNotReady) as error:
        request_package(advisor_user, application)

    assert [d["code"] for d in error.value.details] == ["DOCUMENTS_NOT_CONFIGURED"]


@pytest.mark.parametrize("status", [ApplicationStatus.WITHDRAWN, ApplicationStatus.CANCELLED])
def test_a_closed_application_cannot_be_packaged(
    package_dossier: PackageDossier, advisor_user: User, status: str
) -> None:
    set_status(package_dossier.application, status)

    with pytest.raises(ApplicationClosed):
        request_package(advisor_user, package_dossier.application)


def test_any_open_status_admits_a_package(
    package_dossier: PackageDossier, advisor_user: User
) -> None:
    set_status(package_dossier.application, ApplicationStatus.READY_TO_FILE)

    assert request_package(advisor_user, package_dossier.application).created is True


def test_expired_optional_approvals_stay_out_of_the_package(
    package_dossier: PackageDossier,
    advisor_user: User,
    make_slot: SlotFactory,
    approve_stored: ApproveStored,
) -> None:
    optional = make_slot(document_type=doc_type("PENSION_CERTIFICATE"), is_required=False)
    approve_stored(optional, document_date=date(2026, 1, 1), expires_at=date(2026, 2, 1))

    job = request_package(advisor_user, package_dossier.application).job

    assert job.manifest is not None
    assert str(optional.pk) not in [entry["slot_id"] for entry in job.manifest["documents"]]


# --- Reutilización (decisión 14) ---------------------------------------------------------


@pytest.mark.parametrize(
    "status", [PackageJobStatus.PENDING, PackageJobStatus.RUNNING, PackageJobStatus.COMPLETED]
)
def test_a_live_job_with_the_same_fingerprint_is_reused(
    requested: DocumentPackageJob,
    package_dossier: PackageDossier,
    other_advisor: User,
    status: str,
) -> None:
    if status == PackageJobStatus.RUNNING:
        DocumentPackageJob.objects.filter(pk=requested.pk).update(
            status=status, started_at=timezone.now()
        )
    elif status == PackageJobStatus.COMPLETED:
        build_package(requested.pk)

    result = request_package(other_advisor, package_dossier.application)

    assert result.created is False
    assert result.job.pk == requested.pk
    assert DocumentPackageJob.objects.count() == 1


def test_a_changed_dossier_gets_a_new_job(
    requested: DocumentPackageJob,
    package_dossier: PackageDossier,
    advisor_user: User,
    approve_stored: ApproveStored,
) -> None:
    approve_stored(package_dossier.identity, client_filename="cedula nueva.pdf")

    result = request_package(advisor_user, package_dossier.application)

    assert result.created is True
    assert result.job.pk != requested.pk


@pytest.mark.parametrize("ending", ["expired", "failed"])
def test_expired_or_failed_jobs_are_not_reused(
    requested: DocumentPackageJob,
    package_dossier: PackageDossier,
    advisor_user: User,
    ending: str,
) -> None:
    if ending == "expired":
        build_package(requested.pk)
        DocumentPackageJob.objects.filter(pk=requested.pk).update(expires_at=timezone.now())
    else:
        DocumentPackageJob.objects.filter(pk=requested.pk).update(
            status=PackageJobStatus.FAILED,
            error_code=CHECKSUM_MISMATCH,
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )

    assert request_package(advisor_user, package_dossier.application).created is True


def test_a_broker_down_leaves_the_job_pending(
    package_dossier: PackageDossier,
    advisor_user: User,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: Callable[..., Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broker_down(job_id: str) -> None:
        raise OperationalError("Redis no responde")

    monkeypatch.setattr(tasks.build_document_package, "delay", broker_down)

    with django_capture_on_commit_callbacks(execute=True):
        job = request_package(advisor_user, package_dossier.application).job

    assert reload(job).status == PackageJobStatus.PENDING
    assert "No se pudo encolar el paquete" in caplog.text


def test_the_request_enqueues_the_build_after_commit(
    package_dossier: PackageDossier,
    advisor_user: User,
    django_capture_on_commit_callbacks: Callable[..., Any],
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        job = request_package(advisor_user, package_dossier.application).job

    assert reload(job).status == PackageJobStatus.COMPLETED


# --- Worker -----------------------------------------------------------------------------


def test_the_worker_builds_the_zip_with_both_manifests(
    requested: DocumentPackageJob, package_dossier: PackageDossier
) -> None:
    assert build_package(requested.pk) == PackageJobStatus.COMPLETED

    job = reload(requested)
    assert job.status == PackageJobStatus.COMPLETED
    assert job.error_code is None
    assert job.started_at is not None and job.completed_at is not None
    assert job.expires_at == job.completed_at + timedelta(days=7)
    archive = zip_of(job)
    assert archive.namelist() == [*EXPECTED_PATHS, "manifest.json"]
    contents = package_dossier.contents
    for path, name in zip(
        EXPECTED_PATHS,
        ["ownership", "identity", "payroll_1", "payroll_2", "co_identity"],
        strict=True,
    ):
        assert archive.read(path) == contents[name]

    bank = json.loads(archive.read("manifest.json"))
    assert bank["application_code"] == package_dossier.application.code
    assert [entry["status"] for entry in bank["documents"]] == [
        "APPROVED",
        "WAIVED",
        "APPROVED",
        "APPROVED",
        "APPROVED",
        "APPROVED",
    ]
    assert bank["documents"][1]["file"] is None
    assert bank["documents"][2] == {
        "document_type": {"code": "IDENTITY_DOCUMENT", "name": "Copia del documento de identidad"},
        "label": "Copia del documento de identidad",
        "holder": {
            "scope": "PARTICIPANT",
            "role": "PRIMARY",
            "role_name": "Titular",
            "full_name": "Laura Gómez Vélez",
        },
        "status": "APPROVED",
        "document_date": None,
        "expires_at": None,
        "file": {
            "path": EXPECTED_PATHS[1],
            "mime_type": "application/pdf",
            "size_bytes": len(contents["identity"]),
            "sha256": hashlib.sha256(contents["identity"]).hexdigest(),
        },
    }
    # Decisión 39: nada interno en el manifiesto del banco.
    raw = archive.read("manifest.json").decode("utf-8")
    assert job.manifest is not None
    for entry in job.manifest["documents"]:
        assert entry["slot_id"] not in raw
        if entry["file"]:
            assert entry["file"]["document_file_id"] not in raw
            assert entry["file"]["client_filename"] not in raw
    for forbidden in ("waiver_reason", "Otro", "participant_id", "client_filename", "comment"):
        assert forbidden not in raw
    assert str(package_dossier.application.pk) not in raw


def test_the_zip_is_registered_clean_without_the_antivirus(
    requested: DocumentPackageJob, package_dossier: PackageDossier
) -> None:
    """Decisión 41."""
    build_package(requested.pk)

    output = reload(requested).output_file_object
    assert output is not None
    content = memory().objects[output.object_key][0]
    assert output.scan_status == ScanStatus.CLEAN
    assert output.scanned_at == reload(requested).completed_at
    assert output.detected_mime_type == ZIP
    assert output.size_bytes == len(content)
    assert output.sha256 == hashlib.sha256(content).hexdigest()
    assert output.object_key.startswith(f"packages/{package_dossier.application.pk}/")
    assert output.original_filename == f"{package_dossier.application.code}_expediente.zip"
    assert memory().objects[output.object_key][1] == ZIP


def test_the_worker_packs_the_fixed_list_not_later_uploads(
    requested: DocumentPackageJob,
    package_dossier: PackageDossier,
    approve_stored: ApproveStored,
) -> None:
    approve_stored(package_dossier.identity, content=b"%PDF-1.7 cedula nueva")

    build_package(requested.pk)

    archive = zip_of(requested)
    assert archive.read(EXPECTED_PATHS[1]) == package_dossier.contents["identity"]


@override_settings(DOCUMENT_PACKAGE_TTL_DAYS=2)
def test_the_package_ttl_comes_from_settings(requested: DocumentPackageJob) -> None:
    build_package(requested.pk)

    job = reload(requested)
    assert job.completed_at is not None
    assert job.expires_at == job.completed_at + timedelta(days=2)


def test_a_tampered_object_fails_with_checksum_mismatch(
    requested: DocumentPackageJob,
    package_dossier: PackageDossier,
    caplog: pytest.LogCaptureFixture,
) -> None:
    version = package_dossier.payroll_2.current_file
    assert version is not None
    key = version.file_object.object_key
    memory().objects[key] = (b"otro contenido", "image/png")

    assert build_package(requested.pk) == PackageJobStatus.FAILED

    job = reload(requested)
    assert (job.status, job.error_code, job.output_file_object) == (
        PackageJobStatus.FAILED,
        CHECKSUM_MISMATCH,
        None,
    )
    assert job.completed_at is not None
    assert package_keys() == []
    assert str(package_dossier.payroll_2.pk) in caplog.text


def test_a_file_object_changed_since_the_request_fails_with_checksum_mismatch(
    requested: DocumentPackageJob, package_dossier: PackageDossier
) -> None:
    version = package_dossier.identity.current_file
    assert version is not None
    FileObject.objects.filter(pk=version.file_object_id).update(sha256="0" * 64)

    build_package(requested.pk)

    assert reload(requested).error_code == CHECKSUM_MISMATCH


def test_a_storage_failure_releases_the_job_for_a_retry(
    requested: DocumentPackageJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(key: str, content: BinaryIO, *, content_type: str) -> None:
        raise StorageUnavailable("sin almacenamiento")

    monkeypatch.setattr(memory(), "put", down)

    with pytest.raises(StorageUnavailable):
        build_package(requested.pk, last_attempt=False)

    job = reload(requested)
    assert (job.status, job.started_at, job.error_code) == (PackageJobStatus.PENDING, None, None)


def test_a_cut_read_counts_as_a_storage_failure(
    requested: DocumentPackageJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    class CutStream(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            raise ReadTimeoutError(endpoint_url="http://seaweedfs:8333")

    monkeypatch.setattr(memory(), "open", lambda key: CutStream())

    assert build_package(requested.pk) == PackageJobStatus.FAILED
    assert reload(requested).error_code == STORAGE_UNAVAILABLE


@pytest.mark.usefixtures("eager_retries")
def test_the_task_retries_and_finally_fails_with_storage_unavailable(
    requested: DocumentPackageJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def down(key: str, content: BinaryIO, *, content_type: str) -> None:
        calls.append(key)
        raise StorageUnavailable("sin almacenamiento")

    monkeypatch.setattr(memory(), "put", down)

    result = tasks.build_document_package.apply(args=[str(requested.pk)])

    assert result.get() == PackageJobStatus.FAILED
    assert len(calls) == tasks.PACKAGE_MAX_RETRIES + 1
    # Cada intento escribe en una clave propia.
    assert len(set(calls)) == len(calls)
    job = reload(requested)
    assert (job.status, job.error_code) == (PackageJobStatus.FAILED, STORAGE_UNAVAILABLE)


@pytest.mark.usefixtures("eager_retries")
def test_the_task_recovers_when_storage_comes_back(
    requested: DocumentPackageJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = memory()
    real_put = storage.put
    failures = iter([True, True])

    def flaky(key: str, content: BinaryIO, *, content_type: str) -> None:
        if next(failures, False):
            raise StorageUnavailable("sin almacenamiento")
        real_put(key, content, content_type=content_type)

    monkeypatch.setattr(storage, "put", flaky)

    result = tasks.build_document_package.apply(args=[str(requested.pk)])

    assert result.get() == PackageJobStatus.COMPLETED
    assert len(package_keys()) == 1


def test_the_worker_is_idempotent(requested: DocumentPackageJob) -> None:
    build_package(requested.pk)

    assert build_package(requested.pk) == PackageJobStatus.COMPLETED
    assert len(package_keys()) == 1
    assert build_package(uuid.uuid4()) is None


def test_a_claimed_job_is_not_built_twice(
    requested: DocumentPackageJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otro worker lo tomó entre la lectura y el ``UPDATE`` condicional."""
    monkeypatch.setattr(packages, "_claim", lambda job_id: None)

    assert build_package(requested.pk) == PackageJobStatus.PENDING
    assert package_keys() == []


def test_a_late_worker_does_not_overwrite_the_result(
    requested: DocumentPackageJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decisión 42: el trabajo se reencoló mientras un worker lento subía su ZIP. El
    nuevo intento termina primero; el lento descarta su objeto."""
    storage = memory()
    real_put = storage.put
    slow_keys: list[str] = []

    def slow_put(key: str, content: BinaryIO, *, content_type: str) -> None:
        real_put(key, content, content_type=content_type)
        if not slow_keys:
            slow_keys.append(key)
            # Mientras tanto, `requeue_document_packages` lo devuelve a la cola y otro
            # worker lo arma completo.
            DocumentPackageJob.objects.filter(pk=requested.pk).update(
                status=PackageJobStatus.PENDING, started_at=None
            )
            assert build_package(requested.pk) == PackageJobStatus.COMPLETED

    monkeypatch.setattr(storage, "put", slow_put)

    assert build_package(requested.pk) == PackageJobStatus.COMPLETED

    job = reload(requested)
    assert job.output_file_object is not None
    assert job.output_file_object.object_key != slow_keys[0]
    assert package_keys() == [job.output_file_object.object_key]
    assert FileObject.objects.filter(detected_mime_type=ZIP).count() == 1


def test_a_late_worker_that_cannot_delete_its_zip_logs_it(
    requested: DocumentPackageJob,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(packages, "_owned", lambda job_id, started_at: _none())

    def no_delete(key: str) -> None:
        raise StorageUnavailable("sin almacenamiento")

    monkeypatch.setattr(memory(), "delete", no_delete)

    build_package(requested.pk)

    assert "objeto huérfano" in caplog.text
    assert not FileObject.objects.filter(detected_mime_type=ZIP).exists()


def _none() -> Any:
    return DocumentPackageJob.objects.none()


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_simultaneous_runs_make_one_zip(
    package_dossier: PackageDossier, advisor_user: User
) -> None:
    job = request_package(advisor_user, package_dossier.application).job
    barrier = threading.Barrier(2)
    results: list[str | None] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            barrier.wait(timeout=10)
            results.append(build_package(job.pk))
        except BaseException as exc:  # pragma: no cover - se reporta abajo
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert len(results) == 2
    assert reload(job).status == PackageJobStatus.COMPLETED
    assert len(package_keys()) == 1
    assert FileObject.objects.filter(detected_mime_type=ZIP).count() == 1


# --- Estado derivado y comandos ------------------------------------------------------------


def test_a_completed_package_reads_expired_after_its_ttl(requested: DocumentPackageJob) -> None:
    build_package(requested.pk)
    job = reload(requested)
    assert job.effective_status == PackageJobStatus.COMPLETED

    DocumentPackageJob.objects.filter(pk=job.pk).update(expires_at=timezone.now())

    assert reload(job).effective_status == PackageJobStatus.EXPIRED
    assert reload(job).status == PackageJobStatus.COMPLETED


def test_requeue_document_packages_takes_stale_jobs(
    package_dossier: PackageDossier,
    advisor_user: User,
    approve_stored: ApproveStored,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def new_job() -> DocumentPackageJob:
        approve_stored(package_dossier.identity)
        return request_package(advisor_user, package_dossier.application).job

    old_pending, stale_running, recent_pending, fresh_running, completed = (
        new_job() for _ in range(5)
    )
    an_hour_ago = timezone.now() - timedelta(hours=1)
    DocumentPackageJob.objects.filter(
        pk__in=[old_pending.pk, stale_running.pk, fresh_running.pk, completed.pk]
    ).update(created_at=an_hour_ago)
    DocumentPackageJob.objects.filter(pk=stale_running.pk).update(
        status=PackageJobStatus.RUNNING, started_at=an_hour_ago
    )
    DocumentPackageJob.objects.filter(pk=fresh_running.pk).update(
        status=PackageJobStatus.RUNNING, started_at=timezone.now()
    )
    build_package(completed.pk)
    queued: list[str] = []
    monkeypatch.setattr(tasks.build_document_package, "delay", queued.append)

    call_command("requeue_document_packages")

    assert sorted(queued) == sorted([str(old_pending.pk), str(stale_running.pk)])
    stale = reload(stale_running)
    assert (stale.status, stale.started_at) == (PackageJobStatus.PENDING, None)
    assert reload(fresh_running).status == PackageJobStatus.RUNNING
    assert "Paquetes reencolados: 2." in capsys.readouterr().out


def test_expire_document_packages_persists_and_deletes(
    package_dossier: PackageDossier,
    advisor_user: User,
    approve_stored: ApproveStored,
    capsys: pytest.CaptureFixture[str],
) -> None:
    due = request_package(advisor_user, package_dossier.application).job
    build_package(due.pk)
    approve_stored(package_dossier.identity)
    live = request_package(advisor_user, package_dossier.application).job
    build_package(live.pk)
    DocumentPackageJob.objects.filter(pk=due.pk).update(expires_at=timezone.now())
    due_key = output_key(due)

    call_command("expire_document_packages")

    assert reload(due).status == PackageJobStatus.EXPIRED
    assert due_key not in memory().objects
    # El registro del archivo se conserva.
    assert FileObject.objects.filter(object_key=due_key).exists()
    assert reload(live).status == PackageJobStatus.COMPLETED
    assert package_keys() == [output_key(live)]
    assert "Paquetes vencidos: 1." in capsys.readouterr().out


def test_expire_document_packages_retries_later_when_storage_fails(
    requested: DocumentPackageJob,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    build_package(requested.pk)
    DocumentPackageJob.objects.filter(pk=requested.pk).update(expires_at=timezone.now())

    def no_delete(key: str) -> None:
        raise StorageUnavailable("sin almacenamiento")

    monkeypatch.setattr(memory(), "delete", no_delete)

    assert packages.expire_packages() == 0
    assert reload(requested).status == PackageJobStatus.COMPLETED
    assert reload(requested).effective_status == PackageJobStatus.EXPIRED
    assert "No se pudo borrar el ZIP vencido" in caplog.text


def test_slots_retired_after_the_request_do_not_matter_to_the_worker(
    requested: DocumentPackageJob, package_dossier: PackageDossier
) -> None:
    ApplicationDocumentSlot.objects.filter(pk=package_dossier.co_identity.pk).update(
        retired_at=timezone.now()
    )

    build_package(requested.pk)

    assert EXPECTED_PATHS[-1] in zip_of(requested).namelist()
