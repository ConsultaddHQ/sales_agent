# Ticket and Commit Creation Standards

## Purpose
This document outlines the best practices for creating tickets and commits to ensure clarity, consistency, and ease of collaboration. These standards are derived from the current tickets and practices used in the project.

---

## Ticket Creation Standards

### 1. **Title**
- Use a clear and concise title that summarizes the purpose of the ticket.
- Avoid vague terms like "fix" or "update"; instead, describe the outcome (e.g., "Add preview in the UI").

### 2. **Description**
- Provide a detailed description of the ticket, including:
  - **Problem Statement:** Clearly state the issue or requirement.
  - **Expected Outcome:** Describe the desired result or functionality.
  - **Steps to Reproduce (if applicable):** Include steps to replicate the issue.
  - **Updates Section:**
    - **Commit Details:** List relevant commit hashes and their descriptions.
    - **Proof:** Placeholder for proof (e.g., screenshots, logs, demo recordings).
    - **Attachments:** Placeholder for relevant attachments (e.g., documents, links).
  - **Notes:** Add any additional context or information.

### 3. **Labels**
- Apply appropriate labels (e.g., Feature, Bug, Improvement, Demo).
- Set the correct priority (e.g., High, Medium, Low).

### 4. **Relations**
- Link related tickets, PRs, or dependencies using "blocks/blocked by" relations.

### 5. **Assignee and Project**
- Assign the ticket to the responsible team member.
- Ensure the ticket is associated with the correct project.

---

## Commit Creation Standards

### 1. **Commit Message Format**
- Use the following format for commit messages:
  ```
  <type>(<scope>): <description>
  ```
  - **Type:** Use one of the following:
    - `feat`: A new feature.
    - `fix`: A bug fix.
    - `docs`: Documentation changes.
    - `style`: Code style changes (formatting, no logic changes).
    - `refactor`: Code refactoring (no new features or fixes).
    - `test`: Adding or updating tests.
    - `chore`: Maintenance tasks (e.g., updating dependencies).
  - **Scope:** The area of the codebase affected (e.g., `UI`, `backend`, `onboarding`).
  - **Description:** A brief summary of the change.

### 2. **Commit Body**
- Provide a detailed explanation of the change, including:
  - **What:** What was changed.
  - **Why:** The reason for the change.
  - **How:** How the change was implemented.

### 3. **Commit Examples**
- Example 1:
  ```
  feat(UI): Add preview in the UI

  - Implemented a preview feature for suggested products.
  - Updated the widget to display previews instead of dots.
  ```
- Example 2:
  ```
  fix(backend): Resolve timeout issue in API

  - Fixed the `getClusters` API timeout issue.
  - Added error handling for unreachable clusters.
  ```

---

## Best Practices

1. **Keep Tickets and Commits Small**
   - A ticket should represent roughly one week of work.
   - A commit should represent a single logical change.

2. **Use Clear and Descriptive Language**
   - Avoid jargon or ambiguous terms.

3. **Document Progress**
   - Use the ticket's comment section to record key updates, decisions, and blockers.

4. **Link Relevant Resources**
   - Include links to PRs, documents, designs, and demo recordings in the ticket description or comments.

5. **Review and Update Regularly**
   - Ensure tickets are reviewed and updated at least every two days.

---

## References
- [Linear Rules](../Linear%20rules)
- Current Tickets: HPF-158, HPF-159, HPF-166, HPF-168

---

By following these standards, we can ensure that tickets and commits are well-structured, easy to understand, and facilitate smooth collaboration across the team.