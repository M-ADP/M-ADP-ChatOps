# ChatOps CI/CD Design

## Goal

Add the same GitHub Actions CI/CD entrypoints already used by sibling services so the `M-ADP-ChatOps` repository can trigger dev deployment, dev rollback, and hotfix deployment through the shared reusable workflows.

## Source of Truth

- Base workflow set: `/Users/jjm/Desktop/M-ADP-APPLICATION-DEPLOYMENT/.github/workflows`
- Secondary reference: `/Users/jjm/Desktop/M-ADP-PROJECT/.github/workflows`

## Chosen Approach

Copy the existing workflow structure from `application-deployment` and keep behavior aligned with the current platform convention, while normalizing filenames for this repository under `.github/workflows`.

## Files to Add

- `.github/workflows/deploy-dev.yaml`
- `.github/workflows/rollback-dev.yaml`
- `.github/workflows/deploy-hotfix.yaml`

## Behavior

- Push to `dev-*` branches triggers dev deployment.
- Push to `hotfix-*` branches triggers dev deployment.
- Manual dispatch with a `version` input triggers rollback of the dev environment to the requested version.

## Reusable Workflows and Secrets

- Reuse `M-ADP/M-ADP-GITHUB-ACTIONS/.github/workflows/dev.yaml@master`
- Reuse `M-ADP/M-ADP-GITHUB-ACTIONS/.github/workflows/rollback.yaml@master`
- Keep secret contract identical to the reference repositories:
  - `DOCKERHUB_USERNAME`
  - `DOCKERHUB_TOKEN`
  - `PERSONAL_TOKEN`

## Notes

- This is a configuration-only change; no application runtime code is modified.
- Validation will focus on file placement and YAML parsing.
