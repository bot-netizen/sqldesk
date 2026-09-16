# Contributing Guide

Thank you for taking the time to contribute! :tada::+1:

The following is a set of guidelines for contributing to Tealdash. These are guidelines, not rules, please use your best judgement and feel free to propose changes to this document in a pull request.

:star: If you're already here and love the project, please make sure to press the Star button. :star:
## Table of Contents

[How can I contribute?](#how-can-i-contribute)

- [Reporting Bugs](#reporting-bugs)
- [Suggesting Enhancements / Feature Requests](#suggesting-enhancements--feature-requests)
- [Pull Requests](#pull-requests)
- [Documentation](#documentation)
- Design?

[Additional Notes](#additional-notes)

- [Release Method](#release-method)
- [Code of Conduct](#code-of-conduct)

## Quick Links:

- [Discussions](https://github.com/tdot-labs/tealdash/discussions)
- [Documentation](https://tdot-labs.github.io/tealdash/)


---
## How can I contribute?

### Reporting Bugs

When creating a new bug report, please make sure to:

- Search for existing issues first. If you find a previous report of your issue, please update the existing issue with additional information instead of creating a new one.
- If you are not sure if your issue is really a bug or just some configuration/setup problem, please start a [Q&A discussion](https://github.com/tdot-labs/tealdash/discussions/new?category=q-a) first. Unless you can provide clear steps to reproduce, it's probably better to start with a discussion and later to open an issue.
- If you still decide to open an issue, please review the template and guidelines and include as much details as possible.

### Suggesting Enhancements / Feature Requests

If you would like to suggest an enhancement or ask for a new feature:

- Please check [the Ideas discussions](https://github.com/tdot-labs/tealdash/discussions/categories/ideas) for existing threads about what you want to suggest/ask. If there is, feel free to upvote it to signal interest or add your comments.
- If there is no open thread, you're welcome to start one to have a discussion about what you want to suggest. Try to provide as much details and context as possible and include information about *the problem you want to solve* rather only *your proposed solution*.

### Pull Requests

**Code contributions are welcomed**. For big changes or significant features, it's usually better to reach out first and discuss what you want to implement and how (we recommend reading: [Pull Request First](https://medium.com/practical-blend/pull-request-first-f6bb667a9b6#.ozlqxvj36)). This is to make sure that what you want to implement is aligned with our goals for the project and that no one else is already working on it.

#### Criteria for Review / Merging

When you open your pull request, please follow this repository’s PR template carefully:

- Indicate the type of change
  - If you implement multiple unrelated features, bug fixes, or refactors please split them into individual pull requests.
- Describe the change 
- If fixing a bug, please describe the bug or link to an existing github issue / forum discussion
- Include UI screenshots / GIFs whenever possible
- Please add [documentation](#documentation) for new features or changes in functionality along with the code.
- Please follow existing code style:
  - Python: we use [Black](https://github.com/psf/black) to auto format the code.
  - Javascript: we use [Prettier](https://github.com/prettier/prettier) to auto-format the code.

#### Initial Review (1 week)

During this phase, a team member will apply the “Team Review” label if a pull request meets our criteria or a “Needs More Information” label if not. If more information is required, the team member will comment which criteria have not been met.

If your pull request receives the “Needs More Information” label, please make the requested changes and then remove the label. This resets the 1 week timer for an initial review.

Stale pull requests that remain untouched in “Needs More Information” for more than 4 weeks will be closed.

If a team member closes your pull request, you may reopen it after you have made the changes requested during initial review. After you make these changes, remove the “Needs More Information” label. This again resets the timer for another initial review.

#### Full Review (2 weeks)

After the “Team Review” label is applied, a member of the core team will review the PR within 2 weeks. 

Reviews will approve, request changes, or ask questions to discuss areas of uncertainty. After you’ve responded, a member of the team will re-review within one week.

#### Merging (1 week)

After your pull request has been approved, a member of the core team will merge the pull request within a week.

### Documentation

The site at [tdot-labs.github.io/tealdash](https://tdot-labs.github.io/tealdash/) is built from the `docs/` directory in this repository and published by GitHub Pages on every push to `main`. Edit the HTML there and open a pull request; there is no separate docs repository and no build step.

## Additional Notes

### Release Method

We publish a stable release every ~3-4 months, although the goal is to get to a stable release every month. 

Every build of the master branch updates the *tealdash/tealdash:preview* Docker Image. These releases are usually stable, but might contain regressions and therefore recommended for "advanced users" only.

When we release a new stable release, we also update the *latest* Docker image tag, the EC2 AMIs and GCE images.

## Code of Conduct

This project adheres to the Contributor Covenant [code of conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating, you are expected to uphold this code. Please report unacceptable behavior through a GitHub issue.
