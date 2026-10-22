# Website issue reporting

Status: deferred. Planning only; implement after the GitHub Pages launch, when requested.

## Goal

Let someone using Embervale Atlas report a bug or suggest an improvement, with the report recorded as a GitHub issue.

## Repository access

The application repository stays private. Public visitors cannot open issues there without repository access. For community reports, use a separate public repository containing only feedback and issue templates, such as `daniellindem/enshrouded-map-feedback`. Create that repository in this later phase, after confirming its public visibility. If reporting is limited to invited collaborators, the private application repository can be the target instead.

Do not expose a personal access token in the website. GitHub Pages cannot safely hold credentials or run an authenticated server endpoint.

## Proposed scope

1. Add a small “Report an issue” entry in the website footer or help menu.
2. Open a compact form with report type, title, description, steps to reproduce, and expected behaviour. Make the reproduction fields optional for suggestions.
3. Offer an optional checkbox to include the current map view or plan link. Explain that submitting it shares altar names and locations. Do not attach saved plans automatically.
4. Build an encoded GitHub new-issue URL with the supplied title and body. Open GitHub so the visitor can sign in, review the report, and submit it under their own account.
5. Add a “View reported issues” link to the target repository's issue list.
6. Add matching bug and suggestion templates in the feedback repository. Keep all application code in the private repository.

GitHub remains the issue tracker. The website needs no backend, database, GitHub API token, or custom account system. The first version does not create issues automatically or display a live issue feed.

## Acceptance checks

- A visitor without application-repository access can open and submit an issue in the public feedback repository after signing in to GitHub.
- Reports from the website include the entered title and description correctly, including Unicode and URL-special characters.
- The form validates required fields and handles very long reports without silently losing content. Provide a copyable report if it exceeds a safe URL length.
- Sharing a plan is opt-in. A report without consent includes no altar names, locations, or saved-plan data.
- The report remains editable on GitHub before submission. Cancelling does not create an issue.
- Buttons and fields work with keyboard navigation and narrow screens.
- No credentials appear in HTML, JavaScript, local storage, or network requests.
- The application repository remains private and the Pages site continues working.

## References

- [GitHub repository visibility](https://docs.github.com/en/repositories/creating-and-managing-repositories/about-repositories)
- [Using query parameters to create an issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/creating-an-issue)
