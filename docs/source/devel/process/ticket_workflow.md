# Ticket Workflow

## [PIPE](https://open-jira.nrao.edu/projects/PIPE): Feature / Bug / Epic Ticket

Applies to the following PIPE issue types: **Feature**, **Bug**, **Epic**, and **Sub-task**. Engineering and Research Request tickets follow similar but simplified workflows — see below.

### States

- **Open**: Initial state of a new ticket.
- **Reviewed**: Accepted into the backlog "To-Do" list based on scientific or operational priority and available resources; not yet actively worked. Tickets targeting a specific release are labeled accordingly.
- **Input Required**: Awaiting requirements or clarifying information from a stakeholder or developer.
- **Implementing**: Actively being developed; a branch exists. Can transition to **Verifying**, directly to **Validating**, **Input Required**, or **Reviewed**.

  :::{note}
  - Open a [Draft/WIP Pull Request](https://confluence.atlassian.com/bitbucketserver/draft-pull-requests-1354498120.html) as early as the prototyping stage to allow team feedback on algorithm and implementation choices. Use a descriptive title such as `WIP: PIPE-1234: implementing bugfix for task`.
  - Maintain a clear PR description and informative inline comments to surface design questions, explain rationale, and aid both the developer and reviewer.
  :::

  :::{tip}
  A draft PR or a temporary branch used to demonstrate code capability is a legitimate and encouraged collaboration tool — our distributed team relies on asynchronous discussion and co-development. Repository settings are in place to prevent accidental merges into `main` or direct commits to the remote `main` branch.
  :::

- **Verifying**: Assigned to other developer(s) for code review and cross-check changes before stakeholder validation. Do not advance to **Validating** until the development team is satisfied — a single code review approval is sufficient for narrow, well-scoped changes; broader changes should have wider review. A ticket may cycle through **Implementing**, **Verifying**, and **Validating** multiple times before merging.

  :::{note}
  - **Weblog storage**: Post PR testing results to the observatory's internal weblog storage so reviewers and stakeholders can assess impact without needing raw data or deep familiarity with the issue. Use `<PIPE-1234>` as the subdirectory name; weblogs and log files are typically sufficient — avoid large data files. Organize results into labeled sub-directories (e.g. `PIPE-1234/main`, `PIPE-1234/pipe1234-v1-attempt1`, `PIPE-1234/pipe1234-v2-attempt2`). Directories may be removed after the code is released.
  - **Early merge exception**: If both the stakeholder and technical lead agree, a narrow, well-scoped change may be merged into `main` after verification and before formal validation. This still requires at least one developer approval, all PR tasks resolved, and all automated tests passing. The `Validating-MAIN` label must be applied and a merge comment posted with the commit tag (e.g., `2026.1.1.1`); the ticket then advances to **Validating**, where validation occurs on `main`.
  :::

- **Validating**: Assigned to a stakeholder to validate against the ticket branch, or against `main` if the `Validating-MAIN` label is set. On acceptance, moves to **Pending Release**; if issues are found, returns to **Implementing** and may cycle through **Verifying** and **Validating** again.

  :::{note}
  - **Independent validation**: For code changes directly contributed by a scientist, the validator must be someone other than the original contributor and should be selected from the stakeholder group to ensure independent validation.
  :::

- **Pending Release**: Implementation complete; branch ready to merge into `main` pending release. If unexpected issues arise after merging, the ticket can return to **Implementing**.
- **Closed / Released**: Set in bulk via the Jira bulk change tool once a software version is officially released.

```mermaid
flowchart TD
    START(( )) --> OPEN

    OPEN <--> INPUT_REQUIRED
    OPEN --> IMPLEMENTING
    OPEN --> CLOSED_RELEASED
    OPEN --> REVIEWED

    INPUT_REQUIRED <--> REVIEWED
    INPUT_REQUIRED --> IMPLEMENTING

    REVIEWED --> IMPLEMENTING
    REVIEWED --> CLOSED_RELEASED

    IMPLEMENTING --> VERIFYING
    IMPLEMENTING --> INPUT_REQUIRED
    IMPLEMENTING --> VALIDATING
    IMPLEMENTING --> REVIEWED

    VERIFYING --> VALIDATING
    VALIDATING --> IMPLEMENTING
    VALIDATING --> PENDING_RELEASE

    PENDING_RELEASE --> IMPLEMENTING
    PENDING_RELEASE --> CLOSED_RELEASED

    INPUT_REQUIRED(INPUT REQUIRED)
    PENDING_RELEASE(PENDING RELEASE)
    CLOSED_RELEASED(CLOSED / RELEASED)
    OPEN(OPEN)
    REVIEWED(REVIEWED)
    IMPLEMENTING(IMPLEMENTING)
    VERIFYING(VERIFYING)
    VALIDATING(VALIDATING)

    classDef navy  fill:#1e3264,stroke:#1e3264,color:#fff
    classDef blue  fill:#1a5fbf,stroke:#1a5fbf,color:#fff
    classDef green fill:#15803d,stroke:#15803d,color:#fff
    classDef gray  fill:#9ca3af,stroke:#9ca3af,color:#9ca3af

    class OPEN,INPUT_REQUIRED,REVIEWED navy
    class IMPLEMENTING,VERIFYING,VALIDATING blue
    class PENDING_RELEASE,CLOSED_RELEASED green
    class START gray
```

## [PIPE](https://open-jira.nrao.edu/projects/PIPE): Engineering Task Ticket

Applies to the **Engineering Task** issue type. Covers internal infrastructure work — build system changes, CI/CD improvements, tooling, and dependency updates — with no direct scientific impact and no stakeholder validation. The **Validating** state is omitted. Minor non-production changes (documentation fixes, CI/CD updates) may be merged without formal review after contacting the technical lead for a repository permission override.

```mermaid
flowchart TD
    START(( )) --> OPEN

    OPEN <--> INPUT_REQUIRED
    OPEN --> REVIEWED
    OPEN --> IMPLEMENTING
    OPEN --> CLOSED_RELEASED

    INPUT_REQUIRED <--> REVIEWED
    INPUT_REQUIRED --> IMPLEMENTING

    REVIEWED --> IMPLEMENTING
    REVIEWED --> CLOSED_RELEASED

    IMPLEMENTING <--> VERIFYING
    IMPLEMENTING --> INPUT_REQUIRED
    IMPLEMENTING --> REVIEWED

    VERIFYING --> PENDING_RELEASE

    PENDING_RELEASE --> IMPLEMENTING
    PENDING_RELEASE --> CLOSED_RELEASED

    INPUT_REQUIRED(INPUT REQUIRED)
    PENDING_RELEASE(PENDING RELEASE)
    CLOSED_RELEASED(CLOSED / RELEASED)
    OPEN(OPEN)
    REVIEWED(REVIEWED)
    IMPLEMENTING(IMPLEMENTING)
    VERIFYING(VERIFYING)

    classDef navy  fill:#1e3264,stroke:#1e3264,color:#fff
    classDef blue  fill:#1a5fbf,stroke:#1a5fbf,color:#fff
    classDef green fill:#15803d,stroke:#15803d,color:#fff
    classDef gray  fill:#9ca3af,stroke:#9ca3af,color:#9ca3af

    class OPEN,INPUT_REQUIRED,REVIEWED navy
    class IMPLEMENTING,VERIFYING blue
    class PENDING_RELEASE,CLOSED_RELEASED green
    class START gray
```

---

## [PIPE](https://open-jira.nrao.edu/projects/PIPE): Research Request Ticket

Applies to the **Research Request** issue type. Tracks investigative or exploratory work — data analysis, feasibility studies, or algorithm evaluations. No **Verifying** state; **Implementing** and **Pending Release** are bidirectional to support iterative research cycles.

```mermaid
flowchart TD
    START(( )) --> OPEN

    OPEN <--> INPUT_REQUIRED
    OPEN --> REVIEWED
    OPEN --> IMPLEMENTING
    OPEN --> CLOSED_RELEASED

    INPUT_REQUIRED <--> REVIEWED
    INPUT_REQUIRED <--> IMPLEMENTING

    REVIEWED <--> IMPLEMENTING
    REVIEWED --> CLOSED_RELEASED

    IMPLEMENTING <--> PENDING_RELEASE

    PENDING_RELEASE --> CLOSED_RELEASED

    INPUT_REQUIRED(INPUT REQUIRED)
    PENDING_RELEASE(PENDING RELEASE)
    CLOSED_RELEASED(CLOSED / RELEASED)
    OPEN(OPEN)
    REVIEWED(REVIEWED)
    IMPLEMENTING(IMPLEMENTING)

    classDef navy  fill:#1e3264,stroke:#1e3264,color:#fff
    classDef blue  fill:#1a5fbf,stroke:#1a5fbf,color:#fff
    classDef green fill:#15803d,stroke:#15803d,color:#fff
    classDef gray  fill:#9ca3af,stroke:#9ca3af,color:#9ca3af

    class OPEN,INPUT_REQUIRED,REVIEWED navy
    class IMPLEMENTING blue
    class PENDING_RELEASE,CLOSED_RELEASED green
    class START gray
```

---

## [PIPEREQ](https://open-jira.nrao.edu/projects/PIPEREQ): Epic / Improvement / Research Request Ticket

Applies to the following PIPEREQ issue types: **Epic**, **Improvement**, and **Research Request**. These tickets follow a separate, less formalized workflow.

```mermaid
flowchart TD
    START(( )) --> IN_REVIEW
    ALL1([All]) --> IN_REVIEW
    ALL2([All]) --> DONE

    IN_REVIEW --> SCHEDULED
    SCHEDULED --> READY_TO_VALIDATE
    READY_TO_VALIDATE --> DONE

    IN_REVIEW(IN REVIEW)
    SCHEDULED(SCHEDULED)
    READY_TO_VALIDATE(READY TO VALIDATE)
    DONE(DONE)

    classDef lightblue fill:#93c5fd,stroke:#93c5fd,color:#1e3264
    classDef blue      fill:#1a5fbf,stroke:#1a5fbf,color:#fff
    classDef mint      fill:#a7f3d0,stroke:#a7f3d0,color:#065f46
    classDef gray      fill:#9ca3af,stroke:#9ca3af,color:#9ca3af
    classDef dark      fill:#1f2937,stroke:#1f2937,color:#fff

    class IN_REVIEW,READY_TO_VALIDATE lightblue
    class SCHEDULED blue
    class DONE mint
    class START gray
    class ALL1,ALL2 dark
```

### States

- **In Review**: Research in progress, discussion ongoing; not yet ready for a PIPE ticket.
- **Scheduled**: Requirements converged; PIPE ticket(s) created and linked.
- **Ready to Validate**: Rarely used in practice.
- **Done**: Linked PIPE ticket(s) closed.
