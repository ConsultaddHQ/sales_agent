# Engineering Standards & Best Practices

**Version:** 2.0  
**Last Updated:** March 20, 2026  
**Team:** ConsultAdd Digital Sales Agent  
**Audience:** Junior to Senior Engineers

---

## Table of Contents

1. [Commit Message Standards](#1-commit-message-standards)
2. [Linear Ticket Standards](#2-linear-ticket-standards)
3. [AI-Friendly Documentation](#3-ai-friendly-documentation)
4. [Code Documentation Standards](#4-code-documentation-standards)
5. [Pull Request Standards](#5-pull-request-standards)
6. [Testing Standards](#6-testing-standards)
7. [Daily Development Workflow](#7-daily-development-workflow)
8. [AI Tools Parsing Guidelines](#8-ai-tools-parsing-guidelines)

---

## 1. Commit Message Standards

### Format
Use **Conventional Commits** format for all commit messages:

```
<type>(<scope>): <subject>

[optional body]

[optional footer]
```

### 1.1 Types
| Type | When to Use | Example |
|------|-------------|---------|
| `feat` | New feature or functionality | `feat(widget): add voice interrupt capability` |
| `fix` | Bug fix | `fix(carousel): resolve thumbnail scroll sync issue` |
| `docs` | Documentation only | `docs(readme): add installation instructions` |
| `style` | Code formatting (no logic change) | `style(orb): format CSS with prettier` |
| `refactor` | Code restructuring (no new features) | `refactor(agent): extract tool handlers to separate file` |
| `perf` | Performance improvement | `perf(search): add index to products table` |
| `test` | Adding or updating tests | `test(widget): add shadow DOM isolation tests` |
| `build` | Build system or dependencies | `build: upgrade vite to 5.0` |
| `ci` | CI/CD configuration | `ci: add playwright tests to GitHub Actions` |
| `chore` | Maintenance, tooling | `chore: update .gitignore` |
| `revert` | Revert a previous commit | `revert: feat(widget): add voice interrupt` |

### 1.2 Scopes (Project-Specific)
Use these scopes to identify affected area:

- `widget` — Frontend voice widget
- `onboarding` — Shopify onboarding service
- `search` — Search service API
- `dashboard` — React dashboard UI
- `agent` — ElevenLabs agent configuration
- `carousel` — Product carousel component
- `orb` — Voice orb UI component
- `api` — General API changes
- `db` — Database schema/migrations
- `config` — Configuration files

### 1.3 Subject Rules
- Use **imperative mood** ("add" not "added" or "adds")
- No capitalization on first letter
- No period at the end
- Maximum 72 characters
- Be specific and descriptive

### 1.4 Body (Optional)
Use the body to explain:
- **What** changed
- **Why** it changed
- **How** it was implemented
- Any **side effects** or **breaking changes**

Wrap lines at 72 characters.

### 1.5 Footer (Optional)
Use footer for:
- **Breaking changes:** `BREAKING CHANGE: <description>`
- **Issue references:** `Closes HPF-123`, `Relates to HPF-124`, `Fixes #45`
- **Reviewers:** `Reviewed-by: John Doe <john@example.com>`

### 1.6 Examples

#### ✅ Good Examples

**Simple Feature:**
```
feat(carousel): add thumbnail navigation

Users can now click thumbnails to jump to specific products.
Implements smooth scroll behavior and active state highlighting.

Closes HPF-172
```

**Bug Fix:**
```
fix(orb): prevent disconnect during "Generating Audio" state

Added safety lock to prevent disconnect clicks during processing states.
This fixes user frustration when accidentally clicking during audio generation.

Fixes HPF-159
```

**Breaking Change:**
```
feat(widget)!: migrate to Shadow DOM architecture

BREAKING CHANGE: Widget now uses Shadow DOM for style isolation.
Existing host page CSS selectors targeting widget internals will no longer work.

Migration guide: Update widget initialization to use new custom element.

Closes HPF-174
```

**Refactor:**
```
refactor(agent): extract tool handlers into separate modules

Moves update_products, update_carousel_main_view, and product_desc_of_main_view
handlers into individual files for better maintainability.

No functional changes.
```

#### ❌ Bad Examples

**Too vague:**
```
fix: bug fix
```

**Wrong type:**
```
feat: fixed the carousel bug  # Should be "fix"
```

**Poor subject:**
```
feat(widget): Added new feature that allows users to...  # Too long, not imperative
```

**No scope:**
```
feat: add carousel  # Missing scope
```

---

## 2. Linear Ticket Standards

### 2.1 Required Fields

Every ticket MUST have these 9 fields filled:

1. **Title** — Clear, outcome-focused
2. **Description** — Detailed context and acceptance criteria
3. **Team** — Assigned team
4. **Priority** — P0 to P4
5. **Status** — Current workflow state
6. **Assignee** — Who owns the work
7. **Start Date** — When work begins
8. **End Date** — Target completion date
9. **Labels** — Feature, Bug, Improvement, etc.

### 2.2 Title Format

Format: `[Verb] [Outcome] [Context]`

**Examples:**
- ✅ `Add voice interrupt capability to orb widget`
- ✅ `Fix carousel thumbnail scroll sync on manual navigation`
- ✅ `Migrate widget to Shadow DOM architecture`
- ❌ `Widget improvements` (too vague)
- ❌ `Fix bug` (what bug?)

### 2.3 Description Template

Use this template for all tickets:

```markdown
## Problem Statement
[Describe the issue, requirement, or opportunity. Why does this need to be done?]

## Expected Outcome
[What should be true when this ticket is complete? What can users/developers do?]

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Technical Approach (Optional)
[High-level implementation plan, if known]

## Steps to Reproduce (Bug Tickets Only)
1. Step one
2. Step two
3. Observe error

## Updates
<!-- AI_CONTEXT_START: track_progress -->
**Commits:**
- [hash] Description

**Proof:**
- Screenshot/Recording: [link]

**Attachments:**
- Design doc: [link]
- Related PR: [link]
<!-- AI_CONTEXT_END -->

## Notes
[Additional context, dependencies, blockers, questions]
```

### 2.4 Labels

| Label | When to Use |
|-------|-------------|
| `Feature` | New functionality |
| `Bug` | Something broken |
| `Improvement` | Enhancement to existing feature |
| `Tech Debt` | Refactoring, cleanup |
| `Demo` | Demo preparation work |
| `Documentation` | Docs-only changes |
| `Research` | Investigation or spike |

### 2.5 Priority Levels & SLAs

| Priority | Meaning | Response Time | Example |
|----------|---------|---------------|---------|
| **P0** | Critical, blocking | Same day | Production down, data loss |
| **P1** | High, urgent | Within 1 day | Demo broken, core feature unusable |
| **P2** | Normal | Within 1 week | Standard features, minor bugs |
| **P3** | Low | Within 2 weeks | Nice-to-haves, polish |
| **P4** | Backlog | When able | Future ideas, non-urgent improvements |

### 2.6 Status Workflow

```
Backlog → Todo → In Progress → In Review → Done → Canceled
```

- **Backlog** — Not yet prioritized
- **Todo** — Prioritized, waiting to start
- **In Progress** — Actively being worked on
- **In Review** — PR submitted, awaiting review
- **Done** — Merged and deployed
- **Canceled** — Not doing this work

### 2.7 Update Cadence

- **Every ticket in "In Progress"** must be updated **at least every 2 days**
- Updates should include:
  - Progress made (commits, milestones)
  - Blockers encountered
  - Next steps
  - Timeline adjustments

### 2.8 Examples

#### ✅ Good Ticket Example

**Title:** Add voice interrupt capability to orb widget

**Description:**
```markdown
## Problem Statement
Users cannot interrupt the AI while it's speaking, leading to frustration when they want to ask a follow-up question or correct their request.

## Expected Outcome
Users can tap the orb while the AI is speaking to immediately stop audio playback and start a new voice input.

## Acceptance Criteria
- [ ] Tapping orb during "Speaking" state stops audio
- [ ] State immediately transitions to "Listening"
- [ ] Previous conversation context is preserved
- [ ] Works on both mobile and desktop

## Technical Approach
- Add click handler to orb that checks if status === 'SPEAKING'
- Call conversation.endSession() to stop audio
- Immediately call conversation.startSession() to begin listening

## Updates
**Commits:**
- [13b487d] feat(orb): add interrupt handler for speaking state
- [506022b] test(orb): verify interrupt behavior

**Proof:**
- Demo recording: [link to Loom]
```

---

## 3. AI-Friendly Documentation

Make your code and tickets easy for AI tools to understand by using semantic markers and structured formats.

### 3.1 Semantic Markers in Tickets

Wrap key information in AI-parseable markers:

```markdown
<!-- AI_CONTEXT_START: category_name -->
Content here
<!-- AI_CONTEXT_END -->
```

**Categories:**
- `problem_statement` — What we're solving
- `technical_approach` — How we're solving it
- `track_progress` — Updates, commits, proof
- `dependencies` — Related tickets, blockers
- `breaking_changes` — API changes, migrations

**Example:**
```markdown
<!-- AI_CONTEXT_START: breaking_changes -->
**Migration Required:**
Widget initialization now uses custom elements instead of imperative API.
Old: `window.TeamPop.init({ ... })`
New: `<team-pop-agent></team-pop-agent>`
<!-- AI_CONTEXT_END -->
```

### 3.2 AI-Friendly Code Comments

Use structured comment format for complex logic:

```javascript
/**
 * AI_SUMMARY: Syncs product carousel with agent's narrative when user manually scrolls.
 * AI_DEPENDENCIES: conversation.sendContextualUpdate, sendUserMessage
 * AI_COMPLEXITY: Medium - handles debouncing and synthetic message injection
 */
const syncMainProduct = useCallback((product) => {
  // ... implementation
}, [conversation.status, sendContextualUpdate, sendUserMessage]);
```

### 3.3 Five Types of Info AI Needs

When documenting or creating tickets, include:

1. **Why** — Why does this exist? What problem does it solve?
2. **What** — What does this do at a high level?
3. **How** — How is it implemented? Key algorithm or approach?
4. **Dependencies** — What does this depend on? What depends on this?
5. **Edge Cases** — What are the gotchas? Known limitations?

### 3.4 AI Prompt Template (For Requesting Help)

Use this structure when asking AI for help:

```
I need [what you need: ticket/commit/documentation].

Context:
- Feature: [what you're building]
- Recent commits: [hash + description]
- Current state: [what works, what doesn't]
- Files involved: [list key files]

Goal: [specific outcome]

Constraints:
- [any technical constraints]
- [any time constraints]
```

---

## 4. Code Documentation Standards

### 4.1 When to Write Comments

**DO comment:**
- Complex algorithms or business logic
- Non-obvious decisions ("why" not "what")
- Workarounds or hacks (with explanation and ticket reference)
- Public APIs and function signatures (JSDoc)
- Edge cases and gotchas

**DON'T comment:**
- Obvious code (`// increment counter` above `counter++`)
- Code that should be self-documenting (use better names instead)
- Dead code (delete it instead)
- Version history (use Git instead)

### 4.2 Comment Examples

#### ✅ Good Comments

**Explaining "Why":**
```javascript
// We debounce for 600ms to ensure user has settled on a product
// before sending expensive API call to agent. Shorter delays cause
// rapid-fire updates that confuse the TTS narration.
if (syncDebounceRef.current) clearTimeout(syncDebounceRef.current);
syncDebounceRef.current = setTimeout(() => {
  sendContextualUpdate(/* ... */);
}, 600);
```

**Documenting Workaround:**
```javascript
// WORKAROUND (HPF-173): ElevenLabs SDK doesn't expose connection state
// directly, so we track it manually via status callbacks. Remove this
// when SDK provides onConnectionChange event.
const [connectionState, setConnectionState] = useState('disconnected');
```

**Edge Case Warning:**
```javascript
// CRITICAL: Do NOT call product_desc_of_main_view from React code.
// Frontend calls this automatically via useEffect when carousel scrolls.
// Manual calls will create duplicate narration and confuse the agent.
```

#### ❌ Bad Comments

**Stating the Obvious:**
```javascript
// Set active index to idx
setActiveIndex(idx); // Bad - comment adds nothing
```

**Should Use Better Names:**
```javascript
// Flag to check if scroll came from agent
const f = true; // Bad - use descriptive name instead

// Good alternative:
const isAgentTriggeredRef = useRef(false);
```

### 4.3 JSDoc for Functions

Use JSDoc for all exported functions and complex internal functions:

```javascript
/**
 * Synchronizes the main product carousel view with agent narration when user manually scrolls.
 * Sends product context to agent and triggers synthetic "Tell me about this one" message.
 * 
 * @param {Object} product - Product object with id, name, price, description
 * @param {string} product.id - Unique product identifier
 * @param {string} product.name - Product display name
 * @param {number} product.price - Price in rupees
 * 
 * @returns {void}
 * 
 * @example
 * syncMainProduct({
 *   id: 'prod_123',
 *   name: 'Blue T-Shirt',
 *   price: 599
 * });
 * 
 * @see {@link updateCarouselMainView} for agent-triggered carousel updates
 */
const syncMainProduct = useCallback((product) => {
  // Implementation...
}, [conversation.status]);
```

### 4.4 File Headers

Add headers to complex files:

```javascript
/**
 * AvatarWidget.jsx
 * 
 * Main voice widget component with three modes:
 * - NONE: Floating orb dock (home state)
 * - PRODUCTS: Full-screen product carousel
 * - CHAT: Full-screen chat history
 * 
 * Architecture:
 * - Shadow DOM isolation for style safety
 * - ElevenLabs conversational agent integration
 * - Client-side tools: update_products, update_carousel_main_view
 * 
 * Key Dependencies:
 * - @elevenlabs/react for voice conversation
 * - React portals for z-index isolation
 * 
 * Related Files:
 * - ShoppingCard.jsx (product card UI)
 * - WidgetZIndexFix.jsx (z-index isolation HOC)
 * 
 * @see HPF-174 for Shadow DOM architecture
 * @see HPF-173 for agent tool integration
 */
```

### 4.5 TODO and FIXME Format

```javascript
// TODO(gautam): Add error boundary around carousel
// Priority: P2 - Nice to have but not blocking
// Issue: Create ticket if not done by April 1

// FIXME(gautam): Carousel doesn't update when products array length changes
// Bug: HPF-XXX
// Impact: Medium - affects edge case when search returns different count
```

### 4.6 README Structure

Every major component/service should have a README:

```markdown
# Component/Service Name

Brief one-sentence description.

## Purpose
Why does this exist? What problem does it solve?

## Architecture
High-level structure, key files, data flow.

## Getting Started
```bash
npm install
npm run dev
```

## Configuration
Environment variables, settings, etc.

## Usage Examples
Code snippets showing typical usage.

## Testing
How to run tests, what's covered.

## Troubleshooting
Common issues and solutions.

## Related Documentation
Links to design docs, tickets, etc.
```

---

## 5. Pull Request Standards

### 5.1 PR Template

Use this template for all PRs:

```markdown
## Summary
[One-sentence description of what this PR does]

## Type of Change
- [ ] Feature
- [ ] Bug Fix
- [ ] Refactor
- [ ] Documentation
- [ ] Performance
- [ ] Breaking Change

## Related Issues
Closes HPF-XXX
Relates to HPF-YYY

## Changes Made
- Bullet list of key changes
- Focus on "what" not "how"

## Testing Done
- [ ] Manual testing on Chrome/Safari/Firefox
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Tested on mobile viewport

## Screenshots/Demo
[If UI change, include before/after screenshots or video]

## Breaking Changes
[If yes, describe migration path]

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex logic
- [ ] Documentation updated
- [ ] No console.logs or debugger statements
- [ ] Tests pass locally
```

### 5.2 Author Checklist (Before Submitting PR)

Before clicking "Create Pull Request":

1. ✅ **Self-review** — Read your own diff line-by-line
2. ✅ **Run tests** — `npm test` or `pytest` passes
3. ✅ **Check console** — No errors in browser console
4. ✅ **Update docs** — README, comments, JSDoc if needed
5. ✅ **Clean up** — Remove debug statements, commented code
6. ✅ **Squash WIP** — Rebase if you have "WIP" or "fix typo" commits
7. ✅ **Link ticket** — "Closes HPF-XXX" in PR description
8. ✅ **Test edge cases** — Empty states, errors, loading states

### 5.3 Reviewer Guidelines

When reviewing PRs:

1. **Check ticket first** — Does PR match acceptance criteria?
2. **Test locally** — Pull branch and test manually
3. **Review logic** — Does the approach make sense?
4. **Check style** — Follows project conventions?
5. **Security** — Any XSS, injection, or data leak risks?
6. **Performance** — Any unnecessary re-renders or heavy operations?
7. **Be kind** — Suggest, don't demand. Explain "why" in comments.

**Comment Format:**
```
**Issue:** This causes unnecessary re-renders on every keystroke.

**Suggestion:** Debounce the input handler:
```js
const debouncedSearch = useMemo(
  () => debounce(handleSearch, 300),
  []
);
```

**Why:** Reduces API calls and improves UX.
```

---

## 6. Testing Standards

### 6.1 File Naming

```
src/components/AvatarWidget.jsx
src/components/AvatarWidget.test.jsx  ← Test file
```

### 6.2 Test Structure (AAA Pattern)

```javascript
describe('AvatarWidget', () => {
  describe('syncMainProduct', () => {
    it('should send product context when user manually scrolls', () => {
      // Arrange - Setup test data and mocks
      const mockProduct = {
        id: 'prod_123',
        name: 'Blue Shirt',
        price: 599
      };
      const mockSendContextualUpdate = jest.fn();
      
      // Act - Execute the function
      syncMainProduct(mockProduct);
      
      // Assert - Verify the outcome
      expect(mockSendContextualUpdate).toHaveBeenCalledWith(
        expect.stringContaining('Blue Shirt')
      );
    });
  });
});
```

### 6.3 What to Test

**DO test:**
- Critical business logic
- Edge cases (empty arrays, null values, errors)
- User interactions (clicks, form submissions)
- API integrations (mocked)
- State management
- Conditional rendering

**DON'T test:**
- Third-party libraries
- Trivial getters/setters
- React/framework internals
- Implementation details (test behavior, not internals)

### 6.4 Coverage Goals

- **Unit tests:** 80% coverage minimum
- **Integration tests:** Cover critical user flows
- **E2E tests:** Cover 3-5 most important journeys

### 6.5 Test Documentation

Add comments for complex test setup:

```javascript
it('should debounce carousel sync to prevent rapid-fire agent updates', async () => {
  // SETUP: Mock timers to control debounce behavior
  jest.useFakeTimers();
  
  // ACT: Simulate rapid scrolling (3 products in 100ms)
  syncMainProduct(product1);
  jest.advanceTimersByTime(100);
  syncMainProduct(product2);
  jest.advanceTimersByTime(100);
  syncMainProduct(product3);
  
  // Fast-forward past debounce window (600ms)
  jest.advanceTimersByTime(600);
  
  // ASSERT: Only final product should trigger agent update
  expect(sendContextualUpdate).toHaveBeenCalledTimes(1);
  expect(sendContextualUpdate).toHaveBeenCalledWith(
    expect.stringContaining(product3.name)
  );
});
```

---

## 7. Daily Development Workflow

### 7.1 Morning Routine (15 min)

1. ✅ **Check Linear** — Review assigned tickets, priorities
2. ✅ **Pull latest** — `git pull origin main`
3. ✅ **Read Slack** — Team updates, blockers
4. ✅ **Plan day** — Which ticket(s) to work on today?
5. ✅ **Update ticket** — Move to "In Progress", add start date

### 7.2 During Development

1. ✅ **Branch naming** — `feat/hpf-123-short-description`
2. ✅ **Commit often** — Small, logical commits
3. ✅ **Test as you go** — Don't wait until the end
4. ✅ **Update ticket** — Add commits, screenshots to ticket description
5. ✅ **Ask early** — Blocked for >30 min? Ask for help.

### 7.3 End of Day (10 min)

1. ✅ **Commit work** — Even if incomplete (mark as WIP)
2. ✅ **Update ticket** — Progress comment: what's done, what's next
3. ✅ **Push branch** — Backup your work
4. ✅ **Review tomorrow** — What will you tackle first?

### 7.4 Weekly Routine

**Friday afternoon:**
1. ✅ **Review week** — What shipped? What's blocked?
2. ✅ **Update tickets** — Close "Done", update "In Progress"
3. ✅ **Plan next week** — Which tickets are priority?
4. ✅ **Clean branches** — Delete merged branches locally

---

## 8. AI Tools Parsing Guidelines

When creating content that AI tools will parse (tickets, docs), use these structured formats:

### 8.1 YAML Metadata Block

```markdown
---
ticket: HPF-174
priority: P1
type: feature
complexity: high
estimated_hours: 16
dependencies: [HPF-173, HPF-172]
---

## Problem Statement
...
```

### 8.2 File Reference Format

When referencing files in tickets/docs:

```
📁 Files Modified:
- `src/components/AvatarWidget.jsx` (main component)
- `src/styles/AvatarWidget.css` (styling)
- `src/main.jsx` (shadow DOM setup)
```

### 8.3 Dependency Graph Format

```
Dependencies:
HPF-174 (this)
  ├─ depends on: HPF-173 (agent tools)
  ├─ depends on: HPF-172 (carousel)
  └─ blocks: HPF-175 (deployment)
```

### 8.4 Error/Warning Code Format

```
<!-- AI_ERROR_CODES -->
WIDGET_001: Shadow DOM not supported
WIDGET_002: Agent ID missing
WIDGET_003: Search API unreachable
<!-- /AI_ERROR_CODES -->
```

---

## Quick Reference Card

**Commit:** `<type>(<scope>): <subject>`  
**Ticket Title:** `[Verb] [Outcome] [Context]`  
**Update Cadence:** Every 2 days minimum  
**PR Size:** < 400 lines changed preferred  
**Test Coverage:** 80% unit tests minimum  
**Code Review:** 1 approval required  

**Emergency Contact:**  
For P0 issues: Ping `@gautam.c` in Slack immediately

---

## Document History

| Date | Version | Changes |
|------|---------|---------|
| 2026-03-20 | 2.0 | Complete rewrite with AI-friendly formats, daily workflow, testing standards |
| 2026-03-15 | 1.0 | Initial version (basic commit and ticket guidelines) |

---

**For AI collaboration best practices specifically, see:** [AI_COLLABORATION_GUIDE.md](./AI_COLLABORATION_GUIDE.md)
