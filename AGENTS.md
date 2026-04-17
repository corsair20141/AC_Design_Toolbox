\# AC\_Design\_Toolbox — Agent Instructions

Python interpreter to use: C:\Users\corsa\mambaforge\envs\generic\python.exe

This repository contains various codes and methods for aircraft conceptual design and performance analysis.



\## Project priorities



Prioritize, in order:



1\. Correctness and physical clarity

2\. Clean architecture and extensibility

3\. Simplicity / low complexity

4\. Good documentation

5\. Reasonable test coverage

6\. Performance optimization only when justified



Do not over-engineer early implementations.




Avoid placing unrelated logic into existing files just because it is convenient.

Prefer adding a new small module over bloating a central one.



\## Modeling conventions



\### Frames

Use the current project convention unless explicitly changing it everywhere:

\- local world frame: ENU

&#x20; - x = East

&#x20; - y = North

&#x20; - z = Up



Any frame change must be centralized and documented.




\## Coding standards



\- Use `snake\_case` for variables and functions.

\- Use `UPPER\_CASE` for constants.

\- Write clear, explicit code.

\- Prefer dataclasses for simple state/config containers.

\- Add type hints on public APIs.

\- Keep functions focused and reasonably short.

\- Keep modules reasonably sized. If a file is getting crowded, split it.

\- Avoid cleverness that hurts readability.

\- Avoid hidden global state.



\## Documentation requirements



This repository must remain understandable to the author and other users.



For every change:

\- Add docstrings to ALL public classes, dataclasses, methods, and functions.

\- Add inline comments where intent or logic is not obvious.

\- Add enough inline comments to follow the overall structure and flow of a chunk of code.

\- Update module-level README/docs when architecture or workflows change.

\- Explain assumptions and limitations.

\- Preserve the distinction between:

&#x20; - what the code does

&#x20; - why it is structured that way

&#x20; - what is prescribed vs solved physically



If you add a new module or subsystem, include enough documentation that a new contributor can understand:

\- what it is for

\- how it works

\- how to use it

\- what it does NOT do



\## Testing expectations



When making changes:

\- add or update focused tests for new functionality

\- prefer small, direct tests over fragile broad ones

\- test physical/logical invariants where reasonable

\- do not silently break existing public interfaces without updating callers/tests/docs



If you change equations, state definitions, or conventions, update tests and docs in the same change.






\## Editing discipline



Before making major edits:

1\. inspect the relevant existing files

2\. understand current naming and structure

3\. preserve compatibility where practical

4\. make the smallest coherent set of changes



When implementing a new feature:

1\. summarize intended architecture briefly

2\. list files to add/update

3\. make the edits

4\. summarize assumptions / limitations / next steps



\## Example-specific guidance for this project



When implementing mission simulation:

\- prefer a phase-based mission plan

\- make outputs map cleanly into `MissionSample`

\- preserve compatibility with the current solar time-history workflow

\- support extension toward battery/net-energy modeling later



When implementing performance logic:

\- keep first-pass methods simple and well documented

\- favor physically transparent equations over opaque complexity

\- clearly label approximations



\## Do not do these things



\- Do not add large undocumented abstractions.

\- Do not mix mission geometry logic with solar facet logic.

\- Do not bury key assumptions in example scripts only.

\- Do not create duplicate utilities when an existing shared helper should be reused.

\- Do not introduce new dependencies without clear justification.

\- Do not remove documentation or comments that are still accurate and useful.



\## Deliverable quality bar



A good change in this repo should:

\- be understandable by inspection

\- have docstrings and comments

\- fit the architecture cleanly

\- come with tests/examples when appropriate

\- leave the repo easier to work on next time

