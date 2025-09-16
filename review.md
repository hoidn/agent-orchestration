to add to claude.md:
-### 3. Running Tests (Backpressure)
-
--   **Run all tests**: Use `pytest` from the project root. Do not use a custom script or manipulate `sys.path`.
-    ```bash
-    pytest -v
-    ```

+### 3. Testing Strategy (Backpressure)
+
+This project uses a tiered testing strategy. It is critical to run the correct suite for the task at hand.
+
+#### Tier 1 & 2: Unit & Fast Integration Tests (Default)
+
+These tests are fast, run locally without network access, and verify all internal logic. The integration tests use fake provider scripts (`tests/fakes/`) to test the full execution pipeline.
+
+-   **Purpose**: Core logic validation, pre-commit checks, main CI loop.
+-   **How to Run**: This is the default command. It runs all tests that are *not* marked as `e2e`.
+    ```bash
+    pytest -v
+    ```
+
+#### Tier 3: End-to-End (E2E) Tests with Real agents
+
+These tests are slow and require network access. They are essential for final validation but should not be run during routine development.
+
+-   **How to Run**: Use the `pytest` marker `-m e2e`.
+    ```bash
+    pytest -v -m e2e
+    ```
