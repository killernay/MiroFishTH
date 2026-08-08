# Domain Docs

This is a single-context repository.

## Before exploring a domain area

- Read root `CONTEXT.md` if it exists.
- Read ADRs in `docs/adr/` that apply to the area being changed.
- If either location does not exist, proceed silently.

## Consumer rules

- Use terminology defined by `CONTEXT.md` in issues, designs, tests, and code.
- Surface any conflict with an applicable ADR instead of silently overriding it.
- Create domain documentation only when a domain term or architectural decision has actually been resolved.

## Intended structure

```text
/
├── CONTEXT.md
└── docs/
    └── adr/
```
