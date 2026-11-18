"""Carreras con transacciones reales (``specs/TAREA-seguridad.md``, Partes 4.2 y 4.7).

pytest corre cada prueba dentro de una transacción que nunca se confirma, así que dos
hilos no compiten de verdad. Este script lo hace contra la base local de auditoría, con
el servidor de auditoría corriendo, después de ``seed_demo_data`` y ``seed_actors.py``::

    python manage.py shell -c "exec(open('security/race_checks.py').read())"

Variables: ``RACE_API`` (por omisión ``http://mvp-sec-api:8000``). Solo con ``DEBUG``.
Escribe datos de prueba (un enlace, un paquete, radicaciones, un desembolso): correrlo
sobre una base de usar y tirar. Imprime conteos y estados, nunca tokens ni cookies.

Casos:
1. 10 consumos simultáneos del mismo enlace mágico (servicio, cada hilo con su conexión).
2. 10 radicaciones simultáneas **sin** ``Idempotency-Key`` de la misma solicitud (HTTP).
3. 2 ``PATCH`` simultáneos con el mismo ``If-Match`` (HTTP).
4. 10 pagos simultáneos de la misma parte de comisión (HTTP).
"""

import json
import os
import threading
import urllib.error
import urllib.request
from collections import Counter
from datetime import timedelta
from http.cookies import SimpleCookie
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import connections
from django.test import RequestFactory
from django.utils import timezone

from apps.applications import services as application_services
from apps.applications.demo_data import DEMO_PASSWORD, _fresh, _item
from apps.applications.models import CreditApplication
from apps.catalogs.workflow import ApplicationStatus
from apps.commissions.models import CommissionSettlement, CommissionShare
from apps.filings import responses
from apps.filings.demo_data import _completed_package
from apps.filings.models import Filing
from apps.identity.buyer_access import default_channel, issue_access_link
from apps.identity.buyer_sessions import consume_access_link
from apps.identity.models import BuyerSession, User

API = os.environ.get("RACE_API", "http://mvp-sec-api:8000")
THREADS = 10


def _run_parallel(count: int, target: Any) -> list[Any]:
    barrier = threading.Barrier(count)
    results: list[Any] = [None] * count

    def worker(index: int) -> None:
        try:
            barrier.wait()
            results[index] = target(index)
        except Exception as exc:  # noqa: BLE001 - se informa el tipo, no se oculta
            results[index] = type(exc).__name__
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def _request(
    method: str, path: str, *, cookie: str = "", body: Any = None, headers: Any = None
) -> tuple[int, dict[str, Any], dict[str, str]]:
    data = json.dumps(body).encode() if body is not None else None
    all_headers = {"Content-Type": "application/json", **(headers or {})}
    if cookie:
        all_headers["Cookie"] = cookie
    req = urllib.request.Request(API + path, data=data, method=method, headers=all_headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw, status, response_headers = resp.read(), resp.status, dict(resp.headers)
    except urllib.error.HTTPError as exc:
        raw, status, response_headers = exc.read(), exc.code, dict(exc.headers)
    try:
        parsed = json.loads(raw) if raw else {}
    except ValueError:
        parsed = {}
    return status, parsed, response_headers


def _login(email: str) -> tuple[str, str]:
    """Cookie y CSRF de una sesión nueva. Nunca se imprimen."""
    req = urllib.request.Request(
        API + "/api/v1/auth/login",
        data=json.dumps({"email": email, "password": DEMO_PASSWORD}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        jar = SimpleCookie()
        for header in resp.headers.get_all("Set-Cookie") or []:
            jar.load(header)
    cookie = "; ".join(f"{key}={morsel.value}" for key, morsel in jar.items())
    return cookie, jar[settings.CSRF_COOKIE_NAME].value


def _advisor_application(advisor: User, status: str) -> CreditApplication:
    application = (
        CreditApplication.objects.filter(assigned_advisor=advisor, status=status)
        .order_by("code")
        .first()
    )
    if application is None:
        raise SystemExit(f"Falta una solicitud {status} de {advisor.email}: corre seed_demo_data.")
    return application


def check_magic_link(advisor: User) -> None:
    application = _advisor_application(advisor, ApplicationStatus.WAITING_DOCUMENTS)
    issued = issue_access_link(advisor, application, channel=default_channel(), expires_in_hours=1)
    token = issued.url.split("token=", 1)[1]
    request = RequestFactory().post("/", REMOTE_ADDR="127.0.0.1", HTTP_USER_AGENT="race_checks")

    def consume(_: int) -> str:
        consume_access_link(request=request, raw_token=token)
        return "OK"

    results = Counter(_run_parallel(THREADS, consume))
    sessions = BuyerSession.objects.filter(access_link_id=issued.link.pk).count()
    print(
        f"1. enlace mágico, {THREADS} consumos simultáneos: {dict(results)}; "
        f"sesiones creadas={sessions}"
    )


def check_double_filing(advisor: User, cookie: str, csrf: str) -> None:
    application = _advisor_application(advisor, ApplicationStatus.READY_TO_FILE)
    job = _completed_package(advisor, application)
    application = _fresh(application)
    body = {
        "bank_product_id": str(application.bank_product_id),
        "package_job_id": str(job.pk),
        "channel_code": "BANK_PORTAL",
        "filed_at": timezone.now().isoformat(),
        "expected_version": application.version,
    }
    path = f"/api/v1/applications/{application.pk}/filings"

    def file(_: int) -> int:
        return _request("POST", path, cookie=cookie, body=body, headers={"X-CSRFToken": csrf})[0]

    results = Counter(_run_parallel(THREADS, file))
    created = Filing.objects.filter(application=application).count()
    print(
        f"2. radicación sin Idempotency-Key, {THREADS} simultáneas ({application.code}): "
        f"{dict(results)}; radicaciones creadas={created}"
    )


def check_if_match(advisor: User, cookie: str, csrf: str) -> None:
    application = _advisor_application(advisor, ApplicationStatus.DRAFT)
    path = f"/api/v1/applications/{application.pk}"
    version = _fresh(application).version
    # El mismo cambio en los dos: el perdedor solo puede fallar por la versión.
    purposes = ["PURCHASE_USED", "PURCHASE_USED"]

    def patch(index: int) -> int:
        return _request(
            "PATCH",
            path,
            cookie=cookie,
            body={"purpose_code": purposes[index]},
            headers={"X-CSRFToken": csrf, "If-Match": f'"{version}"'},
        )[0]

    results = Counter(_run_parallel(2, patch))
    after = _fresh(application)
    print(
        f"3. dos PATCH con el mismo If-Match ({application.code}): {dict(results)}; "
        f"versión {version} -> {after.version}"
    )


def _disbursed_settlement(admin: User, advisor: User) -> CommissionSettlement:
    settlement = CommissionSettlement.objects.filter(status="ACTIVE").order_by("created_at").first()
    if settlement is not None:
        return settlement
    application = _advisor_application(advisor, ApplicationStatus.APPROVED)
    application_services.transition_application(
        advisor,
        _fresh(application),
        to_status=ApplicationStatus.LEGALIZATION,
        expected_version=_fresh(application).version,
    )
    responses.record_response(
        advisor,
        Filing.objects.filter(application=application).latest("filed_at"),
        responses.ResponseInput(
            response_type=_item(responses.RESPONSE_TYPE_CATALOG, responses.DISBURSED),
            received_at=timezone.now() - timedelta(minutes=1),
            disbursed_amount_cop=150_000_000,
        ),
        expected_version=_fresh(application).version,
    )
    return CommissionSettlement.objects.get(application=application, status="ACTIVE")


def check_double_payment(admin: User, advisor: User, cookie: str, csrf: str) -> None:
    settlement = _disbursed_settlement(admin, advisor)
    share = CommissionShare.objects.filter(settlement=settlement, paid_at__isnull=True).first()
    if share is None:
        print("4. pago doble: no hay partes sin pagar; se omite")
        return
    body = {"paid_at": timezone.localdate().isoformat(), "payment_reference": "CARRERA-1"}
    path = f"/api/v1/commission-shares/{share.pk}/pay"

    def pay(_: int) -> int:
        return _request("POST", path, cookie=cookie, body=body, headers={"X-CSRFToken": csrf})[0]

    results = Counter(_run_parallel(THREADS, pay))
    share.refresh_from_db()
    print(
        f"4. pago de la misma parte, {THREADS} simultáneos: {dict(results)}; "
        f"pagada={share.paid_at is not None}"
    )


def main() -> None:
    if not settings.DEBUG:
        raise SystemExit("race_checks solo corre con DEBUG=True (entorno local).")
    cache.clear()  # Los límites de login de la corrida anterior.
    admin = User.objects.get(email="admin@demo.local")
    advisor = User.objects.get(email="asesora.lucia@demo.local")
    advisor_cookie, advisor_csrf = _login(advisor.email)
    admin_cookie, admin_csrf = _login(admin.email)
    check_magic_link(advisor)
    check_double_filing(advisor, advisor_cookie, advisor_csrf)
    check_if_match(advisor, advisor_cookie, advisor_csrf)
    check_double_payment(admin, advisor, admin_cookie, admin_csrf)


main()
