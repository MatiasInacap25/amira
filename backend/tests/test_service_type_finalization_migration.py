import importlib.util
import re
from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).parents[1] / "alembic" / "versions" / "20261010_0006_finalize_service_types.py"
)
SEEDED_IDS = {
    "a1000000-0000-4000-8000-000000000005": ("Mudanzas", "mudanzas"),
    "a1000000-0000-4000-8000-000000000006": ("Carga compartida", "carga-compartida"),
}
NEW_TYPES = {
    "fecf8e67-8387-4ab3-aa1f-8ea453c95b82": ("Transporte de mercadería", "mercaderia"),
    "f4940a97-9fca-4665-a813-5e6ff396e4fa": ("Fletes y traslados", "fletes"),
    "f9c72b3d-413c-4af5-94a0-d239e1b19ff2": ("Recolección de escombros", "escombros"),
    "bbbc620f-9faa-4675-bd0c-2d7ea0f20a51": ("Servicios de grúa", "grua"),
}


def load_migration():
    spec = importlib.util.spec_from_file_location("finalize_service_types", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_chains_after_the_current_head() -> None:
    migration = load_migration()

    assert migration.revision == "20261010_0006"
    assert migration.down_revision == "20261010_0005"


def test_seeded_rows_are_renamed_in_place_with_their_original_ids() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for service_id, (name, slug) in SEEDED_IDS.items():
        assert re.search(
            rf"UPDATE public\.\"Tipos_Servicio\"\s+SET \"Nombre_servicio\" = '{re.escape(name)}', \"Slug\" = '{slug}'\s+WHERE \"ID\" = '{service_id}'",
            source,
        ), service_id


def test_new_service_types_have_fixed_ids_names_and_slugs() -> None:
    migration = load_migration()

    assert dict(migration.NEW_SERVICE_TYPES) == {
        service_id: (name, slug) for service_id, (name, slug) in NEW_TYPES.items()
    }
    ids = [service_id for service_id, _ in migration.NEW_SERVICE_TYPES]
    assert len(set(ids)) == len(ids)
    slugs = [slug for _, (_, slug) in migration.NEW_SERVICE_TYPES] + ["mudanzas", "carga-compartida"]
    assert len(set(slugs)) == len(slugs)
    for _, slug in NEW_TYPES.values():
        assert re.fullmatch(r"^[a-z0-9]+(-[a-z0-9]+)*$", slug)


def test_insert_is_idempotent_on_the_id_key() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert 'INSERT INTO public."Tipos_Servicio"' in source
    assert 'ON CONFLICT ("ID") DO NOTHING' in source


def test_downgrade_restores_names_and_deletes_only_unreferenced_inserted_rows() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade() -> None:", 1)[1]

    for name in ("[DEMO] Mudanzas", "[DEMO] Carga compartida"):
        assert name in downgrade
    for table, column in (
        ("Servicios_Disponibles", "ID_Tipo_Servicio"),
        ("Formulario_servicio", "Tipo_Servicio"),
        ("Cotizacion", "Tipo_Servicio"),
    ):
        assert f'NOT EXISTS (SELECT 1 FROM public."{table}"' in downgrade
        assert f'"{column}"' in downgrade
    for service_id in NEW_TYPES:
        assert service_id in downgrade
    assert "DELETE FROM public" in downgrade
    # Seeded rows are never deleted by the downgrade; they are only renamed back.
    delete_statement = downgrade.split("DELETE FROM", 1)[1].split('"""', 1)[0]
    for service_id in SEEDED_IDS:
        assert service_id not in delete_statement
