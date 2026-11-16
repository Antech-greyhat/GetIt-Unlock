<p align="center">
  <img src="docs/assets/readme-banner.svg" alt="GitHub Achievement Python — your next achievement, one workflow away" width="1200">
</p>

# GitHub Achievement Python

Run and verify five GitHub achievement workflows from an interactive menu or a command. The app creates the required PRs, issues, or discussions in a personal repository you own and saves its progress between runs.

<p align="center">
  <img src="docs/assets/project-info.svg" alt="Python 3.11+ · Five badge workflows · No extra Python packages · MIT code license" width="1000">
</p>

<p align="center">
  <a href="#pull-shark"><img src="docs/assets/badges/pull-shark.png" alt="Pull Shark guide" title="Pull Shark" width="88" height="88"></a>
  <a href="#pair-extraordinaire"><img src="docs/assets/badges/pair-extraordinaire.png" alt="Pair Extraordinaire guide" title="Pair Extraordinaire" width="88" height="88"></a>
  <a href="#quickdraw"><img src="docs/assets/badges/quickdraw.png" alt="Quickdraw guide" title="Quickdraw" width="88" height="88"></a>
  <a href="#yolo"><img src="docs/assets/badges/yolo.png" alt="YOLO guide" title="YOLO" width="88" height="88"></a>
  <a href="#galaxy-brain"><img src="docs/assets/badges/galaxy-brain.png" alt="Galaxy Brain guide" title="Galaxy Brain" width="88" height="88"></a>
</p>

**Badge guides:** [Pull Shark](#pull-shark) · [Pair Extraordinaire](#pair-extraordinaire) · [Quickdraw](#quickdraw) · [YOLO](#yolo) · [Galaxy Brain](#galaxy-brain)

> [!TIP]
> **Start with `.env`, then follow the numbered steps.** If you have not downloaded the app, use [Get the app](#get-the-app) first. You need Python 3.11 or newer; no extra Python packages are required.

## Find your next step

| Step | What you will do |
| :--- | :--- |
| **01 · [Set up tokens](#1-put-your-tokens-in-env)** | Configure your primary account, target repository, and optional helper. |
| **02 · [Check the connection](#2-check-the-repository-and-connection)** | Confirm the repository is ready and run `doctor`. |
| **03 · [Try Pull Shark](#3-run-your-first-pr-test)** | Choose a level and run from a command or the menu. |
| **04 · [Choose another badge](#4-run-another-badge)** | Check its level table, complete its prerequisites, and run. |
| **05 · [Check progress](#5-check-progress-and-badges)** | See completed operations and check your public badges. |
| **06 · [Clean up](#6-clean-up-leftover-branches)** | Preview and remove verified merged branches. |

[Common fixes](#common-fixes) · [Rate limits](#rate-limits-let-the-app-wait) · [Advanced options](ADVANCED.md) · [Get the app](#get-the-app)

---

## 1. Put your tokens in `.env`

Open the project folder. Create **`.env`** next to `main.py`, using [.env.example](.env.example) as a reference, or edit your existing file:

```dotenv
GITHUB_TOKEN=PASTE_YOUR_PRIMARY_TOKEN_HERE
TARGET_REPO=your-username/your-repository
HELPER_TOKEN=
```

Replace the placeholders locally after creating your token below. Save the file as **`.env`**, not `.env.txt`.

### Two accounts, one target repository

| Account | Repository relationship | Token goes in |
| --- | --- | --- |
| Primary account | Owns the personal repository that receives the activity | `GITHUB_TOKEN` |
| Helper account | A different GitHub username used for the badges listed below | `HELPER_TOKEN` |

Set `TARGET_REPO` to **your primary account's repository**, in `username/repository` format. Both tokens go in the same local `.env`; one copy of the CLI uses the appropriate account for each action. The helper needs no separate repository, fork, or CLI installation.

If you need a target repository, sign in as your primary account, open [Create a repository](https://github.com/new), choose that account as the owner, enter a name, and select **Add a README file**. Put the resulting `owner/name` in `TARGET_REPO`. You can use this repository for all five workflows.

### How to create the primary token

An existing, unexpired classic token with **repo** selected can be reused.

1. Sign in to your **primary GitHub account**, which owns the target repository.
2. Open **[Personal access tokens](https://github.com/settings/tokens)**.
3. Click **Generate new token → Generate new token (classic)**.
4. Enter a name, choose an expiration date, and select the **repo** checkbox.
5. Click **Generate token** and copy the value while GitHub displays it.
6. Paste it after `GITHUB_TOKEN=` in `.env`, then save.

The menu path is **Profile picture → Settings → Developer settings → Personal access tokens → Tokens (classic)**. Token creation happens in personal account settings. A classic `repo` token can access repositories its account already has permission to use; it does not ask you to select one repository. For a primary token limited to your target, follow the [fine-grained token steps](ADVANCED.md#use-a-token-limited-to-one-repository).

### How to create the helper token

Create a helper token only for **Pair Extraordinaire, YOLO, or Galaxy Brain**. It must belong to a different GitHub account.

1. Sign in as the **helper** and check its username under the profile picture.
2. Open its **[personal token settings](https://github.com/settings/tokens)** and choose **Generate new token (classic)**.
3. Enter a name and expiration date, select **repo**, and generate the token. An existing working classic `repo` token can be reused.
4. Paste the helper's token after `HELPER_TOKEN=` in the same `.env`:

```dotenv
GITHUB_TOKEN=TOKEN_FROM_PRIMARY_ACCOUNT
TARGET_REPO=your-username/your-repository
HELPER_TOKEN=TOKEN_FROM_SECOND_ACCOUNT
```

Replace these placeholders locally. Keep the primary token in `GITHUB_TOKEN` and the primary repository in `TARGET_REPO`. For Pull Shark and Quickdraw, leave `HELPER_TOKEN=` empty. If a required helper token is missing, the interactive CLI asks for it with hidden input.

### Which token does each badge need?

The primary classic `repo` token works for all five workflows. The helper classic `repo` token works for all three helper workflows, with the repository access shown below.

| Badge | Helper token | Must the helper accept a repository invitation? |
| --- | --- | --- |
| [Pull Shark](#pull-shark) | Not needed | No |
| [Quickdraw](#quickdraw) | Not needed | No |
| [Pair Extraordinaire](#pair-extraordinaire) | Required | No |
| [YOLO](#yolo) | Required | Yes |
| [Galaxy Brain](#galaxy-brain) | Required | Yes |

If the helper is only used for **Pair Extraordinaire** with default co-author settings, a classic token with no scopes selected is sufficient. A custom co-author email needs **user:email** access for verification; see [co-author email options](ADVANCED.md#co-author-email-options).

### Invite the helper for YOLO and Galaxy Brain

Complete this once for the same target repository; YOLO and Galaxy Brain can reuse the invitation and helper token.

1. Sign in as the **repository owner** and open the target repository.
2. Open **Settings → Collaborators**, under **Access**, then click **Add people**.
3. Search for the helper's username, select that account, and send the invitation.
4. Sign in as the **helper**, open the invitation from GitHub's email or notifications, and accept it.
5. As the owner, check **Settings → Collaborators** again. The helper must have access, with no pending invitation.

The accepted invitation grants repository access; the helper's token lets the app use it. Accepting an invitation does not require replacing an already suitable token. Use a **classic `repo` helper token** for these workflows because fine-grained tokens have limitations accessing another personal account's repository. See [GitHub's invitation guide](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository) if needed.

> [!IMPORTANT]
> **Never share or commit `.env`.** The app reads it automatically, so tokens do not need to appear in commands.

---

## 2. Check the repository and connection

For Pull Shark, Pair Extraordinaire, and YOLO, the target must have at least one commit. Add a README if it is empty. Under **Settings → General → Pull Requests**, enable **Allow merge commits**. Branch rules and required checks still apply when merging.

Open a terminal **inside this project folder** and run:

```powershell
python main.py doctor
```

You should see `Connected as your-username to your-username/your-repository`, with your actual account and target. Resolve any error using [Common fixes](#common-fixes) before running a workflow. `doctor` checks access without creating GitHub activity; each badge below also lists any specific setup it needs.

If your computer uses `python3`, replace `python` with `python3` throughout this guide. On Windows, an existing project virtual environment can be used as `.venv\Scripts\python`. No package installation is needed to run the source.

---

## 3. Run your first PR test

The level tables show **total qualifying activity**, rather than an additional count for each upgrade. These are [community-reported thresholds](https://github.com/Schweinepriester/github-profile-achievements#tiers), matching the app's targets. GitHub decides whether and when to award a badge.

All `run` commands below perform GitHub actions with `--execute`. Leave that option off to preview the plan and sample messages first.

### Pull Shark

<p>
  <img src="docs/assets/badges/pull-shark.png" alt="GitHub Pull Shark achievement badge" width="120" height="120">
</p>

**Goal:** get your pull requests (PRs) merged. **Helper:** not needed.

| Level | Total merged PRs | CLI target |
| --- | ---: | --- |
| Base (default) | 2 | `--tier base` |
| Bronze (x2) | 16 | `--tier bronze` |
| Silver (x3) | 128 | `--tier silver` |
| Gold (x4) | 1,024 | `--tier gold` |

After completing Steps 1 and 2, choose either option below. Both use the tokens and repository saved in `.env`.

#### Option 1: Run a command

To reach the base workflow target:

```powershell
python main.py run pull-shark --tier base --execute
```

The app creates a temporary branch, makes a small activity-file change, opens and merges a PR, verifies the merge, and removes the branch. It chooses PR and commit messages automatically. API writes are paced, so allow the run to finish.

To create **exactly one new PR** instead of working toward a total:

```powershell
python main.py run pull-shark --count 1 --execute
```

#### Option 2: Use the interactive CLI

Start the menu from the project folder:

```powershell
python main.py
```

Use **Up/Down** to highlight an option and **Enter** to select it. You can also press its number. **Esc** goes back.

1. Check that the dashboard shows your repository in **username/repository** format.
2. Select **Unlock an achievement**.
3. Select **Pull Shark**, then **Base**. For one new PR, choose **Custom count** and enter **1**.
4. Read the plan and messages. Select **Run this workflow** to execute, or **Keep as preview** to inspect the plan.
5. Wait for the progress display to finish, then press **Enter** to return to the dashboard.

Other badges use the same menu: **Unlock an achievement → badge → level → Run this workflow**. Complete their prerequisites below first.

### How levels and counts work

`--tier` uses successful operations saved by this app for the **current account, repository, and selected workflow**. It runs only what remains for that target. `--count N` always requests N new operations; use either `--tier` or `--count`, not both.

For example, with 16 saved Pull Shark successes, this command schedules **112 more PRs** to reach Silver at 128:

```powershell
python main.py run pull-shark --tier silver --execute
```

A Base command schedules zero new operations if its target is already met. Activity completed elsewhere or under another workflow is not subtracted from the app's target. Check your GitHub profile before starting a higher tier if you already have qualifying activity.

### Predefined PR and commit messages

Pull Shark, Pair Extraordinaire, and YOLO automatically select messages from these included files. You do not need to type titles, descriptions, or commit messages:

| File | Used for |
| --- | --- |
| [prtitle.txt](github_achievement/message_files/prtitle.txt) | PR titles |
| [prdescription.txt](github_achievement/message_files/prdescription.txt) | PR descriptions |
| [messages.txt](github_achievement/message_files/messages.txt) | Activity commit messages |
| [mergetitle.txt](github_achievement/message_files/mergetitle.txt) | Merge commit titles |
| [mergedescription.txt](github_achievement/message_files/mergedescription.txt) | Merge commit descriptions |

Each file has **12 entries** that cycle in order. Saved attempts keep the position for each account, repository, and workflow, including failed or interrupted attempts. Every message includes a unique operation ID; Pair Extraordinaire also adds the verified helper's `Co-authored-by` credit automatically.

To change the wording, edit the relevant UTF-8 `.txt` file before your next run, using one entry per line. Blank lines and lines starting with `#` are ignored. The app validates messages before making changes. See [advanced message options](ADVANCED.md#message-options) for placeholders, multiline text, custom folders, and overrides.

---

## 4. Run another badge

Choose a badge in the interactive menu or use its command below. Each workflow uses the same `TARGET_REPO` and primary token from Step 1.

### Pair Extraordinaire

<p>
  <img src="docs/assets/badges/pair-extraordinaire.png" alt="GitHub Pair Extraordinaire achievement badge" width="120" height="120">
</p>

**Goal:** merge PRs containing a co-authored commit. **Helper:** required; no repository invitation needed.

| Level | Total co-authored merged PRs | CLI target |
| --- | ---: | --- |
| Base (default) | 1 | `--tier base` |
| Bronze (x2) | 10 | `--tier bronze` |
| Silver (x3) | 24 | `--tier silver` |
| Gold (x4) | 48 | `--tier gold` |

1. Complete the PR repository setup in Step 2 and save the [helper's token](#how-to-create-the-helper-token) in `HELPER_TOKEN`.
2. Leave `COAUTHOR_NAME` and `COAUTHOR_EMAIL` unset for automatic identity and GitHub noreply email selection. For overrides, use [co-author email options](ADVANCED.md#co-author-email-options).
3. Check the setup:

   ```powershell
   python main.py doctor --workflow pair-extraordinaire
   ```

4. When the check passes, run:

   ```powershell
   python main.py run pair-extraordinaire --tier base --execute
   ```

The primary account creates and merges the PR. The helper token supplies its identity for co-author credit. The app verifies that GitHub recognizes both authors before merging and removes the temporary branch after success.

[↑ Badge guides](#find-your-next-step)

---

### Quickdraw

<p>
  <img src="docs/assets/badges/quickdraw.png" alt="GitHub Quickdraw achievement badge" width="120" height="120">
</p>

**Goal:** close an issue within five minutes of opening it. **Helper:** not needed.

| Level | Unlock requirement | CLI target |
| --- | --- | --- |
| Base (only level) | 1 issue closed within 5 minutes | `--tier base` |

Quickdraw has no Bronze, Silver, or Gold levels. GitHub also recognizes qualifying PR closures; this app uses an issue.

1. In the target repository, open **Settings → General → Features** and enable **Issues**.
2. Run:

   ```powershell
   python main.py run quickdraw --tier base --execute
   ```

The app opens an issue, closes it, and verifies that it closed within the five-minute window.

[↑ Badge guides](#find-your-next-step)

---

### YOLO

<p>
  <img src="docs/assets/badges/yolo.png" alt="GitHub YOLO achievement badge" width="120" height="120">
</p>

**Goal:** merge a PR without a code review. **Helper:** required, with an accepted repository invitation.

| Level | Unlock requirement | CLI target |
| --- | --- | --- |
| Base (only level) | 1 PR merged without a review | `--tier base` |

YOLO has no Bronze, Silver, or Gold levels. In this app, the primary account opens the PR and the helper merges it without a review.

1. Complete the PR repository setup in Step 2.
2. Save the helper's classic `repo` token and complete [the collaborator invitation](#invite-the-helper-for-yolo-and-galaxy-brain).
3. Check the setup:

   ```powershell
   python main.py doctor --workflow yolo
   ```

4. When the check passes, run:

   ```powershell
   python main.py run yolo --tier base --execute
   ```

The app verifies that the helper performed the merge and that the PR has no reviews. Required review rules can prevent this workflow from merging.

[↑ Badge guides](#find-your-next-step)

---

### Galaxy Brain

<p>
  <img src="docs/assets/badges/galaxy-brain.png" alt="GitHub Galaxy Brain achievement badge" width="120" height="120">
</p>

**Goal:** have your answers accepted in GitHub Discussions. **Helper:** required, with an accepted repository invitation.

| Level | Total accepted answers | CLI target |
| --- | ---: | --- |
| Base (default) | 2 | `--tier base` |
| Bronze (x2) | 8 | `--tier bronze` |
| Silver (x3) | 16 | `--tier silver` |
| Gold (x4) | 32 | `--tier gold` |

The helper posts questions in the target repository, the primary account answers, and the helper marks those replies as accepted. Each completed operation records **one accepted answer** for the primary account.

#### A. Prepare both accounts

Follow [Step 1](#1-put-your-tokens-in-env) to save both accounts' classic `repo` tokens and [accept the collaborator invitation](#invite-the-helper-for-yolo-and-galaxy-brain). Keep `TARGET_REPO` set to the primary account's repository. Existing access from YOLO can be reused.

#### B. Enable Discussions and a Q&A category

1. As the owner, open the repository's **Settings → General → Features**.
2. Enable **Discussions**, using **Set up discussions** if shown. Complete the welcome discussion if prompted, then open the **Discussions** tab.
3. Check that a category such as **Q&A** uses the **Question and Answer** format, which supports accepting replies as answers.
4. If needed, use the pencil/edit control beside **Categories → New category**. Enter a name, emoji, and description, select **Question and Answer**, and create it. Edit an existing category if it has the wrong format.

The app finds a category that supports accepted answers automatically. Leave `DISCUSSION_CATEGORY_ID` unset unless you want a specific category. See [GitHub's category guide](https://docs.github.com/en/discussions/managing-discussions-for-your-community/managing-categories-for-discussions) for help.

#### C. Check setup, then run

Check both accounts, the helper's access, and the Q&A category:

```powershell
python main.py doctor --workflow galaxy-brain
```

When the check passes, run:

```powershell
python main.py run galaxy-brain --tier base --execute
```

For another level, replace `--tier base` with its CLI target from the table. Open the resulting discussion links to confirm that the primary account's replies are accepted. If access fails, use the [token access checklist](#fix-resource-not-accessible-by-personal-access-token).

[↑ Badge guides](#find-your-next-step)

---

## 5. Check progress and badges

```powershell
python main.py status
python main.py verify
```

`status` shows this app's completed operations. `verify` checks whether badges are visible on your public profile; it does not read their tier. A verified PR, issue closure, or accepted answer confirms the workflow completed, while GitHub controls the badge award. Hidden or delayed badges may show **not visible yet**.

To allow two minutes for a badge to appear, without creating more activity:

```powershell
python main.py verify --achievement pull-shark --wait 120
```

Keep **`.achievement-state`** between runs. It holds progress for each account, repository, and workflow. After an interrupted or failed run, inspect `python main.py status --history` and its linked resources before retrying; GitHub may have completed a write even if its response was lost.

In the menu, choose **Your progress** for saved operations or **Check GitHub badges** for your public profile.

---

## 6. Clean up leftover branches

Successfully merged workflow branches are removed automatically. If a cleanup failed or a run was interrupted, check for leftovers:

```powershell
python main.py cleanup
```

This is a preview. To remove branches marked **READY**:

```powershell
python main.py cleanup --execute
```

Cleanup removes recorded workflow branches after confirming that their PR is merged and their head commit still matches the record. **KEPT** means inspect the branch manually. PR records, issues, discussions, activity files, repository history, and local progress remain.

In the menu, choose **Clean up merged branches**, read the preview, then select **Remove verified merged branches**. Run one copy of the app at a time and avoid editing its temporary branches while it runs.

---

## Rate limits: let the app wait

The app spaces API writes **eight seconds apart** and pauses between operations. It honors GitHub's rate-limit headers for REST and GraphQL. A secondary limit without a retry time starts with a wait of at least 60 seconds; repeated limits get longer waits.

If GitHub requires a wait longer than five minutes or retries are exhausted, the run stops with a retry hint. Completed progress stays saved. Wait before restarting; if branch cleanup hit the limit, run `python main.py cleanup --execute` after the wait. See [API pacing and retries](ADVANCED.md#api-pacing-and-retries) for details.

---

## Common fixes

| Message or problem | What to do |
| --- | --- |
| `401` / invalid token | Check which account created the token and replace it if expired or incorrect. Save it in the appropriate `.env` line. |
| `403` / `404` | Check `TARGET_REPO`, token permissions, and any required helper invitation. `doctor` cannot test every write permission. |
| `You don't have access to repository options` | Open [personal token settings](https://github.com/settings/tokens) to create a token. Only the owner needs repository settings for invitations and features. |
| `Resource not accessible by personal access token` | Follow the [token access checklist below](#fix-resource-not-accessible-by-personal-access-token). |
| `0 operation(s) to run` | Saved progress meets the chosen tier. Use `--count 1` if you want one new operation. |
| PR cannot merge | Check conflicts, required reviews/checks, and **Allow merge commits**. |
| Co-author not recognized | Check the helper account. See [co-author email options](ADVANCED.md#co-author-email-options). |
| `.env` changes seem ignored | An old shell variable can override the file. See [environment precedence](ADVANCED.md#environment-precedence). |
| Badge is not visible | Wait and run `verify` again; do not assume more PRs are needed. |

### Fix `Resource not accessible by personal access token`

This message means a token lacks access to the requested resource or action.

1. Confirm that `GITHUB_TOKEN` belongs to the owner of `TARGET_REPO` and `HELPER_TOKEN` belongs to a different account.
2. For **YOLO or Galaxy Brain**, check the helper's classic `repo` token and accepted invitation to this exact target. A pending invitation or access to a fork is insufficient. Pair Extraordinaire needs no invitation.
3. For **Galaxy Brain**, enable Discussions and a **Question and Answer** category. For a fine-grained primary token, check the [workflow permissions](ADVANCED.md#use-a-token-limited-to-one-repository).
4. Save `.env`, restart the CLI, and run the badge's `doctor --workflow` command. If old credentials are still used, check [environment precedence](ADVANCED.md#environment-precedence). Inspect `status --history` before retrying an attempt that already created resources.

---

## Get the app

Install [Python 3.11+](https://www.python.org/downloads/). If using [Git](https://git-scm.com/downloads), download the source with:

```powershell
git clone https://github.com/Antech-greyhat/GetIt-Unlock.git
cd GetIt-Unlock
```

Alternatively, open [the repository](https://github.com/Antech-greyhat/GetIt-Unlock), choose **Code → Download ZIP**, and extract it. Open a terminal in the extracted folder, then follow [Step 1](#1-put-your-tokens-in-env).

The downloaded folder contains this app. `TARGET_REPO` identifies the personal GitHub repository that receives the workflow activity. Git is needed for cloning only; the workflows use GitHub's API.

---

[↑ Back to top](#github-achievement-python) · [Advanced options](ADVANCED.md) · [License](LICENSE) · [Artwork sources](docs/assets/README.md)
