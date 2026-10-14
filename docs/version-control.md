# GitHub and progress history

The project is saved in the private repository
[ahmadkamrancps-design/Digital-CCKAT](https://github.com/ahmadkamrancps-design/Digital-CCKAT).
The local `main` branch tracks `origin/main` through HTTPS with GitHub CLI
authentication. Linking the account has been completed and source has been pushed.

Recorded checkpoints:

- `a10ab75`: existing application through Milestone 5.
- `d011a87`: Milestone 6 administration portal, migration, tests, and handover.

Earlier milestones were not separately committed, so their historical code
snapshots cannot be reconstructed from the handovers alone. New milestones should
continue to receive focused commits and verified pushes.

The local folder is named `cck-digital-test`; the GitHub repository is
`Digital-CCKAT`. Include source, dependency
lockfiles, migrations, tests, public branding assets, and documentation. Actual
environment files, credentials, candidate data, database backups, dependencies,
build output, and test artifacts must stay outside Git. The root `.gitignore`
already excludes the normal local files; review new files before each commit.
Git records committed files, not database contents or this conversation.

## Inspect and synchronize the existing repository

Run inside Ubuntu/WSL at the project root:

```bash
git status
git log --oneline -5
git remote -v
git push origin main
```

Review and commit new source changes before pushing. The configured remote is
`https://github.com/ahmadkamrancps-design/Digital-CCKAT.git`. GitHub Actions runs
backend and frontend checks after pushes. Do not recreate `origin` or publish a
second repository for the current checkout.

## Initial publishing instructions for a different checkout

In VS Code, open this folder through WSL and use Source Control. Configure your
commit name/email if prompted; a GitHub noreply address is suitable. Review the
staged changes and create the initial commit with a message such as:

```text
Checkpoint CCK application through Milestone 5
```

Use **Publish to GitHub**, authenticate in the browser, and choose a **private**
repository with the intended project name. If a repository already exists, connect its
URL as `origin` and push the existing branch instead of creating another repo.
Complete authentication in GitHub/VS Code; never paste credentials into chat or
commit them into a file. Confirm that the repository shows the source files and
commit before treating it as a remote backup.

For an existing empty GitHub repository, after identity and authentication are
configured, these commands run inside Ubuntu/WSL at the project root:

```bash
git remote add origin https://github.com/YOUR_USERNAME/cck-digital-test.git
git push -u origin main
```

Replace the username with the actual account. If `origin` already exists, inspect
`git remote -v` before changing it. Do not force-push or overwrite another
repository's history. HTTPS pushes need a configured Git credential helper or
GitHub CLI authentication; connecting Codex Cloud does not replace local Git
authentication.

## Connect Codex Cloud

For cloud tasks, create/select a Codex Cloud environment, choose the GitHub
repository, and complete GitHub connection when prompted. Review the environment
setup, then publish it before starting cloud tasks. See the
[official OpenAI Codex Cloud instructions](https://learn.chatgpt.com/docs/cloud).
Local Codex can continue working in this folder using its local Git checkout.

## Record later progress

After a milestone or meaningful fix:

1. Run the checks relevant to the change and update its handover.
2. Review `git status` and the diff, including newly added files and secret exclusions.
3. Make a focused commit with a message describing the completed work.
4. Push to the configured repository and verify the remote branch matches.

Commits and GitHub synchronization are explicit actions; linking an account alone
does not upload every edit. Failed checks should be documented honestly, and work
in progress should be labeled as such. Database backup and recovery remain a
separate operational responsibility.
