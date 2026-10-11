"""Assignment options for a provider service: the drivers and vehicles that PUT .../assignments accepts.

The options and the assignment write share one predicate per resource, so a listed driver or vehicle is always
accepted and an accepted one is always listed. Only the profile owner gets the list, and it carries no contact details.
"""

from uuid import uuid4

from sqlalchemy.orm import Session

from amira_api.models import Conductor, Usuario, Vehiculo
from test_provider_service_actions import (  # noqa: F401  (pytest fixture re-export)
    GUS_AUTH,
    OUTSIDER_AUTH,
    OUTSIDER_DRIVER_AUTH,
    Fleet,
    call,
    fleet,
)
from test_provider_service_routes import (  # noqa: F401  (pytest fixture re-export)
    CUSTOMER_AUTH,
    EMPLOYED_DRIVER_AUTH,
    INDEPENDENT_AUTH,
    OWNER_AUTH,
    db,
)


def _options(call, service, *, auth=OWNER_AUTH):
    return call("GET", f"/api/provider/services/{service.id}/assignment-options", as_auth_id=auth)


def _assignments(call, service, pairs: list[dict], *, auth=OWNER_AUTH):
    return call(
        "PUT", f"/api/provider/services/{service.id}/assignments", as_auth_id=auth, json={"assignments": pairs}
    )


def test_owner_gets_the_employed_drivers_and_vehicles_of_the_service_profile(call, fleet: Fleet):
    response = _options(call, fleet.service_a)

    assert response.status_code == 200
    assert response.json() == {
        "drivers": [
            {"driverId": str(fleet.eli.id), "firstName": "Eli", "lastName": "Employee", "isOwner": False},
            {"driverId": str(fleet.gus.id), "firstName": "Gus", "lastName": "Second", "isOwner": False},
        ],
        "vehicles": [
            {"vehicleId": str(fleet.van.id), "vehicleLabel": "Hyundai Porter", "plate": "ABCD12"},
            {"vehicleId": str(fleet.truck.id), "vehicleLabel": "Toyota Hiace", "plate": "EFGH34"},
        ],
    }


def test_independent_owner_gets_their_own_driver_row_marked_as_owner(call, fleet: Fleet):
    response = _options(call, fleet.solo_service, auth=INDEPENDENT_AUTH)

    assert response.status_code == 200
    assert response.json() == {
        "drivers": [{"driverId": str(fleet.dana.id), "firstName": "Dana", "lastName": "Driver", "isOwner": True}],
        "vehicles": [{"vehicleId": str(fleet.solo_van.id), "vehicleLabel": "Kia Frontier", "plate": "IJKL56"}],
    }


def test_drivers_and_vehicles_of_other_profiles_are_not_listed(call, fleet: Fleet):
    body = _options(call, fleet.service_a).json()

    listed_drivers = {driver["driverId"] for driver in body["drivers"]}
    listed_vehicles = {vehicle["vehicleId"] for vehicle in body["vehicles"]}
    assert str(fleet.outsider_driver.id) not in listed_drivers
    assert str(fleet.dana.id) not in listed_drivers
    assert str(fleet.outsider_van.id) not in listed_vehicles
    assert str(fleet.solo_van.id) not in listed_vehicles


def test_options_are_sorted_by_name_and_label_not_by_insertion_order(call, db: Session, fleet: Fleet):
    late_user = Usuario(
        id=uuid4(), auth_user_id=uuid4(), first_name="Ana", last_name="Zapata",
        email="ana.zapata@example.test", role_id=fleet.eli_user.role_id,
    )
    late_driver = Conductor(
        id=uuid4(), user_id=late_user.id, employer_profile_id=fleet.company.id, driver_type_id=uuid4()
    )
    late_van = Vehiculo(
        id=uuid4(), profile_id=fleet.company.id, plate="AAAA00", brand="Audi", model="A3",
        image_storage_key="vehicles/aaaa00.webp",
    )
    db.add_all([late_user, late_driver, late_van])
    db.commit()

    body = _options(call, fleet.service_a).json()

    assert [driver["firstName"] for driver in body["drivers"]] == ["Ana", "Eli", "Gus"]
    assert [vehicle["vehicleLabel"] for vehicle in body["vehicles"]] == ["Audi A3", "Hyundai Porter", "Toyota Hiace"]


def test_listed_drivers_and_vehicles_are_accepted_by_put_assignments(call, fleet: Fleet):
    body = _options(call, fleet.service_next_day).json()
    pairs = [
        {"driverId": driver["driverId"], "vehicleId": vehicle["vehicleId"]}
        for driver, vehicle in zip(body["drivers"], body["vehicles"])
    ]

    response = _assignments(call, fleet.service_next_day, pairs)

    assert response.status_code == 200
    assigned = {assignment["driverId"] for assignment in response.json()["assignments"]}
    assert assigned == {str(fleet.eli.id), str(fleet.gus.id)}


def test_independent_owners_own_driver_row_is_accepted_by_put_assignments(call, fleet: Fleet):
    body = _options(call, fleet.solo_service, auth=INDEPENDENT_AUTH).json()
    pair = {"driverId": body["drivers"][0]["driverId"], "vehicleId": body["vehicles"][0]["vehicleId"]}

    response = _assignments(call, fleet.solo_service, [pair], auth=INDEPENDENT_AUTH)

    assert response.status_code == 200
    assert response.json()["assignments"][0]["driverId"] == str(fleet.dana.id)


def test_assigned_employed_driver_gets_403_on_options(call, fleet: Fleet):
    response = _options(call, fleet.service_a, auth=EMPLOYED_DRIVER_AUTH)

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the profile owner can manage this service."


def test_employed_driver_not_assigned_to_the_service_gets_404(call, fleet: Fleet):
    response = _options(call, fleet.service_a, auth=GUS_AUTH)

    assert response.status_code == 404
    assert response.json()["detail"] == "Service not found."


def test_owner_of_another_company_gets_404(call, fleet: Fleet):
    response = _options(call, fleet.service_a, auth=OUTSIDER_AUTH)

    assert response.status_code == 404
    assert response.json()["detail"] == "Service not found."


def test_driver_of_another_company_gets_404(call, fleet: Fleet):
    response = _options(call, fleet.service_a, auth=OUTSIDER_DRIVER_AUTH)

    assert response.status_code == 404
    assert response.json()["detail"] == "Service not found."


def test_customer_gets_403_on_provider_options(call, fleet: Fleet):
    response = _options(call, fleet.service_a, auth=CUSTOMER_AUTH)

    assert response.status_code == 403
    assert response.json()["detail"] == "Only provider accounts can access provider services."
