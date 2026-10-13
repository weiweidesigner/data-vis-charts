# Repository instructions

- This repository contains standalone general-purpose chart components and their runtime dependencies.
- Preserve component styles, interactions, CLI contracts, and schema semantics.
- Read the corresponding schema before changing a public component contract.
- Keep runtime paths relative to this repository.
- Never commit secrets, cookies, generated user reports, local environments, or machine-specific paths.
- Run `python -m pytest tests -q` after changing components or bundled dependencies.
