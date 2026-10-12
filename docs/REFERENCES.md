# Architectural references

## REA

[REA](https://github.com/morluto/rea) is an MIT-licensed reverse-engineering
platform. ScholarFlow does not use REA as a dependency and does not copy its
reverse-engineering implementation. The project informed several general
engineering patterns used here:

- separate browser/API surfaces from application and domain logic;
- expose explicit capability availability and remediation;
- return structured evidence, limitations, and unresolved questions;
- use deterministic semantic identifiers for exportable records;
- distinguish heuristic findings from observed outcomes;
- verify modules, boundaries, entry points, and acceptance behavior separately.

ScholarFlow applies those patterns to academic revision through its own
`AcademicEditorService`, revision-receipt contract, repository checker, and
test suite. A revision receipt intentionally records text digests rather than
manuscript content. It is an audit aid, not proof of semantic equivalence or
scholarly quality.

## Product behavior references

QuillBot is used only as a high-level product-category reference for a
side-by-side writing workflow. ScholarFlow's implementation, interface,
research safeguards, and source code are original to this repository.
