# Copilot Instructions for AI Coding Agents

## Project Overview
- This is a Django-based multi-app project for a burger delivery or restaurant platform.
- Major apps: `core` (utilities, base logic), `customers` (user/customer management), `menu` (product catalog), `orders` (order management), `tenants` (multi-tenancy support).
- Project root: `burger/` (settings, URLs, WSGI/ASGI entrypoints).

## Key Patterns & Conventions
- Each app follows Django conventions: `models.py`, `views.py`, `admin.py`, `apps.py`, `migrations/`, and `tests.py`.
- Templates are organized under `templates/`, with subfolders for each domain (e.g., `loja/`).
- Static/media assets are under `core/assets/`.
- Multi-tenancy logic is in `tenants/`, including custom `middleware.py`.
- Use Django ORM for all database access; avoid raw SQL unless necessary.
- Place business logic in models or `core/utils.py` for reusability.

## Developer Workflows
- **Run server:** `python manage.py runserver`
- **Migrate DB:** `python manage.py makemigrations && python manage.py migrate`
- **Create superuser:** `python manage.py createsuperuser`
- **Run tests:** `python manage.py test`
- **Seed data:** `python seed.py`
- Activate the virtual environment: `source myenv/bin/activate`

## Integration Points
- No external API integrations are present by default; add them in the relevant app.
- For multi-tenant logic, see `tenants/middleware.py` and `tenants/models.py`.
- Cross-app communication uses Django signals or direct model imports.

## Project-Specific Notes
- All new features should include tests in the relevant app's `tests.py`.
- Use the `core/utils.py` for shared helpers.
- Templates should extend `base.html`.
- Static files should be placed in the appropriate `core/assets/` subfolder.
- Keep migrations up to date for each app.

## Example File References
- Main settings: `burger/settings.py`
- URL routing: `burger/urls.py`
- Customer model: `customers/models.py`
- Menu/category logic: `menu/models.py`
- Order processing: `orders/models.py`
- Multi-tenancy: `tenants/middleware.py`, `tenants/models.py`

---
If any conventions or workflows are unclear, please request clarification or examples from the user.
