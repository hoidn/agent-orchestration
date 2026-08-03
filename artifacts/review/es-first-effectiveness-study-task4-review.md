# ES First Effectiveness Study Task 4 Review

Status: approved; ES Tasks 0–4 are complete and Task 5 is selected. Live
provider allocation remains gated on the exact Task-6 scientific-lock owner
adoption.

Reviewed implementation:

- base commit:
  `4998e7509af0b1f05840e3fa50dfdae99f28de5c`, tree
  `b20769c5fcbb3e548a5146b6de204a1c18435671`
- implementation commit:
  `d72c6085a3d3fdda23ec3ce48d1dd96a3585529d`, tree
  `4e576d09b92dd5877f8326ba057127923de8f77e`
- reviewed binary-diff SHA-256:
  `52802bc7567384288a610f66885383ed14292e445268c8ebd9f26f5f3ac4a2d8`

Frozen implementation bindings:

- provider registry:
  `sha256:b3cb58c13d9ad0dd8c280fc381944577fc5fc2c6a5f048defe313eb24e61b83f`
- trial consuming-site typecheck:
  `sha256:50bb853eedb30bfd8e47d69ed1729f67e910fbdf003775cd0b54cd0bd8a61c20`
- provider specification:
  `sha256:3e02267753c60c65866a67be51e9aa3aa60b3f5b1f3b19d868a39a091954331f`
- treatment arms:
  `sha256:af07155a121bdf86ee5b057c68c29828c3ce13d93966770aba106e0c6a787315`
- four-cell trial:
  `sha256:fec828de15f900a070e6caf96c54b296b8bc5bc15a6240e5d842ca7ee0f1028d`
- provider externs:
  `sha256:30c70c1ef7ccb81a7f28a86f3e15f40ff5b58038fc6b5b53552d6a6f74605ffb`
- prompt externs:
  `sha256:fd0401fd15769e18f2ddf1a5bb4fd2c316036845563db1fca84fe561aa0d7ef6`
- trial rubric:
  `sha256:ef4a30bc3b200a3ad014034af2b1e7e6dd04bfc2679d046e3a05336462f5d935`
- structural contract tests:
  `sha256:c9abeb1a2dcabcf1989acb55104ceb1e88e1a3c868cc5c3b4eda310bdefc476c`
- runtime and four-cell tests:
  `sha256:0c3d8000d14c454404ed0d41d90b1f8e5be6aa8a54947f0be18235a528d181ac`
- provider-policy tests:
  `sha256:b0d1b1e59a9daaa98b63c95d8d91295520e47ef2249143b21076d1824e5cad9b`
- trial frontend tests:
  `sha256:86a37616ecd01397c28ba62d28eea0dc58435fb1f3e014185d97b97d4c9710f1`
- trial lowering tests:
  `sha256:9bc57304ceb09adffcd36672d7046a26fb7b238eb7e721a9d779eb2a252d5d45`
- trial adjudication fixtures:
  `sha256:9704a94bda990b825f40613875f85245565bd910e825352f35646c5c11bcc6d0`
- trial end-to-end fixtures:
  `sha256:00a26b1f6982af2ee0942248b98fe535415ed571f89b3b7049868cba6ef844be`

Ordered final-byte verdicts:

1. `ES_TASK4_SPEC_APPROVED`
2. `ES_TASK4_QUALITY_APPROVED`

## Findings resolved before approval

The initial specification review rejected a locally duplicated DIRECT arm,
provider-authored output paths, and runtime coverage that did not execute the
complete locked route set or a real sibling-preserving failure. The corrected
workflow imports the canonical DIRECT implementation, uses compiler-owned
`:out` paths, and executes all 22 route rows plus colliding `BLOCKED`, malformed
typed-review, and sibling-settlement cases.

A second specification pass found that E2 scorer preparation supplied empty
provider parameters to the no-default unrestricted profile and that action
failure rows used malformed bundles rather than valid `Bool=false` values.
The corrected candidate uses one generic defaulted unrestricted
`gpt-5.5`/`high` profile for every role and scorer and gives action-failure
rows valid typed false results.

The direct scorer-preparation regression then exposed that trial typechecking
validated `ProviderExtern` but serialized its authored alias. The generic fix
retains the alias in the parsed source expression while carrying the resolved
provider ID in the typed expression and static runtime contract. Existing
missing-provider and missing-rubric diagnostics remain fail closed. The first
full-suite run found two shared injected test fixtures that still required the
authored alias; the final fixtures require only the resolved provider ID and
do not accept both forms. The corrected exact bytes received a specification
replay before the distinct quality review.

## Evidence and boundary

The focused candidate gate passed 222 tests in 36.04 seconds. The six-module
regression cluster passed 56 tests in 12.95 seconds, the adjacent E2/ES gate
passed 89 tests in 6.20 seconds, and Pyright reported zero diagnostics on the
changed public surfaces. The final full-repository control passed 12,916 tests
with 23 skips in 408.63 seconds. Fresh postcommit controls passed 222 tests in
35.87 seconds and 56 tests in 12.46 seconds.

Task 4 implements four ordinary target-2.25 treatment workflows with a common
`Bool` result, exact bounded call topology, fresh calls, one nonceremonial
correction per placement, typed review decisions, compiler-owned artifact
paths, and one E2 four-cell entry. It makes no provider-bearing attempt and
does not adopt the proposed scientific lock, implement the Task-5 controller,
authorize E3, or make whole-program effectiveness or promotion claims.
