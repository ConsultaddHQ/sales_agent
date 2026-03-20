# Ticket and Commit Creation Standards

## Purpose
This document outlines the best practices for creating tickets and commits to ensure clarity, consistency, and ease of collaboration. These standards are derived from the current tickets and practices used in the project.

---

## Ticket Creation Standards

### 1. **Title**
- Use a clear and concise title that summarizes the purpose of the ticket.
- Avoid vague terms like "fix" or "update"; instead, describe the outcome (e.g., "Add preview in the UI").

### 2. **Description**
- Use a structured markdown format with the following sections:

#### **Description Structure Template**

```markdown
## Summary

[One-line clear description of what the ticket accomplishes]

## Problem Statement

[Describe the user pain point, business requirement, or current blocker. What is broken or missing? Why does it matter?]

## Expected Outcome

- [Specific, measurable deliverable 1]
- [Specific, measurable deliverable 2]
- [Add any acceptance criteria]

## What Was Done

[For completed tickets: Describe implementation details, approach taken, and key changes made. For new tickets: Leave blank or add "(To be filled on completion)"]

## Updates Section

**Commit Details**: [Relevant commit hashes and descriptions, or "pending"]  
**Proof**: [Screenshots, demo recordings, logs, or "pending"]  
**Attachments**: [Links, documents, or "pending"]

## Notes

- [Implementation guidance, edge cases, or testing requirements]
- [Related tickets or dependencies]
- [Any warnings or special considerations]
```

#### **Example Tickets**

**Feature Ticket (HPF-175):**
```markdown
## Summary
Research cross-site scraping strategy across different site types using no-cost (keyword scraping → Playwright → LLM) and paid methods.

## Problem Statement
Current crawler approach is unclear for varied website structures (static CMS, SPAs, ecommerce platforms, anti-bot protected). No documented strategy for handling different site types, and no evaluation of cost vs. free options.

## Expected Outcome
- 3-phase strategy: pure scraping (HTML/CSS) → Playwright (JS-heavy) → LLM extraction (quick POC)
- Site classification matrix: static, SPA, ecommerce, anti-bot, gated content
- Comparison: no-cost options (BeautifulSoup, Scrapy, Playwright) vs. paid (Apify, ScrapingBee, BrightData)
- Risk assessment and robots.txt compliance guidelines

## Updates Section
**Commit Details**: pending  
**Proof**: Research document + comparison matrix  
**Attachments**: pending

## Notes
- No target website selected yet; will select after strategy research
- Include throughput, error rate, and legal compliance metrics
```

**UI Bug Ticket (HPF-178):**
```markdown
## Summary
Remove unnecessary input field from homepage UI beside Magic Crawl button to reduce clutter.

## Problem Statement
The homepage displays an input box next to the Magic Crawl button that causes confusion about its purpose and competes with the primary CTA.

## Expected Outcome
- Input field removed from homepage layout
- Magic Crawl button is the only CTA in that row
- Keyboard accessibility and focus management maintained
- Responsive design works on mobile/tablet/desktop

## What Was Done
(To be filled on completion)

## Updates Section
**Commit Details**: pending  
**Proof**: before/after screenshots  
**Attachments**: pending

## Notes
- Low-risk UI-only change
- Test on all viewport sizes
- Verify keyboard navigation
```

**Voice/UX Ticket (HPF-179):**
```markdown
## Summary
Stop agent speech synthesis when product carousel is dismissed, preventing audio spillover.

## Problem Statement
Users close the carousel expecting to mute the agent, but speech continues playing. This creates poor UX and feels like the agent is not responding to user actions.

## Expected Outcome
- Carousel close event (click, ESC, or programmatic) triggers `speechStop()`
- All in-flight TTS API requests are cancelled
- Agent speaking state clears in UI
- Regression test verifies silence on close

## Updates Section
**Commit Details**: pending  
**Proof**: video demo of carousel close + silence verification  
**Attachments**: pending

## Notes
- High priority: direct user experience impact
- Related: HPF-176 (End/Pause buttons)
- Test: rapid open/close, mid-sentence closures, network delays
```

---

### Key Formatting Rules

1. **Summary**: Single line, action-oriented (what gets built/fixed)
2. **Problem Statement**: User perspective (why it matters), not implementation detail
3. **Expected Outcome**: Bullet list of concrete deliverables, not vague promises
4. **What Was Done**: For new tickets, mark as "(To be filled on completion)" to show structure
5. **Updates Section**: Always include with pending placeholders so team knows what to fill on completion
6. **Notes**: Development hints, related tickets, testing edge cases—context for implementer

### Dos and Don'ts

✅ **DO:**
- Be specific about deliverables ("Stop TTS on carousel close" not "fix voice issue")
- Include user impact ("poor UX when users..." not just "needs fixing")
- List dependencies and related tickets
- Provide clear testing guidance

❌ **DON'T:**
- Write vague titles ("Update stuff", "Fix bug", "Improvement needed")
- Skip the Problem Statement (always explain why, not just what)
- Leave Expected Outcome as a single sentence
- Assume readers know the context without explanation

### 3. **Labels**
- Apply appropriate labels based on ticket type:
  - **Feature**: New functionality or capability
  - **Bug**: Defect or issue in existing code
  - **Improvement**: Enhancement to existing feature
  - **Demo**: Demo-related work
  - **Testing**: QA and test coverage
- Set the correct **priority**:
  - **Urgent (1)**: Blocking production or critical path
  - **High (2)**: Important feature or significant issue
  - **Medium (3)**: Standard feature or improvement
  - **Low (4)**: Nice-to-have or cosmetic fix

### 4. **Required Dates**
- **Start Date**: When work begins (fill at ticket creation)
- **End Date / Target Completion Date**: Expected completion (fill at ticket creation)
- Update these if scope or timeline changes during work

### 5. **Ticket Scope & Sizing**
- Each ticket should represent **roughly one week of work**
- Avoid tickets that are:
  - ❌ Too small (micro-tasks creating noise)
  - ❌ Too large (multi-week efforts with unclear scope)
- If work exceeds one week, split into smaller deliverables with clear dependencies

### 6. **Update Cadence**
- Ticket owner must review and update status **at least every 2 days**
- Update if: status changes, progress made, blockers encountered, or decisions recorded
- Use **Comments section** for meaningful progress, not step-by-step logs
- Move ticket to Backlog when switching to other work

### 7. **Acceptance Criteria**
- Define clear "Definition of Done" in the description
- Include specific, verifiable requirements
- Example: "✓ API endpoint responds within 200ms" (not "API works")

### 8. **Relations & Dependencies**
- Link related tickets, PRs, or dependencies using "blocks/blocked by" relations
- Gives visibility into cross-ticket impact
- Update relations if scope changes

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