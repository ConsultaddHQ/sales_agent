# AI Collaboration Guide for Junior Developers
*How to work effectively with Claude, GitHub Copilot, and other AI coding assistants*

---

## Why This Matters

As a junior developer, AI tools are your **senior pair programmer**. But like any tool, you need to use them correctly. This guide shows you how to structure your work so AI can help you 10x faster.

---

## The Core Principle: AI Needs Structure

**Think of AI like a really smart intern:**
- ✅ Give them clear context → They excel
- ❌ Give vague instructions → They guess wrong

AI tools work by **pattern matching**. The better your patterns, the better their output.

---

## Part 1: Structuring Requests for AI

### **Before Asking AI Anything**

Create a **context checklist**:

```
□ What files are involved? (full paths)
□ What commits are related? (hashes + summaries)
□ Why am I doing this? (ticket reference)
□ What's the current status?
□ What's the priority?
```

### **Template 1: Asking AI to Create a Ticket**

```
Hey Claude, I need a Linear ticket for the work I just completed.

COMMITS:
- 13b487d: feat(carousel): add thumbnail navigation
- 506022b: test(carousel): add thumbnail click tests

FILES:
- www.teampop/frontend/src/components/Carousel.jsx (added thumbnail component)
- www.teampop/frontend/src/styles/Carousel.css (added thumbnail styles)

CONTEXT:
- This implements HPF-172 (thumbnail navigation feature)
- Users can now click thumbnails to jump to products
- Works with both manual clicks and agent-driven navigation

STATUS: Completed and tested
PRIORITY: P1 (blocks demo)

Please create a Linear ticket with:
1. Descriptive title following our format
2. Full description using our template
3. AI context markers for file paths and dependencies
4. Updates section with commit details
```

### **Template 2: Asking AI to Document Code**

```
Hey Claude, I need help documenting this function.

FILE: www.teampop/frontend/src/components/AvatarWidget.jsx
FUNCTION: syncMainProduct (lines 145-167)

PURPOSE: When user manually clicks a product thumbnail, this syncs the context
         with the ElevenLabs agent so it knows what product to talk about.

COMPLEXITY: Medium - handles debouncing and prevents race conditions

DEPENDENCIES:
- @elevenlabs/react useConversation hook
- sendContextualUpdate function

Please add:
1. JSDoc comment with proper @param, @returns, @example
2. Inline comments for the debounce logic
3. AI_SUMMARY marker for future AI tools
```

### **Template 3: Asking AI to Update a Ticket**

```
Hey Claude, update ticket HPF-172 with my progress.

TICKET: HPF-172 (Add thumbnail navigation to carousel)

NEW COMMITS:
- 13b487d: feat(carousel): add thumbnail navigation
- 506022b: test(carousel): add tests

WHAT'S DONE:
- ✅ Thumbnail carousel renders below main product
- ✅ Click handler syncs with agent
- ✅ Auto-scroll to active thumbnail
- ✅ Tests added (3 test cases)

WHAT'S LEFT:
- ⏳ Mobile responsive styles
- ⏳ Accessibility (keyboard navigation)

BLOCKERS: None

STATUS: In Progress (90% done)

Please add a progress comment with today's date.
```

### **Template 4: Asking AI for Commit Message**

```
Hey Claude, I need a commit message for these changes.

FILES CHANGED:
- src/components/Orb.jsx
  - Fixed disconnect function (wasn't clearing WebRTC connection)
  - Added error handling for connection failures

- src/components/AvatarWidget.jsx  
  - Updated Orb component usage
  - Passed new onError prop

TICKET: HPF-159
TYPE: fix
SCOPE: orb

Please write a conventional commit message with:
- Proper type(scope): subject format
- Body explaining the bug and fix
- Reference to ticket
```

---

## Part 2: Common AI Request Patterns

### **Pattern 1: "I just finished a feature, create the ticket"**

```
TRIGGER: You've pushed commits and want to document the work

PREPARATION:
1. Get commit hashes: git log --oneline -n 5
2. List changed files: git show --stat HEAD
3. Note ticket reference from commits

PROMPT: Use Template 1 above
```

### **Pattern 2: "Explain this code I'm reading"**

```
TRIGGER: You're trying to understand existing code

PREPARATION:
1. Copy the function/class
2. Note the file path
3. Check what it imports

PROMPT:
"Hey Claude, explain this code from {filepath}:

[paste code]

Specifically:
- What is its purpose?
- Why is {confusing line} written this way?
- Are there any gotchas I should know about?"
```

### **Pattern 3: "Help me debug this error"**

```
TRIGGER: You're stuck on an error for >15 minutes

PREPARATION:
1. Copy the full error message
2. Note what you tried
3. Include relevant code

PROMPT:
"I'm getting this error:

[paste error]

FILE: {filepath}
CODE:
[paste relevant code]

WHAT I TRIED:
- {attempt 1}
- {attempt 2}

CONTEXT:
- This started after {what changed}
- It only happens when {condition}

What's the issue and how do I fix it?"
```

### **Pattern 4: "Write tests for my code"**

```
TRIGGER: You wrote a feature, need tests

PREPARATION:
1. Know what your function does
2. List edge cases
3. Check if similar tests exist

PROMPT:
"Help me write tests for this function:

FILE: {filepath}
FUNCTION: {function name}

[paste function]

EDGE CASES TO TEST:
- {case 1}
- {case 2}

We use Jest + React Testing Library.
Please follow the AAA pattern (Arrange, Act, Assert)."
```

### **Pattern 5: "Review my code before PR"**

```
TRIGGER: Ready to create PR, want AI review first

PREPARATION:
1. Self-review your diff
2. Run tests locally
3. Check for console.logs

PROMPT:
"Review this code before I create a PR:

TICKET: HPF-XXX
FILES:
[paste git diff or key changes]

Please check for:
- Logic errors
- Performance issues
- Missing edge cases
- Code style problems
- Security issues"
```

---

## Part 3: Improving Your AI Workflow

### **Week 1: Start Here**
- ✅ Use commit message template (Template 4)
- ✅ Ask AI to explain confusing code (Pattern 2)
- ✅ Get AI to review before PR (Pattern 5)

### **Week 2-4: Add These**
- ✅ Use ticket creation template (Template 1)
- ✅ Add AI context markers to code
- ✅ Document functions with AI help (Template 2)

### **Month 2+: Advanced**
- ✅ Create reusable prompt templates
- ✅ Build a personal knowledge base
- ✅ Teach others your AI workflow

---

## Part 4: Red Flags - When AI Gets It Wrong

### **🚨 Warning Sign 1: Too Generic**

**Bad AI Output:**
```markdown
## Problem
The feature needs to be implemented.

## Solution
Add the code to make it work.
```

**Fix:**
```
"Claude, that's too vague. Include:
- Specific file paths
- Actual function names
- Concrete acceptance criteria"
```

### **🚨 Warning Sign 2: No Context**

**Bad AI Output:**
```
feat: update widget
```

**Fix:**
```
"Claude, this commit message needs:
- What specifically changed in the widget?
- Why was this change needed?
- Reference to HPF-XXX ticket"
```

### **🚨 Warning Sign 3: Wrong Assumptions**

**Bad AI Output:**
```javascript
// AI assumes you're using Redux, but you're using React Context
```

**Fix:**
```
"Claude, we don't use Redux. We use React Context.
Please rewrite using:
- useContext hook
- Our existing ProductContext from src/context/ProductContext.jsx"
```

### **🚨 Warning Sign 4: Copy-Paste Without Understanding**

**Bad AI Output:**
```javascript
// Code that works but you don't understand why
```

**Fix:**
```
"Claude, explain this code line by line:
[paste the code]

I need to understand:
- What each part does
- Why it's written this way
- What would break if I changed X"
```

### **🚨 Warning Sign 5: Overly Complex**

**Bad AI Output:**
```javascript
// 50 lines of abstraction for a simple task
```

**Fix:**
```
"Claude, this seems over-engineered. Can you:
- Simplify to the minimum working solution
- Explain why each part is necessary
- Show me a simpler alternative if possible"
```

### **🚨 Warning Sign 6: Missing Error Handling**

**Bad AI Output:**
```javascript
const data = await fetch(url).then(r => r.json());
// No try-catch, no error handling
```

**Fix:**
```
"Claude, add error handling for:
- Network failures
- Invalid JSON
- Timeout scenarios

Use our existing error format from src/utils/errors.js"
```

---

## Part 5: Quick Checklist Before Sending AI Prompts

```
□ Did I include file paths? (not just "the file")
□ Did I include version numbers? (React 19.2, not "React")
□ Did I specify what I tried? (not "nothing works")
□ Did I include error messages? (full stacktrace)
□ Did I reference related tickets? (HPF-XXX)
□ Did I explain WHY? (not just WHAT)
□ Is my request specific? (not "make it better")
```

---

## Part 6: Advanced - Reusable Prompt Library

Save these in a personal notes file:

### **Prompt Library**

```markdown
# My AI Prompts

## Create Ticket from Commits
Hey Claude, create a Linear ticket for:
COMMITS: {paste git log}
FILES: {paste git show --stat}
CONTEXT: {what/why}
STATUS: {status}
PRIORITY: {priority}

## Document Function
Hey Claude, add JSDoc to:
FILE: {path}
FUNCTION: {name}
PURPOSE: {what it does}
Add: @param, @returns, @example, inline comments

## Write Tests
Hey Claude, write tests for:
FILE: {path}
FUNCTION: {name}
EDGE CASES: {list}
Use: Jest + React Testing Library, AAA pattern

## Commit Message
Hey Claude, write commit for:
FILES: {changes}
TICKET: {HPF-XXX}
TYPE: {feat/fix/etc}
SCOPE: {area}

## Code Review
Hey Claude, review:
FILES: {changes}
Check: logic, performance, edge cases, security

## Debug Error
Hey Claude, debug:
ERROR: {message}
FILE: {path}
CODE: {relevant code}
TRIED: {attempts}
```

Save this in your notes app, fill in blanks, paste to AI!

---

## Part 7: VS Code Snippets for AI Context

Add these to your VS Code `snippets.code-snippets`:

```json
{
  "AI Context Block": {
    "prefix": "aicontext",
    "body": [
      "<!-- AI_CONTEXT_START -->",
      "**File Paths:**",
      "- ${1:path}",
      "",
      "**Dependencies:**",
      "- ${2:package@version}",
      "",
      "**Environment Variables:**",
      "- ${3:VAR_NAME}",
      "<!-- AI_CONTEXT_END -->"
    ]
  },
  "AI Function Summary": {
    "prefix": "aisummary",
    "body": [
      "/**",
      " * AI_SUMMARY: ${1:Brief description}",
      " * AI_DEPENDENCIES: ${2:Dependencies}",
      " * AI_COMPLEXITY: ${3|Low,Medium,High|} - ${4:Reason}",
      " */"
    ]
  }
}
```

---

## Part 8: Common Mistakes & Fixes

| Mistake | Better Approach |
|---------|-----------------|
| "Fix the bug" | "Fix carousel scroll bug in Carousel.jsx line 145" |
| "Update docs" | "Update README.md with new AGENT_ID env var" |
| "The file" | "www.teampop/frontend/src/components/Orb.jsx" |
| "Latest version" | "@elevenlabs/react@0.14.1" |
| "It doesn't work" | "Getting 'undefined is not a function' at line 67" |
| "Make it better" | "Reduce carousel scroll animation from 500ms to 300ms" |

---

## Part 9: Example Full Session

### **Scenario: You finished implementing carousel thumbnails**

**Step 1: Gather Context** (2 min)
```bash
git log --oneline -n 3
# Output:
# 13b487d feat(carousel): add thumbnail navigation
# 506022b test(carousel): add thumbnail tests
# abc123d style(carousel): adjust spacing

git show --stat HEAD
# Shows which files changed
```

**Step 2: Prepare Prompt** (3 min)
```
Hey Claude, create a Linear ticket for my carousel work.

COMMITS:
- 13b487d: feat(carousel): add thumbnail navigation
- 506022b: test(carousel): add thumbnail tests

FILES:
- www.teampop/frontend/src/components/ProductCarousel.jsx (added Thumbnail component)
- www.teampop/frontend/src/styles/Carousel.css (added .thumbnail styles)
- www.teampop/frontend/src/components/ProductCarousel.test.jsx (added 3 test cases)

CONTEXT:
- Implements HPF-172 requirement
- Users can click thumbnails to jump to products
- Works alongside agent-driven navigation
- Includes smooth scroll animation

STATUS: Completed
PRIORITY: P1

Please create Linear ticket with full template.
```

**Step 3: Review AI Output** (2 min)
- Check file paths are correct
- Verify ticket reference
- Ensure description is specific
- Confirm all commits listed

**Step 4: Post to Linear** (1 min)
- Copy AI output
- Create ticket in Linear
- Double-check fields

**Total time: 8 minutes** (vs 20-30 min manual)

---

## Part 10: Measuring Success

Track these over time:

**Week 1 Baseline:**
- Time to create ticket: ___ min
- Time to write commit msg: ___ min
- Time to document function: ___ min

**After 1 Month:**
- Time to create ticket: ___ min (goal: <10 min)
- Time to write commit msg: ___ min (goal: <2 min)
- Time to document function: ___ min (goal: <5 min)

**Quality Metrics:**
- Tickets need revision: ___% (goal: <20%)
- PRs need rework: ___% (goal: <30%)
- Time debugging: ___ hrs/week (goal: reduce 30%)

---

## Quick Win: Start Today

1. **Copy Template 4** (commit messages)
2. **Before your next commit**, paste it to Claude
3. **Fill in the blanks**
4. **Use the AI-generated message**

That's it! One template, immediate improvement.

---

## Remember

**AI is a tool, not a crutch:**
- ✅ Use AI to speed up tedious work
- ✅ Use AI to learn patterns
- ✅ Use AI to catch mistakes

- ❌ Don't blindly copy-paste without understanding
- ❌ Don't let AI make decisions for you
- ❌ Don't skip learning fundamentals

**The goal:** AI handles formatting/boilerplate, you focus on problem-solving.

---

*Questions? Try asking Claude: "Based on this AI Collaboration Guide, how should I [your question]?"*

*Last updated: 2026-03-20 by Gautam C*
