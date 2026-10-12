---
generated: 2026-10-13
engine: 2026-10-11.3
nodes: 56
edges: 105
design pass-rate: 83% (25/30 source files without a design candidate)
---

# Requirement Map

## System Map

_Capabilities grouped by area; thick border = bus; arrows = `depends_on`. Edges into the bus/hubs are hidden (the Dependency Map shows area-level coupling)._

```mermaid
graph LR
  subgraph sg_ARCH["ARCH"]
    ARCH_CONSILIUM_IMPLEMENT_001["Implementation pipeline<br><small>ARCH-CONSILIUM-IMPLEMENT-001</small>"]
    ARCH_CONSILIUM_LEARNING_001["Learning loop: feedback journal, outcomes and priors<br><small>ARCH-CONSILIUM-LEARNING-001</small>"]
    ARCH_CONSILIUM_MODES_001["Deliberation modes<br><small>ARCH-CONSILIUM-MODES-001</small>"]
    ARCH_CONSILIUM_REPO_GATES_001["Repository gates<br><small>ARCH-CONSILIUM-REPO-GATES-001</small>"]
    ARCH_CONSILIUM_REPORT_001["Report pipeline: aggregate, score, assemble, validate<br><small>ARCH-CONSILIUM-REPORT-001</small>"]
    ARCH_CONSILIUM_VOICES_001["Deliberation voices and personality lenses<br><small>ARCH-CONSILIUM-VOICES-001</small>"]
  end
  subgraph sg_CONSILIUM["CONSILIUM"]
    CONSILIUM_AGGREGATOR_001["aggregator<br><small>CONSILIUM-AGGREGATOR-001</small>"]
    CONSILIUM_AUDIT_COUNTER_001["Silent parallel audit counter<br><small>CONSILIUM-AUDIT-COUNTER-001</small>"]
    CONSILIUM_AUDIT_FEEDBACK_001["Orphan run detection and PEND backfill<br><small>CONSILIUM-AUDIT-FEEDBACK-001</small>"]
    CONSILIUM_BUILD_REPORT_001["build_report<br><small>CONSILIUM-BUILD-REPORT-001</small>"]
    CONSILIUM_CHECK_DOC_DRIFT_001["check_doc_drift<br><small>CONSILIUM-CHECK-DOC-DRIFT-001</small>"]
    CONSILIUM_CHECK_DOC_DRIFT_EXPLAINER_001["check_doc_drift — explainer parity checks<br><small>CONSILIUM-CHECK-DOC-DRIFT-EXPLAINER-001</small>"]
    CONSILIUM_CHECK_PUBLIC_LEAK_001["check_public_leak<br><small>CONSILIUM-CHECK-PUBLIC-LEAK-001</small>"]
    CONSILIUM_CHECK_VERSIONS_001["check_versions<br><small>CONSILIUM-CHECK-VERSIONS-001</small>"]
    CONSILIUM_CONFIDENCE_001["confidence<br><small>CONSILIUM-CONFIDENCE-001</small>"]
    CONSILIUM_CONFIDENCE_CALIBRATION_001["confidence_calibration<br><small>CONSILIUM-CONFIDENCE-CALIBRATION-001</small>"]
    CONSILIUM_FEEDBACK_001["feedback<br><small>CONSILIUM-FEEDBACK-001</small>"]
    CONSILIUM_IMPLEMENT_CODER_001["implement-coder<br><small>CONSILIUM-IMPLEMENT-CODER-001</small>"]
    CONSILIUM_IMPLEMENT_PIPELINE_001["implement_pipeline<br><small>CONSILIUM-IMPLEMENT-PIPELINE-001</small>"]
    CONSILIUM_IMPLEMENT_SUBAGENT_001["consilium-implement-subagent<br><small>CONSILIUM-IMPLEMENT-SUBAGENT-001</small>"]
    CONSILIUM_IMPLEMENT_TEST_WRITER_001["implement-test-writer<br><small>CONSILIUM-IMPLEMENT-TEST-WRITER-001</small>"]
    CONSILIUM_INFER_PIPELINE_001["Infer implementation pipeline steps<br><small>CONSILIUM-INFER-PIPELINE-001</small>"]
    CONSILIUM_LENS_ESSENTIALIST_001["essentialist lens<br><small>CONSILIUM-LENS-ESSENTIALIST-001</small>"]
    CONSILIUM_LENS_SENTINEL_001["sentinel lens<br><small>CONSILIUM-LENS-SENTINEL-001</small>"]
    CONSILIUM_LENS_VERIFIER_001["verifier lens<br><small>CONSILIUM-LENS-VERIFIER-001</small>"]
    CONSILIUM_LOG_FEEDBACK_001["log_feedback<br><small>CONSILIUM-LOG-FEEDBACK-001</small>"]
    CONSILIUM_MARK_OUTCOME_001["mark_outcome<br><small>CONSILIUM-MARK-OUTCOME-001</small>"]
    CONSILIUM_MEMORY_001["memory<br><small>CONSILIUM-MEMORY-001</small>"]
    CONSILIUM_MODE_DIALECTIC_001["dialectic mode<br><small>CONSILIUM-MODE-DIALECTIC-001</small>"]
    CONSILIUM_MODE_LENS_001["opt-in personality-lens ladder ('--lens')<br><small>CONSILIUM-MODE-LENS-001</small>"]
    CONSILIUM_MODE_SEQUENTIAL_001["sequential mode<br><small>CONSILIUM-MODE-SEQUENTIAL-001</small>"]
    CONSILIUM_MODE_SKEPTIC_ON_CHOSEN_001["skeptic_on_chosen flag<br><small>CONSILIUM-MODE-SKEPTIC-ON-CHOSEN-001</small>"]
    CONSILIUM_MODE_TRIAS_001["trias mode<br><small>CONSILIUM-MODE-TRIAS-001</small>"]
    CONSILIUM_PERSONALITIES_001["personalities<br><small>CONSILIUM-PERSONALITIES-001</small>"]
    CONSILIUM_PRIORS_001["priors<br><small>CONSILIUM-PRIORS-001</small>"]
    CONSILIUM_RENDER_FEEDBACK_HTML_001["render_feedback_html<br><small>CONSILIUM-RENDER-FEEDBACK-HTML-001</small>"]
    CONSILIUM_RENDER_IMPL_PREVIEW_001["render_impl_preview<br><small>CONSILIUM-RENDER-IMPL-PREVIEW-001</small>"]
    CONSILIUM_RUN_EVALS_001["run_evals<br><small>CONSILIUM-RUN-EVALS-001</small>"]
    CONSILIUM_SCOPE_GATE_001["scope_gate<br><small>CONSILIUM-SCOPE-GATE-001</small>"]
    CONSILIUM_STRIP_CONTEXT_001["strip_context<br><small>CONSILIUM-STRIP-CONTEXT-001</small>"]
    CONSILIUM_SUBAGENT_001["consilium-subagent<br><small>CONSILIUM-SUBAGENT-001</small>"]
    CONSILIUM_TRIAS_MODEL_SCHEMA_001["trias-model-assignment<br><small>CONSILIUM-TRIAS-MODEL-SCHEMA-001</small>"]
    CONSILIUM_UTILS_001["utils<br><small>CONSILIUM-UTILS-001</small>"]
    CONSILIUM_VALIDATE_REPORT_001["validate_report<br><small>CONSILIUM-VALIDATE-REPORT-001</small>"]
    CONSILIUM_VALIDATE_SKEPTIC_001["validate_skeptic<br><small>CONSILIUM-VALIDATE-SKEPTIC-001</small>"]
    CONSILIUM_VERSION_001["version<br><small>CONSILIUM-VERSION-001</small>"]
    CONSILIUM_VOCABULARY_MAP_001["vocabulary_map<br><small>CONSILIUM-VOCABULARY-MAP-001</small>"]
    CONSILIUM_VOICE_CONSERVATOR_001["conservator voice<br><small>CONSILIUM-VOICE-CONSERVATOR-001</small>"]
    CONSILIUM_VOICE_CONTROL_001["control voice<br><small>CONSILIUM-VOICE-CONTROL-001</small>"]
    CONSILIUM_VOICE_GENERATOR_001["generator voice<br><small>CONSILIUM-VOICE-GENERATOR-001</small>"]
    CONSILIUM_VOICE_SKEPTIC_001["skeptic voice<br><small>CONSILIUM-VOICE-SKEPTIC-001</small>"]
    CONSILIUM_VOTE_DEGENERACY_001["Trias vote degeneracy measurement<br><small>CONSILIUM-VOTE-DEGENERACY-001</small>"]
  end
  subgraph sg_SYS["SYS"]
    SYS_CONSILIUM_IMPLEMENT_001["A verified implementation from a GO verdict<br><small>SYS-CONSILIUM-IMPLEMENT-001</small>"]
    SYS_CONSILIUM_INTEGRITY_001["A repository that stays consistent with itself<br><small>SYS-CONSILIUM-INTEGRITY-001</small>"]
    SYS_CONSILIUM_VERDICT_001["A trustworthy verdict on a change before it is committed<br><small>SYS-CONSILIUM-VERDICT-001</small>"]
  end
  subgraph sg_misc["misc"]
    SKILL_RUN_CONSILIUM_001["run-consilium driver<br><small>SKILL-RUN-CONSILIUM-001</small>"]
  end
  ARCH_CONSILIUM_IMPLEMENT_001 --> CONSILIUM_IMPLEMENT_PIPELINE_001
  ARCH_CONSILIUM_IMPLEMENT_001 --> CONSILIUM_IMPLEMENT_CODER_001
  ARCH_CONSILIUM_IMPLEMENT_001 --> CONSILIUM_IMPLEMENT_TEST_WRITER_001
  ARCH_CONSILIUM_IMPLEMENT_001 --> CONSILIUM_IMPLEMENT_SUBAGENT_001
  ARCH_CONSILIUM_IMPLEMENT_001 --> CONSILIUM_INFER_PIPELINE_001
  ARCH_CONSILIUM_LEARNING_001 --> CONSILIUM_LOG_FEEDBACK_001
  ARCH_CONSILIUM_LEARNING_001 --> CONSILIUM_MARK_OUTCOME_001
  ARCH_CONSILIUM_LEARNING_001 --> CONSILIUM_MEMORY_001
  ARCH_CONSILIUM_LEARNING_001 --> CONSILIUM_PRIORS_001
  ARCH_CONSILIUM_LEARNING_001 --> CONSILIUM_AUDIT_FEEDBACK_001
  ARCH_CONSILIUM_LEARNING_001 --> CONSILIUM_CONFIDENCE_CALIBRATION_001
  ARCH_CONSILIUM_MODES_001 --> CONSILIUM_MODE_SEQUENTIAL_001
  ARCH_CONSILIUM_MODES_001 --> CONSILIUM_MODE_DIALECTIC_001
  ARCH_CONSILIUM_MODES_001 --> CONSILIUM_MODE_TRIAS_001
  ARCH_CONSILIUM_MODES_001 --> CONSILIUM_MODE_SKEPTIC_ON_CHOSEN_001
  ARCH_CONSILIUM_MODES_001 --> CONSILIUM_MODE_LENS_001
  ARCH_CONSILIUM_MODES_001 --> CONSILIUM_VOTE_DEGENERACY_001
  ARCH_CONSILIUM_REPO_GATES_001 --> CONSILIUM_CHECK_DOC_DRIFT_001
  ARCH_CONSILIUM_REPO_GATES_001 --> CONSILIUM_CHECK_DOC_DRIFT_EXPLAINER_001
  ARCH_CONSILIUM_REPO_GATES_001 --> CONSILIUM_CHECK_PUBLIC_LEAK_001
  ARCH_CONSILIUM_REPO_GATES_001 --> CONSILIUM_CHECK_VERSIONS_001
  ARCH_CONSILIUM_REPO_GATES_001 --> CONSILIUM_RUN_EVALS_001
  ARCH_CONSILIUM_REPO_GATES_001 --> SKILL_RUN_CONSILIUM_001
  ARCH_CONSILIUM_REPORT_001 --> CONSILIUM_AGGREGATOR_001
  ARCH_CONSILIUM_REPORT_001 --> CONSILIUM_CONFIDENCE_001
  ARCH_CONSILIUM_REPORT_001 --> CONSILIUM_BUILD_REPORT_001
  ARCH_CONSILIUM_REPORT_001 --> CONSILIUM_STRIP_CONTEXT_001
  ARCH_CONSILIUM_REPORT_001 --> CONSILIUM_SCOPE_GATE_001
  ARCH_CONSILIUM_VOICES_001 --> CONSILIUM_VOICE_GENERATOR_001
  ARCH_CONSILIUM_VOICES_001 --> CONSILIUM_VOICE_CONTROL_001
  ARCH_CONSILIUM_VOICES_001 --> CONSILIUM_VOICE_CONSERVATOR_001
  ARCH_CONSILIUM_VOICES_001 --> CONSILIUM_VOICE_SKEPTIC_001
  ARCH_CONSILIUM_VOICES_001 --> CONSILIUM_LENS_ESSENTIALIST_001
  ARCH_CONSILIUM_VOICES_001 --> CONSILIUM_LENS_VERIFIER_001
  ARCH_CONSILIUM_VOICES_001 --> CONSILIUM_LENS_SENTINEL_001
  CONSILIUM_IMPLEMENT_CODER_001 --> CONSILIUM_IMPLEMENT_PIPELINE_001
  CONSILIUM_IMPLEMENT_SUBAGENT_001 --> CONSILIUM_IMPLEMENT_PIPELINE_001
  CONSILIUM_IMPLEMENT_TEST_WRITER_001 --> CONSILIUM_IMPLEMENT_PIPELINE_001
  CONSILIUM_INFER_PIPELINE_001 --> CONSILIUM_IMPLEMENT_PIPELINE_001
  CONSILIUM_MODE_DIALECTIC_001 --> CONSILIUM_MODE_SEQUENTIAL_001
  CONSILIUM_MODE_DIALECTIC_001 --> CONSILIUM_VOICE_SKEPTIC_001
  CONSILIUM_MODE_LENS_001 --> CONSILIUM_LENS_ESSENTIALIST_001
  CONSILIUM_MODE_LENS_001 --> CONSILIUM_LENS_VERIFIER_001
  CONSILIUM_MODE_LENS_001 --> CONSILIUM_MODE_SEQUENTIAL_001
  CONSILIUM_MODE_LENS_001 --> CONSILIUM_MODE_DIALECTIC_001
  CONSILIUM_MODE_SEQUENTIAL_001 --> CONSILIUM_VOICE_GENERATOR_001
  CONSILIUM_MODE_SEQUENTIAL_001 --> CONSILIUM_VOICE_CONTROL_001
  CONSILIUM_MODE_SEQUENTIAL_001 --> CONSILIUM_VOICE_CONSERVATOR_001
  CONSILIUM_MODE_SEQUENTIAL_001 --> CONSILIUM_AGGREGATOR_001
  CONSILIUM_MODE_SKEPTIC_ON_CHOSEN_001 --> CONSILIUM_VOICE_SKEPTIC_001
  CONSILIUM_MODE_TRIAS_001 --> CONSILIUM_MODE_SEQUENTIAL_001
  CONSILIUM_MODE_TRIAS_001 --> CONSILIUM_MODE_SKEPTIC_ON_CHOSEN_001
  CONSILIUM_MODE_TRIAS_001 --> CONSILIUM_LENS_ESSENTIALIST_001
  CONSILIUM_MODE_TRIAS_001 --> CONSILIUM_LENS_VERIFIER_001
  CONSILIUM_MODE_TRIAS_001 --> CONSILIUM_LENS_SENTINEL_001
  CONSILIUM_SUBAGENT_001 --> CONSILIUM_MODE_SEQUENTIAL_001
  CONSILIUM_TRIAS_MODEL_SCHEMA_001 --> CONSILIUM_MODE_TRIAS_001
  CONSILIUM_VALIDATE_SKEPTIC_001 --> CONSILIUM_VOICE_SKEPTIC_001
  SKILL_RUN_CONSILIUM_001 --> CONSILIUM_AGGREGATOR_001
  SKILL_RUN_CONSILIUM_001 --> CONSILIUM_CONFIDENCE_001
  style CONSILIUM_FEEDBACK_001 stroke-width:3px
  style CONSILIUM_PERSONALITIES_001 stroke-width:3px
  style CONSILIUM_RENDER_FEEDBACK_HTML_001 stroke-width:3px
  style CONSILIUM_RENDER_IMPL_PREVIEW_001 stroke-width:3px
  style CONSILIUM_SUBAGENT_001 stroke-width:3px
  style CONSILIUM_TRIAS_MODEL_SCHEMA_001 stroke-width:3px
  style CONSILIUM_UTILS_001 stroke-width:3px
  style CONSILIUM_VALIDATE_REPORT_001 stroke-width:3px
  style CONSILIUM_VALIDATE_SKEPTIC_001 stroke-width:3px
  style CONSILIUM_VERSION_001 stroke-width:3px
  style CONSILIUM_VOCABULARY_MAP_001 stroke-width:3px
```

## Requirement-to-Code

_Each system/architecture requirement → its code; arrow label = role (`implements` / `tested-by`). Red = confirmed but no code linked (a gap); grey = baseline/draft, not linked yet (expected). Code-level requirements are omitted here (see the viewer)._

```mermaid
graph LR
  ARCH_CONSILIUM_IMPLEMENT_001["Implementation pipeline<br><small>ARCH-CONSILIUM-IMPLEMENT-001</small>"]
  f_docs_architecture_html_4["docs/architecture.html:4"]
  ARCH_CONSILIUM_IMPLEMENT_001 -->|generated-from| f_docs_architecture_html_4
  f_docs_architecture_index_html_4["docs/architecture/index.html:4"]
  ARCH_CONSILIUM_IMPLEMENT_001 -->|generated-from| f_docs_architecture_index_html_4
  ARCH_CONSILIUM_LEARNING_001["Learning loop: feedback journal, outcomes and priors<br><small>ARCH-CONSILIUM-LEARNING-001</small>"]
  f_docs_architecture_html_4["docs/architecture.html:4"]
  ARCH_CONSILIUM_LEARNING_001 -->|generated-from| f_docs_architecture_html_4
  f_docs_architecture_index_html_4["docs/architecture/index.html:4"]
  ARCH_CONSILIUM_LEARNING_001 -->|generated-from| f_docs_architecture_index_html_4
  ARCH_CONSILIUM_MODES_001["Deliberation modes<br><small>ARCH-CONSILIUM-MODES-001</small>"]
  f_docs_architecture_html_4["docs/architecture.html:4"]
  ARCH_CONSILIUM_MODES_001 -->|generated-from| f_docs_architecture_html_4
  f_docs_architecture_index_html_4["docs/architecture/index.html:4"]
  ARCH_CONSILIUM_MODES_001 -->|generated-from| f_docs_architecture_index_html_4
  ARCH_CONSILIUM_REPO_GATES_001["Repository gates<br><small>ARCH-CONSILIUM-REPO-GATES-001</small>"]
  f_docs_architecture_html_4["docs/architecture.html:4"]
  ARCH_CONSILIUM_REPO_GATES_001 -->|generated-from| f_docs_architecture_html_4
  f_docs_architecture_index_html_4["docs/architecture/index.html:4"]
  ARCH_CONSILIUM_REPO_GATES_001 -->|generated-from| f_docs_architecture_index_html_4
  ARCH_CONSILIUM_REPORT_001["Report pipeline: aggregate, score, assemble, validate<br><small>ARCH-CONSILIUM-REPORT-001</small>"]
  f_docs_architecture_html_4["docs/architecture.html:4"]
  ARCH_CONSILIUM_REPORT_001 -->|generated-from| f_docs_architecture_html_4
  f_docs_architecture_index_html_4["docs/architecture/index.html:4"]
  ARCH_CONSILIUM_REPORT_001 -->|generated-from| f_docs_architecture_index_html_4
  ARCH_CONSILIUM_VOICES_001["Deliberation voices and personality lenses<br><small>ARCH-CONSILIUM-VOICES-001</small>"]
  f_docs_architecture_html_4["docs/architecture.html:4"]
  ARCH_CONSILIUM_VOICES_001 -->|generated-from| f_docs_architecture_html_4
  f_docs_architecture_index_html_4["docs/architecture/index.html:4"]
  ARCH_CONSILIUM_VOICES_001 -->|generated-from| f_docs_architecture_index_html_4
  SYS_CONSILIUM_IMPLEMENT_001["A verified implementation from a GO verdict<br><small>SYS-CONSILIUM-IMPLEMENT-001</small>"]
  style SYS_CONSILIUM_IMPLEMENT_001 fill:#fee,stroke:#c66
  SYS_CONSILIUM_INTEGRITY_001["A repository that stays consistent with itself<br><small>SYS-CONSILIUM-INTEGRITY-001</small>"]
  style SYS_CONSILIUM_INTEGRITY_001 fill:#fee,stroke:#c66
  SYS_CONSILIUM_VERDICT_001["A trustworthy verdict on a change before it is committed<br><small>SYS-CONSILIUM-VERDICT-001</small>"]
  f_docs_architecture_html_4["docs/architecture.html:4"]
  SYS_CONSILIUM_VERDICT_001 -->|generated-from| f_docs_architecture_html_4
  f_docs_architecture_index_html_4["docs/architecture/index.html:4"]
  SYS_CONSILIUM_VERDICT_001 -->|generated-from| f_docs_architecture_index_html_4
```

## Dependency Map

_Area-level coupling: one box per area (N caps), arrow A->B = some capability in A depends on one in B. The System Map has the per-capability detail._

```mermaid
graph LR
  a_ARCH["ARCH<br><small>6 caps</small>"]
  a_CONSILIUM["CONSILIUM<br><small>46 caps</small>"]
  a_SYS["SYS<br><small>3 caps</small>"]
  a_misc["misc<br><small>1 caps</small>"]
  a_ARCH --> a_CONSILIUM
  a_ARCH --> a_misc
  a_misc --> a_CONSILIUM
  style a_CONSILIUM stroke-width:3px
```

## Risk & Unknowns

_Requirements needing attention: red = unimplemented (confirmed, no code); orange = unreviewed (promote after review); yellow = untested (implemented but no tested-by — set `test_exempt` to silence), or unverified-intent (open verify-intent question)._

```mermaid
graph LR
  ok["No risk signals detected"]
```
