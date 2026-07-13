# Backend Architecture and Development Conventions

This document is the source of truth for future backend work and prompts. New code and refactors must follow these rules unless an explicit decision changes them.

## Architecture

The backend is organized by business module under `backend/app`. A module owns the code needed for one business capability: routes, dependencies, services, repositories, DTOs, prompts, and module-specific behavior.

The normal request flow is:

```text
HTTP request
  -> route/controller
  -> service/domain logic
  -> repository/data access
  -> shared models/database
```

Routes handle HTTP concerns and delegate business behavior to services. Services coordinate domain behavior, translate repository failures into domain failures, and return DTOs. Repositories own persistence queries and translate database failures into repository exceptions. Dependencies construct and inject repositories, services, and shared providers.

The scan analysis pipeline is an internal workflow under `analysis/services/scan_engine/pipeline`. Its internal components use dataclass DTOs because the pipeline controls the input types and does not need external-request validation.

## Module layout

Current modules include `auth`, `users`, `github`, `projects`, `scans`, `analysis`, `scan_visualization`, `overview`, `files`, and `queues`.

Use descriptive filenames that include the module or responsibility:

```text
app/files/
  files_routes.py
  files_service.py
  files_repository.py
  files_dtos.py
  dependencies.py

app/github/
  github_routes.py
  github_dtos.py
  services/
    github_service.py
    github_client_service.py
```

Do not create generic files such as `service.py`, `repository.py`, `routes.py`, `schemas.py`, or `prompts.py`. A descriptive name makes global search reliable.

When a module has one implementation of a layer, keep its descriptive file directly in the module. When it has multiple implementations of a layer, group them in the corresponding subfolder:

- multiple services: `<module>/services/`
- multiple repositories: `<module>/repositories/`
- multiple DTO files: `<module>/dtos/`
- multiple schema/validation files: `<module>/dtos/` (the project convention is still DTO)

The filename must remain descriptive inside a subfolder, for example `users/repositories/user_repository.py` and `users/repositories/role_repository.py`.

## DTO convention

Use **DTO** as the only project-wide naming convention. Do not introduce new `schema` filenames or a global `app/schemas` package.

- Pydantic DTOs are for data crossing an external boundary, especially API request bodies, query/filter data, and API responses. They validate and serialize data.
- Dataclass DTOs are for trusted internal interactions, such as repository rows and scan-pipeline values, where the producing component controls the type and strict external validation is unnecessary.
- Keep DTOs with the module that owns the data contract: `files/files_dtos.py`, `projects/projects_dtos.py`, `scans/scans_dtos.py`, and so on.
- DTOs used broadly by multiple modules belong in `core/common_dtos.py`.
- Do not put ORM models in DTO files and do not expose SQLAlchemy models directly from routes.

## Shared core code

Shared code belongs under `app/core`:

- `core/enums.py`: all shared enums, including `UserRole` and `ScanStatus`.
- `core/constants.py`: shared constants, endpoint/query names, prompt templates, provider URLs, cookie settings, language mappings, and limits. Modules import constants from this file; modules must not create their own constants files.
- `core/common_dtos.py`: DTOs used across modules, including pagination and API response metadata.
- `core/database.py`: database/session setup.
- `core/security.py`: password hashing and token encryption.
- `core/route_dependencies.py`: shared authentication and authorization dependencies.

The `models` folder is intentionally separate and remains high-level and shared. Keep SQLAlchemy models in `app/models`; do not scatter models into business modules.

Shared LLM access is in `app/utils/llm_provider.py`. Modules consume the `LlmProvider` abstraction and must not copy provider clients into a business module. Provider construction belongs in dependency wiring. Gemini uses the `google-genai` SDK and Interactions API with the configured `GEMINI_MODEL` (currently `gemini-3.5-flash`).

## Exceptions and error handling

Each layer uses its own exception vocabulary:

- `core/exceptions/repository_exceptions.py`: repositories raise these for database and persistence failures.
- `core/exceptions/domain_exceptions.py`: services raise domain errors and translate repository exceptions into meaningful domain failures.
- `core/exceptions/http_exceptions.py`: routes and middleware use these for HTTP-specific failures.
- `core/middlewares/exceptions_handler.py`: the centralized handler catches known and unexpected exception types and converts them into user-facing HTTP responses.

Repositories should not raise HTTP exceptions. Services should not leak raw SQLAlchemy exceptions. Routes should not contain persistence queries or duplicate exception translation.

## Naming rules

- Use the business term in class and filename names: `FilesService`/`files_service.py`, `ProjectRepository`/`projects_repository.py`, and `GithubClientService`/`github_client_service.py`.
- Prefer names that describe responsibility over generic names such as `service`, `repository`, `routes`, `data`, or `utils`.
- Keep route functions descriptive and make route modules end in `_routes.py`.
- Keep service modules end in `_service.py`, repository modules in `_repository.py`, and DTO modules in `_dtos.py`.
- Import shared enums, constants, DTOs, models, and providers from their canonical shared location rather than duplicating definitions.

## Rules for future changes

Before adding a file, identify its owning module and layer. Before adding a shared type, confirm that at least two modules genuinely need it; otherwise keep it in the owning module. When adding a second implementation to a layer, introduce the matching layer subfolder and use descriptive filenames. Update imports and tests in the same change, remove obsolete generic files, and run the backend test suite or the narrowest relevant tests.
