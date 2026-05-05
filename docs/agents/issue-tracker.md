# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

The canonical upstream is `toolsforexperiments/instrumentserver`. The local clone has multiple remotes (`origin` = personal fork `marcosfrenkel/instrumentserver`, `upstream` = canonical, `chao` = `hatlabcz/instrumentserver`). When creating or reading issues, target the upstream by passing `--repo toolsforexperiments/instrumentserver` unless the user explicitly asks for a fork.

## Conventions

- **Create an issue**: `gh issue create --repo toolsforexperiments/instrumentserver --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --repo toolsforexperiments/instrumentserver --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --repo toolsforexperiments/instrumentserver --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --repo toolsforexperiments/instrumentserver --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --repo toolsforexperiments/instrumentserver --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --repo toolsforexperiments/instrumentserver --comment "..."`

## When a skill says "publish to the issue tracker"

Create a GitHub issue on `toolsforexperiments/instrumentserver`.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --repo toolsforexperiments/instrumentserver --comments`.
