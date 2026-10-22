# Website issue reporting

Status: deferred. Planning only; implement after the GitHub Pages launch, when requested.

## Goal

Let someone using Embervale Atlas report a bug or suggest an improvement, with the report recorded as a GitHub issue.

## Repository access

The application repository, `daniellindem/enshrouded-map`, is public to support GitHub Pages on the current plan. Use its Issues for community reports. A separate feedback repository is unnecessary.

If the application repository becomes private later, public visitors will lose issue access. At that point, either limit reporting to invited collaborators or use a separate public repository containing only feedback and templates. Confirm that choice before changing the report destination.

Do not expose a personal access token in the website. GitHub Pages cannot safely hold credentials or run an authenticated server endpoint.

## Proposed scope

1. Add a small “Report an issue” entry in the website footer or help menu.
2. Open a compact form with report type, title, description, steps to reproduce, and expected behaviour. Make the reproduction fields optional for suggestions.
3. Offer an optional checkbox to include the current map view or plan link. Explain that submitting it shares altar names and locations. Do not attach saved plans automatically.
4. Build an encoded GitHub new-issue URL with the supplied title and body. Open GitHub so the visitor can sign in, review the report, and submit it under their own account.
5. Add a “View reported issues” link to the target repository's issue list.
6. Add matching bug and suggestion templates in the application repository.

GitHub remains the issue tracker. The website needs no backend, database, GitHub API token, or custom account system. The first version does not create issues automatically or display a live issue feed.

## Acceptance checks

- Any visitor can open and submit an issue in `daniellindem/enshrouded-map` after signing in to GitHub, subject to the repository's GitHub interaction settings.
- Reports from the website include the entered title and description correctly, including Unicode and URL-special characters.
- The form validates required fields and handles very long reports without silently losing content. Provide a copyable report if it exceeds a safe URL length.
- Sharing a plan is opt-in. A report without consent includes no altar names, locations, or saved-plan data.
- The report remains editable on GitHub before submission. Cancelling does not create an issue.
- Buttons and fields work with keyboard navigation and narrow screens.
- No credentials appear in HTML, JavaScript, local storage, or network requests.
- The report destination remains accessible to site visitors and the Pages site continues working.

## References

- [GitHub repository visibility](https://docs.github.com/en/repositories/creating-and-managing-repositories/about-repositories)
- [Using query parameters to create an issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/creating-an-issue)
