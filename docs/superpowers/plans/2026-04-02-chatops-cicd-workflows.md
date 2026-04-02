# ChatOps CI/CD Workflows Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the standard dev deploy, dev rollback, and hotfix deploy GitHub Actions workflows to the ChatOps repository.

**Architecture:** Reuse the same shared GitHub Actions workflows used by adjacent M-ADP services and keep the repository-local files as thin entrypoints. Limit the change to workflow configuration so behavior stays aligned with the established deployment convention.

**Tech Stack:** GitHub Actions YAML, reusable workflows, repository secrets

---

### Task 1: Add deploy workflow entrypoints

**Files:**
- Create: `.github/workflows/deploy-dev.yaml`
- Create: `.github/workflows/deploy-hotfix.yaml`
- Reference: `/Users/jjm/Desktop/M-ADP-APPLICATION-DEPLOYMENT/.github/workflows/deploy-dev.yaml`
- Reference: `/Users/jjm/Desktop/M-ADP-APPLICATION-DEPLOYMENT/.github/workflows/deploy-hotfix.yaml`

- [ ] **Step 1: Create the dev deploy workflow**

Add a workflow that triggers on push to `dev-*`, grants `contents`, `packages`, and `pull-requests` write permissions, and calls `M-ADP/M-ADP-GITHUB-ACTIONS/.github/workflows/dev.yaml@master` with `deploy_repo: "M-ADP/M-ADP-ARGOCD"`.

- [ ] **Step 2: Create the hotfix deploy workflow**

Add a workflow that mirrors the dev deploy workflow but triggers on push to `hotfix-*`.

- [ ] **Step 3: Validate the YAML files parse**

Run: `python3 -c "import yaml, pathlib; [yaml.safe_load(path.read_text()) for path in pathlib.Path('.github/workflows').glob('*.yaml')]; print('yaml ok')"`
Expected: `yaml ok`

### Task 2: Add rollback workflow entrypoint

**Files:**
- Create: `.github/workflows/rollback-dev.yaml`
- Reference: `/Users/jjm/Desktop/M-ADP-APPLICATION-DEPLOYMENT/.github/workflows/rollback-dev.yaml`

- [ ] **Step 1: Create the rollback workflow**

Add a workflow that supports `workflow_dispatch`, requires a `version` string input, and calls `M-ADP/M-ADP-GITHUB-ACTIONS/.github/workflows/rollback.yaml@master` with `target_env: "dev"`, `target_version: ${{ inputs.version }}`, and `deploy_repo: "M-ADP/M-ADP-ARGOCD"`.

- [ ] **Step 2: Validate the full workflow set**

Run: `find .github/workflows -maxdepth 1 -type f | sort`
Expected: three workflow files are present.

- [ ] **Step 3: Re-run YAML validation**

Run: `python3 -c "import yaml, pathlib; [yaml.safe_load(path.read_text()) for path in pathlib.Path('.github/workflows').glob('*.yaml')]; print('yaml ok')"`
Expected: `yaml ok`
